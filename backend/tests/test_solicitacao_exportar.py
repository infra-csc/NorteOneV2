"""Exportação CSV da aba Acompanhamento (task #249): o relatório precisa
refletir exatamente os mesmos filtros da tela (busca, área, evento, tipo,
status) e a MESMA regra de visibilidade da task #248 — um usuário comum
nunca pode extrair, via nenhuma combinação de filtros, solicitação de outra
pessoa. Admins e quem tem a permissão de aplicar código de cupom (pode_editar
do módulo cortesia_solicitacao) exportam o conjunto completo.

Cada teste recebe seu próprio engine SQLite in-memory (fixture
function-scoped), mesmo padrão de test_solicitacao_visibilidade.py."""

import asyncio
import csv
import io

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — registra todos os mappers
from app.core.database import Base
from app.models.cortesia_solicitacao import (
    CortesiaSolicitacao,
    CortesiaCupomCodigo,
    TIPO_CUPOM,
    TIPO_PLANILHA,
    STATUS_SOLICITADO,
    STATUS_GERADO,
)
from app.models.projecao import AreaProjecao, AreaProjecaoUsuario
from app.models.cadastro_evento import CadastroEvento
from app.models.user import Usuario
from app.models.perfil_acesso import PerfilAcesso, PerfilPermissao
from app.api.routes.cortesia_solicitacao import exportar_acompanhamento


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
        perfil_admin = PerfilAcesso(id=201, nome="Admin", is_admin=True, ativo=True)
        perfil_comum = PerfilAcesso(id=202, nome="Responsável de Área", is_admin=False, ativo=True)
        db.add_all([perfil_admin, perfil_comum])
        db.flush()

        db.add(PerfilPermissao(
            perfil_acesso_id=perfil_comum.id, modulo="cortesia_solicitacao",
            pode_visualizar=True, pode_criar=True, pode_editar=False, pode_deletar=False,
        ))
        db.flush()

        admin_user = Usuario(id=9501, nome="Admin User", email="admin-exp@test.local", auth_provider="local", ativo=True, perfil_acesso_id=perfil_admin.id)
        user1 = Usuario(id=9502, nome="Usuário Um", email="u1-exp@test.local", auth_provider="local", ativo=True, perfil_acesso_id=perfil_comum.id)
        user2 = Usuario(id=9503, nome="Usuário Dois", email="u2-exp@test.local", auth_provider="local", ativo=True, perfil_acesso_id=perfil_comum.id)
        db.add_all([admin_user, user1, user2])
        db.flush()

        area = AreaProjecao(id=9601, nome="Área Compartilhada", sigla="AC", ativo=True)
        db.add(area)
        db.flush()
        db.add_all([
            AreaProjecaoUsuario(area_projecao_id=area.id, usuario_id=user1.id),
            AreaProjecaoUsuario(area_projecao_id=area.id, usuario_id=user2.id),
        ])

        evento1 = CadastroEvento(id=9701, nome="Evento Um", sku="EVUM")
        evento2 = CadastroEvento(id=9702, nome="Evento Dois", sku="EVDOIS")
        db.add_all([evento1, evento2])
        db.flush()

        # user1: 3 solicitações cobrindo os 3 status kanban (aguardando /
        # gerado / recebida) espalhadas em 2 eventos, uma com observação
        # específica para o teste de busca.
        sol1_aguardando = CortesiaSolicitacao(
            id=9801, evento_id=evento1.id, area_projecao_id=area.id,
            tipo=TIPO_CUPOM, quantidade=2, status=STATUS_SOLICITADO,
            solicitado_por=user1.id,
        )
        sol1_gerado = CortesiaSolicitacao(
            id=9802, evento_id=evento1.id, area_projecao_id=area.id,
            tipo=TIPO_CUPOM, quantidade=5, status=STATUS_GERADO,
            solicitado_por=user1.id, observacao="Observação especial do pedido",
        )
        sol1_planilha = CortesiaSolicitacao(
            id=9803, evento_id=evento2.id, area_projecao_id=area.id,
            tipo=TIPO_PLANILHA, quantidade=10, status=STATUS_SOLICITADO,
            solicitado_por=user1.id, nome_arquivo="lista.xlsx",
        )
        # user2: mesma área/evento de sol1_aguardando — prova que filtrar por
        # área/evento não basta pra vazar a linha do colega.
        sol2_aguardando = CortesiaSolicitacao(
            id=9804, evento_id=evento1.id, area_projecao_id=area.id,
            tipo=TIPO_CUPOM, quantidade=1, status=STATUS_SOLICITADO,
            solicitado_por=user2.id,
        )
        db.add_all([sol1_aguardando, sol1_gerado, sol1_planilha, sol2_aguardando])
        db.flush()

        db.add(CortesiaCupomCodigo(solicitacao_id=sol1_gerado.id, codigo="ABC123", usado=False))
        db.commit()
    finally:
        db.close()

    # IDs literais (setados explicitamente acima) em vez de reler .id dos
    # objetos ORM: a sessão já fechou e expire_on_commit=True (default do
    # sessionmaker) expira os atributos no commit — reler exigiria a sessão
    # ainda aberta.
    return {
        "admin_id": 9501, "user1_id": 9502, "user2_id": 9503,
        "evento1_id": 9701, "evento2_id": 9702, "area_id": 9601,
        "sol1_aguardando_id": 9801, "sol1_gerado_id": 9802,
        "sol1_planilha_id": 9803, "sol2_aguardando_id": 9804,
    }


