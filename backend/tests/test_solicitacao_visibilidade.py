"""Visibilidade de solicitações de cortesia (task #248): um usuário comum só
pode ver (listar e baixar o arquivo anexado d)as solicitações que ele mesmo
criou — mesmo que um colega da MESMA área tenha aberto outras. Admins e quem
tem a permissão de aplicar código de cupom (pode_editar do módulo
cortesia_solicitacao — o mesmo grupo que trabalha a fila de cupons hoje)
continuam vendo tudo, independente de vínculo com a área.

Cobre:
- `list_solicitacoes`: usuário comum só recebe as próprias; admin e
  "gerador" (pode_editar, propositalmente SEM vínculo com a área) recebem
  todas.
- `baixar_arquivo`: mesma regra — 403 para usuário comum tentando baixar o
  anexo de outra pessoa, sucesso para o próprio dono, admin e "gerador".
- As consultas de saldo (`/eventos`, `/saldo`) e a fila de geração
  permanecem fora do escopo desta mudança — não testadas aqui de propósito.

Cada teste recebe seu próprio engine SQLite in-memory (fixture
function-scoped) em vez de compartilhar um único engine/sessão entre todos os
testes do módulo — evita qualquer janela de estado compartilhado entre
testes quando o arquivo roda junto com o resto da suíte (StaticPool +
threads reais de outros arquivos de teste no mesmo processo)."""

import os
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import patch
from fastapi import HTTPException

import app.models  # noqa: F401 — registra todos os mappers
from app.core.database import Base
from app.models.cortesia_solicitacao import CortesiaSolicitacao, CortesiaCupomCodigo, TIPO_CUPOM, STATUS_SOLICITADO
from app.models.projecao import AreaProjecao, AreaProjecaoUsuario
from app.models.cadastro_evento import CadastroEvento
from app.models.user import Usuario
from app.models.perfil_acesso import PerfilAcesso, PerfilPermissao
from app.api.routes.cortesia_solicitacao import list_solicitacoes, baixar_arquivo


@pytest.fixture
def SessionFactory():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng, tables=[
        Usuario.__table__,
        PerfilAcesso.__table__,
        PerfilPermissao.__table__,
        AreaProjecao.__table__,
        AreaProjecaoUsuario.__table__,
        CadastroEvento.__table__,
        CortesiaSolicitacao.__table__,
        CortesiaCupomCodigo.__table__,
    ])
    factory = sessionmaker(bind=eng, autocommit=False, autoflush=False)
    yield factory
    eng.dispose()


@pytest.fixture
def seed(SessionFactory):
    db = SessionFactory()
    try:
        perfil_admin = PerfilAcesso(id=101, nome="Admin", is_admin=True, ativo=True)
        perfil_gerador = PerfilAcesso(id=102, nome="Gerador de Cupom", is_admin=False, ativo=True)
        perfil_comum = PerfilAcesso(id=103, nome="Responsável de Área", is_admin=False, ativo=True)
        db.add_all([perfil_admin, perfil_gerador, perfil_comum])
        db.flush()

        # "Gerador": pode_editar no módulo — o grupo que hoje trabalha a fila
        # de cupons e deve enxergar tudo, mesmo sem vínculo com nenhuma área.
        db.add(PerfilPermissao(
            perfil_acesso_id=perfil_gerador.id, modulo="cortesia_solicitacao",
            pode_visualizar=True, pode_criar=False, pode_editar=True, pode_deletar=False,
        ))
        # "Comum": só visualizar/criar — sem pode_editar, sujeito à regra nova.
        db.add(PerfilPermissao(
            perfil_acesso_id=perfil_comum.id, modulo="cortesia_solicitacao",
            pode_visualizar=True, pode_criar=True, pode_editar=False, pode_deletar=False,
        ))
        db.flush()

        admin_user = Usuario(id=9101, nome="Admin User", email="admin@test.local", auth_provider="local", ativo=True, perfil_acesso_id=perfil_admin.id)
        gerador_user = Usuario(id=9102, nome="Gerador User", email="gerador@test.local", auth_provider="local", ativo=True, perfil_acesso_id=perfil_gerador.id)
        user1 = Usuario(id=9103, nome="Usuário Um", email="u1@test.local", auth_provider="local", ativo=True, perfil_acesso_id=perfil_comum.id)
        user2 = Usuario(id=9104, nome="Usuário Dois", email="u2@test.local", auth_provider="local", ativo=True, perfil_acesso_id=perfil_comum.id)
        db.add_all([admin_user, gerador_user, user1, user2])
        db.flush()

        area = AreaProjecao(id=9201, nome="Área Compartilhada", sigla="AC", ativo=True)
        db.add(area)
        db.flush()

        # user1 e user2 são colegas da MESMA área — gerador_user propositalmente
        # NÃO tem vínculo com nenhuma área (prova que a visão ampla dele vem da
        # permissão, não de um vínculo de área que não existe).
        db.add_all([
            AreaProjecaoUsuario(area_projecao_id=area.id, usuario_id=user1.id),
            AreaProjecaoUsuario(area_projecao_id=area.id, usuario_id=user2.id),
        ])

        evento = CadastroEvento(id=9301, nome="Evento Compartilhado", sku="EVCOMP")
        db.add(evento)
        db.flush()

        sol_user1 = CortesiaSolicitacao(
            id=9401, evento_id=evento.id, area_projecao_id=area.id,
            tipo=TIPO_CUPOM, quantidade=3, status=STATUS_SOLICITADO,
            solicitado_por=user1.id, caminho_arquivo="sol1.txt", nome_arquivo="sol1.txt",
        )
        sol_user2 = CortesiaSolicitacao(
            id=9402, evento_id=evento.id, area_projecao_id=area.id,
            tipo=TIPO_CUPOM, quantidade=4, status=STATUS_SOLICITADO,
            solicitado_por=user2.id, caminho_arquivo="sol2.txt", nome_arquivo="sol2.txt",
        )
        db.add_all([sol_user1, sol_user2])
        db.commit()
    finally:
        db.close()

    return {
        "admin_id": 9101, "gerador_id": 9102, "user1_id": 9103, "user2_id": 9104,
        "sol_user1_id": 9401, "sol_user2_id": 9402,
    }


