"""Guard against ISC year-mixing regression in fetch_isc_pricing_data.

Bug (fixed in task #195): when an evento_grupo had active SkuMapping rows for
both current_year AND current_year+1, the snapshot totals of one year could
"leak" into the other year's SKU row — one edition stole the combined total
while the other showed near-zero.

These tests assert that:
 1. get_isc_totals_from_snapshot(db, ano) is correctly year-scoped (rows for
    year A never appear in the totals for year B).
 2. fetch_isc_pricing_data returns each year's SKU with *only its own year's*
    qtd_site / receita_liquida_site — never the combined total and never the
    other year's figures.
"""

import os
import sys

# Ensure app package is importable when run from backend/
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from datetime import date, timedelta
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Register ALL mappers so relationship targets resolve across modules.
import app.models  # noqa: F401
from app.core.database import Base
from app.models.dimensoes import SkuMapping
from app.models.vendas_snapshot import VendasDiariaSnapshot


# ---------------------------------------------------------------------------
# Shared in-memory engine for this module
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture(scope="module")
def Session(engine):
    return sessionmaker(bind=engine)


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

GRUPO = "Corrida Teste Dual Year"
SKU_CURRENT = "COR25SP1"   # edition current_year
SKU_NEXT    = "COR26SP1"   # edition current_year+1

CURRENT_YEAR = date.today().year
NEXT_YEAR    = CURRENT_YEAR + 1

QTD_CURRENT   = 300
RECEITA_CURRENT = 15_000.0

QTD_NEXT    = 50
RECEITA_NEXT = 2_500.0


@pytest.fixture(scope="module")
def db_with_dual_year_data(Session):
    """DB session seeded with a dual-year grupo: distinct totals per edition."""
    db = Session()
    try:
        # --- SkuMapping rows ---
        db.add(SkuMapping(
            fonte="MAGENTO",
            id_externo=9001,
            sku=SKU_CURRENT,
            evento_grupo=GRUPO,
            ano=CURRENT_YEAR,
            nome_evento=GRUPO,
            ativo=True,
            data_evento=date(CURRENT_YEAR, 6, 15),
        ))
        db.add(SkuMapping(
            fonte="MAGENTO",
            id_externo=9002,
            sku=SKU_NEXT,
            evento_grupo=GRUPO,
            ano=NEXT_YEAR,
            nome_evento=GRUPO,
            ativo=True,
            data_evento=date(NEXT_YEAR, 6, 15),
        ))

        # --- VendasDiariaSnapshot rows for current_year ---
        # Use several days to give rolling-window averages something to work with.
        today = date.today()
        for offset in range(5):
            d = today - timedelta(days=offset + 2)  # stay in the past
            db.add(VendasDiariaSnapshot(
                evento_grupo=GRUPO,
                fonte="MAGENTO",
                data_venda=d,
                quantidade=QTD_CURRENT // 5,
                receita=RECEITA_CURRENT / 5,
                ano=CURRENT_YEAR,
            ))

        # --- VendasDiariaSnapshot rows for next_year ---
        # Distinct dates to satisfy the unique constraint (grupo, fonte, data_venda).
        for offset in range(5):
            d = today - timedelta(days=offset + 8)  # earlier window, no date clash
            db.add(VendasDiariaSnapshot(
                evento_grupo=GRUPO,
                fonte="MAGENTO",
                data_venda=d,
                quantidade=QTD_NEXT // 5,
                receita=RECEITA_NEXT / 5,
                ano=NEXT_YEAR,
            ))

        db.commit()
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Test 1: get_isc_totals_from_snapshot is year-scoped
# ---------------------------------------------------------------------------

class TestGetIscTotalsFromSnapshot:
    """Unit-tests get_isc_totals_from_snapshot in isolation."""

    def test_current_year_sees_only_current_year_rows(self, db_with_dual_year_data):
        from app.services.snapshot_service import get_isc_totals_from_snapshot

        result = get_isc_totals_from_snapshot(db_with_dual_year_data, CURRENT_YEAR)

        assert GRUPO in result, f"Expected grupo '{GRUPO}' in year {CURRENT_YEAR} snapshot"
        row = result[GRUPO]
        assert row["qtd_site"] == QTD_CURRENT, (
            f"qtd_site should be {QTD_CURRENT} (current-year only), got {row['qtd_site']}"
        )
        # Must NOT include next-year figures
        assert row["qtd_site"] != QTD_CURRENT + QTD_NEXT, (
            "Current-year snapshot must not include next-year sales"
        )

    def test_next_year_sees_only_next_year_rows(self, db_with_dual_year_data):
        from app.services.snapshot_service import get_isc_totals_from_snapshot

        result = get_isc_totals_from_snapshot(db_with_dual_year_data, NEXT_YEAR)

        assert GRUPO in result, f"Expected grupo '{GRUPO}' in year {NEXT_YEAR} snapshot"
        row = result[GRUPO]
        assert row["qtd_site"] == QTD_NEXT, (
            f"qtd_site should be {QTD_NEXT} (next-year only), got {row['qtd_site']}"
        )
        # Must NOT include current-year figures
        assert row["qtd_site"] != QTD_CURRENT + QTD_NEXT, (
            "Next-year snapshot must not include current-year sales"
        )

    def test_receita_is_year_scoped(self, db_with_dual_year_data):
        from app.services.snapshot_service import get_isc_totals_from_snapshot

        cy = get_isc_totals_from_snapshot(db_with_dual_year_data, CURRENT_YEAR)
        ny = get_isc_totals_from_snapshot(db_with_dual_year_data, NEXT_YEAR)

        assert abs(cy[GRUPO]["receita_liquida_site"] - RECEITA_CURRENT) < 0.01, (
            f"Current-year receita should be {RECEITA_CURRENT}, "
            f"got {cy[GRUPO]['receita_liquida_site']}"
        )
        assert abs(ny[GRUPO]["receita_liquida_site"] - RECEITA_NEXT) < 0.01, (
            f"Next-year receita should be {RECEITA_NEXT}, "
            f"got {ny[GRUPO]['receita_liquida_site']}"
        )

    def test_totals_are_not_combined_across_years(self, db_with_dual_year_data):
        """Neither year's total should equal the sum of both years."""
        from app.services.snapshot_service import get_isc_totals_from_snapshot

        cy = get_isc_totals_from_snapshot(db_with_dual_year_data, CURRENT_YEAR)
        ny = get_isc_totals_from_snapshot(db_with_dual_year_data, NEXT_YEAR)

        combined_qty = QTD_CURRENT + QTD_NEXT

        assert cy[GRUPO]["qtd_site"] != combined_qty, (
            f"Current-year row must not contain combined qty {combined_qty}"
        )
        assert ny[GRUPO]["qtd_site"] != combined_qty, (
            f"Next-year row must not contain combined qty {combined_qty}"
        )