def _load(db, user_id):
    return db.query(Usuario).filter(Usuario.id == user_id).first()


def _csv_rows(response) -> list[dict]:
    """Drena o StreamingResponse (mesmo padrão de
    test_cupom_importacao.py::test_modelo_download_...) e devolve as linhas
    de dados como dicts (cabeçalho -> valor)."""
    async def _drain():
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        return b"".join(chunks)

    conteudo = asyncio.run(_drain()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(conteudo), delimiter=';')
    return list(reader)


# ---------------------------------------------------------------------------
# Visibilidade (mesma regra da task #248)
# ---------------------------------------------------------------------------

def test_regular_user_export_contains_only_own_rows(SessionFactory, seed):
    db = SessionFactory()
    try:
        user1 = _load(db, seed["user1_id"])
        response = exportar_acompanhamento(
            evento_id=None, area_projecao_id=None, tipo=None, status=None, busca=None,
            db=db, current_user=user1,
        )
        rows = _csv_rows(response)
        assert len(rows) == 3
        assert {r["Evento"] for r in rows} == {"Evento Um", "Evento Dois"}
        for r in rows:
            assert r["Solicitante"] == "Usuário Um"
    finally:
        db.close()


def test_regular_user_cannot_widen_export_via_filters(SessionFactory, seed):
    """user2 usa os mesmos evento/área que user1 — se o filtro por área/
    evento fosse aplicado ANTES da regra de visibilidade (ou a substituísse),
    a linha de user1 vazaria aqui."""
    db = SessionFactory()
    try:
        user2 = _load(db, seed["user2_id"])
        response = exportar_acompanhamento(
            evento_id=seed["evento1_id"], area_projecao_id=seed["area_id"], tipo=None, status=None, busca=None,
            db=db, current_user=user2,
        )
        rows = _csv_rows(response)
        assert len(rows) == 1
        assert rows[0]["Solicitante"] == "Usuário Dois"
    finally:
        db.close()


def test_admin_export_contains_all_rows(SessionFactory, seed):
    db = SessionFactory()
    try:
        admin = _load(db, seed["admin_id"])
        response = exportar_acompanhamento(
            evento_id=None, area_projecao_id=None, tipo=None, status=None, busca=None,
            db=db, current_user=admin,
        )
        rows = _csv_rows(response)
        assert len(rows) == 4
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Filtros (mesma semântica de aplicarFiltro()/colunaDe()/buscaCasa() no
# frontend)
# ---------------------------------------------------------------------------

def test_filter_by_evento_id(SessionFactory, seed):
    db = SessionFactory()
    try:
        admin = _load(db, seed["admin_id"])
        response = exportar_acompanhamento(
            evento_id=seed["evento2_id"], area_projecao_id=None, tipo=None, status=None, busca=None,
            db=db, current_user=admin,
        )
        rows = _csv_rows(response)
        assert len(rows) == 1
        assert rows[0]["Evento"] == "Evento Dois"
    finally:
        db.close()


def test_filter_by_tipo_planilha(SessionFactory, seed):
    db = SessionFactory()
    try:
        admin = _load(db, seed["admin_id"])
        response = exportar_acompanhamento(
            evento_id=None, area_projecao_id=None, tipo="planilha", status=None, busca=None,
            db=db, current_user=admin,
        )
        rows = _csv_rows(response)
        assert len(rows) == 1
        assert rows[0]["Tipo"] == "Planilha"
    finally:
        db.close()


def test_filter_by_status_kanban_gerado_and_recebida(SessionFactory, seed):
    """status recebe a coluna kanban derivada (aguardando/gerado/recebida),
    não o campo status bruto — cobre os dois casos onde eles divergem."""
    db = SessionFactory()
    try:
        admin = _load(db, seed["admin_id"])

        gerado = _csv_rows(exportar_acompanhamento(
            evento_id=None, area_projecao_id=None, tipo=None, status="gerado", busca=None,
            db=db, current_user=admin,
        ))
        assert len(gerado) == 1
        assert gerado[0]["Status"] == "Aplicado"
        assert gerado[0]["Código(s)"] == "ABC123"

        recebida = _csv_rows(exportar_acompanhamento(
            evento_id=None, area_projecao_id=None, tipo=None, status="recebida", busca=None,
            db=db, current_user=admin,
        ))
        assert len(recebida) == 1
        assert recebida[0]["Status"] == "Recebida"
        # tipo=planilha sempre cai em 'recebida' mesmo com status bruto
        # 'solicitado' — prova que a coluna usada é a derivada, não a bruta.
        assert recebida[0]["Tipo"] == "Planilha"
    finally:
        db.close()


def test_filter_by_busca_matches_observacao(SessionFactory, seed):
    db = SessionFactory()
    try:
        admin = _load(db, seed["admin_id"])
        response = exportar_acompanhamento(
            evento_id=None, area_projecao_id=None, tipo=None, status=None, busca="especial",
            db=db, current_user=admin,
        )
        rows = _csv_rows(response)
        assert len(rows) == 1
        assert rows[0]["Status"] == "Aplicado"
    finally:
        db.close()
