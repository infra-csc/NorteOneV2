"""
Avisos por e-mail do fluxo de Aprovação de Redução no Corte de Ajuste
(Task #212).

Dois eventos discretos e pouco frequentes — sem necessidade de debounce
(diferente do aviso de alteração de projeção, que agrupa saves consecutivos):

  - notificar_solicitacao_criada:  avisa a área aprovadora que um chamado
    novo está pendente. Se nenhuma área aprovadora estiver configurada,
    não há para quem avisar — só o admin verá o chamado na fila, então a
    função sai silenciosamente.
  - notificar_solicitacao_decidida: avisa o solicitante original que o
    chamado foi aprovado ou rejeitado.

Sempre best-effort: qualquer falha (credenciais ausentes, Graph fora do ar,
etc.) só loga um warning e nunca propaga para o caller (o save/decisão já
foi commitado antes do aviso ser disparado).
"""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from ..models.projecao import ProjecaoReducaoSolicitacao, AreaProjecaoUsuario
from ..models.user import Usuario
from .email_service import send_email, EmailError

logger = logging.getLogger(__name__)


def _emails_area(db: Session, area_projecao_id: int) -> list[str]:
    """E-mails de usuários ATIVOS vinculados à área (mesmo vínculo
    área↔usuário usado pelas pendências, `area_projecao_usuario`)."""
    rows = db.query(Usuario.email).join(
        AreaProjecaoUsuario, AreaProjecaoUsuario.usuario_id == Usuario.id
    ).filter(
        AreaProjecaoUsuario.area_projecao_id == area_projecao_id,
        Usuario.ativo.is_(True),
    ).all()
    return sorted({r[0].strip().lower() for r in rows if r[0] and "@" in r[0]})


def _send_best_effort(email: str, subject: str, html: str, text: str, contexto: str) -> None:
    try:
        send_email(email, subject, html=html, text=text)
    except EmailError as exc:
        logger.warning("[ReducaoAprovacao] Falha e-mail (%s) para %s: %s", contexto, email, exc)
    except Exception as exc:
        logger.warning("[ReducaoAprovacao] Erro inesperado (%s) enviando para %s: %s", contexto, email, exc)


def _fmt_dt_br(dt: datetime | None) -> str:
    if not dt:
        return "—"
    return dt.strftime("%d/%m/%Y %H:%M")


def _render_criada(sol: ProjecaoReducaoSolicitacao) -> tuple[str, str, str]:
    evento = sol.evento.nome if sol.evento else f"Evento #{sol.evento_id}"
    area = sol.area_projecao.nome if sol.area_projecao else f"Área #{sol.area_projecao_id}"
    solicitante = sol.solicitante.nome if sol.solicitante else f"Usuário #{sol.solicitado_por}"

    subject = f"[Norte One] Chamado de redução pendente — {evento} / {area}"
    motivo_html = (
        f'<tr><td style="padding:8px 12px;color:#666;">Motivo</td><td style="padding:8px 12px;">{sol.motivo}</td></tr>'
        if sol.motivo else ""
    )
    motivo_txt = f"Motivo: {sol.motivo}\n" if sol.motivo else ""

    html = f"""<!DOCTYPE html>
<html lang="pt-br"><head><meta charset="utf-8"></head>
<body style="margin:0;background:#f5f6f8;font-family:Arial,Helvetica,sans-serif;color:#222;">
  <div style="max-width:640px;margin:0 auto;padding:24px;">
    <div style="background:#b45309;color:#fff;padding:18px 22px;border-radius:10px 10px 0 0;">
      <h1 style="margin:0;font-size:18px;">Chamado de redução aguardando aprovação</h1>
    </div>
    <div style="background:#fff;padding:22px;border-radius:0 0 10px 10px;border:1px solid #eee;border-top:none;">
      <p style="margin:0 0 16px;color:#444;">
        Uma redução de projeção no Corte de Ajuste precisa da sua aprovação:
      </p>
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <tbody>
          <tr><td style="padding:8px 12px;color:#666;width:180px;">Evento</td><td style="padding:8px 12px;font-weight:600;">{evento}</td></tr>
          <tr><td style="padding:8px 12px;color:#666;">Área solicitante</td><td style="padding:8px 12px;font-weight:600;">{area}</td></tr>
          <tr><td style="padding:8px 12px;color:#666;">Solicitado por</td><td style="padding:8px 12px;">{solicitante}</td></tr>
          <tr><td style="padding:8px 12px;color:#666;">Quantidade</td>
              <td style="padding:8px 12px;"><span style="color:#666;">{sol.quantidade_atual}</span>
              &nbsp;→&nbsp; <strong style="color:#b45309;font-size:16px;">{sol.quantidade_proposta}</strong></td></tr>
          {motivo_html}
          <tr><td style="padding:8px 12px;color:#666;">Aberto em</td><td style="padding:8px 12px;">{_fmt_dt_br(sol.solicitado_em)} (BRT)</td></tr>
        </tbody>
      </table>
      <p style="margin:22px 0 0;color:#999;font-size:12px;">
        Acesse Projeção de Inscritos → Aprovações no Norte One para aprovar ou rejeitar este chamado.
      </p>
    </div>
  </div>
</body></html>"""

    txt = (
        "Chamado de redução aguardando aprovação\n\n"
        f"Evento: {evento}\n"
        f"Área solicitante: {area}\n"
        f"Solicitado por: {solicitante}\n"
        f"Quantidade: {sol.quantidade_atual} → {sol.quantidade_proposta}\n"
        f"{motivo_txt}"
        f"Aberto em: {_fmt_dt_br(sol.solicitado_em)} (BRT)\n\n"
        "Acesse Projeção de Inscritos → Aprovações no Norte One para aprovar ou rejeitar este chamado."
    )
    return subject, html, txt


