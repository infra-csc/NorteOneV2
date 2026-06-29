"""
Sincronização do diretório Microsoft Entra ID com a tabela de usuários local.

Regras (task #72):
  - Sincroniza TODOS os usuários do diretório.
  - Usuário novo (oid desconhecido) → cria conta SSO com o perfil de acesso
    mais restritivo (ver `resolve_default_perfil_id`).
  - Usuário do diretório que casa por e-mail com uma conta local existente →
    "adota" a conta (vincula o ms_oid, marca auth_provider='microsoft' e zera a
    senha_hash — a partir daí ela só autentica via SSO).
  - `accountEnabled=false` no diretório → conta desativada localmente e sessões
    invalidadas. A fonte da verdade de ativo/inativo é o diretório.
  - Conta SSO que sumiu do diretório → desativada (não apagada) e sessões
    invalidadas.
  - Contas locais (auth_provider='local', ex.: break-glass admin) NUNCA são
    tocadas por este job — ele só opera sobre contas Microsoft. Para garantir
    break-glass, mantenha o admin de emergência como conta local FORA do
    diretório Entra (assim nunca é adotado nem desativado pelo sync).
"""
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.security import invalidate_user_sessions
from ..models.user import Usuario
from ..models.perfil_acesso import PerfilAcesso, PerfilPermissao
from .ms_auth_service import list_directory_users, MSAuthError

logger = logging.getLogger(__name__)


def resolve_default_perfil_id(db: Session) -> Optional[int]:
    """Resolve o perfil de acesso para contas SSO recém-criadas.

    Ordem de prioridade:
      1. MS_DEFAULT_PERFIL_NOME (nome exato, case-insensitive).
      2. MS_DEFAULT_PERFIL_ID (id numérico).
      3. Heurística: perfil ativo, não-admin e não-sistema, com o MENOR número
         de permissões (o mais restritivo). Empate → menor id.
      4. None — sem perfil. É o acesso mais restritivo possível: o usuário
         autentica mas `require_permission` nega tudo e a sidebar fica vazia.
    """
    nome = (settings.MS_DEFAULT_PERFIL_NOME or "").strip()
    if nome:
        p = (
            db.query(PerfilAcesso)
            .filter(func.lower(PerfilAcesso.nome) == nome.lower())
            .first()
        )
        if p:
            return p.id
        logger.warning("[MSDirSync] MS_DEFAULT_PERFIL_NOME='%s' não encontrado — caindo p/ heurística.", nome)

    pid_raw = (settings.MS_DEFAULT_PERFIL_ID or "").strip()
    if pid_raw:
        try:
            pid = int(pid_raw)
        except ValueError:
            logger.warning("[MSDirSync] MS_DEFAULT_PERFIL_ID='%s' não é inteiro — ignorando.", pid_raw)
        else:
            if db.query(PerfilAcesso).filter(PerfilAcesso.id == pid).first():
                return pid
            logger.warning("[MSDirSync] MS_DEFAULT_PERFIL_ID=%s não existe — caindo p/ heurística.", pid)

    # Heurística: perfil ativo não-admin/não-sistema com menos permissões.
    perm_count = (
        db.query(
            PerfilPermissao.perfil_acesso_id.label("pid"),
            func.count(PerfilPermissao.id).label("n"),
        )
        .group_by(PerfilPermissao.perfil_acesso_id)
        .subquery()
    )
    row = (
        db.query(PerfilAcesso.id)
        .outerjoin(perm_count, perm_count.c.pid == PerfilAcesso.id)
        .filter(
            PerfilAcesso.ativo == True,  # noqa: E712
            PerfilAcesso.is_admin == False,  # noqa: E712
            PerfilAcesso.is_sistema == False,  # noqa: E712
        )
        .order_by(func.coalesce(perm_count.c.n, 0).asc(), PerfilAcesso.id.asc())
        .first()
    )
    if row:
        return row[0]

    logger.info("[MSDirSync] Nenhum perfil restritivo encontrado — conta SSO ficará sem perfil.")
    return None


