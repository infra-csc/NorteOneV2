"""
Resumo diário das pendências de Projeção de Inscritos por E-mail e/ou Teams DM.

Reaproveita exatamente a mesma regra do alerta in-app (`get_pendencias`):
o alerta dispara no dia em que `hoje == Data de corte Envio - dias_alerta_envio`,
para eventos 'Em andamento' sem projeção registrada em alguma área. Aqui as
pendências são agrupadas POR USUÁRIO responsável da área (via
`area_projecao_usuario`); cada responsável recebe apenas as suas áreas.

Canais suportados (config.notif_canal):
  'email'  → Microsoft Graph sendMail (MS_SENDER_EMAIL)
  'teams'  → Microsoft Graph Chat 1:1 (Chat.Create + ChatMessage.Send + User.Read.All)
  'ambos'  → e-mail E Teams DM; erros de um canal não bloqueiam o outro
"""
import logging
import os
from collections import defaultdict
from datetime import datetime, date
from typing import Optional
from zoneinfo import ZoneInfo

import requests
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.projecao import (
    AreaProjecao,
    AreaProjecaoUsuario,
    ProjecaoInscritos,
    ProjecaoCutoffEventoArea,
    ProjecaoCorteConfig,
)
from ..models.cadastro_evento import CadastroEvento
from ..models.user import Usuario
from .email_service import send_email, EmailError, _acquire_token

logger = logging.getLogger(__name__)

_BRT = ZoneInfo("America/Sao_Paulo")
_GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _app_base_url() -> str:
    base = os.environ.get("APP_BASE_URL")
    if base:
        return base.rstrip("/")
    dev = os.environ.get("REPLIT_DEV_DOMAIN")
    if dev:
        return f"https://{dev}"
    return ""


# ── Caches leves de session para Graph IDs (evita lookup duplo na mesma execução) ──
_aad_id_cache: dict[str, Optional[str]] = {}
_sender_aad_id_cache: Optional[str] = None


def _get_aad_user_id(email: str, token: str) -> Optional[str]:
    """Retorna o AAD object ID do usuário pelo e-mail. None se não encontrado."""
    global _aad_id_cache
    if email in _aad_id_cache:
        return _aad_id_cache[email]
    try:
        resp = requests.get(
            f"{_GRAPH_BASE}/users",
            params={"$filter": f"mail eq '{email}'", "$select": "id,mail"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            values = resp.json().get("value", [])
            uid = values[0]["id"] if values else None
            _aad_id_cache[email] = uid
            return uid
        logger.warning("[TeamsNotif] Falha ao buscar AAD ID de %s: %s", email, resp.status_code)
    except Exception as exc:
        logger.warning("[TeamsNotif] Erro ao buscar AAD ID de %s: %s", email, exc)
    _aad_id_cache[email] = None
    return None


def _get_or_create_dm_chat(sender_aad_id: str, recipient_aad_id: str, token: str) -> Optional[str]:
    """Cria (ou recupera) um chat 1:1 entre o remetente e o destinatário. Retorna chatId."""
    try:
        payload = {
            "chatType": "oneOnOne",
            "members": [
                {
                    "@odata.type": "#microsoft.graph.aadUserConversationMember",
                    "roles": ["owner"],
                    "user@odata.bind": f"{_GRAPH_BASE}/users('{sender_aad_id}')",
                },
                {
                    "@odata.type": "#microsoft.graph.aadUserConversationMember",
                    "roles": ["owner"],
                    "user@odata.bind": f"{_GRAPH_BASE}/users('{recipient_aad_id}')",
                },
            ],
        }
        resp = requests.post(
            f"{_GRAPH_BASE}/chats",
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=15,
        )
        if resp.status_code in (200, 201):
            return resp.json().get("id")
        logger.warning("[TeamsNotif] Falha ao criar chat 1:1: %s — %s", resp.status_code, resp.text[:300])
    except Exception as exc:
        logger.warning("[TeamsNotif] Erro ao criar chat: %s", exc)
    return None


def _build_adaptive_card(usuario: Usuario, eventos: list) -> dict:
    """
    Constrói um Adaptive Card (v1.2) com o resumo de pendências do usuário.
    Compatível com Teams via Graph API chatMessage attachments.
    """
    import uuid as _uuid
    base = _app_base_url()
    link = f"{base}/projecao-inscritos" if base else None
    total_areas = sum(len(e["areas"]) for e in eventos)
    plural_ev = "evento" if len(eventos) == 1 else "eventos"
    primeiro_nome = (usuario.nome or "").split(" ")[0] if usuario.nome else ""
    saudacao = f"Olá, {primeiro_nome}!" if primeiro_nome else "Olá!"

    # Bloco de fatos por evento
    event_blocks: list[dict] = []
    for e in eventos:
        areas_str = ", ".join(e["areas"])
        data_ev = _fmt_data_br(e["data_evento"])
        data_corte = _fmt_data_br(e["cutoff_data"])
        event_blocks.append({
            "type": "Container",
            "style": "emphasis",
            "spacing": "Small",
            "items": [
                {
                    "type": "TextBlock",
                    "text": e["nome"],
                    "weight": "Bolder",
                    "size": "Small",
                    "wrap": True,
                },
                {
                    "type": "FactSet",
                    "facts": [
                        {"title": "Evento:", "value": data_ev},
                        {"title": "Corte Envio:", "value": data_corte},
                        {"title": "Áreas pendentes:", "value": areas_str},
                    ],
                },
            ],
        })

    body: list[dict] = [
        {
            "type": "TextBlock",
            "text": "Norte One — Projeção de Inscritos",
            "weight": "Bolder",
            "size": "Medium",
            "color": "Accent",
        },
        {
            "type": "TextBlock",
            "text": saudacao,
            "spacing": "Small",
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": (
                f"Você tem **{len(eventos)} {plural_ev}** com projeção pendente "
                f"em **{total_areas} área(s)** que atingiram o ponto de corte hoje."
            ),
            "wrap": True,
            "spacing": "Small",
        },
        {"type": "Separator"},
        *event_blocks,
    ]

    actions: list[dict] = []
    if link:
        actions.append({
            "type": "Action.OpenUrl",
            "title": "Abrir Projeção de Inscritos",
            "url": link,
        })

    card = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.2",
        "body": body,
        "actions": actions,
    }
    return card


