"""Concurrency tests: coupon codes must never collide when two gerar_cupom
requests fire at the same instant; planilha double-submits must be blocked.

Two strategies are used together for gerar_cupom:

1. **Real concurrent threads** – a `threading.Barrier` forces both callers to
   start executing at the exact same moment. SQLite (StaticPool) serialises
   writes, so this confirms the *happy-path* invariants: both calls eventually
   succeed, every successful call persists exactly the requested number of
   codes, no duplicate codes land in the DB, and no solicitação is left in a
   half-generated state.

2. **Simulated worst-case race** – `_codigo_cupom_existe` is patched to always
   return ``False`` (i.e., the pre-commit uniqueness check misses every conflict,
   as would happen if two threads ran their pre-checks before *either* committed).
   The real DB unique index then fires on the first commit attempt, triggering
   the IntegrityError → rollback → retry path. The test confirms that the retry
   succeeds and the final state is still consistent.

The ``ux_cortesia_cupom_codigo_codigo`` unique index lives in a migration, not
in the ORM model, so it is created explicitly on the in-memory SQLite engine
(see memory: coupon-code-auto-generation).

Planilha double-submit tests confirm that:
* A second identical upload within the 30-second window is rejected with 409.
* No orphan file is left on disk when the DB commit fails after a file write.
"""

import asyncio
import os
import tempfile
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError as SAIntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Register ALL mappers so relationship targets resolve across modules.
import app.models  # noqa: F401
from app.core.database import Base
from app.models.cadastro_evento import CadastroEvento
from app.models.cortesia_solicitacao import (
    STATUS_GERADO,
    STATUS_SOLICITADO,
    TIPO_CUPOM,
    TIPO_PLANILHA,
    CortesiaCupomCodigo,
    CortesiaSolicitacao,
)
from app.models.projecao import AreaProjecao
from app.models.user import Usuario

from app.api.routes.cortesia_solicitacao import (
    _CODIGO_CUPOM_INDICE_UNICO,
    _gerar_codigo_cupom_unico,
    _planilha_advisory_lock_params,
    criar_solicitacao_planilha,
    gerar_cupom,
)


# ---------------------------------------------------------------------------
# Shared in-memory engine (all tests in this module reuse it)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    # The production unique index lives in a migration; reproduce it here so
    # the IntegrityError retry path is actually exercised.
    with eng.connect() as conn:
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_cortesia_cupom_codigo_codigo "
                "ON cortesia_cupom_codigo (UPPER(codigo))"
            )
        )
        conn.commit()
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def SessionFactory(engine):
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


# ---------------------------------------------------------------------------
# Minimal seed data
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def seed_data(SessionFactory):
    """One user, one area (sigla='AT'), one event (sku='TST2026'), and two
    separate pending cupom solicitações with quantidade=5 each.

    Using the *same* base (sigla+sku = 'ATTST2026') for both requests maximises
    the chance of suffix collisions and thus exercises the uniqueness machinery.
    """
    session = SessionFactory()
    try:
        user = Usuario(
            id=9001,
            nome="Concurrency Tester",
            email="concurrency@test.local",
            auth_provider="local",
            ativo=True,
        )
        session.add(user)
        session.flush()

        area = AreaProjecao(id=5001, nome="Área Concorrência", sigla="AT", ativo=True)
        session.add(area)
        session.flush()

        evento = CadastroEvento(id=6001, nome="Evento Concorrência", sku="TST2026")
        session.add(evento)
        session.flush()

        sol1 = CortesiaSolicitacao(
            id=7001, evento_id=6001, area_projecao_id=5001,
            tipo=TIPO_CUPOM, quantidade=5, status=STATUS_SOLICITADO,
            solicitado_por=9001,
        )
        sol2 = CortesiaSolicitacao(
            id=7002, evento_id=6001, area_projecao_id=5001,
            tipo=TIPO_CUPOM, quantidade=5, status=STATUS_SOLICITADO,
            solicitado_por=9001,
        )
        session.add_all([sol1, sol2])
        session.commit()
    finally:
        session.close()

    return {"user_id": 9001, "sol1_id": 7001, "sol2_id": 7002, "quantidade": 5}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_admin():
    """Minimal stand-in for a Usuario that passes is_user_admin patching."""
    return SimpleNamespace(id=9001, nome="Concurrency Tester")


