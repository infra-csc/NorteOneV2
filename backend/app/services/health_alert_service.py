import logging
import threading
import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Optional

logger = logging.getLogger(__name__)

SEVERITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}

_dispatch_lock = threading.Lock()
_last_alert_times: dict = {}
MIN_ALERT_INTERVAL_SECONDS = 300


def _get_config():
    try:
        from app.core.database import SessionLocal
        from app.models.system_health import SystemAlertConfig
        db = SessionLocal()
        try:
            cfg = db.query(SystemAlertConfig).filter(SystemAlertConfig.id == 1).first()
            return cfg
        finally:
            db.close()
    except Exception as e:
        logger.error(f"[HealthAlert] Failed to load alert config: {e}")
        return None


def log_event(
    event_type: str,
    severity: str,
    message: str,
    detail: Optional[str] = None,
) -> Optional[int]:
    try:
        from app.core.database import SessionLocal
        from app.models.system_health import SystemHealthEvent
        db = SessionLocal()
        try:
            event = SystemHealthEvent(
                event_type=event_type,
                severity=severity,
                message=message,
                detail=detail,
            )
            db.add(event)
            db.commit()
            db.refresh(event)
            event_id = event.id
            logger.info(f"[HealthAlert] Event logged: [{severity}] {event_type} — {message}")
            return event_id
        except Exception as e:
            db.rollback()
            logger.error(f"[HealthAlert] Failed to log event: {e}")
            return None
        finally:
            db.close()
    except Exception as e:
        logger.error(f"[HealthAlert] DB session error: {e}")
        return None


def log_and_alert(
    event_type: str,
    severity: str,
    message: str,
    detail: Optional[str] = None,
):
    event_id = log_event(event_type, severity, message, detail)
    threading.Thread(
        target=_dispatch_alert,
        args=(event_type, severity, message, detail),
        daemon=True,
    ).start()
    return event_id


def _should_throttle(event_type: str) -> bool:
    with _dispatch_lock:
        last = _last_alert_times.get(event_type)
        now = datetime.now(timezone.utc).timestamp()
        if last and (now - last) < MIN_ALERT_INTERVAL_SECONDS:
            return True
        _last_alert_times[event_type] = now
        return False


def _dispatch_alert_force(event_type: str, severity: str, message: str, detail: Optional[str]):
    """Like _dispatch_alert but bypasses severity threshold — used by test endpoint."""
    try:
        with _dispatch_lock:
            _last_alert_times[event_type] = 0
        cfg = _get_config()
        if cfg is None:
            return
        now_brt = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M:%S BRT")
        subject = f"[TESTE] Verificação dos canais de alerta"
        body_text = f"""Teste de Alerta
===============
Este é um alerta de teste enviado manualmente.
Horário: {now_brt}
Disparado por: {detail or ''}

Se você recebeu este e-mail, a configuração SMTP está funcionando corretamente.
"""
        body_html = f"""
<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;background:#f5f5f5">
<div style="background:white;border-radius:8px;padding:24px;border-top:4px solid #3b82f6">
  <h2 style="margin:0 0 8px;color:#111">✅ Teste de Alerta</h2>
  <p style="color:#666;margin:0 0 20px;font-size:14px">{now_brt}</p>
  <p>Este é um alerta de teste enviado manualmente para verificar a configuração dos canais de notificação.</p>
  <p style="color:#555;font-size:13px">{detail or ''}</p>
  <p style="color:#6b7280;font-size:12px;margin-top:20px">Se você recebeu esta mensagem, a configuração está funcionando corretamente.</p>
</div>
</body></html>
"""
        if cfg.email_enabled and cfg.smtp_host and cfg.email_recipients:
            try:
                recipients = [r.strip() for r in cfg.email_recipients.split(",") if r.strip()]
                _send_email(cfg, subject, body_text, body_html, recipients)
            except Exception as e:
                logger.error(f"[HealthAlert] Test email dispatch failed: {e}")
        if cfg.slack_enabled and cfg.slack_webhook_url:
            try:
                _send_slack(cfg.slack_webhook_url, "TEST", "INFO", "Teste de alerta enviado manualmente", detail, now_brt)
            except Exception as e:
                logger.error(f"[HealthAlert] Test Slack dispatch failed: {e}")
    except Exception as e:
        logger.error(f"[HealthAlert] _dispatch_alert_force error: {e}")


