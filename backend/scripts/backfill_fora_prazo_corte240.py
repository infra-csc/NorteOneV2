"""
Correção retroativa de selos "fora do prazo" indevidos (Task #240).

Contexto:
  Antes desta correção, qualquer edição/exclusão/aprovação de redução numa
  projeção durante a janela "Corte 1 congelado e Corte 2 ainda não congelado"
  era marcada como fora do prazo — mesmo quando a área já existia ANTES do
  Corte 1 congelar, o que é um ajuste esperado do Corte de Ajuste (Corte 2),
  não uma inclusão fora do prazo. A trava do Corte 1 sozinha só deveria valer
  para inclusões NOVAS feitas depois do congelamento.

  `_detectar_trava_ativa` (backend/app/api/routes/projecao.py) foi corrigida
  para perdoar esse caso, comparando `created_at` da projeção com
  `congelado_corte_1_em` do evento — mas o RESUMO já persistido em
  ProjecaoInscritos.fora_prazo_trava/em/por continua com o valor antigo para
  quem já foi marcado antes da correção, até este backfill rodar.

  Este script NÃO reescreve ProjecaoInscritosHistorico (auditoria permanente
  — preservada como estava). Só recalcula o resumo (fora_prazo_trava/em/por)
  em ProjecaoInscritos, varrendo o próprio histórico da projeção em busca da
  ocorrência mais recente que AINDA seria fora do prazo sob a regra corrigida
  (ex.: um Corte 2 congelado ou uma trava automática D-N anteriores à marca
  indevida de Corte 1) — ou limpando o resumo quando não sobra nenhuma.

Uso (idempotente — pode ser rodado quantas vezes quiser):
    cd backend
    python -m scripts.backfill_fora_prazo_corte240           # dry-run (default)
    python -m scripts.backfill_fora_prazo_corte240 --apply   # aplica a correção
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional, Tuple

# Permite execução tanto como `python -m scripts.backfill_fora_prazo_corte240`
# quanto via `python backend/scripts/backfill_fora_prazo_corte240.py`.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import SessionLocal  # noqa: E402
from app.models.projecao import (  # noqa: E402
    ProjecaoInscritos,
    ProjecaoInscritosHistorico,
    ProjecaoCorteSnapshot,
)


def _recomputar_resumo(db, projecao: ProjecaoInscritos, corte1_em) -> Optional[Tuple[str, object, int]]:
    """Varre o histórico da projeção (mais recente primeiro) e devolve
    (trava, quando, usuario_id) da última ocorrência que AINDA seria fora do
    prazo sob a regra corrigida, ou None se não sobra nenhuma."""
    historicos = db.query(ProjecaoInscritosHistorico).filter(
        ProjecaoInscritosHistorico.projecao_id == projecao.id,
        ProjecaoInscritosHistorico.fora_prazo == True,  # noqa: E712
    ).order_by(
        ProjecaoInscritosHistorico.created_at.desc(),
        ProjecaoInscritosHistorico.id.desc(),
    ).all()
    for h in historicos:
        if h.trava_ativa == 'corte_1' and corte1_em is not None and projecao.created_at is not None and projecao.created_at < corte1_em:
            continue  # essa ocorrência também seria perdoada pela regra corrigida
        return (h.trava_ativa, h.created_at, h.usuario_id)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="Aplica a correção (default é dry-run).")
    parser.add_argument("--json", action="store_true",
                        help="Saída final em JSON (para automação).")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        candidatos = db.query(ProjecaoInscritos).filter(
            ProjecaoInscritos.fora_prazo_trava == 'corte_1'
        ).all()

        corte1_em_por_evento = {
            s.evento_id: s.congelado_corte_1_em
            for s in db.query(ProjecaoCorteSnapshot).all()
        }

        afetados = []
        for p in candidatos:
            corte1_em = corte1_em_por_evento.get(p.evento_id)
            if corte1_em is None or p.created_at is None or not (p.created_at < corte1_em):
                continue  # inclusão nova de fato (ou sem dado suficiente) — marca segue válida
            novo = _recomputar_resumo(db, p, corte1_em)
            afetados.append((p, novo))

        if not args.json:
            print(f"Projeções com fora_prazo_trava='corte_1': {len(candidatos)}")
            print(f"Marcadas indevidamente (área já existia antes do Corte 1 congelar): {len(afetados)}")
            for p, novo in afetados:
                antes = f"corte_1 em {p.fora_prazo_em}"
                depois = f"{novo[0]} em {novo[1]}" if novo else "(limpo — nenhuma ocorrência restante)"
                print(f"  - projecao_id={p.id} evento_id={p.evento_id} area_id={p.area_projecao_id} criada_em={p.created_at}: {antes}  ->  {depois}")

        if afetados and args.apply:
            for p, novo in afetados:
                if novo:
                    p.fora_prazo_trava, p.fora_prazo_em, p.fora_prazo_por = novo
                else:
                    p.fora_prazo_trava = None
                    p.fora_prazo_em = None
                    p.fora_prazo_por = None
            db.commit()
            if not args.json:
                print(f"\n{len(afetados)} projeções corrigidas.")
        elif afetados and not args.json:
            print("\n[dry-run] rode com --apply para gravar a correção.")

        if args.json:
            print(json.dumps({
                "inspected": len(candidatos),
                "affected": len(afetados),
                "applied": args.apply,
                "details": [
                    {
                        "projecao_id": p.id,
                        "evento_id": p.evento_id,
                        "area_projecao_id": p.area_projecao_id,
                        "novo_trava": novo[0] if novo else None,
                    }
                    for p, novo in afetados
                ],
            }, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
