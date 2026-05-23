"""
Auditoria automatizada da tela "Detalhe de Eventos".

Usa FastAPI TestClient + JWT real para chamar todos os endpoints
consumidos pela tela em todos os eventos ativos, exatamente como o
frontend faria. Procura anomalias detectáveis programaticamente.

Endpoints cobertos:
  Dashboard:    GET /marketing/eventos/{id}             (event + dailySales)
                GET /marketing/eventos/{id}/medias-vendas
                GET /marketing/eventos/{id}/insights
                GET /marketing/eventos/{id}/version
  Simulador:    GET /marketing/eventos/{id}/simulacao
                GET /marketing/eventos/{id}/projetado-faixas
  Controle:     GET /marketing/eventos/{id}/curva-snapshot
                GET /api/marketing/curva-comparativa/{id}

Anomalias:
  CRIT  endpoint estoura 5xx
  CRIT  currentSales < 0
  CRIT  curva ainda saturada após o resolve (não deveria mais ocorrer)
  CRIT  Meta Dia zerada em TODOS os pontos com sales_goal>0
  CRIT  medias-vendas.media_geral < 0
  WARN  sales_goal ausente/<=0 em evento futuro
  WARN  dailySales vazio em evento futuro
  WARN  soma(dailySales) divergindo >5% e >5 inscritos de currentSales
  WARN  curva-snapshot vazia em evento futuro com meta
  WARN  endpoint retorna 4xx inesperado

Uso:
  cd backend
  python -m scripts.audit_event_detail                     # console resumido
  python -m scripts.audit_event_detail --limit 5
  python -m scripts.audit_event_detail --evento-id 123
  python -m scripts.audit_event_detail --json > audit.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Silencia warnings ruidosos do uvicorn/sqlalchemy durante a auditoria
os.environ.setdefault("PYTHONWARNINGS", "ignore")


def _build_client_and_token(base_url: str):
    """
    Se base_url for 'inprocess', usa TestClient (cria nova app, cold cache).
    Caso contrário, usa httpx contra um backend rodando (default port 8000),
    o que pega o estado real de cache/warmup.
    """
    import httpx
    from app.core.database import SessionLocal
    from app.core.security import create_access_token, decode_token
    from app.models.user import Usuario
    from app.models.user_session import UserSession

    db = SessionLocal()
    try:
        # Exige usuário admin estrito — falhar cedo evita falso "0 issues"
        # mascarado por 403 em endpoints com permissões específicas
        # (ex.: /curva-comparativa requer marketing_comparativo).
        user = (
            db.query(Usuario)
            .filter(Usuario.ativo == True)  # noqa: E712
            .filter(Usuario.email.like("admin@%"))
            .first()
            or db.query(Usuario)
            .filter(Usuario.ativo == True)  # noqa: E712
            .filter(Usuario.perfil_acesso_id == 1)
            .first()
        )
        if not user:
            raise RuntimeError(
                "Nenhum usuário admin (email admin@* ou perfil_acesso_id=1) "
                "encontrado. Audit precisa de admin para acessar todos os "
                "endpoints de marketing — falhe cedo em vez de mascarar 403."
            )
        token = create_access_token({"sub": str(user.id)},
                                    expires_delta=timedelta(hours=2))
        jti = decode_token(token)["jti"]
        sess = UserSession(
            user_id=user.id,
            jti=jti,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=2),
        )
        db.add(sess)
        db.commit()
        if base_url == "inprocess":
            from fastapi.testclient import TestClient
            import app.core.rate_limit as _rl
            _rl.LIMIT_NORMAL = 10**6
            _rl.LIMIT_FORCE_REFRESH = 10**6
            from main import app
            client = TestClient(app)
        else:
            client = httpx.Client(base_url=base_url, timeout=90.0)
        client.headers.update({"Authorization": f"Bearer {token}"})
        # devolve callback de cleanup (deleta a sessão ao final)
        def _cleanup():
            try:
                d = SessionLocal()
                d.query(UserSession).filter(UserSession.jti == jti).delete()
                d.commit(); d.close()
            except Exception:
                pass
        return client, user, _cleanup
    finally:
        db.close()


SEV_CRIT, SEV_WARN, SEV_INFO = "CRIT", "WARN", "INFO"


def _is_saturated(snap_data: List[dict]) -> bool:
    """Reusa o helper canônico do snapshot_service para evitar deriva.
    Espera lista com {d_minus, percentual_acumulado(0..100)} e converte para
    o dict {d_minus: pct(0..1)} esperado pelo helper."""
    if not snap_data:
        return False
    from app.services.snapshot_service import is_curve_saturated
    pat = {int(p["d_minus"]): float(p["percentual_acumulado"]) / 100.0
           for p in snap_data}
    return is_curve_saturated(pat)


def _classify_http(status_code: int, expected_ok: bool = True) -> Optional[str]:
    """Retorna severidade para um status code. None = sem issue."""
    if status_code >= 500:
        return SEV_CRIT
    if status_code >= 400:
        return SEV_WARN
    return None


def _safe_get(client, path: str, params: Optional[dict] = None):
    import time
    for attempt in range(3):
        try:
            r = client.get(path, params=params or {}, timeout=60)
        except Exception as e:
            return None, f"{type(e).__name__}: {e}"
        if r.status_code == 429 and attempt < 2:
            # janela do limiter = 60s; espera 35s e re-tenta
            time.sleep(35)
            continue
        return r, None
    return r, None


def _audit_event(client, event_id: str, hoje: date) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []

    def add(sev: str, ep: str, msg: str, det: Optional[dict] = None):
        issues.append({"severity": sev, "endpoint": ep, "msg": msg,
                       "details": det or {}})

    # 1) Detalhe principal
    r, err = _safe_get(client, f"/api/marketing/eventos/{event_id}")
    if err:
        add(SEV_CRIT, "GET /eventos/{id}", "exceção", {"err": err})
        return issues
    if r.status_code >= 500:
        add(SEV_CRIT, "GET /eventos/{id}", f"HTTP {r.status_code}",
            {"body": r.text[:200]})
        return issues
    if r.status_code >= 400:
        add(SEV_WARN, "GET /eventos/{id}", f"HTTP {r.status_code}",
            {"body": r.text[:200]})
        return issues
    try:
        detail = r.json()
    except Exception as e:
        add(SEV_CRIT, "GET /eventos/{id}", "resposta não-JSON",
            {"err": str(e), "body": r.text[:200],
             "ct": r.headers.get("content-type", ""),
             "len": len(r.content)})
        return issues
    # Status especiais devolvidos pelo endpoint quando snapshot não existe
    _status = detail.get("status")
    if _status == "no_snapshot":
        add(SEV_WARN, "GET /eventos/{id}", "snapshot não consolidado",
            {"msg": detail.get("message", "")[:140]})
        return issues
    if _status == "partial":
        add(SEV_INFO, "GET /eventos/{id}", "snapshot parcial",
            {"msg": detail.get("message", "")[:140]})
    evento = detail.get("evento") or {}
    daily = detail.get("dailySales") or []
    sales_goal = (evento.get("salesGoal") or evento.get("sales_goal") or 0) or 0
    current_sales = (evento.get("currentSales")
                     or evento.get("current_sales") or 0) or 0
    de_str = (evento.get("eventDate") or evento.get("data_evento"))
    data_evento: Optional[date] = None
    if isinstance(de_str, str):
        try:
            data_evento = date.fromisoformat(de_str[:10])
        except Exception:
            pass
    is_future = bool(data_evento and data_evento >= hoje)

    if is_future and sales_goal <= 0:
        add(SEV_WARN, "GET /eventos/{id}",
            "sales_goal ausente/<=0 em evento futuro",
            {"sales_goal": sales_goal, "data_evento": str(data_evento)})
    if current_sales < 0:
        add(SEV_CRIT, "GET /eventos/{id}", "currentSales negativo",
            {"currentSales": current_sales})
    if is_future and not daily:
        add(SEV_WARN, "GET /eventos/{id}", "dailySales vazio em evento futuro",
            {"data_evento": str(data_evento)})
    if daily and current_sales > 0:
        sum_d = sum((d.get("sales") or 0) for d in daily)
        if sum_d > 0:
            diff = abs(sum_d - current_sales)
            # Janela móvel: dailySales devolve N dias mais recentes; vendas
            # anteriores à janela aparecem só em currentSales. Só vira WARN
            # se a janela for menor e a divergência for incompatível.
            window_days = len(daily)
            if diff > 5 and diff / max(current_sales, 1) > 0.05:
                sev = SEV_INFO if window_days <= 100 else SEV_WARN
                add(sev, "GET /eventos/{id}",
                    "dailySales (janela móvel) < currentSales (acumulado)",
                    {"sum_daily": sum_d, "current": current_sales,
                     "diff": diff, "window_days": window_days})

    # 2) Curva snapshot
    r, err = _safe_get(client, f"/api/marketing/eventos/{event_id}/curva-snapshot")
    if err:
        add(SEV_CRIT, "GET /curva-snapshot", "exceção", {"err": err})
    elif r.status_code >= 500:
        add(SEV_CRIT, "GET /curva-snapshot", f"HTTP {r.status_code}",
            {"body": r.text[:200]})
    elif r.status_code < 400:
        snap = r.json()
        snap_data = snap.get("data") or []
        if is_future and sales_goal > 0 and not snap_data:
            add(SEV_WARN, "GET /curva-snapshot",
                "curva vazia em evento futuro com meta",
                {"msg": snap.get("message")})
        if snap_data:
            if _is_saturated(snap_data):
                add(SEV_CRIT, "GET /curva-snapshot",
                    "curva exibida ainda saturada (deveria ser linear)",
                    {"tipo": snap.get("tipo_curva"),
                     "fonte": snap.get("fonte_curva"),
                     "linear": snap.get("fabricated_linear")})
            non_zero = sum(1 for p in snap_data if (p.get("meta_dia") or 0) > 0)
            if non_zero == 0 and sales_goal > 0:
                add(SEV_CRIT, "GET /curva-snapshot",
                    "Meta Dia zerada em TODOS os pontos",
                    {"sales_goal": sales_goal, "pts": len(snap_data),
                     "tipo": snap.get("tipo_curva")})

    def _check_aux(label: str, path: str, on_ok=None):
        r, err = _safe_get(client, path)
        if err:
            add(SEV_CRIT, label, "exceção", {"err": err})
            return None
        sev = _classify_http(r.status_code)
        if sev:
            add(sev, label, f"HTTP {r.status_code}",
                {"body": r.text[:160]})
            return None
        if on_ok:
            try:
                on_ok(r.json())
            except Exception as e:
                add(SEV_WARN, label, "JSON inválido no payload OK",
                    {"err": str(e)[:120]})
        return r

    # 3) Médias
    def _check_medias(j):
        mg = (j or {}).get("media_geral")
        if mg is not None and mg < 0:
            add(SEV_CRIT, "GET /medias-vendas", "media_geral negativa",
                {"media_geral": mg})
    _check_aux("GET /medias-vendas",
               f"/api/marketing/eventos/{event_id}/medias-vendas",
               on_ok=_check_medias)

    # 4) Simulação
    _check_aux("GET /simulacao",
               f"/api/marketing/eventos/{event_id}/simulacao")

    # 5) Insights (não-bloqueante: registra apenas se erro)
    _check_aux("GET /insights",
               f"/api/marketing/eventos/{event_id}/insights")

    # 6) Version
    _check_aux("GET /version",
               f"/api/marketing/eventos/{event_id}/version")

    # 7) Curva comparativa
    _check_aux("GET /curva-comparativa",
               f"/api/marketing/curva-comparativa/{event_id}")

    # 8) Projetado faixas (aba Simulador)
    _check_aux("GET /projetado-faixas",
               f"/api/marketing/eventos/{event_id}/projetado-faixas")

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--evento-id", type=str, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--show-info", action="store_true")
    parser.add_argument("--base-url", default="http://localhost:8000",
                        help="URL do backend (use 'inprocess' para TestClient).")
    parser.add_argument("--pace-ms", type=int, default=600,
                        help="Sleep entre eventos (ms) para evitar rate-limit. "
                             "Default 600 → ~13 eventos/min, sob 120/min.")
    args = parser.parse_args()

    client, _user, _cleanup = _build_client_and_token(args.base_url)

    from app.core.database import SessionLocal
    from app.models.cadastro_evento import CadastroEvento

    hoje = date.today()
    if args.evento_id:
        event_ids = [args.evento_id]
    else:
        # Lista os IDs exatamente como o frontend faz — assim o id casa com a
        # chave usada no evento_detail_snapshot (DimProjeto.id ou grp_*).
        r, err = _safe_get(client, "/api/marketing/eventos",
                           params={"status": "active"})
        if err or r.status_code >= 400:
            print(f"Falha ao listar eventos: {err or r.status_code}",
                  file=sys.stderr)
            return 3
        listing = r.json()
        eventos_raw = (listing.get("events") or listing.get("eventos") or
                       listing.get("data") or [])
        event_ids = [str(e.get("id") or e.get("evento_id")) for e in eventos_raw]
        event_ids = [eid for eid in event_ids if eid and eid != "None"]
        if args.limit:
            event_ids = event_ids[:args.limit]

    all_results: List[Dict[str, Any]] = []
    sev_counts: Dict[str, int] = defaultdict(int)
    started = datetime.utcnow()
    import time as _time
    for idx, ev_id in enumerate(event_ids, 1):
        if idx > 1 and args.pace_ms > 0:
            _time.sleep(args.pace_ms / 1000.0)
        issues = _audit_event(client, ev_id, hoje)
        if not args.show_info:
            issues = [i for i in issues if i["severity"] != SEV_INFO]
        for i in issues:
            sev_counts[i["severity"]] += 1
        all_results.append({"event_id": ev_id, "issues": issues})
        if not args.json:
            mark = "OK" if not issues else (
                "CRIT" if any(i["severity"] == SEV_CRIT for i in issues) else "WARN"
            )
            print(f"  [{idx:3d}/{len(event_ids)}] {ev_id:>6}  {mark}  "
                  f"({len(issues)} issue/s)")

    elapsed = (datetime.utcnow() - started).total_seconds()

    if args.json:
        print(json.dumps({
            "total_events": len(event_ids),
            "summary": dict(sev_counts),
            "elapsed_sec": round(elapsed, 1),
            "results": all_results,
        }, ensure_ascii=False, indent=2, default=str))
    else:
        print()
        print(f"Eventos auditados: {len(event_ids)}  ({elapsed:.1f}s)")
        print(f"Resumo: CRIT={sev_counts[SEV_CRIT]} "
              f"WARN={sev_counts[SEV_WARN]} INFO={sev_counts[SEV_INFO]}")
        print()
        printed = 0
        for r in all_results:
            if not r["issues"]:
                continue
            printed += 1
            print(f"=== evento {r['event_id']} ({len(r['issues'])} issue/s) ===")
            for i in r["issues"]:
                det = ""
                if i.get("details"):
                    det = "  " + json.dumps(i["details"],
                                            ensure_ascii=False, default=str)[:240]
                print(f"  [{i['severity']}] {i['endpoint']}: {i['msg']}{det}")
            print()
        if printed == 0:
            print("Nenhuma anomalia encontrada.")
    _cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
