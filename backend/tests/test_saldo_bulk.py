"""Tests for `_calcular_saldos_bulk`: the batched (GROUP BY) saldo
computation used by the read endpoints (`/eventos`, `/saldo`), which must
return exactly the same numbers as the point-to-point `_calcular_saldo` used
by the write-time quota check — just without one round trip per
evento×área combination.

Covers:
- Parity with `_calcular_saldo` across a grid of eventos x áreas, including
  combinations with only projetado, only solicitado, both, or neither.
- Multiple rows per combination are summed correctly (not just the first row).
- Soft-deleted rows (deleted_at set) are excluded from the sums.
- Combinations absent from the returned dict default to (0, 0, 0), matching
  the COALESCE(SUM(...), 0) behaviour of the point-to-point version.
- Empty evento_ids/area_ids short-circuits to `{}` without querying.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime

import app.models  # noqa: F401 — register all mappers
from app.core.database import Base
from app.models.cortesia_solicitacao import CortesiaSolicitacao, TIPO_CUPOM, STATUS_SOLICITADO
from app.models.projecao import AreaProjecao, ProjecaoInscritos
from app.models.cadastro_evento import CadastroEvento
from app.models.user import Usuario
from app.api.routes.cortesia_solicitacao import _calcular_saldo, _calcular_saldos_bulk


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Cria só as tabelas que este teste usa. `Base.metadata.create_all(eng)`
    # sem filtro tentaria criar TODAS as tabelas do app nesse SQLite in-memory
    # — incluindo modelos com colunas JSONB (ex.: evento_detail_snapshot),
    # que o dialeto SQLite não sabe compilar — e quebraria mesmo sem nenhuma
    # relação com saldo de cortesias.
    Base.metadata.create_all(eng, tables=[
        Usuario.__table__,
        AreaProjecao.__table__,
        CadastroEvento.__table__,
        ProjecaoInscritos.__table__,
        CortesiaSolicitacao.__table__,
    ])
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def SessionFactory(engine):
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


# Eventos e áreas usados na grade de combinações.
EVENTO_IDS = [3001, 3002, 3003]
AREA_IDS = [4001, 4002, 4003]


@pytest.fixture(scope="module")
def seed(SessionFactory):
    db = SessionFactory()
    try:
        db.add(Usuario(id=8001, nome="Tester", email="t@t.local", auth_provider="local", ativo=True))
        for area_id in AREA_IDS:
            db.add(AreaProjecao(id=area_id, nome=f"Área {area_id}", sigla=f"A{area_id}", ativo=True))
        for evento_id in EVENTO_IDS:
            db.add(CadastroEvento(id=evento_id, nome=f"Evento {evento_id}", sku=f"EV{evento_id}"))
        db.commit()

        # (3001, 4001): projetado (2 linhas somadas) e solicitado (1 linha).
        db.add(ProjecaoInscritos(evento_id=3001, area_projecao_id=4001, quantidade=30, created_by=8001))
        db.add(ProjecaoInscritos(evento_id=3001, area_projecao_id=4001, quantidade=20, created_by=8001))
        db.add(CortesiaSolicitacao(
            evento_id=3001, area_projecao_id=4001, tipo=TIPO_CUPOM, quantidade=15,
            status=STATUS_SOLICITADO, solicitado_por=8001,
        ))

        # (3001, 4002): só projetado, sem nenhuma solicitação.
        db.add(ProjecaoInscritos(evento_id=3001, area_projecao_id=4002, quantidade=50, created_by=8001))

        # (3002, 4001): só solicitado (ex.: projeção removida depois do pedido).
        db.add(CortesiaSolicitacao(
            evento_id=3002, area_projecao_id=4001, tipo=TIPO_CUPOM, quantidade=5,
            status=STATUS_SOLICITADO, solicitado_por=8001,
        ))

        # (3002, 4002): linhas soft-deleted em ambas as tabelas — não podem contar.
        db.add(ProjecaoInscritos(
            evento_id=3002, area_projecao_id=4002, quantidade=999, created_by=8001,
            deleted_at=datetime(2020, 1, 1),
        ))
        db.add(CortesiaSolicitacao(
            evento_id=3002, area_projecao_id=4002, tipo=TIPO_CUPOM, quantidade=999,
            status=STATUS_SOLICITADO, solicitado_por=8001, deleted_at=datetime(2020, 1, 1),
        ))

        # (3003, *) e (*, 4003) permanecem sem nenhuma linha — grade completa
        # de "nem projetado nem solicitado" para confirmar o default (0,0,0).
        db.commit()
    finally:
        db.close()


def test_bulk_matches_point_to_point_for_full_grid(SessionFactory, seed):
    db = SessionFactory()
    try:
        bulk = _calcular_saldos_bulk(db, EVENTO_IDS, AREA_IDS)
        for evento_id in EVENTO_IDS:
            for area_id in AREA_IDS:
                expected = _calcular_saldo(db, evento_id, area_id)
                actual = bulk.get((evento_id, area_id), (0, 0, 0))
                assert actual == expected, f"mismatch at ({evento_id}, {area_id}): {actual} != {expected}"
    finally:
        db.close()


def test_bulk_sums_multiple_rows_and_excludes_soft_deleted(SessionFactory, seed):
    db = SessionFactory()
    try:
        bulk = _calcular_saldos_bulk(db, EVENTO_IDS, AREA_IDS)
        # 30 + 20 projetado, 15 solicitado -> saldo 35.
        assert bulk[(3001, 4001)] == (50, 15, 35)
        # Só projetado.
        assert bulk[(3001, 4002)] == (50, 0, 50)
        # Só solicitado (saldo negativo é esperado/possível).
        assert bulk[(3002, 4001)] == (0, 5, -5)
        # Ambas as linhas são soft-deleted -> combinação não aparece no dict.
        assert (3002, 4002) not in bulk
    finally:
        db.close()


def test_bulk_omits_combinations_with_no_rows(SessionFactory, seed):
    db = SessionFactory()
    try:
        bulk = _calcular_saldos_bulk(db, EVENTO_IDS, AREA_IDS)
        assert (3003, 4001) not in bulk
        assert (3001, 4003) not in bulk
    finally:
        db.close()


def test_bulk_empty_inputs_short_circuit(SessionFactory, seed):
    db = SessionFactory()
    try:
        assert _calcular_saldos_bulk(db, [], AREA_IDS) == {}
        assert _calcular_saldos_bulk(db, EVENTO_IDS, []) == {}
        assert _calcular_saldos_bulk(db, [], []) == {}
    finally:
        db.close()
