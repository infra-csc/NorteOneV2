"""Tests for the short-TTL SWR cache that backs the "Alterar Curva de Referência"
modal (GET /grupos/available-curves).

These guard two behaviors that, if they regressed, would let the modal show
stale options for up to the cache TTL (5 min):

1. Repeated calls to ``list_available_curves`` serve from the in-memory cache
   (the heavy ``_compute_available_curves`` only runs once while the entry is
   fresh).
2. After an override change (``set_curva_override``) or a group edit
   (``_invalidate_all_marketing_caches``) the cache is invalidated, so the next
   call recomputes the available curves.
"""

from unittest.mock import MagicMock

import pytest

from app.api.routes import sku_mappings
from app.api.routes.sku_mappings import (
    list_available_curves,
    set_curva_override,
    _invalidate_all_marketing_caches,
)
from app.core.cache import available_curves_cache


@pytest.fixture(autouse=True)
def clean_available_curves_cache():
    """Each test starts and ends with an empty available_curves cache so the
    in-process singleton can't leak state between tests."""
    available_curves_cache.invalidate()
    yield
    available_curves_cache.invalidate()


@pytest.fixture
def compute_counter(monkeypatch):
    """Replace the heavy recompute with a counting stub so we can assert exactly
    how many times it ran."""
    state = {"calls": 0}

    def fake_compute(db):
        state["calls"] += 1
        return {
            "historicas": [{"grupo": "Etapa X", "anoReferencia": 2025}],
            "vigentes": [],
            "call": state["calls"],
        }

    monkeypatch.setattr(sku_mappings, "_compute_available_curves", fake_compute)
    # Avoid the proactive eventos-list refresh kicking off real DB work in a
    # background thread during invalidation; the cache behavior under test does
    # not depend on it.
    monkeypatch.setattr(
        sku_mappings, "_proactive_eventos_list_refresh", lambda *a, **k: None
    )
    return state


def _call_list():
    # current_user is only used by the permission dependency, which is bypassed
    # when calling the route function directly; db is unused because the compute
    # is stubbed.
    return list_available_curves(force_refresh=False, db=object(), current_user=object())


def test_repeated_calls_serve_from_cache(compute_counter):
    first = _call_list()
    second = _call_list()

    # The second call must be served from the cache, not recomputed.
    assert compute_counter["calls"] == 1
    assert first == second
    assert first["call"] == 1


def test_force_refresh_bypasses_cache(compute_counter):
    _call_list()
    assert compute_counter["calls"] == 1

    # force_refresh must always recompute, even with a fresh cache entry.
    list_available_curves(force_refresh=True, db=object(), current_user=object())
    assert compute_counter["calls"] == 2


def test_invalidate_all_marketing_caches_forces_recompute(compute_counter):
    _call_list()
    assert compute_counter["calls"] == 1

    # Simulates the group-edit path, which clears caches via this helper.
    _invalidate_all_marketing_caches()

    _call_list()
    assert compute_counter["calls"] == 2


def test_set_curva_override_invalidates_cache(compute_counter):
    _call_list()
    assert compute_counter["calls"] == 1

    db = MagicMock()
    grupo = MagicMock()
    grupo.nome = "Etapa X"
    grupo.curva_override = "Etapa Y"
    db.query.return_value.filter.return_value.first.return_value = grupo

    set_curva_override(
        grupo_id=1,
        payload={"curva_override": "Etapa Y", "curva_override_modo": "historico"},
        db=db,
        current_user=object(),
    )

    # The override write must have invalidated the available-curves cache, so the
    # next modal open recomputes instead of serving the pre-override options.
    _call_list()
    assert compute_counter["calls"] == 2
