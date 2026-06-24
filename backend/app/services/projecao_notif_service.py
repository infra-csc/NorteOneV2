"""
Resumo diário por e-mail das pendências de Projeção de Inscritos.

Reaproveita exatamente a mesma regra do alerta in-app (`get_pendencias`):
o alerta dispara no dia em que `hoje == Data de corte Envio - dias_alerta_envio`,
para eventos 'Em andamento' sem projeção registrada em alguma área. Aqui as
pendências são agrupadas POR USUÁRIO responsável da área (via
`area_projecao_usuario`); cada responsável recebe apenas as suas áreas.
"""
import logging
from collections import defaultdict
from datetime import datetime, date
from zoneinfo import ZoneInfo

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
from .email_service import send_email, EmailError

logger = logging.getLogger(__name__)

_BRT = ZoneInfo("America/Sao_Paulo")


def _app_base_url() -> str:
    import os
    base = os.environ.get("APP_BASE_URL")
    if base:
        return base.rstrip("/")
    dev = os.environ.get("REPLIT_DEV_DOMAIN")
    if dev:
        return f"https://{dev}"
    return ""


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

    # "Data de corte Envio" por evento = a MAIS ANTIGA entre as áreas (mesma
    # âncora do congelamento do Corte 1 e do alerta in-app).
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

    # Responsáveis por área
    vinc = (
        db.query(AreaProjecaoUsuario)
        .filter(AreaProjecaoUsuario.area_projecao_id.in_(all_areas_ids))
        .all()
    )
    users_by_area = defaultdict(set)
    for v in vinc:
        users_by_area[v.area_projecao_id].add(v.usuario_id)

    # Monta: usuario_id -> evento_id -> [nomes de áreas pendentes]
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
    Envia o resumo diário. Quando `force=False` respeita `notif_email_ativo`.
    Retorna um sumário { ativo, enviados, falhas, destinatarios, erros, total_eventos }.
    """
    config = db.query(ProjecaoCorteConfig).first()
    ativo = bool(config and config.notif_email_ativo)

    if not force and not ativo:
        return {
            "ativo": ativo,
            "enviados": 0,
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
            "enviados": 0,
            "falhas": 0,
            "destinatarios": [],
            "erros": [],
            "total_eventos": 0,
        }

    enviados = 0
    falhas = 0
    destinatarios = []
    erros = []
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
            send_email(
                u.email,
                subject,
                html=html,
                text=txt,
                to_name=u.nome,
            )
            enviados += 1
            destinatarios.append(u.email)
        except EmailError as exc:
            falhas += 1
            erros.append(f"{u.email}: {exc}")
            logger.warning(f"[ProjecaoNotif] Falha ao enviar para {u.email}: {exc}")

    logger.info(
        f"[ProjecaoNotif] Resumo diário: {enviados} enviado(s), {falhas} falha(s)."
    )
    return {
        "ativo": ativo,
        "enviados": enviados,
        "falhas": falhas,
        "destinatarios": destinatarios,
        "erros": erros,
        "total_eventos": sum(len(g["eventos"]) for g in grupos),
    }
