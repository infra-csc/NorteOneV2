import os
import sys

# Ensure the backend root (which contains the `app` package) is importable
# regardless of the directory pytest is invoked from.
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

# ---------------------------------------------------------------------------
# SQLite compatibility shim for Postgres-only column types
# ---------------------------------------------------------------------------
# Several app models (e.g. evento_detail_snapshot, nori_insights) use
# sqlalchemy.dialects.postgresql.JSONB.  When the full test suite is collected
# and run together, pytest imports every test module before running any of
# them.  That means *all* models — including those with JSONB columns — end up
# registered in the single shared Base.metadata by the time the first fixture
# calls Base.metadata.create_all(sqlite_engine).  SQLite has no JSONB compiler,
# so the whole create_all blows up with:
#
#   AttributeError: 'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'
#
# The fix: register a cross-dialect compiler shim that maps JSONB → TEXT for
# any dialect that doesn't natively support it (i.e. anything that isn't
# Postgres).  This must happen at import time — before any test module's
# engine fixture fires — so it lives here in conftest.py, which pytest always
# loads first.
from sqlalchemy.dialects.postgresql import JSONB as _JSONB
from sqlalchemy.ext.compiler import compiles as _compiles
from sqlalchemy import Text as _Text


@_compiles(_JSONB, "sqlite")
def _compile_jsonb_as_text_sqlite(type_, compiler, **kw):
    """Render JSONB as TEXT on SQLite so create_all doesn't crash."""
    return "TEXT"