def _send_teams_chat_message(chat_id: str, card: dict, token: str) -> bool:
    """Envia Adaptive Card como mensagem num chat Teams 1:1. Retorna True se bem-sucedido."""
    import json as _json
    import uuid as _uuid
    attachment_id = _uuid.uuid4().hex
    payload = {
        "body": {
            "contentType": "html",
            "content": f'<attachment id="{attachment_id}"></attachment>',
        },
        "attachments": [
            {
                "id": attachment_id,
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": _json.dumps(card),
            }
        ],
    }
    try:
        resp = requests.post(
            f"{_GRAPH_BASE}/chats/{chat_id}/messages",
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=15,
        )
        if resp.status_code in (200, 201):
            return True
        logger.warning("[TeamsNotif] Falha ao enviar mensagem: %s — %s", resp.status_code, resp.text[:300])
    except Exception as exc:
        logger.warning("[TeamsNotif] Erro ao enviar mensagem Teams: %s", exc)
    return False


def send_teams_dm_per_user(grupos: list) -> dict:
    """
    Envia DM individual no Teams para cada responsável de área com pendências.
    Usa Chat.Create + ChatMessage.Send + User.Read.All via Graph API.
    Retorna sumário { enviados, falhas, destinatarios, erros }.
    """
    global _sender_aad_id_cache
    enviados = 0
    falhas = 0
    destinatarios: list[str] = []
    erros: list[str] = []

    sender_email = os.environ.get("MS_SENDER_EMAIL", "").strip()
    if not sender_email:
        return {"enviados": 0, "falhas": len(grupos), "destinatarios": [], "erros": ["MS_SENDER_EMAIL ausente"]}

    try:
        token = _acquire_token()
    except Exception as exc:
        return {"enviados": 0, "falhas": len(grupos), "destinatarios": [], "erros": [f"Token Graph falhou: {exc}"]}

    # Busca AAD ID do remetente uma vez
    if _sender_aad_id_cache is None:
        _sender_aad_id_cache = _get_aad_user_id(sender_email, token)
    sender_aad_id = _sender_aad_id_cache

    if not sender_aad_id:
        return {
            "enviados": 0,
            "falhas": len(grupos),
            "destinatarios": [],
            "erros": [f"Remetente '{sender_email}' não encontrado no Azure AD. Verifique o MS_SENDER_EMAIL."],
        }

    for g in grupos:
        u: Usuario = g["usuario"]
        if not (u.email or "").strip():
            falhas += 1
            erros.append(f"(id={u.id}): sem e-mail cadastrado")
            continue

        recipient_aad_id = _get_aad_user_id(u.email, token)
        if not recipient_aad_id:
            falhas += 1
            erros.append(f"{u.email}: usuário não encontrado no Azure AD")
            logger.warning("[TeamsNotif] Usuário não encontrado no AAD: %s", u.email)
            continue

        chat_id = _get_or_create_dm_chat(sender_aad_id, recipient_aad_id, token)
        if not chat_id:
            falhas += 1
            erros.append(f"{u.email}: falha ao criar/obter chat 1:1")
            continue

        card = _build_adaptive_card(u, g["eventos"])
        ok = _send_teams_chat_message(chat_id, card, token)
        if ok:
            enviados += 1
            destinatarios.append(u.email)
            logger.info("[TeamsNotif] DM enviada para %s (chat %s)", u.email, chat_id)
        else:
            falhas += 1
            erros.append(f"{u.email}: falha ao enviar mensagem Teams")

    logger.info("[TeamsNotif] DMs: %d enviada(s), %d falha(s)", enviados, falhas)
    return {"enviados": enviados, "falhas": falhas, "destinatarios": destinatarios, "erros": erros}