def _load(db, user_id):
    return db.query(Usuario).filter(Usuario.id == user_id).first()


# ---------------------------------------------------------------------------
# list_solicitacoes
# ---------------------------------------------------------------------------

def test_regular_user_sees_only_own_requests(SessionFactory, seed):
    db = SessionFactory()
    try:
        user1 = _load(db, seed["user1_id"])
        rows = list_solicitacoes(evento_id=None, area_projecao_id=None, db=db, current_user=user1)
        assert {r.id for r in rows} == {seed["sol_user1_id"]}

        user2 = _load(db, seed["user2_id"])
        rows = list_solicitacoes(evento_id=None, area_projecao_id=None, db=db, current_user=user2)
        assert {r.id for r in rows} == {seed["sol_user2_id"]}
    finally:
        db.close()


def test_admin_sees_all_requests(SessionFactory, seed):
    db = SessionFactory()
    try:
        admin = _load(db, seed["admin_id"])
        rows = list_solicitacoes(evento_id=None, area_projecao_id=None, db=db, current_user=admin)
        assert {r.id for r in rows} == {seed["sol_user1_id"], seed["sol_user2_id"]}
    finally:
        db.close()


def test_gerador_permission_sees_all_even_without_area_link(SessionFactory, seed):
    """gerador_user não tem NENHUM vínculo de área — se a visão ampla dele
    dependesse de área (bug antigo), ele veria uma lista vazia. Ver tudo aqui
    prova que a regra nova é por permissão, não por área."""
    db = SessionFactory()
    try:
        gerador = _load(db, seed["gerador_id"])
        rows = list_solicitacoes(evento_id=None, area_projecao_id=None, db=db, current_user=gerador)
        assert {r.id for r in rows} == {seed["sol_user1_id"], seed["sol_user2_id"]}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# baixar_arquivo
# ---------------------------------------------------------------------------

def test_regular_user_cannot_download_others_file(SessionFactory, seed):
    with tempfile.TemporaryDirectory() as tmpdir:
        open(os.path.join(tmpdir, "sol1.txt"), "w").close()
        open(os.path.join(tmpdir, "sol2.txt"), "w").close()
        with patch("app.api.routes.cortesia_solicitacao._UPLOAD_DIR", tmpdir):
            db = SessionFactory()
            try:
                user2 = _load(db, seed["user2_id"])
                with pytest.raises(HTTPException) as exc_info:
                    baixar_arquivo(solicitacao_id=seed["sol_user1_id"], db=db, current_user=user2)
                assert exc_info.value.status_code == 403
            finally:
                db.close()


def test_regular_user_can_download_own_file(SessionFactory, seed):
    with tempfile.TemporaryDirectory() as tmpdir:
        open(os.path.join(tmpdir, "sol1.txt"), "w").close()
        with patch("app.api.routes.cortesia_solicitacao._UPLOAD_DIR", tmpdir):
            db = SessionFactory()
            try:
                user1 = _load(db, seed["user1_id"])
                response = baixar_arquivo(solicitacao_id=seed["sol_user1_id"], db=db, current_user=user1)
                assert response.path == os.path.join(tmpdir, "sol1.txt")
            finally:
                db.close()


def test_admin_and_gerador_can_download_any_file(SessionFactory, seed):
    with tempfile.TemporaryDirectory() as tmpdir:
        open(os.path.join(tmpdir, "sol1.txt"), "w").close()
        open(os.path.join(tmpdir, "sol2.txt"), "w").close()
        with patch("app.api.routes.cortesia_solicitacao._UPLOAD_DIR", tmpdir):
            db = SessionFactory()
            try:
                admin = _load(db, seed["admin_id"])
                gerador = _load(db, seed["gerador_id"])
                # Admin baixa o anexo de user1; gerador (sem vínculo de área)
                # baixa o anexo de user2 — ambos fora do próprio "criei eu".
                r1 = baixar_arquivo(solicitacao_id=seed["sol_user1_id"], db=db, current_user=admin)
                r2 = baixar_arquivo(solicitacao_id=seed["sol_user2_id"], db=db, current_user=gerador)
                assert r1.path == os.path.join(tmpdir, "sol1.txt")
                assert r2.path == os.path.join(tmpdir, "sol2.txt")
            finally:
                db.close()
