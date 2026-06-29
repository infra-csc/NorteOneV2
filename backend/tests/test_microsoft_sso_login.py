"""Testes de regressão do fluxo principal de login: Microsoft SSO.

Contexto: a maioria dos usuários entra todos os dias pelo SSO Microsoft
(`/auth/microsoft/login` → callback → emissão do token da aplicação). Uma
regressão silenciosa nesse caminho tranca todo mundo para fora, então estes
testes travam três garantias do callback (`/auth/microsoft/callback`):

1. **Defesa login-CSRF (state double-submit):** o `state` devolvido pela
   Microsoft precisa bater com o cookie gravado no navegador que iniciou o
   login. State divergente/ausente é rejeitado SEM emitir token.
2. **Provisionamento restritivo:** um usuário novo do diretório (oid
   desconhecido) é criado com o perfil de acesso MAIS restritivo no primeiro
   login.
3. **Desprovisão respeitada:** uma conta SSO desativada/órfã (ativo=False) NÃO
   consegue obter token, mesmo passando por todo o fluxo de callback.

Seguem o padrão SQLite em memória de `test_break_glass_emergency_access.py`.
O callback faz chamadas de rede (troca de código por claims) — essas são
substituídas por monkeypatch; o restante (validação de state, find/provision,
emissão de sessão) roda de verdade contra o banco em memória.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Importa o pacote de models inteiro para registrar todos os mappers.
import app.models  # noqa: F401
from app.core.database import Base
from app.core.config import settings
from app.models.user import Usuario
from app.models.user_session import UserSession
from app.models.perfil_acesso import PerfilAcesso, PerfilPermissao

from app.api.routes import auth as auth_routes
from app.services import ms_auth_service


@pytest.fixture
def db():
    """Sessão SQLite em memória com as tabelas necessárias ao fluxo SSO."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Usuario.__table__,
            UserSession.__table__,
            PerfilAcesso.__table__,
            PerfilPermissao.__table__,
        ],
    )
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(autouse=True)
def _isolate_state_and_settings(monkeypatch):
    """Cada teste começa com o registro de states limpo e sem override de
    perfil padrão (força a heurística do perfil mais restritivo)."""
    ms_auth_service._pending_states.clear()
    monkeypatch.setattr(settings, "MS_DEFAULT_PERFIL_NOME", "", raising=False)
    monkeypatch.setattr(settings, "MS_DEFAULT_PERFIL_ID", "", raising=False)
    monkeypatch.setattr(settings, "MS_REDIRECT_URI", "", raising=False)
    yield
    ms_auth_service._pending_states.clear()


class _FakeRequest:
    """Stand-in mínimo para `fastapi.Request` no callback do SSO."""

    def __init__(self, cookies=None, base_url="http://testserver/"):
        self.cookies = cookies or {}
        self.base_url = base_url


def _location(resp) -> str:
    return resp.headers["location"]


def _claims(oid: str, email: str, nome: str = "Fulano de Tal") -> dict:
    """Claims já validados que `exchange_code_for_claims` retornaria."""
    return {"oid": oid, "email": email, "name": nome}


def _patch_exchange(monkeypatch, claims: dict):
    """Substitui a troca de código (rede) por claims fixos."""
    monkeypatch.setattr(
        ms_auth_service,
        "exchange_code_for_claims",
        lambda code, redirect_uri: claims,
    )


# ---------------------------------------------------------------------------
# (1) Defesa login-CSRF: state double-submit (cookie vs query)
# ---------------------------------------------------------------------------


def test_callback_rejects_divergent_state(db, monkeypatch):
    """State da query diverge do cookie → erro, nenhum token, troca de código
    nem é tentada."""
    called = {"exchange": False}

    def _boom(code, redirect_uri):
        called["exchange"] = True
        raise AssertionError("não deveria trocar o código com state inválido")

    monkeypatch.setattr(ms_auth_service, "exchange_code_for_claims", _boom)

    req = _FakeRequest(cookies={auth_routes._SSO_STATE_COOKIE: "cookie-AAA"})
    resp = auth_routes.microsoft_callback(
        req, code="qualquer", state="query-BBB", db=db
    )

    assert resp.status_code == 302
    loc = _location(resp)
    assert "sso_error" in loc
    assert "#token=" not in loc
    assert called["exchange"] is False
    assert db.query(UserSession).count() == 0


def test_callback_rejects_missing_state_entirely(db):
    """Sem cookie e sem query → rejeitado (defesa contra state ausente)."""
    req = _FakeRequest(cookies={})
    resp = auth_routes.microsoft_callback(req, code="qualquer", state="", db=db)

    loc = _location(resp)
    assert "sso_error" in loc
    assert "#token=" not in loc


def test_callback_rejects_query_state_without_cookie(db):
    """State na query mas sem cookie de origem → rejeitado (double-submit)."""
    req = _FakeRequest(cookies={})
    resp = auth_routes.microsoft_callback(
        req, code="qualquer", state="orfao", db=db
    )

    loc = _location(resp)
    assert "sso_error" in loc
    assert "#token=" not in loc


def test_callback_rejects_unissued_matching_state(db):
    """Cookie e query batem, mas o state nunca foi emitido pelo servidor →
    `consume_state` falha (uso único + expiração), nenhum token."""
    forjado = "state-forjado-que-bate-mas-nao-foi-emitido"
    req = _FakeRequest(cookies={auth_routes._SSO_STATE_COOKIE: forjado})
    resp = auth_routes.microsoft_callback(
        req, code="qualquer", state=forjado, db=db
    )

    loc = _location(resp)
    assert "sso_error" in loc
    assert "#token=" not in loc