# ─────────────────────────────────────────────────────────────────────────────

def computar_pendencias_por_usuario(db: Session):
    """
    Retorna lista de dicts por usuário responsável:
      { "usuario": Usuario, "eventos": [ {nome, data_evento, cutoff_data, areas:[nomes]} ] }
    Só inclui usuários ativos com e-mail. Vazio quando não há disparo hoje.
    """
    today = datetime.now(_BRT).date()

    config = db.query(ProjecaoCorteConfig).first()
    n = config.dias_alerta_envio if config else 30
    if not n or n <= 0:
        return []

    areas = db.query(AreaProjecao).filter(AreaProjecao.ativo == True).all()
    if not areas:
        return []
    areas_nome_by_id = {a.id: a.nome for a in areas}
    all_areas_ids = set(areas_nome_by_id.keys())

    cesb_rows = (
        db.query(
            ProjecaoCutoffEventoArea.evento_id,
            func.min(ProjecaoCutoffEventoArea.data_corte_1),
        )
        .filter(ProjecaoCutoffEventoArea.data_corte_1.isnot(None))
        .group_by(ProjecaoCutoffEventoArea.evento_id)
        .all()
    )
    corte_envio_by_evento = {eid: dt for eid, dt in cesb_rows}

    trigger = {
        eid: dt
        for eid, dt in corte_envio_by_evento.items()
        if (dt - today).days == n
    }
    if not trigger:
        return []

    evs = (
        db.query(CadastroEvento)
        .filter(
            CadastroEvento.id.in_(list(trigger.keys())),
            CadastroEvento.deleted_at.is_(None),
            CadastroEvento.status == "Em andamento",
        )
        .all()
    )
    if not evs:
        return []

    evento_ids = {ev.id for ev in evs}
    projs = (
        db.query(ProjecaoInscritos.evento_id, ProjecaoInscritos.area_projecao_id)
        .filter(
            ProjecaoInscritos.evento_id.in_(evento_ids),
            ProjecaoInscritos.area_projecao_id.in_(all_areas_ids),
            ProjecaoInscritos.deleted_at.is_(None),
        )
        .all()
    )
    existentes = {(p.evento_id, p.area_projecao_id) for p in projs}

    vinc = (
        db.query(AreaProjecaoUsuario)
        .filter(AreaProjecaoUsuario.area_projecao_id.in_(all_areas_ids))
        .all()
    )
    users_by_area = defaultdict(set)
    for v in vinc:
        users_by_area[v.area_projecao_id].add(v.usuario_id)

    per_user = defaultdict(lambda: defaultdict(list))
    for ev in evs:
        for aid in all_areas_ids:
            if (ev.id, aid) in existentes:
                continue
            for uid in users_by_area.get(aid, ()):
                per_user[uid][ev.id].append(areas_nome_by_id[aid])

    if not per_user:
        return []

    usuarios = (
        db.query(Usuario)
        .filter(
            Usuario.id.in_(list(per_user.keys())),
            Usuario.ativo == True,
            Usuario.email.isnot(None),
        )
        .all()
    )
    eventos_by_id = {ev.id: ev for ev in evs}

    resultado = []
    for u in usuarios:
        if not (u.email or "").strip():
            continue
        eventos_payload = []
        for eid, area_nomes in per_user[u.id].items():
            ev = eventos_by_id[eid]
            eventos_payload.append({
                "nome": ev.nome,
                "data_evento": ev.data_evento.isoformat() if ev.data_evento else None,
                "cutoff_data": trigger[eid].isoformat(),
                "areas": sorted(set(area_nomes)),
            })
        eventos_payload.sort(key=lambda e: (e["data_evento"] or "", e["nome"]))
        resultado.append({"usuario": u, "eventos": eventos_payload})

    resultado.sort(key=lambda r: r["usuario"].nome or "")
    return resultado