# ---------------------------------------------------------------------------
# Test 2: fetch_isc_pricing_data assigns each SKU only its own year's totals
# ---------------------------------------------------------------------------

class TestFetchIscPricingDataYearIsolation:
    """Integration-level: fetch_isc_pricing_data must not mix years."""

    def _run_fetch(self, db):
        """Call fetch_isc_pricing_data with cache bypassed."""
        from app.api.routes import marketing as mkt

        # Bypass the in-process SmartCache so every call recomputes.
        mock_cache = MagicMock()
        mock_cache.get.return_value = None   # always cache miss
        mock_cache.get_info.return_value = {}
        mock_cache.set.return_value = None

        with patch.object(mkt, "_smart_isc_cache", mock_cache):
            return mkt.fetch_isc_pricing_data(db=db, force_refresh=True)

    def test_current_year_sku_gets_current_year_qty(self, db_with_dual_year_data):
        from app.api.routes.inscricoes_consolidado import normalize_sku

        result = self._run_fetch(db_with_dual_year_data)
        sku_norm = normalize_sku(SKU_CURRENT)

        assert sku_norm in result, (
            f"SKU '{sku_norm}' (current year) not found in fetch_isc_pricing_data output"
        )
        row = result[sku_norm]
        assert row["qtd_site"] == QTD_CURRENT, (
            f"Current-year SKU '{sku_norm}' should have qtd_site={QTD_CURRENT}, "
            f"got {row['qtd_site']}"
        )

    def test_next_year_sku_gets_next_year_qty(self, db_with_dual_year_data):
        from app.api.routes.inscricoes_consolidado import normalize_sku

        result = self._run_fetch(db_with_dual_year_data)
        sku_norm = normalize_sku(SKU_NEXT)

        assert sku_norm in result, (
            f"SKU '{sku_norm}' (next year) not found in fetch_isc_pricing_data output"
        )
        row = result[sku_norm]
        assert row["qtd_site"] == QTD_NEXT, (
            f"Next-year SKU '{sku_norm}' should have qtd_site={QTD_NEXT}, "
            f"got {row['qtd_site']}"
        )

    def test_no_sku_has_combined_total(self, db_with_dual_year_data):
        """The combined total must never appear in any SKU row — the classic year-mixing symptom."""
        from app.api.routes.inscricoes_consolidado import normalize_sku

        combined = QTD_CURRENT + QTD_NEXT
        result = self._run_fetch(db_with_dual_year_data)

        for sku_key in (normalize_sku(SKU_CURRENT), normalize_sku(SKU_NEXT)):
            if sku_key in result:
                qty = result[sku_key].get("qtd_site", 0)
                assert qty != combined, (
                    f"SKU '{sku_key}' has the combined qty {combined} — "
                    "year-mixing regression detected"
                )

    def test_receita_not_mixed(self, db_with_dual_year_data):
        """receita_liquida_site must be year-scoped for both SKUs."""
        from app.api.routes.inscricoes_consolidado import normalize_sku

        result = self._run_fetch(db_with_dual_year_data)
        combined_rec = RECEITA_CURRENT + RECEITA_NEXT

        for sku_key, expected_rec in (
            (normalize_sku(SKU_CURRENT), RECEITA_CURRENT),
            (normalize_sku(SKU_NEXT),    RECEITA_NEXT),
        ):
            if sku_key not in result:
                continue
            rec = result[sku_key].get("receita_liquida_site", 0.0)
            assert abs(rec - expected_rec) < 0.5, (
                f"SKU '{sku_key}' receita should be ~{expected_rec}, got {rec}"
            )
            assert abs(rec - combined_rec) > 1.0, (
                f"SKU '{sku_key}' receita equals combined total {combined_rec} — "
                "year-mixing regression detected"
            )