def _render_decidida(sol: ProjecaoReducaoSolicitacao) -> tuple[str, str, str]:
    evento = sol.evento.nome if sol.evento else f"Evento #{sol.evento_id}"
    area = sol.area_projecao.nome if sol.area_projecao else f"Área #{sol.area_projecao_id}"
    decisor = sol.decisor.nome if sol.decisor else "—"
    aprovado = sol.status == "aprovado"
    cor = "#15803d" if aprovado else "#b91c1c"
    label = "APROVADO" if aprovado else "REJEITADO"

    subject = f"[Norte One] Chamado de redução {label.lower()} — {evento} / {area}"
    motivo_rejeicao_html = (
        f'<tr><td style="padding:8px 12px;color:#666;">Motivo</td><td style="padding:8px 12px;">{sol.motivo_rejeicao}</td></tr>'
        if (not aprovado and sol.motivo_rejeicao) else ""
    )
    motivo_rejeicao_txt = f"Motivo: {sol.motivo_rejeicao}\n" if (not aprovado and sol.motivo_rejeicao) else ""

    html = f"""<!DOCTYPE html>
<html lang="pt-br"><head><meta charset="utf-8"></head>
<body style="margin:0;background:#f5f6f8;font-family:Arial,Helvetica,sans-serif;color:#222;">
  <div style="max-width:640px;margin:0 auto;padding:24px;">
    <div style="background:{cor};color:#fff;padding:18px 22px;border-radius:10px 10px 0 0;">
      <h1 style="margin:0;font-size:18px;">Chamado de redução {label}</h1>
    </div>
    <div style="background:#fff;padding:22px;border-radius:0 0 10px 10px;border:1px solid #eee;border-top:none;">
      <p style="margin:0 0 16px;color:#444;">
        Seu chamado de redução de projeção foi <strong style="color:{cor};">{label.lower()}</strong>.
      </p>
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <tbody>
          <tr><td style="padding:8px 12px;color:#666;width:180px;">Evento</td><td style="padding:8px 12px;font-weight:600;">{evento}</td></tr>
          <tr><td style="padding:8px 12px;color:#666;">Área</td><td style="padding:8px 12px;font-weight:600;">{area}</td></tr>
          <tr><td style="padding:8px 12px;color:#666;">Quantidade solicitada</td>
              <td style="padding:8px 12px;"><span style="color:#666;">{sol.quantidade_atual}</span>
              &nbsp;→&nbsp; <strong>{sol.quantidade_proposta}</strong></td></tr>
          <tr><td style="padding:8px 12px;color:#666;">Decidido por</td><td style="padding:8px 12px;">{decisor}</td></tr>
          <tr><td style="padding:8px 12px;color:#666;">Decidido em</td><td style="padding:8px 12px;">{_fmt_dt_br(sol.decidido_em)} (BRT)</td></tr>
          {motivo_rejeicao_html}
        </tbody>
      </table>
      <p style="margin:22px 0 0;color:#999;font-size:12px;">
        Você recebeu este e-mail por ser o solicitante deste chamado no Norte One.
      </p>
    </div>
  </div>
</body></html>"""

    txt = (
        f"Chamado de redução {label}\n\n"
        f"Evento: {evento}\n"
        f"Área: {area}\n"
        f"Quantidade solicitada: {sol.quantidade_atual} → {sol.quantidade_proposta}\n"
        f"Decidido por: {decisor}\n"
        f"Decidido em: {_fmt_dt_br(sol.decidido_em)} (BRT)\n"
        f"{motivo_rejeicao_txt}"
    )
    return subject, html, txt


def notificar_solicitacao_criada(db: Session, sol: ProjecaoReducaoSolicitacao, area_aprovadora_id: int | None) -> None:
    """Avisa a área aprovadora configurada que um novo chamado está
    pendente. Sem área aprovadora configurada, não há destinatário — sai
    silenciosamente (o chamado continua visível para admins na fila)."""
    if not area_aprovadora_id:
        logger.info("[ReducaoAprovacao] Sem área aprovadora configurada — aviso de criação não enviado (chamado #%s)", sol.id)
        return
    emails = _emails_area(db, area_aprovadora_id)
    if not emails:
        logger.info("[ReducaoAprovacao] Área aprovadora %s sem usuários com e-mail — aviso de criação não enviado (chamado #%s)", area_aprovadora_id, sol.id)
        return
    subject, html, txt = _render_criada(sol)
    for email in emails:
        _send_best_effort(email, subject, html, txt, contexto=f"criação #{sol.id}")


def notificar_solicitacao_decidida(db: Session, sol: ProjecaoReducaoSolicitacao) -> None:
    """Avisa o solicitante original que o chamado foi aprovado/rejeitado."""
    solicitante = sol.solicitante
    if not solicitante or not solicitante.email:
        logger.info("[ReducaoAprovacao] Solicitante sem e-mail cadastrado — aviso de decisão não enviado (chamado #%s)", sol.id)
        return
    subject, html, txt = _render_decidida(sol)
    _send_best_effort(solicitante.email, subject, html, txt, contexto=f"decisão #{sol.id}")