def _fmt_data_br(iso: str | None) -> str:
    if not iso:
        return "-"
    try:
        return date.fromisoformat(iso).strftime("%d/%m/%Y")
    except Exception:
        return iso


def _render_email(usuario: Usuario, eventos: list) -> tuple[str, str]:
    base = _app_base_url()
    link = f"{base}/projecao-inscritos" if base else "/projecao-inscritos"

    total_areas = sum(len(e["areas"]) for e in eventos)
    plural_ev = "evento" if len(eventos) == 1 else "eventos"

    linhas_html = []
    linhas_txt = []
    for e in eventos:
        areas = ", ".join(e["areas"])
        data_ev = _fmt_data_br(e["data_evento"])
        data_corte = _fmt_data_br(e["cutoff_data"])
        linhas_html.append(
            f"""<tr>
              <td style="padding:10px 12px;border-bottom:1px solid #eee;">
                <strong style="color:#111;">{e['nome']}</strong><br>
                <span style="color:#666;font-size:13px;">Data do evento: {data_ev} &nbsp;•&nbsp; Data de corte Envio: {data_corte}</span>
              </td>
              <td style="padding:10px 12px;border-bottom:1px solid #eee;color:#b91c1c;font-weight:600;">{areas}</td>
            </tr>"""
        )
        linhas_txt.append(f"- {e['nome']} (evento {data_ev}, corte envio {data_corte}) → áreas: {areas}")

    primeiro_nome = (usuario.nome or "").split(" ")[0] if usuario.nome else ""
    saudacao = f"Olá, {primeiro_nome}!" if primeiro_nome else "Olá!"

    html = f"""<!DOCTYPE html>
<html lang="pt-br"><head><meta charset="utf-8"></head>
<body style="margin:0;background:#f5f6f8;font-family:Arial,Helvetica,sans-serif;color:#222;">
  <div style="max-width:640px;margin:0 auto;padding:24px;">
    <div style="background:#b91c1c;color:#fff;padding:18px 22px;border-radius:10px 10px 0 0;">
      <h1 style="margin:0;font-size:18px;">Alerta de Pendência — Projeção de Inscritos</h1>
    </div>
    <div style="background:#fff;padding:22px;border-radius:0 0 10px 10px;border:1px solid #eee;border-top:none;">
      <p style="margin:0 0 12px;">{saudacao}</p>
      <p style="margin:0 0 16px;color:#444;">
        Você tem <strong>{len(eventos)} {plural_ev}</strong> com projeção pendente em
        <strong>{total_areas} área(s)</strong> que atingiram o ponto de corte hoje.
        Por favor, registre as projeções:
      </p>
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <thead>
          <tr style="text-align:left;color:#666;font-size:12px;text-transform:uppercase;">
            <th style="padding:8px 12px;">Evento</th>
            <th style="padding:8px 12px;">Áreas pendentes</th>
          </tr>
        </thead>
        <tbody>{''.join(linhas_html)}</tbody>
      </table>
      <div style="margin-top:22px;">
        <a href="{link}" style="background:#b91c1c;color:#fff;text-decoration:none;padding:11px 20px;border-radius:8px;font-weight:600;display:inline-block;">Abrir Projeção de Inscritos</a>
      </div>
      <p style="margin:22px 0 0;color:#999;font-size:12px;">
        Você recebeu este e-mail porque é responsável por uma ou mais áreas no Norte One.
      </p>
    </div>
  </div>
</body></html>"""

    txt = (
        f"{saudacao}\n\n"
        f"Você tem {len(eventos)} {plural_ev} com projeção pendente em {total_areas} área(s) "
        f"que atingiram o ponto de corte hoje.\n\n"
        + "\n".join(linhas_txt)
        + f"\n\nAbra a Projeção de Inscritos: {link}\n\n"
        "Você recebeu este e-mail porque é responsável por uma ou mais áreas no Norte One."
    )
    return html, txt


