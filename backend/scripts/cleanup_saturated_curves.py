"""
Limpeza idempotente de curvas históricas saturadas.

Contexto:
  Bug histórico no job de consolidação produzia curvas com
  percentual_acumulado=1.0 em todos (ou quase todos) os d_minus quando:
    • a edição anterior teve baixíssimo volume (1-5 inscrições);
    • havia um bloco de dias sem venda antes de D=0
      (o gap-fill em _fetch_previous_year_cumulative_pattern forçava
      pct=1.0 nesse intervalo);
    • a curva foi derivada regionalmente de irmãos já saturados (cascata).

  Consequência: Meta Dia=0 em todos os pontos do "Controle Diário" e
  "Composição da Curva" para os eventos afetados.

  As guards de saturação foram instaladas no código
  (snapshot_service.is_curve_saturated, _fetch_previous_year_cumulative_pattern,
  consolidar_curvas_historicas_batch e _resolve_hist_pattern), mas curvas
  saturadas que já estavam persistidas continuariam sendo lidas até este
  script rodar.

Uso (idempotente — pode ser rodado quantas vezes quiser):
    cd backend
    python -m scripts.cleanup_saturated_curves           # dry-run (default)
    python -m scripts.cleanup_saturated_curves --apply   # aplica as deleções

O script:
  1) Lê todas as CurvaHistoricaSnapshot dos anos relevantes.
  2) Aplica o helper canônico is_curve_saturated em cada grupo/ano.
  3) Em dry-run, apenas lista o que seria deletado.
  4) Em --apply, deleta as linhas afetadas, faz commit e re-valida.
  5) Registra um SyncEventLog (job_name=cleanup_saturated_curves) com
     resumo do que foi removido, para auditoria.

Saída: código 0 sempre que rodar sem exceção. Em --apply, devolve
contagem total de linhas removidas via stdout no formato JSON.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple

# Permite execução tanto como `python -m scripts.cleanup_saturated_curves`
# quanto via `python backend/scripts/cleanup_saturated_curves.py`.
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import SessionLocal  # noqa: E402
from app.models.vendas_snapshot import CurvaHistoricaSnapshot  # noqa: E402
from app.services.snapshot_service import is_curve_saturated  # noqa: E402

DEFAULT_YEARS = [2023, 2024, 2025, 2026]


def _collect_curves(db, years: List[int]) -> Dict[Tuple[str, int], Dict[int, float]]:
    rows = db.query(
        CurvaHistoricaSnapshot.evento_grupo,
        CurvaHistoricaSnapshot.ano_referencia,
        CurvaHistoricaSnapshot.d_minus,
        CurvaHistoricaSnapshot.percentual_acumulado,
    ).filter(CurvaHistoricaSnapshot.ano_referencia.in_(years)).all()
    curves: Dict[Tuple[str, int], Dict[int, float]] = defaultdict(dict)
    for grupo, ano, dm, pct in rows:
        curves[(grupo, ano)][dm] = float(pct)
    return curves


def _find_saturated(curves) -> List[Tuple[str, int, int]]:
    """Returns list of (grupo, ano, num_pontos) for saturated curves."""
    bad = []
    for (grupo, ano), pat in curves.items():
        if is_curve_saturated(pat):
            bad.append((grupo, ano, len(pat)))
    return sorted(bad, key=lambda x: (x[1], x[0]))


def _log_audit(db, removed: List[Tuple[str, int, int]], dry_run: bool) -> None:
    """Best-effort: registra em SyncEventLog se o model existir.
    Não falha o script se a tabela não existir nesse ambiente."""
    try:
        from app.models.sync_event_log import SyncEventLog  # type: ignore
        entry = SyncEventLog(
            ciclo_id=f"cleanup-{uuid.uuid4().hex[:12]}",
            job_name="cleanup_saturated_curves",
            status="DRY_RUN" if dry_run else "OK",
            nivel="INFO",
            detalhes=json.dumps({
                "removed_count": len(removed),
                "removed": [
                    {"grupo": g, "ano": a, "pontos": n} for g, a, n in removed
                ],
                "dry_run": dry_run,
            }, ensure_ascii=False),
        )
        db.add(entry)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"  [aviso] não foi possível registrar SyncEventLog: {e}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="Aplica as deleções (default é dry-run).")
    parser.add_argument("--years", type=int, nargs="+", default=DEFAULT_YEARS,
                        help=f"Anos a inspecionar (default {DEFAULT_YEARS}).")
    parser.add_argument("--json", action="store_true",
                        help="Saída final em JSON (para automação).")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        curves = _collect_curves(db, args.years)
        bad = _find_saturated(curves)

        if not args.json:
            print(f"Curvas inspecionadas: {len(curves)} (anos={args.years})")
            print(f"Curvas saturadas detectadas: {len(bad)}")
            for grupo, ano, n in bad:
                print(f"  - [{ano}] {grupo}  ({n} pontos)")

        deleted_rows = 0
        if bad and args.apply:
            for grupo, ano, _ in bad:
                d = db.query(CurvaHistoricaSnapshot).filter(
                    CurvaHistoricaSnapshot.evento_grupo == grupo,
                    CurvaHistoricaSnapshot.ano_referencia == ano,
                ).delete()
                deleted_rows += d
            db.commit()
            _log_audit(db, bad, dry_run=False)

            # Re-validação: roda o detector novamente para garantir 0 sobrando.
            remaining = _find_saturated(_collect_curves(db, args.years))
            if not args.json:
                print(f"\nLinhas deletadas: {deleted_rows}")
                print(f"Curvas saturadas remanescentes: {len(remaining)} "
                      f"(deveria ser 0)")
        elif bad and not args.apply:
            _log_audit(db, bad, dry_run=True)
            if not args.json:
                print("\n[dry-run] rode com --apply para deletar essas curvas.")

        if args.json:
            print(json.dumps({
                "inspected": len(curves),
                "saturated_found": len(bad),
                "applied": args.apply,
                "rows_deleted": deleted_rows,
                "details": [
                    {"grupo": g, "ano": a, "pontos": n} for g, a, n in bad
                ],
            }, ensure_ascii=False, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
