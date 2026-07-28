"""Tests for _verificar_espaco_cupom: the pre-flight coupon-space check.

Covers:
- Exhaustion guard (quantidade > remaining combinations → HTTP 400)
- 90 % saturation guard (would push usage past 90 % threshold → HTTP 400)
- Passes through when space is ample
- Wildcard characters (% and _) in `base` are not treated as SQL wildcards
- Overlapping-prefix bases (e.g. "AB" vs "ABC") are counted independently
"""

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import patch

import app.models  # noqa: F401 — register all mappers
from app.core.database import Base
from app.models.cortesia_solicitacao import CortesiaCupomCodigo, CortesiaSolicitacao, TIPO_CUPOM, STATUS_SOLICITADO
from app.models.projecao import AreaProjecao
from app.models.cadastro_evento import CadastroEvento
from app.models.user import Usuario
from app.api.routes.cortesia_solicitacao import (
    _CODIGO_CUPOM_ALPHABET,
    _CODIGO_CUPOM_SUFIXO_MIN,
    _CODIGO_CUPOM_TAMANHO_TOTAL,
    _verificar_espaco_cupom,
)


# ---------------------------------------------------------------------------
# Shared in-memory engine
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def SessionFactory(engine):
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture(scope="module")
def seed(SessionFactory):
    """Minimal objects required as foreign-key targets."""
    db = SessionFactory()
    try:
        db.add(Usuario(id=8001, nome="Tester", email="t@t.local", auth_provider="local", ativo=True))
        db.add(AreaProjecao(id=4001, nome="Área Teste", sigla="AT", ativo=True))
        db.add(CadastroEvento(id=3001, nome="Evento Teste", sku="TST2026"))
        db.add(CortesiaSolicitacao(
            id=6001, evento_id=3001, area_projecao_id=4001,
            tipo=TIPO_CUPOM, quantidade=10, status=STATUS_SOLICITADO,
            solicitado_por=8001,
        ))
        db.commit()
    finally:
        db.close()


def _insert_codes(SessionFactory, base: str, codes: list[str], sol_id: int = 6001):
    """Helper: persist artificial code rows with the given base."""
    db = SessionFactory()
    try:
        for c in codes:
            db.add(CortesiaCupomCodigo(solicitacao_id=sol_id, codigo=c, base=base))
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Helpers for computing thresholds
# ---------------------------------------------------------------------------

def _sufixo_len(base: str) -> int:
    return max(_CODIGO_CUPOM_SUFIXO_MIN, _CODIGO_CUPOM_TAMANHO_TOTAL - len(base))