def enviar_resumo_diario(db: Session, *, force: bool = False) -> dict:
    """
    Envia o resumo diário pelo(s) canal(is) configurado(s).
    Quando `force=False` respeita `notif_email_ativo`.
    Retorna sumário { ativo, canal, enviados_email, enviados_teams, falhas, destinatarios, erros, total_eventos }.
    """
    config = db.query(ProjecaoCorteConfig).first()
    ativo = bool(config and config.notif_email_ativo)
    canal = (getattr(config, 'notif_canal', None) or 'email').strip().lower()

    if not force and not ativo:
        return {
            "ativo": ativo,
            "canal": canal,
            "enviados": 0,
            "enviados_email": 0,
            "enviados_teams": 0,
            "falhas": 0,
            "destinatarios": [],
            "erros": [],
            "total_eventos": 0,
            "skipped": "notificacao_desativada",
        }

    grupos = computar_pendencias_por_usuario(db)
    if not grupos:
        return {
            "ativo": ativo,
            "canal": canal,
            "enviados": 0,
            "enviados_email": 0,
            "enviados_teams": 0,
            "falhas": 0,
            "destinatarios": [],
            "erros": [],
            "total_eventos": 0,
        }

    result_email = {"enviados": 0, "falhas": 0, "destinatarios": [], "erros": []}
    result_teams = {"enviados": 0, "falhas": 0, "destinatarios": [], "erros": []}

    # ── E-mail ──────────────────────────────────────────────────────────────
    if canal in ('email', 'ambos'):
        e_env = 0
        e_falh = 0
        e_dest: list[str] = []
        e_errs: list[str] = []
        for g in grupos:
            u = g["usuario"]
            html, txt = _render_email(u, g["eventos"])
            n_ev = len(g["eventos"])
            subject = (
                f"[Norte One] {n_ev} evento(s) com projeção pendente"
                if n_ev != 1 else
                "[Norte One] 1 evento com projeção pendente"
            )
            try:
                send_email(u.email, subject, html=html, text=txt, to_name=u.nome)
                e_env += 1
                e_dest.append(u.email)
            except EmailError as exc:
                e_falh += 1
                e_errs.append(f"{u.email}: {exc}")
                logger.warning("[ProjecaoNotif] Falha e-mail para %s: %s", u.email, exc)
        result_email = {"enviados": e_env, "falhas": e_falh, "destinatarios": e_dest, "erros": e_errs}
        logger.info("[ProjecaoNotif] E-mail: %d enviado(s), %d falha(s)", e_env, e_falh)

    # ── Teams DM ────────────────────────────────────────────────────────────
    if canal in ('teams', 'ambos'):
        result_teams = send_teams_dm_per_user(grupos)

    enviados_total = result_email["enviados"] + result_teams["enviados"]
    falhas_total = result_email["falhas"] + result_teams["falhas"]
    destinatarios_all = list(dict.fromkeys(result_email["destinatarios"] + result_teams["destinatarios"]))
    erros_all = result_email["erros"] + result_teams["erros"]

    return {
        "ativo": ativo,
        "canal": canal,
        "enviados": enviados_total,
        "enviados_email": result_email["enviados"],
        "enviados_teams": result_teams["enviados"],
        "falhas": falhas_total,
        "destinatarios": destinatarios_all,
        "erros": erros_all,
        "total_eventos": sum(len(g["eventos"]) for g in grupos),
    }


