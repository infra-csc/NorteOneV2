"""
Aviso imediato por e-mail de ALTERAÇÃO de projeção (evento/área).

Regras (Task #120):
- Só EDIÇÕES disparam (criação/primeiro input não passa por aqui).
- Destinatários configurados POR ÁREA em `projecao_alteracao_notif_config`
  (lista própria, separada do vínculo área↔usuário das pendências).
- Debounce por (evento, área, usuário): salvamentos consecutivos em janela
  curta são agrupados — envia só o estado final (baseline anterior → novo).
- O envio roda em background (threading.Timer) e NUNCA quebra o save:
  qualquer falha só loga.

Detalhamento por kit: quando a distribuição por kit está envolvida, o e-mail
lista cada kit alterado (anterior → novo), incluindo ligar/desligar o toggle
(dict vazio ↔ dict preenchido).
"""
import json
import logging
import os
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from ..models.projecao import ProjecaoAlteracaoNotifConfig
from .email_service import send_email, EmailError

logger = logging.getLogger(__name__)

_BRT = ZoneInfo("America/Sao_Paulo")

# Janela de debounce (segundos). Salvamentos consecutivos do mesmo usuário no
# mesmo evento/área dentro da janela reiniciam o timer e agrupam num só e-mail.
def _debounce_seconds() -> float:
    try:
        v = float(os.environ.get("PROJECAO_ALTERACAO_NOTIF_DEBOUNCE_SEGUNDOS", "120"))
        return max(0.0, min(v, 1800.0))
    except (TypeError, ValueError):
        return 120.0


# Estado de debounce: chave (evento_id, area_id, usuario_id) → entry.
# entry = { baseline_qtd, baseline_kits, nova_qtd, novos_kits, meta, timer }
_pending: dict[tuple[int, int, int], dict] = {}
_lock = threading.Lock()