def _dispatch_alert(event_type: str, severity: str, message: str, detail: Optional[str]):
    try:
        if _should_throttle(event_type):
            logger.info(f"[HealthAlert] Throttled duplicate alert for {event_type}")
            return

        cfg = _get_config()
        if cfg is None:
            return

        min_sev_level = SEVERITY_ORDER.get(cfg.min_severity or "HIGH", 3)
        event_sev_level = SEVERITY_ORDER.get(severity, 0)
        if event_sev_level < min_sev_level:
            return

        now_brt = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M:%S BRT")
        subject = f"[{severity}] Alerta do Sistema: {event_type}"
        body_text = f"""Alerta do Sistema
=================
Tipo: {event_type}
Severidade: {severity}
Horário: {now_brt}
Mensagem: {message}

{f'Detalhe:{chr(10)}{detail}' if detail else ''}

---
Sistema de Monitoramento
"""

        body_html = f"""
<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;background:#f5f5f5">
<div style="background:white;border-radius:8px;padding:24px;border-top:4px solid {'#dc2626' if severity=='CRITICAL' else '#f97316' if severity=='HIGH' else '#eab308' if severity=='MEDIUM' else '#3b82f6'}">
  <h2 style="margin:0 0 8px;color:#111">⚠️ Alerta do Sistema</h2>
  <p style="color:#666;margin:0 0 20px;font-size:14px">{now_brt}</p>
  <table style="width:100%;border-collapse:collapse;font-size:14px">
    <tr><td style="padding:8px;background:#f9fafb;font-weight:bold;width:130px;border:1px solid #e5e7eb">Tipo</td>
        <td style="padding:8px;border:1px solid #e5e7eb">{event_type}</td></tr>
    <tr><td style="padding:8px;background:#f9fafb;font-weight:bold;border:1px solid #e5e7eb">Severidade</td>
        <td style="padding:8px;border:1px solid #e5e7eb">
          <span style="background:{'#fee2e2' if severity=='CRITICAL' else '#ffedd5' if severity=='HIGH' else '#fef9c3' if severity=='MEDIUM' else '#eff6ff'};
                       color:{'#991b1b' if severity=='CRITICAL' else '#9a3412' if severity=='HIGH' else '#854d0e' if severity=='MEDIUM' else '#1d4ed8'};
                       padding:2px 8px;border-radius:4px;font-weight:bold">{severity}</span></td></tr>
    <tr><td style="padding:8px;background:#f9fafb;font-weight:bold;border:1px solid #e5e7eb">Mensagem</td>
        <td style="padding:8px;border:1px solid #e5e7eb">{message}</td></tr>
    {'<tr><td style="padding:8px;background:#f9fafb;font-weight:bold;border:1px solid #e5e7eb;vertical-align:top">Detalhe</td><td style="padding:8px;border:1px solid #e5e7eb;font-family:monospace;font-size:12px;white-space:pre-wrap">' + (detail or '') + '</td></tr>' if detail else ''}
  </table>
</div>
</body></html>
"""

        if cfg.email_enabled and cfg.smtp_host and cfg.email_recipients:
            try:
                recipients = [r.strip() for r in cfg.email_recipients.split(",") if r.strip()]
                _send_email(cfg, subject, body_text, body_html, recipients)
            except Exception as e:
                logger.error(f"[HealthAlert] Email dispatch failed: {e}")

        if cfg.slack_enabled and cfg.slack_webhook_url:
            try:
                _send_slack(cfg.slack_webhook_url, event_type, severity, message, detail, now_brt)
            except Exception as e:
                logger.error(f"[HealthAlert] Slack dispatch failed: {e}")

    except Exception as e:
        logger.error(f"[HealthAlert] _dispatch_alert error: {e}")


def _send_email(cfg, subject: str, body_text: str, body_html: str, recipients: list):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg.email_from or cfg.smtp_user or "alertas@sistema.com"
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    port = cfg.smtp_port or 587
    use_ssl = port == 465

    if use_ssl:
        server = smtplib.SMTP_SSL(cfg.smtp_host, port, timeout=15)
    else:
        server = smtplib.SMTP(cfg.smtp_host, port, timeout=15)
        server.ehlo()
        if port != 25:
            server.starttls()
            server.ehlo()

    if cfg.smtp_user and cfg.smtp_password:
        server.login(cfg.smtp_user, cfg.smtp_password)

    server.sendmail(msg["From"], recipients, msg.as_string())
    server.quit()
    logger.info(f"[HealthAlert] Email sent to {recipients}")


def _send_slack(webhook_url: str, event_type: str, severity: str, message: str, detail: Optional[str], timestamp: str):
    import requests  # lazy import: evita falha de módulo se requests não estiver instalado
    color_map = {
        "CRITICAL": "#dc2626",
        "HIGH": "#f97316",
        "MEDIUM": "#eab308",
        "LOW": "#3b82f6",
        "INFO": "#6b7280",
    }
    emoji_map = {
        "CRITICAL": "🔴",
        "HIGH": "🟠",
        "MEDIUM": "🟡",
        "LOW": "🔵",
        "INFO": "⚪",
    }
    color = color_map.get(severity, "#6b7280")
    emoji = emoji_map.get(severity, "⚠️")

    fields = [
        {"title": "Tipo", "value": event_type, "short": True},
        {"title": "Severidade", "value": severity, "short": True},
        {"title": "Horário", "value": timestamp, "short": True},
    ]
    if detail:
        fields.append({"title": "Detalhe", "value": detail[:300], "short": False})

    payload = {
        "attachments": [
            {
                "color": color,
                "title": f"{emoji} Alerta do Sistema",
                "text": message,
                "fields": fields,
                "footer": "Sistema de Monitoramento",
            }
        ]
    }

    resp = requests.post(webhook_url, json=payload, timeout=10)
    resp.raise_for_status()
    logger.info(f"[HealthAlert] Slack notification sent (status {resp.status_code})")
