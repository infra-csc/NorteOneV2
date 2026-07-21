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

Multi-worker safe (Task #122): o estado do debounce é PERSISTIDO em
`projecao_alteracao_notif_pending` (UPSERT que preserva o baseline da 1ª
alteração da janela e empurra `flush_after`). Cada worker agenda um timer
local, mas o envio só acontece para quem vencer o claim atômico
(DELETE ... WHERE flush_after <= now RETURNING) — mesmo com múltiplos
workers/instâncias, sai UM e-mail por janela, agrupando saves que caíram em
processos diferentes. Linhas órfãs (worker morreu antes do timer disparar)
são varridas oportunisticamente a cada novo save.

Detalhamento por kit: quando a distribuição por kit está envolvida, o e-mail
lista cada kit alterado (anterior → novo), incluindo ligar/desligar o toggle
(dict vazio ↔ dict preenchido).
"""
import json
import logging
import os
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text

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


# Timers locais por chave (só para não acumular N timers por save neste
# worker; a correção entre workers vem do claim atômico no banco).
_timers: dict[tuple[int, int, int], threading.Timer] = {}
_lock = threading.Lock()


def _dumps_kits(kits: dict[str, int]) -> str:
    return json.dumps(kits or {}, ensure_ascii=False)


def _loads_json(raw: str | None, default):
    if not raw:
        return default
    try:
        v = json.loads(raw)
        return v if isinstance(v, type(default)) else default
    except (ValueError, TypeError):
        return default


def _row_to_entry(row) -> dict:
    """Converte uma linha claimed de projecao_alteracao_notif_pending em entry."""
    return {
        "baseline_qtd": row.baseline_qtd,
        "baseline_kits": _loads_json(row.baseline_kits_json, {}),
        "nova_qtd": row.nova_qtd,
        "novos_kits": _loads_json(row.novos_kits_json, {}),
        "ultima_em": row.ultima_em,
        "fora_prazo_trava": getattr(row, "fora_prazo_trava", None),
        "meta": _loads_json(row.meta_json, {}) or {
            "evento_nome": f"Evento #{row.evento_id}",
            "area_nome": f"Área #{row.area_projecao_id}",
            "usuario_nome": f"Usuário #{row.usuario_id}",
        },
    }


_TRAVA_LABELS = {
    "corte_1": "Corte 1 congelado",
    "corte_2": "Corte 2 congelado",
    "auto_lock": "Trava automática D-N",
}


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

    # Task #126: sinaliza quando alguma alteração da janela foi feita FORA DO
    # PRAZO (corte congelado ou trava D-N vigente no momento do save).
    trava = entry.get("fora_prazo_trava")
    fora_prazo_msg = None
    if trava:
        trava_label = _TRAVA_LABELS.get(trava, trava)
        fora_prazo_msg = (
            f"ATENÇÃO: alteração registrada FORA DO PRAZO — trava vigente: {trava_label}."
        )
    fora_prazo_html = (
        f'<p style="margin:14px 0 0;color:#991b1b;background:#fee2e2;border:1px solid #fecaca;border-radius:8px;padding:10px 14px;font-size:13px;font-weight:600;">&#9888;&#65039; {fora_prazo_msg}</p>'
        if fora_prazo_msg else ""
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
      {fora_prazo_html}
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
    txt_fora_prazo = f"\n{fora_prazo_msg}\n" if fora_prazo_msg else ""
    txt = (
        "Alteração de Projeção de Inscritos\n\n"
        f"Evento: {evento}\n"
        f"Área: {area}\n"
        f"Alterado por: {usuario}\n"
        f"Quantidade: {old_q} → {new_q}\n"
        f"Data/Hora: {quando} (BRT)\n"
        f"{txt_fora_prazo}{txt_toggle}{txt_kits}\n"
        f'Você recebeu este e-mail porque está na lista de avisos de alteração da área "{area}" no Norte One.'
    )
    return subject, html, txt


_CLAIM_SQL = text("""
    DELETE FROM projecao_alteracao_notif_pending
    WHERE evento_id = :evento_id
      AND area_projecao_id = :area_id
      AND usuario_id = :usuario_id
      AND flush_after <= :now
    RETURNING evento_id, area_projecao_id, usuario_id,
              baseline_qtd, baseline_kits_json, nova_qtd, novos_kits_json,
              meta_json, ultima_em, fora_prazo_trava
""")

# Varredura de órfãs: linhas cujo flush_after passou há mais que a folga
# (worker que agendou o timer morreu/reiniciou). O RETURNING garante que só
# um worker pega cada linha.
_SWEEP_SQL = text("""
    DELETE FROM projecao_alteracao_notif_pending
    WHERE flush_after <= :cutoff
    RETURNING evento_id, area_projecao_id, usuario_id,
              baseline_qtd, baseline_kits_json, nova_qtd, novos_kits_json,
              meta_json, ultima_em, fora_prazo_trava
""")

# fora_prazo_trava é STICKY na janela: COALESCE preserva a primeira marcação
# não-nula mesmo que saves seguintes da mesma janela estejam dentro do prazo.
_UPSERT_SQL = text("""
    INSERT INTO projecao_alteracao_notif_pending
        (evento_id, area_projecao_id, usuario_id,
         baseline_qtd, baseline_kits_json, nova_qtd, novos_kits_json,
         meta_json, ultima_em, flush_after, fora_prazo_trava)
    VALUES (:evento_id, :area_id, :usuario_id,
            :baseline_qtd, :baseline_kits_json, :nova_qtd, :novos_kits_json,
            :meta_json, :ultima_em, :flush_after, :fora_prazo_trava)
    ON CONFLICT (evento_id, area_projecao_id, usuario_id) DO UPDATE SET
        nova_qtd = EXCLUDED.nova_qtd,
        novos_kits_json = EXCLUDED.novos_kits_json,
        meta_json = EXCLUDED.meta_json,
        ultima_em = EXCLUDED.ultima_em,
        flush_after = EXCLUDED.flush_after,
        fora_prazo_trava = COALESCE(
            projecao_alteracao_notif_pending.fora_prazo_trava,
            EXCLUDED.fora_prazo_trava
        )
""")


def _now_naive_brt() -> datetime:
    return datetime.now(_BRT).replace(tzinfo=None)


def _flush(key: tuple[int, int, int]) -> None:
    """Timer callback: tenta o claim atômico da chave e envia se vencer."""
    with _lock:
        _timers.pop(key, None)
    try:
        from ..core.database import SessionLocal
        if SessionLocal is None:
            logger.warning("[ProjecaoAlteracaoNotif] SessionLocal indisponível — flush abortado")
            return
        evento_id, area_id, usuario_id = key
        db = SessionLocal()
        try:
            row = db.execute(_CLAIM_SQL, {
                "evento_id": evento_id,
                "area_id": area_id,
                "usuario_id": usuario_id,
                "now": _now_naive_brt(),
            }).first()
            db.commit()
        finally:
            db.close()
        if row is None:
            # Outro worker já enviou, ou um save posterior empurrou flush_after
            # (o timer daquele save cuidará do envio).
            return
        _send_entry(key, _row_to_entry(row))
    except Exception as exc:  # nunca propaga — envio é best-effort
        logger.warning("[ProjecaoAlteracaoNotif] Falha inesperada no envio (%s): %s", key, exc)


def _sweep_orfas() -> None:
    """Envia pendências órfãs (flush_after vencido há mais que a folga)."""
    try:
        from ..core.database import SessionLocal
        if SessionLocal is None:
            return
        cutoff = _now_naive_brt() - timedelta(seconds=max(30.0, _debounce_seconds() * 0.5))
        db = SessionLocal()
        try:
            rows = db.execute(_SWEEP_SQL, {"cutoff": cutoff}).fetchall()
            db.commit()
        finally:
            db.close()
        for row in rows:
            key = (row.evento_id, row.area_projecao_id, row.usuario_id)
            try:
                _send_entry(key, _row_to_entry(row))
            except Exception as exc:
                logger.warning("[ProjecaoAlteracaoNotif] Falha no envio de órfã %s: %s", key, exc)
    except Exception as exc:
        logger.warning("[ProjecaoAlteracaoNotif] Falha na varredura de órfãs: %s", exc)


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
    fora_prazo_trava: str | None = None,
) -> None:
    """
    Registra uma alteração para envio (com debounce). Chamar APÓS o commit do
    update. Nunca lança — falhas só logam.
    """
    try:
        key = (evento_id, area_projecao_id, usuario_id)
        now = _now_naive_brt()
        delay = _debounce_seconds()

        from ..core.database import SessionLocal
        if SessionLocal is None:
            logger.warning("[ProjecaoAlteracaoNotif] SessionLocal indisponível — aviso descartado")
            return
        db = SessionLocal()
        try:
            db.execute(_UPSERT_SQL, {
                "evento_id": evento_id,
                "area_id": area_projecao_id,
                "usuario_id": usuario_id,
                "baseline_qtd": old_qtd,
                "baseline_kits_json": _dumps_kits(old_kits),
                "nova_qtd": new_qtd,
                "novos_kits_json": _dumps_kits(new_kits),
                "meta_json": json.dumps({
                    "evento_nome": evento_nome,
                    "area_nome": area_nome,
                    "usuario_nome": usuario_nome,
                }, ensure_ascii=False),
                "ultima_em": now,
                "flush_after": now + timedelta(seconds=delay),
                "fora_prazo_trava": fora_prazo_trava,
            })
            db.commit()
        finally:
            db.close()

        # Timer local (best-effort): claim atômico no flush decide quem envia.
        # Pequena folga sobre a janela para o flush_after já ter vencido.
        with _lock:
            old_timer = _timers.pop(key, None)
            if old_timer is not None:
                try:
                    old_timer.cancel()
                except Exception:
                    pass
            timer = threading.Timer(delay + 1.0, _flush, args=(key,))
            timer.daemon = True
            _timers[key] = timer
            timer.start()

        # Varre órfãs de workers que morreram antes do próprio timer (thread
        # separada para não segurar o request).
        sweeper = threading.Thread(target=_sweep_orfas, daemon=True)
        sweeper.start()
    except Exception as exc:
        logger.warning("[ProjecaoAlteracaoNotif] Falha ao agendar notificação: %s", exc)