def _parse_emails(emails_json: str | None) -> list[str]:
    if not emails_json:
        return []
    try:
        data = json.loads(emails_json)
    except (ValueError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    seen = set()
    for e in data:
        if isinstance(e, str):
            e2 = e.strip().lower()
            if e2 and "@" in e2 and e2 not in seen:
                seen.add(e2)
                out.append(e2)
    return out


def get_destinatarios_area(db, area_projecao_id: int) -> list[str]:
    """Retorna a lista de e-mails se o aviso estiver ATIVO para a área; senão []."""
    cfg = db.query(ProjecaoAlteracaoNotifConfig).filter(
        ProjecaoAlteracaoNotifConfig.area_projecao_id == area_projecao_id
    ).first()
    if not cfg or not cfg.ativo:
        return []
    return _parse_emails(cfg.emails_json)


def _diff_kits(old_kits: dict[str, int], new_kits: dict[str, int]) -> list[dict]:
    """Lista de {nome, anterior, novo} apenas para kits alterados."""
    diffs: list[dict] = []
    for nome in sorted(set(old_kits) | set(new_kits)):
        a = old_kits.get(nome)
        n = new_kits.get(nome)
        if a != n:
            diffs.append({"nome": nome, "anterior": a, "novo": n})
    return diffs


def _fmt_dt_br(dt: datetime) -> str:
    return dt.strftime("%d/%m/%Y %H:%M")


def _render_email_alteracao(entry: dict) -> tuple[str, str, str]:
    """Retorna (subject, html, txt)."""
    meta = entry["meta"]
    evento = meta["evento_nome"]
    area = meta["area_nome"]
    usuario = meta["usuario_nome"]
    quando = _fmt_dt_br(entry["ultima_em"])
    old_q = entry["baseline_qtd"]
    new_q = entry["nova_qtd"]

    old_kits = entry["baseline_kits"]
    new_kits = entry["novos_kits"]
    kit_diffs = _diff_kits(old_kits, new_kits)
    toggle_msg = None
    if old_kits and not new_kits:
        toggle_msg = "Distribuição por kit foi DESATIVADA nesta alteração."
    elif new_kits and not old_kits:
        toggle_msg = "Distribuição por kit foi ATIVADA nesta alteração."

    subject = f"[Norte One] Projeção alterada — {evento} / {area}"

    linhas_kit_html = ""
    linhas_kit_txt = []
    if kit_diffs:
        rows = []
        for d in kit_diffs:
            a = "—" if d["anterior"] is None else str(d["anterior"])
            n = "—" if d["novo"] is None else str(d["novo"])
            rows.append(
                f"""<tr>
                  <td style="padding:8px 12px;border-bottom:1px solid #eee;">{d['nome']}</td>
                  <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:center;color:#666;">{a}</td>
                  <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:center;font-weight:600;color:#b91c1c;">{n}</td>
                </tr>"""
            )
            linhas_kit_txt.append(f"  - {d['nome']}: {a} → {n}")
        linhas_kit_html = f"""
      <h3 style="margin:20px 0 8px;font-size:14px;color:#333;">Alterações por kit</h3>
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <thead>
          <tr style="text-align:left;color:#666;font-size:12px;text-transform:uppercase;">
            <th style="padding:8px 12px;">Kit</th>
            <th style="padding:8px 12px;text-align:center;">Anterior</th>
            <th style="padding:8px 12px;text-align:center;">Novo</th>
          </tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>"""

    toggle_html = (
        f'<p style="margin:14px 0 0;color:#92400e;background:#fef3c7;border:1px solid #fde68a;border-radius:8px;padding:10px 14px;font-size:13px;">{toggle_msg}</p>'
        if toggle_msg else ""
    )

    html = f"""<!DOCTYPE html>
<html lang="pt-br"><head><meta charset="utf-8"></head>
<body style="margin:0;background:#f5f6f8;font-family:Arial,Helvetica,sans-serif;color:#222;">
  <div style="max-width:640px;margin:0 auto;padding:24px;">
    <div style="background:#b91c1c;color:#fff;padding:18px 22px;border-radius:10px 10px 0 0;">
      <h1 style="margin:0;font-size:18px;">Alteração de Projeção — Projeção de Inscritos</h1>
    </div>
    <div style="background:#fff;padding:22px;border-radius:0 0 10px 10px;border:1px solid #eee;border-top:none;">
      <p style="margin:0 0 16px;color:#444;">
        Uma projeção de inscritos foi <strong>alterada</strong>. Detalhes:
      </p>
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <tbody>
          <tr><td style="padding:8px 12px;color:#666;width:180px;">Evento</td><td style="padding:8px 12px;font-weight:600;">{evento}</td></tr>
          <tr><td style="padding:8px 12px;color:#666;">Área</td><td style="padding:8px 12px;font-weight:600;">{area}</td></tr>
          <tr><td style="padding:8px 12px;color:#666;">Alterado por</td><td style="padding:8px 12px;">{usuario}</td></tr>
          <tr><td style="padding:8px 12px;color:#666;">Quantidade</td>
              <td style="padding:8px 12px;"><span style="color:#666;">{old_q}</span>
              &nbsp;→&nbsp; <strong style="color:#b91c1c;font-size:16px;">{new_q}</strong></td></tr>
          <tr><td style="padding:8px 12px;color:#666;">Data/Hora</td><td style="padding:8px 12px;">{quando} (BRT)</td></tr>
        </tbody>
      </table>
      {toggle_html}
      {linhas_kit_html}
      <p style="margin:22px 0 0;color:#999;font-size:12px;">
        Você recebeu este e-mail porque está na lista de avisos de alteração da área "{area}" no Norte One.
      </p>
    </div>
  </div>
</body></html>"""

    txt_kits = ("\nAlterações por kit:\n" + "\n".join(linhas_kit_txt) + "\n") if linhas_kit_txt else ""
    txt_toggle = f"\n{toggle_msg}\n" if toggle_msg else ""
    txt = (
        "Alteração de Projeção de Inscritos\n\n"
        f"Evento: {evento}\n"
        f"Área: {area}\n"
        f"Alterado por: {usuario}\n"
        f"Quantidade: {old_q} → {new_q}\n"
        f"Data/Hora: {quando} (BRT)\n"
        f"{txt_toggle}{txt_kits}\n"
        f'Você recebeu este e-mail porque está na lista de avisos de alteração da área "{area}" no Norte One.'
    )
    return subject, html, txt


def _flush(key: tuple[int, int, int]) -> None:
    """Timer callback: envia o e-mail agrupado da chave (roda em thread própria)."""
    with _lock:
        entry = _pending.pop(key, None)
    if entry is None:
        return
    try:
        _send_entry(key, entry)
    except Exception as exc:  # nunca propaga — envio é best-effort
        logger.warning("[ProjecaoAlteracaoNotif] Falha inesperada no envio (%s): %s", key, exc)


def _send_entry(key: tuple[int, int, int], entry: dict) -> None:
    # Sem mudança líquida (usuário voltou ao valor original e kits idem) → não envia.
    if entry["baseline_qtd"] == entry["nova_qtd"] and not _diff_kits(entry["baseline_kits"], entry["novos_kits"]):
        logger.info("[ProjecaoAlteracaoNotif] Mudança líquida nula para %s — e-mail suprimido", key)
        return

    _, area_id, _ = key
    from ..core.database import SessionLocal
    if SessionLocal is None:
        logger.warning("[ProjecaoAlteracaoNotif] SessionLocal indisponível — envio abortado")
        return
    db = SessionLocal()
    try:
        emails = get_destinatarios_area(db, area_id)
    finally:
        db.close()

    if not emails:
        logger.info("[ProjecaoAlteracaoNotif] Área %s sem aviso ativo/destinatários — nada a enviar", area_id)
        return

    subject, html, txt = _render_email_alteracao(entry)
    enviados = 0
    for email in emails:
        try:
            send_email(email, subject, html=html, text=txt)
            enviados += 1
        except EmailError as exc:
            logger.warning("[ProjecaoAlteracaoNotif] Falha e-mail para %s: %s", email, exc)
        except Exception as exc:
            logger.warning("[ProjecaoAlteracaoNotif] Erro inesperado enviando para %s: %s", email, exc)
    logger.info(
        "[ProjecaoAlteracaoNotif] Evento %s / área %s: %d/%d e-mail(s) enviados (qtd %s→%s)",
        entry["meta"]["evento_nome"], entry["meta"]["area_nome"],
        enviados, len(emails), entry["baseline_qtd"], entry["nova_qtd"],
    )


def notificar_alteracao_projecao(
    *,
    evento_id: int,
    area_projecao_id: int,
    usuario_id: int,
    evento_nome: str,
    area_nome: str,
    usuario_nome: str,
    old_qtd: int,
    new_qtd: int,
    old_kits: dict[str, int],
    new_kits: dict[str, int],
) -> None:
    """
    Registra uma alteração para envio (com debounce). Chamar APÓS o commit do
    update. Nunca lança — falhas só logam.
    """
    try:
        key = (evento_id, area_projecao_id, usuario_id)
        now = datetime.now(_BRT).replace(tzinfo=None)
        delay = _debounce_seconds()
        with _lock:
            existing = _pending.get(key)
            if existing is not None:
                # Agrupa: mantém baseline (estado antes da 1ª alteração da janela),
                # atualiza estado final e reinicia o timer.
                try:
                    existing["timer"].cancel()
                except Exception:
                    pass
                existing["nova_qtd"] = new_qtd
                existing["novos_kits"] = dict(new_kits)
                existing["ultima_em"] = now
                entry = existing
            else:
                entry = {
                    "baseline_qtd": old_qtd,
                    "baseline_kits": dict(old_kits),
                    "nova_qtd": new_qtd,
                    "novos_kits": dict(new_kits),
                    "ultima_em": now,
                    "meta": {
                        "evento_nome": evento_nome,
                        "area_nome": area_nome,
                        "usuario_nome": usuario_nome,
                    },
                }
                _pending[key] = entry
            timer = threading.Timer(delay, _flush, args=(key,))
            timer.daemon = True
            entry["timer"] = timer
            timer.start()
    except Exception as exc:
        logger.warning("[ProjecaoAlteracaoNotif] Falha ao agendar notificação: %s", exc)