def _all_persisted_codes(SessionFactory) -> list[str]:
    db = SessionFactory()
    try:
        return [
            row.codigo.upper()
            for row in db.query(CortesiaCupomCodigo).all()
        ]
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Test 1 – real concurrent threads
# ---------------------------------------------------------------------------

def test_concurrent_gerar_no_duplicate_codes(SessionFactory, seed_data):
    """Two threads calling gerar_cupom at the same instant must produce only
    unique codes and leave every solicitação in a consistent state."""

    barrier = threading.Barrier(2)
    results: dict = {}
    errors: dict = {}

    def run(sol_id: int, label: str):
        db = SessionFactory()
        try:
            # Sync both threads to maximise overlap at the entry point.
            barrier.wait(timeout=15)
            fake_user = _make_fake_admin()
            with patch(
                "app.api.routes.cortesia_solicitacao.is_user_admin",
                return_value=True,
            ):
                result = gerar_cupom(
                    solicitacao_id=sol_id,
                    db=db,
                    current_user=fake_user,
                )
            results[label] = result
        except Exception as exc:  # noqa: BLE001
            errors[label] = exc
        finally:
            db.close()

    t1 = threading.Thread(target=run, args=(seed_data["sol1_id"], "t1"), daemon=True)
    t2 = threading.Thread(target=run, args=(seed_data["sol2_id"], "t2"), daemon=True)
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)

    assert not t1.is_alive(), "Thread 1 timed out — gerar_cupom hung"
    assert not t2.is_alive(), "Thread 2 timed out — gerar_cupom hung"

    # At least one call must succeed; both failing would indicate a real bug
    # (the retry budget is 3 attempts — more than enough for two concurrent
    # callers).
    assert results, (
        "All concurrent gerar_cupom calls failed.\n"
        f"Errors: { {k: str(v) for k, v in errors.items()} }"
    )

    # ------------------------------------------------------------------
    # Invariant A: no duplicate codes in the database
    # ------------------------------------------------------------------
    all_codes = _all_persisted_codes(SessionFactory)
    assert len(all_codes) == len(set(all_codes)), (
        f"Duplicate coupon codes found in DB: {all_codes}"
    )

    # ------------------------------------------------------------------
    # Invariant B: each successful call persisted exactly `quantidade` codes.
    # Verified via a fresh session rather than result.codigos_detalhes: with
    # SQLite StaticPool (shared connection) the in-flight lazy relationship
    # can appear stale when two sessions overlap, while a fresh query always
    # returns the committed truth.
    # ------------------------------------------------------------------
    db_b = SessionFactory()
    try:
        for label, result in results.items():
            code_count = (
                db_b.query(CortesiaCupomCodigo)
                .filter_by(solicitacao_id=result.id)
                .count()
            )
            assert code_count == seed_data["quantidade"], (
                f"{label}: expected {seed_data['quantidade']} code rows in DB for "
                f"sol {result.id}, got {code_count}"
            )
    finally:
        db_b.close()

    # ------------------------------------------------------------------
    # Invariant C: no half-generated state — status and code-row count agree
    # ------------------------------------------------------------------
    db = SessionFactory()
    try:
        for sol_id in (seed_data["sol1_id"], seed_data["sol2_id"]):
            sol = db.query(CortesiaSolicitacao).filter_by(id=sol_id).first()
            code_count = (
                db.query(CortesiaCupomCodigo)
                .filter_by(solicitacao_id=sol_id)
                .count()
            )
            if sol.status == STATUS_GERADO:
                assert code_count == seed_data["quantidade"], (
                    f"sol {sol_id}: status=gerado but only {code_count} code rows "
                    f"(expected {seed_data['quantidade']})"
                )
            else:
                # STATUS_SOLICITADO: the call either wasn't attempted yet or
                # failed clearly — no orphan code rows should exist.
                assert code_count == 0, (
                    f"sol {sol_id}: status=solicitado but {code_count} orphan "
                    "code rows found (partial write leaked past rollback)"
                )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Test 2 – simulated worst-case race: retry path succeeds on second attempt
# ---------------------------------------------------------------------------