# ---------------------------------------------------------------------------
# (2) Usuário novo do diretório → perfil mais restritivo no primeiro login
# ---------------------------------------------------------------------------


def _seed_perfis(db):
    """Cria perfis: admin (excluído), restrito (1 perm) e gestor (3 perms).
    A heurística deve escolher o restrito."""
    admin = PerfilAcesso(nome="Administrador", is_admin=True, is_sistema=True, ativo=True)
    restrito = PerfilAcesso(nome="Visualizador", is_admin=False, is_sistema=False, ativo=True)
    gestor = PerfilAcesso(nome="Gestor", is_admin=False, is_sistema=False, ativo=True)
    db.add_all([admin, restrito, gestor])
    db.commit()
    db.refresh(restrito)
    db.refresh(gestor)

    db.add(PerfilPermissao(perfil_acesso_id=restrito.id, modulo="dashboard", pode_visualizar=True))
    for modulo in ("dashboard", "marketing", "cadastros"):
        db.add(PerfilPermissao(perfil_acesso_id=gestor.id, modulo=modulo, pode_visualizar=True))
    db.commit()
    return restrito


def test_callback_provisions_new_user_with_most_restrictive_profile(db, monkeypatch):
    """Primeiro login de um oid desconhecido cria a conta SSO com o perfil mais
    restritivo e emite token + sessão."""
    restrito = _seed_perfis(db)

    state = ms_auth_service.issue_state()
    _patch_exchange(monkeypatch, _claims("oid-novo-123", "novato@empresa.com", "Novato"))

    req = _FakeRequest(cookies={auth_routes._SSO_STATE_COOKIE: state})
    resp = auth_routes.microsoft_callback(req, code="code-ok", state=state, db=db)

    loc = _location(resp)
    assert resp.status_code == 302
    assert "#token=" in loc
    assert "sso_error" not in loc

    user = db.query(Usuario).filter(Usuario.ms_oid == "oid-novo-123").first()
    assert user is not None
    assert user.email == "novato@empresa.com"
    assert user.auth_provider == "microsoft"
    assert user.senha_hash is None
    assert user.ativo is True
    # Perfil mais restritivo (menos permissões, não-admin, não-sistema).
    assert user.perfil_acesso_id == restrito.id
    # Sessão emitida para a conta recém-criada.
    assert db.query(UserSession).filter(UserSession.user_id == user.id).count() == 1


def test_callback_state_is_single_use(db, monkeypatch):
    """O mesmo state não pode ser reutilizado num segundo callback (replay)."""
    _seed_perfis(db)
    state = ms_auth_service.issue_state()
    _patch_exchange(monkeypatch, _claims("oid-replay", "replay@empresa.com"))

    req = _FakeRequest(cookies={auth_routes._SSO_STATE_COOKIE: state})
    first = auth_routes.microsoft_callback(req, code="c1", state=state, db=db)
    assert "#token=" in _location(first)

    # Replay com o mesmo state já consumido.
    second = auth_routes.microsoft_callback(req, code="c2", state=state, db=db)
    assert "sso_error" in _location(second)
    assert "#token=" not in _location(second)


# ---------------------------------------------------------------------------
# (3) Conta SSO desativada/órfã não obtém token
# ---------------------------------------------------------------------------


def test_callback_inactive_sso_account_gets_no_token(db, monkeypatch):
    """Conta SSO existente porém desativada (ativo=False) — caso da conta
    desprovisionada pelo sync — passa pelo callback mas NÃO recebe token."""
    user = Usuario(
        email="desativado@empresa.com",
        nome="Desativado",
        senha_hash=None,
        ms_oid="oid-desativado",
        auth_provider="microsoft",
        permite_login_local=False,
        ativo=False,
    )
    db.add(user)
    db.commit()

    state = ms_auth_service.issue_state()
    _patch_exchange(monkeypatch, _claims("oid-desativado", "desativado@empresa.com"))

    req = _FakeRequest(cookies={auth_routes._SSO_STATE_COOKIE: state})
    resp = auth_routes.microsoft_callback(req, code="code-ok", state=state, db=db)

    loc = _location(resp)
    assert "sso_error" in loc
    assert "#token=" not in loc
    # Continua inativa e sem nenhuma sessão emitida.
    db.refresh(user)
    assert user.ativo is False
    assert db.query(UserSession).filter(UserSession.user_id == user.id).count() == 0


def test_callback_orphan_account_reactivated_only_by_directory(db, monkeypatch):
    """Contraste de sanidade: uma conta ATIVA com oid conhecido (ainda no
    diretório) obtém token normalmente — garante que o gate de (3) é o flag
    `ativo`, não o caminho de callback em si."""
    user = Usuario(
        email="ativo@empresa.com",
        nome="Ativo",
        senha_hash=None,
        ms_oid="oid-ativo",
        auth_provider="microsoft",
        permite_login_local=False,
        ativo=True,
    )
    db.add(user)
    db.commit()

    state = ms_auth_service.issue_state()
    _patch_exchange(monkeypatch, _claims("oid-ativo", "ativo@empresa.com"))

    req = _FakeRequest(cookies={auth_routes._SSO_STATE_COOKIE: state})
    resp = auth_routes.microsoft_callback(req, code="code-ok", state=state, db=db)

    loc = _location(resp)
    assert "#token=" in loc
    assert "sso_error" not in loc
    assert db.query(UserSession).filter(UserSession.user_id == user.id).count() == 1
