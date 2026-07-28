"""
Limpeza idempotente de EventoDetailSnapshot órfãos após agrupamento.

Contexto:
  Quando um projeto (evento) passa a integrar um Evento Grupo, o backend
  passa a ler/gravar seu snapshot de detalhe sob a chave "grp_<nome>".
  A linha antiga, gravada antes do agrupamento sob a chave numérica
  (dim_projeto.id), nunca era apagada nem migrada — virava uma linha
  "fantasma" congelada para sempre, com dados desatualizados (inclusive
  métricas já corrigidas depois, como o Ticket Atual).

  A guarda preventiva foi instalada em app/api/routes/sku_mappings.py
  (create/update/bulk_create de SkuMapping agora apagam o snapshot
  standalone órfão do projeto assim que ele é associado a um grupo ativo),
  mas as linhas órfãs que já existiam continuariam servindo dados antigos
  para qualquer consulta direta por ID numérico até este script rodar.

Critério (mesmo usado no diagnóstico original):
  evento_detail_snapshot.evento_id é um ID numérico de dim_projeto CUJO
  código está mapeado (sku_mappings.ativo=true, evento_grupo preenchido)
  para um evento_grupos.ativo=true.

Uso (idempotente — pode ser rodado quantas vezes quiser):
    cd backend
    python -m scripts.cleanup_orphan_grouped_snapshots           # dry-run (default)
    python -m scripts.cleanup_orphan_grouped_snapshots --apply   # aplica as deleções
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Tuple

import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import SessionLocal  # noqa: E402
from app.models.evento_detail_snapshot import EventoDetailSnapshot  # noqa: E402
from app.models.dimensoes import DimProjeto, SkuMapping, EventoGrupo  # noqa: E402
from app.api.routes.inscricoes_consolidado import normalize_sku  # noqa: E402


def _find_orphans(db) -> List[Tuple[int, str, int]]:
    """Retorna [(snapshot_id, evento_id, ano), ...] de linhas órfãs.

    Uma linha é órfã quando sua chave (evento_id) é puramente numérica e
    corresponde a um dim_projeto cujo código está mapeado, de forma ativa,
    para um evento_grupo também ativo.
    """
    active_grupo_names = {
        n for (n,) in db.query(EventoGrupo.nome).filter(EventoGrupo.ativo == True).all()  # noqa: E712
        if n
    }
    if not active_grupo_names:
        return []

    sku_to_grupo: dict[str, str] = {}
    sm_rows = (
        db.query(SkuMapping.sku, SkuMapping.evento_grupo)
        .filter(
            SkuMapping.ativo == True,  # noqa: E712
            SkuMapping.evento_grupo.in_(list(active_grupo_names)),
        )
        .all()
    )
    for sku, grupo in sm_rows:
        if sku and grupo:
            sku_to_grupo[normalize_sku(str(sku))] = grupo

    if not sku_to_grupo:
        return []

    proj_rows = db.query(DimProjeto.id, DimProjeto.codigo).filter(
        DimProjeto.codigo.isnot(None)
    ).all()
    grouped_projeto_ids = {
        str(pid) for pid, codigo in proj_rows
        if normalize_sku(str(codigo)) in sku_to_grupo
    }
    if not grouped_projeto_ids:
        return []

    snap_rows = db.query(
        EventoDetailSnapshot.id,
        EventoDetailSnapshot.evento_id,
        EventoDetailSnapshot.ano,
    ).filter(
        EventoDetailSnapshot.evento_id.in_(list(grouped_projeto_ids))
    ).all()
    return [(sid, eid, ano) for sid, eid, ano in snap_rows]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="Aplica as deleções (default é dry-run).")
    parser.add_argument("--json", action="store_true",
                        help="Saída final em JSON (para automação).")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        orphans = _find_orphans(db)

        if not args.json:
            print(f"Snapshots órfãos detectados: {len(orphans)}")
            for sid, eid, ano in orphans[:20]:
                print(f"  - id={sid} evento_id={eid} ano={ano}")
            if len(orphans) > 20:
                print(f"  ... e mais {len(orphans) - 20}")

        deleted_rows = 0
        if orphans and args.apply:
            ids = [sid for sid, _, _ in orphans]
            deleted_rows = (
                db.query(EventoDetailSnapshot)
                .filter(EventoDetailSnapshot.id.in_(ids))
                .delete(synchronize_session=False)
            )
            db.commit()

            remaining = _find_orphans(db)
            if not args.json:
                print(f"\nLinhas deletadas: {deleted_rows}")
                print(f"Snapshots órfãos remanescentes: {len(remaining)} (deveria ser 0)")
        elif orphans and not args.apply:
            if not args.json:
                print("\n[dry-run] rode com --apply para deletar essas linhas.")

        if args.json:
            print(json.dumps({
                "orphans_found": len(orphans),
                "applied": args.apply,
                "rows_deleted": deleted_rows,
            }, ensure_ascii=False, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