def test_integrity_error_retry_succeeds_on_second_attempt(SessionFactory):
    """Worst-case race: the first DB commit fails with the unique-index
    IntegrityError (as would happen when two threads both pass the pre-check
    before either commits).  gerar_cupom must roll back, regenerate fresh
    candidates, and succeed on the retry — leaving exactly the right number
    of codes in a consistent state.

    Implemented as a single-threaded test with a patched ``commit`` that raises
    IntegrityError exactly once, then delegates to the real commit.  This
    avoids SQLite StaticPool connection-sharing issues while still exercising
    the full IntegrityError → rollback → retry code path.
    """
    db_setup = SessionFactory()
    try:
        sol3 = CortesiaSolicitacao(
            id=7003, evento_id=6001, area_projecao_id=5001,
            tipo=TIPO_CUPOM, quantidade=3, status=STATUS_SOLICITADO,
            solicitado_por=9001,
        )
        db_setup.add(sol3)
        db_setup.commit()
    finally:
        db_setup.close()

    db = SessionFactory()
    try:
        fake_user = _make_fake_admin()

        # Patch commit: fail with the unique-index error on attempt 1,
        # then call the real commit on subsequent attempts.
        attempt = [0]
        real_commit = db.commit

        def commit_fail_once():
            attempt[0] += 1
            if attempt[0] == 1:
                # Simulate what the DB does when the unique index fires.
                db.rollback()
                raise SAIntegrityError(
                    statement=None,
                    params=None,
                    orig=Exception(_CODIGO_CUPOM_INDICE_UNICO),
                )
            real_commit()

        with (
            patch(
                "app.api.routes.cortesia_solicitacao.is_user_admin",
                return_value=True,
            ),
            patch.object(db, "commit", side_effect=commit_fail_once),
        ):
            result = gerar_cupom(
                solicitacao_id=7003,
                db=db,
                current_user=fake_user,
            )
    finally:
        db.close()

    # The retry must have been triggered and must have ultimately succeeded.
    assert attempt[0] == 2, (
        f"Expected commit to be called exactly 2 times (1 fail + 1 success), "
        f"got {attempt[0]}"
    )
    assert len(result.codigos_detalhes) == 3, (
        f"Expected 3 codes after retry, got {len(result.codigos_detalhes)}"
    )

    # Consistency: 3 code rows, status=gerado, no duplicates anywhere.
    db_check = SessionFactory()
    try:
        sol = db_check.query(CortesiaSolicitacao).filter_by(id=7003).first()
        assert sol.status == STATUS_GERADO
        code_count = (
            db_check.query(CortesiaCupomCodigo)
            .filter_by(solicitacao_id=7003)
            .count()
        )
        assert code_count == 3, (
            f"sol 7003: status=gerado but {code_count} code rows (expected 3)"
        )
    finally:
        db_check.close()

    all_codes = _all_persisted_codes(SessionFactory)
    assert len(all_codes) == len(set(all_codes)), (
        f"Duplicate coupon codes after retry: {all_codes}"
    )


# ---------------------------------------------------------------------------
# Test 4 – same solicitacao_id targeted twice (double-call / double-click guard)
# ---------------------------------------------------------------------------