# ── Health check de permissões Azure para Teams DM ───────────────────────────

def check_teams_permissions() -> dict:
    """
    Verifica se as permissões Azure necessárias para envio de Teams DM estão
    configuradas. Tenta adquirir token e provar User.Read.All + Chat.Create.

    Retorna: { ok: bool, missing_scopes: list[str], error: str | null }
    """
    import os
    from .email_service import _acquire_token, EmailError

    missing_scopes: list[str] = []

    # 1. Credenciais presentes?
    tenant_id = os.environ.get("MS_TENANT_ID", "").strip()
    client_id = os.environ.get("MS_CLIENT_ID", "").strip()
    client_secret = os.environ.get("MS_CLIENT_SECRET", "").strip()

    cred_missing = [k for k, v in [
        ("MS_TENANT_ID", tenant_id),
        ("MS_CLIENT_ID", client_id),
        ("MS_CLIENT_SECRET", client_secret),
    ] if not v]
    if cred_missing:
        return {
            "ok": False,
            "missing_scopes": [],
            "error": f"Variáveis de ambiente ausentes: {', '.join(cred_missing)}",
        }

    # 2. Adquirir token (valida credenciais + consentimento de admin)
    try:
        token = _acquire_token()
    except EmailError as exc:
        return {"ok": False, "missing_scopes": [], "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "missing_scopes": [], "error": f"Erro ao adquirir token: {exc}"}

    # 3. Provar User.Read.All: listar 1 usuário
    try:
        resp = requests.get(
            f"{_GRAPH_BASE}/users",
            params={"$top": "1", "$select": "id,mail"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if resp.status_code == 403:
            missing_scopes.append("User.Read.All")
            logger.warning("[TeamsHealth] User.Read.All ausente: %s", resp.text[:200])
        elif resp.status_code not in (200,):
            missing_scopes.append("User.Read.All")
            logger.warning("[TeamsHealth] GET /users retornou %s", resp.status_code)
    except Exception as exc:
        return {
            "ok": False,
            "missing_scopes": missing_scopes,
            "error": f"Erro ao verificar User.Read.All: {exc}",
        }

    # 4. Provar Chat.Create: POST /chats com payload intencionalmente inválido.
    #    403 → permissão ausente; 400/422/outros → permissão concedida, payload rejeitado (esperado).
    try:
        resp = requests.post(
            f"{_GRAPH_BASE}/chats",
            json={"chatType": "oneOnOne", "members": []},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code == 403:
            missing_scopes.append("Chat.Create")
            logger.warning("[TeamsHealth] Chat.Create ausente: %s", resp.text[:200])
        # 400/422/outros = payload rejeitado mas acesso concedido → OK para este escopo
    except Exception as exc:
        return {
            "ok": False,
            "missing_scopes": missing_scopes,
            "error": f"Erro ao verificar Chat.Create: {exc}",
        }

    # 5. Provar ChatMessage.Send independentemente: POST /chats/{id}/messages com ID fictício.
    #    403 → permissão ausente; 404 → permissão presente mas chat não encontrado (esperado);
    #    400/outros → acesso concedido, payload ou rota rejeitada.
    _FAKE_CHAT_ID = "19:00000000000000000000000000000000_00000000-0000-0000-0000-000000000000@unq.gbl.spaces"
    try:
        resp = requests.post(
            f"{_GRAPH_BASE}/chats/{_FAKE_CHAT_ID}/messages",
            json={"body": {"content": "health-check", "contentType": "text"}},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code == 403:
            missing_scopes.append("ChatMessage.Send")
            logger.warning("[TeamsHealth] ChatMessage.Send ausente: %s", resp.text[:200])
        # 404 = chat não existe mas permissão OK; 400 = permissão OK mas request inválido
    except Exception as exc:
        return {
            "ok": False,
            "missing_scopes": missing_scopes,
            "error": f"Erro ao verificar ChatMessage.Send: {exc}",
        }

    return {
        "ok": len(missing_scopes) == 0,
        "missing_scopes": missing_scopes,
        "error": None,
    }
