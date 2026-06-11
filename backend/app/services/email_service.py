"""
Envio de e-mail via SendGrid usando a conexão (connector) do Replit.

As credenciais (api_key + from_email) são buscadas em tempo de execução no proxy
de conectores do Replit. NUNCA são logadas nem persistidas — o token pode rotar,
então re-buscamos a cada lote de envio.
"""
import os
import logging
from typing import Optional, Tuple

import requests

logger = logging.getLogger(__name__)

_SENDGRID_SEND_URL = "https://api.sendgrid.com/v3/mail/send"


class EmailError(Exception):
    """Falha ao enviar e-mail (credenciais ausentes ou erro do SendGrid)."""


def _get_x_replit_token() -> Optional[str]:
    repl_identity = os.environ.get("REPL_IDENTITY")
    if repl_identity:
        return "repl " + repl_identity
    web_renewal = os.environ.get("WEB_REPL_RENEWAL")
    if web_renewal:
        return "depl " + web_renewal
    return None


def get_sendgrid_credentials() -> Tuple[str, str]:
    """Retorna (api_key, from_email) da conexão SendGrid. Levanta EmailError se faltar."""
    hostname = os.environ.get("REPLIT_CONNECTORS_HOSTNAME")
    token = _get_x_replit_token()
    if not hostname or not token:
        raise EmailError(
            "Conexão SendGrid indisponível (REPLIT_CONNECTORS_HOSTNAME / token ausentes)."
        )

    url = (
        f"https://{hostname}/api/v2/connection"
        "?include_secrets=true&connector_names=sendgrid"
    )
    try:
        resp = requests.get(
            url,
            headers={"Accept": "application/json", "X_REPLIT_TOKEN": token},
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise EmailError(f"Falha ao consultar o proxy de conectores: {exc}") from exc

    items = (resp.json() or {}).get("items", [])
    if not items:
        raise EmailError("Nenhuma conexão SendGrid configurada.")

    settings = items[0].get("settings", {}) or {}
    api_key = settings.get("api_key") or settings.get("apiKey")
    from_email = settings.get("from_email") or settings.get("fromEmail")
    if not api_key:
        raise EmailError("Conexão SendGrid sem api_key.")
    if not from_email:
        raise EmailError("Conexão SendGrid sem from_email (remetente verificado).")
    return api_key, from_email


def send_email(
    to_email: str,
    subject: str,
    html: Optional[str] = None,
    text: Optional[str] = None,
    *,
    credentials: Optional[Tuple[str, str]] = None,
    to_name: Optional[str] = None,
) -> None:
    """Envia um e-mail. Reaproveite `credentials` em lotes para evitar re-buscar."""
    if not to_email:
        raise EmailError("Destinatário (to_email) vazio.")
    if not html and not text:
        raise EmailError("E-mail sem conteúdo (html/text).")

    api_key, from_email = credentials if credentials else get_sendgrid_credentials()

    content = []
    if text:
        content.append({"type": "text/plain", "value": text})
    if html:
        content.append({"type": "text/html", "value": html})

    to_obj = {"email": to_email}
    if to_name:
        to_obj["name"] = to_name

    payload = {
        "personalizations": [{"to": [to_obj]}],
        "from": {"email": from_email},
        "subject": subject,
        "content": content,
    }

    try:
        resp = requests.post(
            _SENDGRID_SEND_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
        )
    except requests.RequestException as exc:
        raise EmailError(f"Falha de rede ao enviar e-mail: {exc}") from exc

    if resp.status_code >= 300:
        # Não logar a api_key; o corpo do SendGrid não a contém.
        raise EmailError(
            f"SendGrid retornou {resp.status_code}: {resp.text[:500]}"
        )