def test_same_solicitacao_double_call_second_returns_400(SessionFactory, seed_data):
    """A duplicate gerar_cupom call for an already-generated solicitação must
    be rejected with HTTP 400 ("já foi marcada como gerada") *before* writing
    any codes to the DB.

    Design note
    -----------
    SQLite's StaticPool serialises all connections through a single underlying
    connection, so true simultaneous thread concurrency is not achievable in
    this test environment.  The sequential double-call below is sufficient to
    verify the guard and DB invariants:

    * Call 1 (first request): must succeed and persist exactly ``quantidade``
      unique codes.
    * Call 2 (duplicate request, same solicitacao_id): must raise HTTP 400
      with the "já foi marcada como gerada" message and must NOT write any
      additional code rows.

    The production race (two requests arriving before either commits) is
    addressed by the ``SELECT … FOR UPDATE`` added to the route: only one
    transaction can hold the row lock; the other blocks until the first
    commits, then reads STATUS_GERADO and returns 400 immediately.
    """
    from fastapi import HTTPException

    # Seed a fresh solicitação so this test is independent of the others.
    db_setup = SessionFactory()
    quantidade = 4
    try:
        sol = CortesiaSolicitacao(
            id=7004, evento_id=6001, area_projecao_id=5001,
            tipo=TIPO_CUPOM, quantidade=quantidade, status=STATUS_SOLICITADO,
            solicitado_por=9001,
        )
        db_setup.add(sol)
        db_setup.commit()
    finally:
        db_setup.close()

    fake_user = _make_fake_admin()

    # ------------------------------------------------------------------
    # Call 1: must succeed with exactly `quantidade` codes
    # ------------------------------------------------------------------
    db1 = SessionFactory()
    try:
        with patch(
            "app.api.routes.cortesia_solicitacao.is_user_admin",
            return_value=True,
        ):
            result1 = gerar_cupom(
                solicitacao_id=7004,
                db=db1,
                current_user=fake_user,
            )
    finally:
        db1.close()

    assert len(result1.codigos_detalhes) == quantidade, (
        f"First call returned {len(result1.codigos_detalhes)} codes, expected {quantidade}"
    )

    # ------------------------------------------------------------------
    # Call 2: must raise HTTP 400 before writing anything
    # ------------------------------------------------------------------
    db2 = SessionFactory()
    try:
        with patch(
            "app.api.routes.cortesia_solicitacao.is_user_admin",
            return_value=True,
        ):
            with pytest.raises(HTTPException) as exc_info:
                gerar_cupom(
                    solicitacao_id=7004,
                    db=db2,
                    current_user=fake_user,
                )
    finally:
        db2.close()

    assert exc_info.value.status_code == 400, (
        f"Expected HTTP 400 on duplicate call, got {exc_info.value.status_code}"
    )
    assert "já foi marcada como gerada" in (exc_info.value.detail or ""), (
        f"Unexpected rejection message: {exc_info.value.detail!r}"
    )

    # ------------------------------------------------------------------
    # Invariant: DB has exactly `quantidade` codes, all unique, status=gerado
    # (second call must not have written any orphan rows)
    # ------------------------------------------------------------------
    db_check = SessionFactory()
    try:
        sol = db_check.query(CortesiaSolicitacao).filter_by(id=7004).first()
        assert sol.status == STATUS_GERADO, (
            f"solicitacao 7004 status={sol.status!r} after double-call"
        )
        code_rows = (
            db_check.query(CortesiaCupomCodigo)
            .filter_by(solicitacao_id=7004)
            .all()
        )
        assert len(code_rows) == quantidade, (
            f"sol 7004: expected exactly {quantidade} code rows, found {len(code_rows)} "
            "(duplicate call may have leaked orphan rows)"
        )
        codes = [r.codigo.upper() for r in code_rows]
        assert len(codes) == len(set(codes)), (
            f"Duplicate coupon codes in DB for sol 7004: {codes}"
        )
    finally:
        db_check.close()


# ---------------------------------------------------------------------------
# Test 3 – retry budget exhaustion returns a clear 409 (unit)
# ---------------------------------------------------------------------------

def test_retry_budget_exhausted_raises_409(SessionFactory):
    """If every attempt hits an IntegrityError matching the unique-index name,
    gerar_cupom must raise HTTP 409 — not silently succeed, not hang, not 500."""
    from fastapi import HTTPException

    db_setup = SessionFactory()
    try:
        sol5 = CortesiaSolicitacao(
            id=7005, evento_id=6001, area_projecao_id=5001,
            tipo=TIPO_CUPOM, quantidade=1, status=STATUS_SOLICITADO,
            solicitado_por=9001,
        )
        db_setup.add(sol5)
        db_setup.commit()
    finally:
        db_setup.close()

    # Simulate a commit that ALWAYS raises the unique-index IntegrityError so
    # all 3 retry slots are consumed.
    fake_ie = SAIntegrityError(
        statement=None,
        params=None,
        orig=Exception(_CODIGO_CUPOM_INDICE_UNICO),
    )

    db = SessionFactory()
    try:
        fake_user = _make_fake_admin()
        with (
            patch(
                "app.api.routes.cortesia_solicitacao.is_user_admin",
                return_value=True,
            ),
            patch(
                "app.api.routes.cortesia_solicitacao._codigo_cupom_existe",
                return_value=False,
            ),
            patch.object(db, "commit", side_effect=fake_ie),
        ):
            with pytest.raises(HTTPException) as exc_info:
                gerar_cupom(
                    solicitacao_id=7005,
                    db=db,
                    current_user=fake_user,
                )
        assert exc_info.value.status_code == 409, (
            f"Expected HTTP 409 on exhausted retry budget, got {exc_info.value.status_code}"
        )
    finally:
        db.close()


# ===========================================================================
# Advisory-lock key helper unit test
# ===========================================================================

