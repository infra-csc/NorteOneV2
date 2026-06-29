"""Testes de regressão do acesso de emergência (break-glass).

Contexto: contas de contingência podem ser marcadas com
``permite_login_local=True``. Mesmo sendo gerenciadas pelo diretório Microsoft
(``auth_provider='microsoft'``), elas devem:

1. Continuar autenticando por SENHA local (acesso de emergência).
2. NUNCA ter a senha apagada pela adoção/sincronização do diretório.
3. NUNCA ser desativadas pela sincronização — nem quando o diretório reporta a
   conta como desabilitada (``accountEnabled=false``), nem quando a conta some
   do diretório.

Uma regressão já quebrou (3) e (2) no passado: a adoção zerava a senha e o sync
desativava a conta, derrubando o acesso de emergência numa hora crítica. Estes
testes travam o comportamento correto. Cada teste inclui um contraste com uma
conta NÃO break-glass para garantir que a desprovisão normal continua valendo —
ou seja, que o teste falharia se a exceção break-glass fosse aplicada larga
demais.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Importa o pacote de models inteiro para registrar todos os mappers
# (relationships do Usuario apontam para PerfilAcesso/DimCentroCusto).
import app.models  # noqa: F401
from app.core.database import Base
from app.core.security import get_password_hash
from app.models.user import Usuario
from app.models.user_session import UserSession

from app.api.routes import auth as auth_routes
from app.services import ms_directory_sync


EMERGENCY_PASSWORD = "Quebra-Vidro-2026!"


@pytest.fixture
def db():
    """Sessão SQLite em memória com apenas as tabelas necessárias.

    Usa StaticPool para que todas as conexões compartilhem o mesmo banco em
    memória dentro do teste.
    """
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[Usuario.__table__, UserSession.__table__],
    )
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


class _Form:
    """Stand-in mínimo para OAuth2PasswordRequestForm."""

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password


def _seed_session(db, user: Usuario, *, n: int = 1) -> None:
    """Cria ``n`` sessões ativas (linhas de user_sessions) para o usuário."""
    for i in range(n):
        db.add(
            UserSession(
                user_id=user.id,
                jti=f"jti-{user.id}-{i}",
                expires_at=datetime.utcnow() + timedelta(hours=8),
            )
        )
    db.commit()


def _session_count(db, user_id: int) -> int:
    return db.query(UserSession).filter(UserSession.user_id == user_id).count()


def _make_break_glass_user(db, *, ativo: bool = True, ms_oid: str = "oid-bg") -> Usuario:
    """Conta de emergência típica: gerenciada pelo Microsoft, mas com senha
    local e o flag break-glass ligado."""
    user = Usuario(
        email="emergencia@empresa.com",
        nome="Admin Emergência",
        senha_hash=get_password_hash(EMERGENCY_PASSWORD),
        ms_oid=ms_oid,
        auth_provider="microsoft",
        permite_login_local=True,
        ativo=ativo,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# (1) Login por senha permitido para a conta break-glass
# ---------------------------------------------------------------------------


def test_break_glass_password_login_allowed(db):
    """microsoft + permite_login_local=True + senha + ativa → login por senha OK."""
    _make_break_glass_user(db)

    result = auth_routes.login(_Form("emergencia@empresa.com", EMERGENCY_PASSWORD), db)

    assert result["token_type"] == "bearer"
    assert result["access_token"]


def test_managed_microsoft_account_password_login_blocked(db):
    """Contraste: a MESMA conta sem o flag break-glass NÃO pode logar por senha,
    mesmo com senha_hash residual. (Garante que a exceção é só para break-glass.)"""
    user = _make_break_glass_user(db)
    user.permite_login_local = False
    db.commit()

    with pytest.raises(Exception) as exc:
        auth_routes.login(_Form("emergencia@empresa.com", EMERGENCY_PASSWORD), db)
    # 401 com a mensagem de "use Microsoft".
    assert getattr(exc.value, "status_code", None) == 401


def test_break_glass_inactive_cannot_login(db):
    """Mesmo break-glass, se a conta estiver inativa, o login é negado."""
    _make_break_glass_user(db, ativo=False)

    with pytest.raises(Exception) as exc:
        auth_routes.login(_Form("emergencia@empresa.com", EMERGENCY_PASSWORD), db)
    assert getattr(exc.value, "status_code", None) == 401


# ---------------------------------------------------------------------------
# (2) Adoção / sincronização NÃO apaga a senha break-glass
# ---------------------------------------------------------------------------


def test_find_or_provision_preserves_break_glass_password(db):
    """Adoção via login SSO (find_or_provision_user): conta local pré-existente
    com break-glass mantém a senha ao ser vinculada ao oid do diretório."""
    user = Usuario(
        email="emergencia@empresa.com",
        nome="Admin Emergência",
        senha_hash=get_password_hash(EMERGENCY_PASSWORD),
        ms_oid=None,
        auth_provider="local",
        permite_login_local=True,
        ativo=True,
    )
    db.add(user)
    db.commit()

    adopted = ms_directory_sync.find_or_provision_user(
        db, ms_oid="oid-novo", email="emergencia@empresa.com", nome="Admin Emergência"
    )
    db.commit()

    assert adopted.ms_oid == "oid-novo"
    assert adopted.auth_provider == "microsoft"
    # A senha de emergência DEVE sobreviver à adoção.
    assert adopted.senha_hash is not None


def test_find_or_provision_zeroes_password_for_non_break_glass(db):
    """Contraste: conta local SEM break-glass tem a senha zerada na adoção."""
    user = Usuario(
        email="comum@empresa.com",
        nome="Usuário Comum",
        senha_hash=get_password_hash("qualquer-senha-123"),
        ms_oid=None,
        auth_provider="local",
        permite_login_local=False,
        ativo=True,
    )
    db.add(user)
    db.commit()

    adopted = ms_directory_sync.find_or_provision_user(
        db, ms_oid="oid-comum", email="comum@empresa.com", nome="Usuário Comum"
    )
    db.commit()

    assert adopted.auth_provider == "microsoft"
    assert adopted.senha_hash is None


def test_sync_adoption_preserves_break_glass_password(db, monkeypatch):
    """Sincronização noturna: ao adotar uma conta local break-glass (match por
    e-mail, sem oid prévio), a senha de emergência é preservada."""
    user = Usuario(
        email="emergencia@empresa.com",
        nome="Admin Emergência",
        senha_hash=get_password_hash(EMERGENCY_PASSWORD),
        ms_oid=None,
        auth_provider="local",
        permite_login_local=True,
        ativo=True,
    )
    db.add(user)
    db.commit()

    monkeypatch.setattr(ms_directory_sync, "resolve_default_perfil_id", lambda _db: None)
    monkeypatch.setattr(
        ms_directory_sync,
        "list_directory_users",
        lambda: [
            {
                "id": "oid-dir",
                "mail": "emergencia@empresa.com",
                "displayName": "Admin Emergência",
                "accountEnabled": True,
            }
        ],
    )

    ms_directory_sync.sincronizar_diretorio_microsoft(db)
    db.refresh(user)

    assert user.ms_oid == "oid-dir"
    assert user.auth_provider == "microsoft"
    assert user.senha_hash is not None
    assert user.ativo is True


# ---------------------------------------------------------------------------
# (3) Sincronização NUNCA desativa a conta break-glass
# ---------------------------------------------------------------------------


def test_sync_does_not_deactivate_break_glass_disabled_in_directory(db, monkeypatch):
    """Cenário 'desabilitada no diretório': o diretório reporta
    accountEnabled=false, mas a conta break-glass permanece ativa e com senha."""
    user = _make_break_glass_user(db, ms_oid="oid-bg")

    monkeypatch.setattr(ms_directory_sync, "resolve_default_perfil_id", lambda _db: None)
    monkeypatch.setattr(
        ms_directory_sync,
        "list_directory_users",
        lambda: [
            {
                "id": "oid-bg",
                "mail": "emergencia@empresa.com",
                "displayName": "Admin Emergência",
                "accountEnabled": False,
            }
        ],
    )

    resumo = ms_directory_sync.sincronizar_diretorio_microsoft(db)
    db.refresh(user)

    assert user.ativo is True
    assert user.senha_hash is not None
    assert resumo["desativados"] == 0


def test_sync_deactivates_non_break_glass_disabled_in_directory(db, monkeypatch):
    """Contraste: conta gerenciada SEM break-glass É desativada quando o
    diretório a reporta como desabilitada."""
    user = Usuario(
        email="comum@empresa.com",
        nome="Usuário Comum",
        senha_hash=None,
        ms_oid="oid-comum",
        auth_provider="microsoft",
        permite_login_local=False,
        ativo=True,
    )
    db.add(user)
    db.commit()

    monkeypatch.setattr(ms_directory_sync, "resolve_default_perfil_id", lambda _db: None)
    monkeypatch.setattr(
        ms_directory_sync,
        "list_directory_users",
        lambda: [
            {
                "id": "oid-comum",
                "mail": "comum@empresa.com",
                "displayName": "Usuário Comum",
                "accountEnabled": False,
            }
        ],
    )

    resumo = ms_directory_sync.sincronizar_diretorio_microsoft(db)
    db.refresh(user)

    assert user.ativo is False
    assert resumo["desativados"] == 1


def test_sync_does_not_deactivate_break_glass_missing_from_directory(db, monkeypatch):
    """Cenário 'sumiu do diretório': a conta break-glass (já adotada, oid
    vinculado) não aparece na listagem do diretório e mesmo assim permanece
    ativa — a query de órfãos exclui break-glass."""
    user = _make_break_glass_user(db, ms_oid="oid-some")

    monkeypatch.setattr(ms_directory_sync, "resolve_default_perfil_id", lambda _db: None)
    # Diretório vazio → a conta é "órfã".
    monkeypatch.setattr(ms_directory_sync, "list_directory_users", lambda: [])

    resumo = ms_directory_sync.sincronizar_diretorio_microsoft(db)
    db.refresh(user)

    assert user.ativo is True
    assert user.senha_hash is not None
    assert resumo["desativados"] == 0


def test_sync_deactivates_non_break_glass_missing_from_directory(db, monkeypatch):
    """Contraste: conta SSO comum que some do diretório É desativada (órfã)."""
    user = Usuario(
        email="comum@empresa.com",
        nome="Usuário Comum",
        senha_hash=None,
        ms_oid="oid-orfao",
        auth_provider="microsoft",
        permite_login_local=False,
        ativo=True,
    )
    db.add(user)
    db.commit()

    monkeypatch.setattr(ms_directory_sync, "resolve_default_perfil_id", lambda _db: None)
    monkeypatch.setattr(ms_directory_sync, "list_directory_users", lambda: [])

    resumo = ms_directory_sync.sincronizar_diretorio_microsoft(db)
    db.refresh(user)

    assert user.ativo is False
    assert resumo["desativados"] == 1


# ---------------------------------------------------------------------------
# (4) Desativação derruba as sessões ativas na hora (desprovisão crítica)
# ---------------------------------------------------------------------------


def test_sync_invalidates_sessions_when_account_disabled_in_directory(db, monkeypatch):
    """Conta SSO comum reportada accountEnabled=false pelo diretório: além de
    desativada, TODAS as suas linhas de user_sessions são removidas (o ex-
    funcionário não continua com sessão válida até o token expirar)."""
    user = Usuario(
        email="comum@empresa.com",
        nome="Usuário Comum",
        senha_hash=None,
        ms_oid="oid-comum",
        auth_provider="microsoft",
        permite_login_local=False,
        ativo=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _seed_session(db, user, n=3)
    assert _session_count(db, user.id) == 3

    monkeypatch.setattr(ms_directory_sync, "resolve_default_perfil_id", lambda _db: None)
    monkeypatch.setattr(
        ms_directory_sync,
        "list_directory_users",
        lambda: [
            {
                "id": "oid-comum",
                "mail": "comum@empresa.com",
                "displayName": "Usuário Comum",
                "accountEnabled": False,
            }
        ],
    )

    resumo = ms_directory_sync.sincronizar_diretorio_microsoft(db)
    db.refresh(user)

    assert user.ativo is False
    assert resumo["desativados"] == 1
    # Sessões derrubadas na hora.
    assert _session_count(db, user.id) == 0


def test_sync_invalidates_sessions_when_account_missing_from_directory(db, monkeypatch):
    """Conta SSO comum que some do diretório (órfã): é desativada E tem as
    sessões removidas no mesmo passo."""
    user = Usuario(
        email="comum@empresa.com",
        nome="Usuário Comum",
        senha_hash=None,
        ms_oid="oid-orfao",
        auth_provider="microsoft",
        permite_login_local=False,
        ativo=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _seed_session(db, user, n=2)
    assert _session_count(db, user.id) == 2

    monkeypatch.setattr(ms_directory_sync, "resolve_default_perfil_id", lambda _db: None)
    monkeypatch.setattr(ms_directory_sync, "list_directory_users", lambda: [])

    resumo = ms_directory_sync.sincronizar_diretorio_microsoft(db)
    db.refresh(user)

    assert user.ativo is False
    assert resumo["desativados"] == 1
    assert _session_count(db, user.id) == 0


def test_sync_keeps_break_glass_sessions_when_disabled_in_directory(db, monkeypatch):
    """Contraste: conta break-glass reportada como desabilitada no diretório
    permanece ativa E mantém suas sessões — não sofre desprovisão."""
    user = _make_break_glass_user(db, ms_oid="oid-bg")
    _seed_session(db, user, n=2)
    assert _session_count(db, user.id) == 2

    monkeypatch.setattr(ms_directory_sync, "resolve_default_perfil_id", lambda _db: None)
    monkeypatch.setattr(
        ms_directory_sync,
        "list_directory_users",
        lambda: [
            {
                "id": "oid-bg",
                "mail": "emergencia@empresa.com",
                "displayName": "Admin Emergência",
                "accountEnabled": False,
            }
        ],
    )

    resumo = ms_directory_sync.sincronizar_diretorio_microsoft(db)
    db.refresh(user)

    assert user.ativo is True
    assert resumo["desativados"] == 0
    # Sessões de emergência preservadas.
    assert _session_count(db, user.id) == 2


def test_sync_keeps_break_glass_sessions_when_missing_from_directory(db, monkeypatch):
    """Contraste: conta break-glass que some do diretório mantém ativa e
    sessões (a query de órfãos exclui break-glass)."""
    user = _make_break_glass_user(db, ms_oid="oid-some")
    _seed_session(db, user, n=2)
    assert _session_count(db, user.id) == 2

    monkeypatch.setattr(ms_directory_sync, "resolve_default_perfil_id", lambda _db: None)
    monkeypatch.setattr(ms_directory_sync, "list_directory_users", lambda: [])

    resumo = ms_directory_sync.sincronizar_diretorio_microsoft(db)
    db.refresh(user)

    assert user.ativo is True
    assert resumo["desativados"] == 0
    assert _session_count(db, user.id) == 2