def find_or_provision_user(db: Session, ms_oid: str, email: str, nome: str) -> Usuario:
    """Encontra ou cria/adota a conta para uma identidade Microsoft.

    Usado tanto pelo login SSO quanto pelo sync. NÃO faz commit — o chamador
    decide quando persistir (o login precisa do id antes de emitir o token).
    """
    email = (email or "").strip().lower()

    user = db.query(Usuario).filter(Usuario.ms_oid == ms_oid).first()
    if user:
        # Mantém nome/e-mail alinhados ao diretório.
        if email and user.email != email:
            user.email = email
        if nome and user.nome != nome:
            user.nome = nome
        user.ms_synced_at = datetime.utcnow()
        return user

    # Sem match por oid: tenta adotar conta local pré-existente pelo e-mail.
    if email:
        existing = db.query(Usuario).filter(func.lower(Usuario.email) == email).first()
        if existing:
            existing.ms_oid = ms_oid
            existing.auth_provider = "microsoft"
            # A conta passa a ser gerenciada pelo diretório: zera a senha local
            # para que não exista caminho de login que contorne a desprovisão.
            # EXCEÇÃO: contas break-glass preservam a senha (acesso de emergência).
            if not existing.permite_login_local:
                existing.senha_hash = None
            existing.ms_synced_at = datetime.utcnow()
            if nome and existing.nome != nome:
                existing.nome = nome
            return existing

    # Conta totalmente nova → provisiona com perfil mais restritivo.
    new_user = Usuario(
        email=email,
        nome=nome or email,
        senha_hash=None,
        ms_oid=ms_oid,
        auth_provider="microsoft",
        perfil_acesso_id=resolve_default_perfil_id(db),
        ativo=True,
        ms_synced_at=datetime.utcnow(),
    )
    db.add(new_user)
    return new_user


def _account_email(entry: dict) -> str:
    return (entry.get("mail") or entry.get("userPrincipalName") or "").strip().lower()


def sincronizar_diretorio_microsoft(db: Session) -> dict:
    """Reconcilia a tabela local com o diretório Microsoft.

    Retorna um resumo com contagens. Levanta MSAuthError se o diretório não
    puder ser lido (credenciais/permissão ausentes).
    """
    started = datetime.utcnow()
    directory = list_directory_users()

    default_perfil_id = resolve_default_perfil_id(db)
    seen_oids: set[str] = set()
    criados = 0
    adotados = 0
    reativados = 0
    desativados = 0
    atualizados = 0

    for entry in directory:
        oid = str(entry.get("id") or "").strip()
        if not oid:
            continue
        seen_oids.add(oid)
        email = _account_email(entry)
        nome = (entry.get("displayName") or email or "Usuário Microsoft").strip()
        enabled = bool(entry.get("accountEnabled", True))

        user = db.query(Usuario).filter(Usuario.ms_oid == oid).first()
        if user is None and email:
            user = db.query(Usuario).filter(func.lower(Usuario.email) == email).first()

        if user is None:
            # Conta nova: só criar se estiver habilitada no diretório.
            if not enabled:
                continue
            db.add(Usuario(
                email=email,
                nome=nome,
                senha_hash=None,
                ms_oid=oid,
                auth_provider="microsoft",
                perfil_acesso_id=default_perfil_id,
                ativo=True,
                ms_synced_at=started,
            ))
            criados += 1
            continue

        # Conta existente: vincular oid se ainda não vinculada (adoção).
        was_adopted = False
        if not user.ms_oid:
            user.ms_oid = oid
            user.auth_provider = "microsoft"
            # Break-glass preserva a senha de emergência; demais zeram.
            if not user.permite_login_local:
                user.senha_hash = None
            was_adopted = True
            adotados += 1

        changed = was_adopted
        if email and user.email != email:
            user.email = email
            changed = True
        if nome and user.nome != nome:
            user.nome = nome
            changed = True

        # Estado ativo segue o diretório.
        if enabled and not user.ativo:
            user.ativo = True
            reativados += 1
            changed = True
        elif not enabled and user.ativo and not user.permite_login_local:
            # Break-glass nunca é desativada pelo diretório (acesso de emergência).
            user.ativo = False
            desativados += 1
            changed = True
            invalidate_user_sessions(user.id, db)

        user.ms_synced_at = started
        if changed and not was_adopted:
            atualizados += 1

    # Contas SSO que sumiram do diretório → desativar.
    # Break-glass (permite_login_local) é excluída: nunca desativada pelo sync.
    orphan_sso = (
        db.query(Usuario)
        .filter(
            Usuario.auth_provider == "microsoft",
            Usuario.ms_oid.isnot(None),
            Usuario.ativo == True,  # noqa: E712
            Usuario.permite_login_local == False,  # noqa: E712
        )
        .all()
    )
    for user in orphan_sso:
        if user.ms_oid not in seen_oids:
            user.ativo = False
            desativados += 1
            invalidate_user_sessions(user.id, db)

    db.commit()

    resumo = {
        "total_diretorio": len(directory),
        "criados": criados,
        "adotados": adotados,
        "reativados": reativados,
        "desativados": desativados,
        "atualizados": atualizados,
        "duracao_ms": int((datetime.utcnow() - started).total_seconds() * 1000),
    }
    logger.info("[MSDirSync] Sync concluído: %s", resumo)
    return resumo