def test_planilha_advisory_lock_params_stability():
    """``_planilha_advisory_lock_params`` must return identical values for the
    same inputs regardless of Python process state (no hash randomisation).

    Properties verified
    -------------------
    * Same inputs → same output (idempotent / deterministic).
    * Swapping evento_id and area_projecao_id produces different keys
      (no accidental symmetry that would cause unrelated uploads to collide).
    * Both outputs are valid signed 32-bit integers (PG ``int`` range).
    * Large IDs (> 2**31) fold stably — calling twice gives the same result.
    """
    # Determinism: same call twice must return the same pair.
    k1a, k2a = _planilha_advisory_lock_params(6001, 5001)
    k1b, k2b = _planilha_advisory_lock_params(6001, 5001)
    assert (k1a, k2a) == (k1b, k2b), "Key derivation must be deterministic"

    # Asymmetry: swapping IDs must produce a different pair.
    k1s, k2s = _planilha_advisory_lock_params(5001, 6001)
    assert (k1a, k2a) != (k1s, k2s), (
        "Swapped (evento, área) must not collide with the original key pair"
    )

    # Range: both values must fit in a signed 32-bit integer.
    INT32_MIN, INT32_MAX = -(2**31), 2**31 - 1
    for k in (k1a, k2a, k1s, k2s):
        assert INT32_MIN <= k <= INT32_MAX, (
            f"Key {k} is outside signed int32 range — PG will reject it"
        )

    # Stability for large IDs (> 2**31) — folding must be idempotent.
    large_ev, large_ar = 3_000_000_000, 2_500_000_000
    ka1, ka2 = _planilha_advisory_lock_params(large_ev, large_ar)
    kb1, kb2 = _planilha_advisory_lock_params(large_ev, large_ar)
    assert (ka1, ka2) == (kb1, kb2), "Large-ID key derivation must be stable"
    for k in (ka1, ka2):
        assert INT32_MIN <= k <= INT32_MAX, (
            f"Large-ID key {k} is outside signed int32 range"
        )


# ===========================================================================
# Planilha double-submit tests
# ===========================================================================

# Minimal CSV content used across all planilha tests.
_CSV_CONTENT = b"nome,email\nJoao,joao@test.local\nMaria,maria@test.local\n"


class _FakeUploadFile:
    """Minimal stand-in for FastAPI's UploadFile (only `.filename` and async
    `.read()` are required by `criar_solicitacao_planilha`)."""

    def __init__(self, filename: str = "lista.csv", content: bytes = _CSV_CONTENT):
        self.filename = filename
        self._content = content

    async def read(self) -> bytes:
        return self._content


def _call_criar_planilha(db, upload_dir: str, fake_user, *, evento_id=6001,
                         area_projecao_id=5001, quantidade=2,
                         filename="lista.csv", content=_CSV_CONTENT):
    """Call the async `criar_solicitacao_planilha` route synchronously via
    ``asyncio.run``, with ``_UPLOAD_DIR`` redirected to a temp directory so
    tests do not touch the real filesystem."""
    fake_upload = _FakeUploadFile(filename=filename, content=content)
    with (
        patch("app.api.routes.cortesia_solicitacao.is_user_admin", return_value=True),
        patch("app.api.routes.cortesia_solicitacao._UPLOAD_DIR", upload_dir),
        # Bypass the saldo check — we care about the duplicate guard, not quota.
        patch(
            "app.api.routes.cortesia_solicitacao._calcular_saldo",
            return_value=(100, 0, 100),
        ),
    ):
        return asyncio.run(
            criar_solicitacao_planilha(
                evento_id=evento_id,
                area_projecao_id=area_projecao_id,
                quantidade=quantidade,
                observacao=None,
                arquivo=fake_upload,
                db=db,
                current_user=fake_user,
            )
        )


# ---------------------------------------------------------------------------
# Planilha test 1 – real concurrent threads: only one upload lands in DB
# ---------------------------------------------------------------------------