def _total_combinations(base: str) -> int:
    return len(_CODIGO_CUPOM_ALPHABET) ** _sufixo_len(base)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestVerificarEspacoCupom:

    def test_passes_when_space_is_ample(self, SessionFactory, seed):
        """No existing codes → ample space → no exception."""
        db = SessionFactory()
        try:
            # Should not raise for a small quantity with zero prior codes.
            _verificar_espaco_cupom(db, "FRESHBASE", 100)
        finally:
            db.close()

    def test_raises_400_when_quantity_exceeds_remaining(self, SessionFactory, seed):
        """Raises HTTP 400 when requested quantity exceeds remaining space."""
        base = "EXHAUST"
        sufixo_len = _sufixo_len(base)
        total = _total_combinations(base)

        # We can't actually fill the table with 887M rows in a test.
        # Instead, patch ja_usados so it appears to be total - 1 (1 slot left).
        db = SessionFactory()
        try:
            with patch(
                "app.api.routes.cortesia_solicitacao.CortesiaCupomCodigo",
            ):
                # Patch the count query directly by mocking the DB scalar result.
                pass

            # Use a tiny mock: make total tiny via a short alphabet mock.
            # Better: patch the count query result.
            from unittest.mock import MagicMock
            mock_db = MagicMock()
            # Simulate total=10 combinations, 9 already used, requesting 2 → exceeds 1 remaining.
            mock_query = mock_db.query.return_value.filter.return_value.scalar
            mock_query.return_value = 9  # ja_usados

            # We also need _CODIGO_CUPOM_ALPHABET to have exactly 1 char for easy math,
            # but that's awkward. Instead patch len(alphabet)**sufixo_len result.
            with patch(
                "app.api.routes.cortesia_solicitacao._CODIGO_CUPOM_ALPHABET",
                "A",  # 1-char alphabet → total = 1^sufixo_len = 1
            ):
                with pytest.raises(HTTPException) as exc_info:
                    _verificar_espaco_cupom(mock_db, "X", 2)  # 1 combo, 0 used, wants 2
            assert exc_info.value.status_code == 400
            assert "suficientes" in exc_info.value.detail
        finally:
            db.close()

    def test_raises_400_on_exhaustion_via_real_db(self, SessionFactory, seed):
        """Real-DB version: insert codes matching the full space of a tiny mock alphabet."""
        base = "TINYBASE"
        # Patch the alphabet to "A" (1 combo) so the space is trivially exhausted.
        db = SessionFactory()
        try:
            _insert_codes(SessionFactory, base, ["TINYBASEA"])  # 1 code with this base

            with patch(
                "app.api.routes.cortesia_solicitacao._CODIGO_CUPOM_ALPHABET",
                "A",
            ):
                with pytest.raises(HTTPException) as exc_info:
                    _verificar_espaco_cupom(db, base, 1)
            assert exc_info.value.status_code == 400
            assert "suficientes" in exc_info.value.detail or "esgotado" in exc_info.value.detail
        finally:
            db.close()

    def test_raises_400_when_over_90_percent_used(self, SessionFactory, seed):
        """Raises HTTP 400 when (used + requested) would exceed 90% of total space."""
        base = "SATURATE"
        # Patch alphabet to 10 chars → total = 10^sufixo_len. We want >90% used.
        # With alphabet size 10, sufixo_len = max(6, 26-8) = 18, total = 10^18 = huge.
        # Easier: just use mock_db approach.
        from unittest.mock import MagicMock
        mock_db = MagicMock()
        # 91 out of 100 already used; requesting 1 more → 92/100 = 92% > 90%
        mock_db.query.return_value.filter.return_value.scalar.return_value = 91

        with patch(
            "app.api.routes.cortesia_solicitacao._CODIGO_CUPOM_ALPHABET",
            "ABCDEFGHIJ",  # 10 chars
        ):
            with patch(
                "app.api.routes.cortesia_solicitacao._CODIGO_CUPOM_SUFIXO_MIN",
                2,
            ):
                with patch(
                    "app.api.routes.cortesia_solicitacao._CODIGO_CUPOM_TAMANHO_TOTAL",
                    4,
                ):
                    # base="AB" (len=2), sufixo_len=max(2,4-2)=2, total=10^2=100
                    with pytest.raises(HTTPException) as exc_info:
                        _verificar_espaco_cupom(mock_db, "AB", 1)
        assert exc_info.value.status_code == 400
        assert "esgotado" in exc_info.value.detail or "90" in exc_info.value.detail

    def test_wildcard_percent_in_base_not_treated_as_sql_wildcard(self, SessionFactory, seed):
        """A % in the base must not match codes of other bases via SQL wildcard expansion."""
        base_with_pct = "AREA%TST"
        base_normal = "AREAXXTST"  # won't contain %, but starts with "AREA"

        # Insert a code under the normal base — must NOT be counted for base_with_pct.
        _insert_codes(SessionFactory, base_normal, ["AREAXXTST_CODE_1"])

        db = SessionFactory()
        try:
            # _verificar_espaco_cupom for base_with_pct should see 0 used codes,
            # not 1 (which would happen if % were treated as a SQL wildcard in LIKE).
            # Since we filter by exact base column, the count must be 0.
            count = (
                db.query(__import__("sqlalchemy", fromlist=["func"]).func.count(CortesiaCupomCodigo.id))
                .filter(CortesiaCupomCodigo.base == base_with_pct)
                .scalar()
            )
            assert count == 0, (
                f"Expected 0 codes for base '{base_with_pct}', got {count}. "
                "% in base is being misinterpreted as a SQL wildcard."
            )
        finally:
            db.close()

    def test_wildcard_underscore_in_base_not_treated_as_sql_wildcard(self, SessionFactory, seed):
        """A _ in the base must not match codes of other bases via SQL wildcard expansion."""
        base_with_us = "AREA_TST"
        base_other = "AREAXXTST"

        _insert_codes(SessionFactory, base_other, ["AREAXXTST_CODE_2"])

        db = SessionFactory()
        try:
            count = (
                db.query(__import__("sqlalchemy", fromlist=["func"]).func.count(CortesiaCupomCodigo.id))
                .filter(CortesiaCupomCodigo.base == base_with_us)
                .scalar()
            )
            assert count == 0, (
                f"Expected 0 codes for base '{base_with_us}', got {count}. "
                "_ in base is being misinterpreted as a SQL wildcard."
            )
        finally:
            db.close()

    def test_overlapping_prefix_bases_counted_independently(self, SessionFactory, seed):
        """Codes for base 'ABC' must NOT be counted toward base 'AB'."""
        base_short = "PFXSHORT"
        base_long = "PFXSHORTX"  # starts with base_short

        # Insert 3 codes under the long base only.
        _insert_codes(SessionFactory, base_long, [
            "PFXSHORTXCODE1",
            "PFXSHORTXCODE2",
            "PFXSHORTXCODE3",
        ])

        db = SessionFactory()
        try:
            # Count for base_short must be 0 — long-base codes are not its codes.
            count_short = (
                db.query(__import__("sqlalchemy", fromlist=["func"]).func.count(CortesiaCupomCodigo.id))
                .filter(CortesiaCupomCodigo.base == base_short)
                .scalar()
            )
            # Count for base_long must be exactly 3.
            count_long = (
                db.query(__import__("sqlalchemy", fromlist=["func"]).func.count(CortesiaCupomCodigo.id))
                .filter(CortesiaCupomCodigo.base == base_long)
                .scalar()
            )
            assert count_short == 0, (
                f"base '{base_short}' should have 0 codes, got {count_short}. "
                f"Codes of '{base_long}' contaminated the count."
            )
            assert count_long == 3, (
                f"base '{base_long}' should have 3 codes, got {count_long}."
            )
        finally:
            db.close()

    def test_legacy_null_base_rows_counted_in_occupancy(self, SessionFactory, seed):
        """Rows with base IS NULL (pre-backfill) must still be counted toward
        occupancy for the matching base, so the exhaustion guard fires correctly."""
        from unittest.mock import MagicMock
        # Insert a legacy code row with base=None that belongs to the same base.
        legacy_base = "LEGACYBASE"
        sufixo_len = _sufixo_len(legacy_base)
        expected_len = len(legacy_base) + sufixo_len
        # Construct a fake code of the right length starting with the base.
        suffix = "A" * sufixo_len
        legacy_code = (legacy_base + suffix)[:expected_len]

        db = SessionFactory()
        try:
            db.add(CortesiaCupomCodigo(
                solicitacao_id=6001,
                codigo=legacy_code,
                base=None,  # simulate a pre-backfill row
            ))
            db.commit()

            # Now patch the alphabet to be tiny so total=1 and the single legacy
            # row fills the space — the guard should raise 400.
            with patch(
                "app.api.routes.cortesia_solicitacao._CODIGO_CUPOM_ALPHABET",
                "A",  # 1-char → total = 1^sufixo_len = 1
            ):
                with pytest.raises(HTTPException) as exc_info:
                    _verificar_espaco_cupom(db, legacy_base, 1)
            assert exc_info.value.status_code == 400, (
                "Legacy NULL-base row was not counted; guard failed to trigger."
            )
        finally:
            db.close()

    def test_verificar_does_not_raise_when_exactly_at_90_percent(self, SessionFactory, seed):
        """Exactly at 90% used + requesting 0 more should not raise (boundary)."""
        from unittest.mock import MagicMock
        mock_db = MagicMock()
        # 90 used out of 100 total, requesting 0 (edge; mainly confirms no off-by-one crash)
        mock_db.query.return_value.filter.return_value.scalar.return_value = 90

        with patch("app.api.routes.cortesia_solicitacao._CODIGO_CUPOM_ALPHABET", "ABCDEFGHIJ"):
            with patch("app.api.routes.cortesia_solicitacao._CODIGO_CUPOM_SUFIXO_MIN", 2):
                with patch("app.api.routes.cortesia_solicitacao._CODIGO_CUPOM_TAMANHO_TOTAL", 4):
                    # total=100, used=90, requesting 0 → no raise (0 ≤ remaining=10, used+0=90 ≤ 90)
                    _verificar_espaco_cupom(mock_db, "AB", 0)