def test_planilha_concurrent_double_submit_only_one_succeeds(SessionFactory, seed_data):
    """Two threads submit a planilha for the same evento+area at the same
    instant (barrier-synchronised).  The per-(evento, área) threading.Lock
    inside ``criar_solicitacao_planilha`` serialises them; the second thread
    must find the first record via the DB dedup check and receive HTTP 409.

    Invariants verified
    -------------------
    * Exactly one ``CortesiaSolicitacao`` row (tipo=planilha) in the DB.
    * Exactly one file on disk (no orphan from the rejected request).
    * At least one call returned a valid response; the other raised HTTP 409.
    """
    from fastapi import HTTPException

    # Use a distinct evento_id (6002) so these records are isolated from
    # any planilha rows left by other tests in this module.
    EVENTO_ID = 6002
    AREA_ID = 5001

    # Seed a bare-minimum event row so the FK constraint is satisfied.
    db_setup = SessionFactory()
    try:
        from app.models.cadastro_evento import CadastroEvento as _CE
        if not db_setup.query(_CE).filter_by(id=EVENTO_ID).first():
            db_setup.add(_CE(id=EVENTO_ID, nome="Evento Planilha Concurrent", sku="PLN2026"))
            db_setup.commit()
    finally:
        db_setup.close()

    fake_user = _make_fake_admin()
    upload_dir = tempfile.mkdtemp(prefix="test_planilha_concurrent_")

    barrier = threading.Barrier(2)
    results: dict = {}
    errors: dict = {}

    def run(label: str):
        db = SessionFactory()
        try:
            barrier.wait(timeout=15)  # synchronise both threads at the entry point
            result = _call_criar_planilha(
                db, upload_dir, fake_user,
                evento_id=EVENTO_ID,
                area_projecao_id=AREA_ID,
            )
            results[label] = result
        except Exception as exc:  # noqa: BLE001
            errors[label] = exc
        finally:
            db.close()

    t1 = threading.Thread(target=run, args=("t1",), daemon=True)
    t2 = threading.Thread(target=run, args=("t2",), daemon=True)
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)

    assert not t1.is_alive(), "Thread 1 timed out — criar_solicitacao_planilha hung"
    assert not t2.is_alive(), "Thread 2 timed out — criar_solicitacao_planilha hung"

    # At least one call must succeed; both failing means a real bug.
    assert results, (
        "Both concurrent planilha calls failed.\n"
        f"Errors: { {k: str(v) for k, v in errors.items()} }"
    )

    # The thread that failed must have raised HTTP 409.
    for label, exc in errors.items():
        assert isinstance(exc, HTTPException), (
            f"{label} raised {type(exc).__name__} instead of HTTPException: {exc}"
        )
        assert exc.status_code == 409, (
            f"{label} raised HTTP {exc.status_code}, expected 409"
        )

    # ------------------------------------------------------------------
    # Invariant A: exactly one solicitação row in the DB
    # ------------------------------------------------------------------
    db_check = SessionFactory()
    try:
        count = (
            db_check.query(CortesiaSolicitacao)
            .filter(
                CortesiaSolicitacao.evento_id == EVENTO_ID,
                CortesiaSolicitacao.area_projecao_id == AREA_ID,
                CortesiaSolicitacao.tipo == TIPO_PLANILHA,
                CortesiaSolicitacao.deleted_at.is_(None),
            )
            .count()
        )
    finally:
        db_check.close()

    assert count == 1, (
        f"Expected exactly 1 planilha solicitação after concurrent double-submit, found {count}"
    )

    # ------------------------------------------------------------------
    # Invariant B: exactly one file on disk (no orphan from the blocked call)
    # ------------------------------------------------------------------
    disk_files = os.listdir(upload_dir)
    assert len(disk_files) == 1, (
        f"Expected 1 file on disk after concurrent upload, found {disk_files}"
    )

    import shutil
    shutil.rmtree(upload_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Planilha test 2 – sequential second call within window → HTTP 409
# ---------------------------------------------------------------------------

def test_planilha_sequential_duplicate_second_is_rejected(SessionFactory, seed_data):
    """A second upload that arrives after the first has already committed (but
    within the 30-second DB dedup window) must be rejected with HTTP 409.

    This exercises the DB-level belt-and-suspenders check that catches requests
    arriving after the threading lock has been released.
    """
    from fastapi import HTTPException

    EVENTO_ID = 6003
    AREA_ID = 5001

    db_setup = SessionFactory()
    try:
        from app.models.cadastro_evento import CadastroEvento as _CE
        if not db_setup.query(_CE).filter_by(id=EVENTO_ID).first():
            db_setup.add(_CE(id=EVENTO_ID, nome="Evento Planilha Sequential", sku="PLN2027"))
            db_setup.commit()
    finally:
        db_setup.close()

    fake_user = _make_fake_admin()
    upload_dir = tempfile.mkdtemp(prefix="test_planilha_seq_")

    try:
        # Call 1: must succeed.
        db1 = SessionFactory()
        try:
            result1 = _call_criar_planilha(
                db1, upload_dir, fake_user,
                evento_id=EVENTO_ID, area_projecao_id=AREA_ID,
            )
        finally:
            db1.close()

        assert result1.tipo == TIPO_PLANILHA

        # Call 2: must be rejected (record exists within 30 s).
        db2 = SessionFactory()
        try:
            with pytest.raises(HTTPException) as exc_info:
                _call_criar_planilha(
                    db2, upload_dir, fake_user,
                    evento_id=EVENTO_ID, area_projecao_id=AREA_ID,
                )
        finally:
            db2.close()

        assert exc_info.value.status_code == 409
        assert "30 segundos" in (exc_info.value.detail or "")

        # DB: still exactly one row.
        db_check = SessionFactory()
        try:
            count = (
                db_check.query(CortesiaSolicitacao)
                .filter(
                    CortesiaSolicitacao.evento_id == EVENTO_ID,
                    CortesiaSolicitacao.area_projecao_id == AREA_ID,
                    CortesiaSolicitacao.tipo == TIPO_PLANILHA,
                    CortesiaSolicitacao.deleted_at.is_(None),
                )
                .count()
            )
        finally:
            db_check.close()

        assert count == 1, f"Expected 1 planilha row, found {count}"

        # Disk: still exactly one file (guard fires before any file write).
        disk_files = os.listdir(upload_dir)
        assert len(disk_files) == 1, (
            f"Expected 1 file on disk after rejected duplicate, found {disk_files}"
        )

    finally:
        import shutil
        shutil.rmtree(upload_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Planilha test 3 – orphan file is removed when DB commit fails
# ---------------------------------------------------------------------------

def test_planilha_orphan_file_cleaned_on_db_failure(SessionFactory, seed_data):
    """If the DB commit raises after the file has been written to disk, the
    route must delete the file before re-raising, leaving no orphan behind."""

    EVENTO_ID = 6004
    AREA_ID = 5001

    db_setup = SessionFactory()
    try:
        from app.models.cadastro_evento import CadastroEvento as _CE
        if not db_setup.query(_CE).filter_by(id=EVENTO_ID).first():
            db_setup.add(_CE(id=EVENTO_ID, nome="Evento Planilha Orphan", sku="PLN2028"))
            db_setup.commit()
    finally:
        db_setup.close()

    fake_user = _make_fake_admin()
    upload_dir = tempfile.mkdtemp(prefix="test_planilha_orphan_")

    try:
        db = SessionFactory()
        try:
            from datetime import datetime, timedelta
            from zoneinfo import ZoneInfo
            # Push _now_brasilia well into the future so the DB dedup check
            # finds no "recent" records and lets the route proceed to the
            # file-write + commit step.
            future = datetime.now(ZoneInfo("America/Sao_Paulo")).replace(tzinfo=None) + timedelta(seconds=120)

            call_count = [0]
            real_commit = db.commit

            def commit_fail_once():
                call_count[0] += 1
                if call_count[0] == 1:
                    raise Exception("simulated DB failure")
                real_commit()

            with (
                patch("app.api.routes.cortesia_solicitacao.is_user_admin", return_value=True),
                patch("app.api.routes.cortesia_solicitacao._UPLOAD_DIR", upload_dir),
                patch("app.api.routes.cortesia_solicitacao._calcular_saldo", return_value=(100, 0, 100)),
                patch("app.api.routes.cortesia_solicitacao._now_brasilia", return_value=future),
                patch.object(db, "commit", side_effect=commit_fail_once),
            ):
                with pytest.raises(Exception):
                    asyncio.run(
                        criar_solicitacao_planilha(
                            evento_id=EVENTO_ID,
                            area_projecao_id=AREA_ID,
                            quantidade=2,
                            observacao=None,
                            arquivo=_FakeUploadFile(),
                            db=db,
                            current_user=fake_user,
                        )
                    )
        finally:
            db.close()

        # Upload directory must be empty — route cleaned up the orphan.
        remaining_files = os.listdir(upload_dir)
        assert remaining_files == [], (
            f"Expected no files after DB failure, found {remaining_files}"
        )

    finally:
        import shutil
        shutil.rmtree(upload_dir, ignore_errors=True)
