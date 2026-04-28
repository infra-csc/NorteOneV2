"""Retry helpers for transient database failures.

Centralizes the policy for retrying transient errors against external
databases (Magento, Ativo). All Magento queries should go through
``magento_run`` so that connection drops, MySQL session timeouts and
short network blips are recovered automatically without losing data
or polluting endpoints with custom retry logic.

Design notes
------------
* Magento queries we issue are always read-only (SELECT). Retries are
  therefore safe — there is no risk of duplicate writes.
* Two profiles are exposed:

  - ``"request"``  — used in the user request path. Short backoff,
    few attempts so a single Magento incident does not freeze the UI.
  - ``"background"`` — used by warmup, snapshot rebuilds and other
    non-blocking jobs. Slightly more aggressive retry to ride out
    longer hiccups without giving up.

* Retry only fires for errors classified as transient by
  :func:`_is_retryable_magento_error`. Programming errors (bad SQL,
  integrity violations, etc.) propagate immediately so bugs are not
  hidden behind retries.
"""

from __future__ import annotations

import logging
import socket
import time
from typing import Any, Callable, Dict

from sqlalchemy.exc import (
    DBAPIError,
    InterfaceError,
    OperationalError,
    TimeoutError as SATimeoutError,
)

import app.core.database as db_module

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

# Each profile defines:
#   - max_attempts: total attempts (including the first)
#   - backoff_base: seconds for the first wait; subsequent waits are
#     exponential (base, base*2, base*4, ...)
#   - max_backoff: hard cap so we never sleep an absurd amount
_PROFILES: Dict[str, Dict[str, float]] = {
    "request": {
        "max_attempts": 2,
        "backoff_base": 0.5,
        "max_backoff": 1.0,
    },
    "background": {
        "max_attempts": 3,
        "backoff_base": 1.0,
        "max_backoff": 4.0,
    },
}


# Substrings that indicate a transient transport-level failure even when the
# raised exception class is generic.
_RETRYABLE_MESSAGE_FRAGMENTS = (
    "lost connection",
    "server has gone away",
    "can't connect",
    "broken pipe",
    "connection reset",
    "connection refused",
    "connection aborted",
    "ssh tunnel",
    "timed out",
    "max retries exceeded",
    "operation timed out",
    "too many connections",
)


def _is_retryable_magento_error(exc: BaseException) -> bool:
    """Return True if ``exc`` looks like a transient Magento DB error."""
    # SQLAlchemy / DB-API errors that are usually transient
    if isinstance(exc, (OperationalError, InterfaceError, SATimeoutError)):
        return True
    if isinstance(exc, DBAPIError):
        # ``connection_invalidated`` is set by SQLAlchemy when it had to
        # invalidate the connection (typically after a transient error).
        if getattr(exc, "connection_invalidated", False):
            return True

    # Plain socket-level errors
    if isinstance(exc, (socket.timeout, ConnectionError, OSError)):
        return True

    # Fallback: inspect message text for known transient signatures
    msg = str(exc).lower()
    return any(frag in msg for frag in _RETRYABLE_MESSAGE_FRAGMENTS)


class MagentoEngineUnavailable(RuntimeError):
    """Raised when the Magento engine is not configured.

    This is *not* a transient error — retrying will not help. We surface
    it as a distinct exception so callers can decide whether to swallow
    or propagate.
    """


def magento_run(
    work_fn: Callable[[Any], Any],
    *,
    label: str,
    profile: str = "request",
) -> Any:
    """Execute ``work_fn(connection)`` with automatic retry on transient errors.

    Parameters
    ----------
    work_fn:
        Callable receiving an open SQLAlchemy connection. May execute
        any number of statements. Must be **idempotent** (Magento
        queries are read-only, so this is naturally satisfied).
    label:
        Short, human-readable identifier used in log lines.
    profile:
        ``"request"`` (low-latency) or ``"background"`` (more
        aggressive). Defaults to ``"request"``.

    Returns
    -------
    Whatever ``work_fn`` returns.

    Raises
    ------
    MagentoEngineUnavailable
        If the Magento engine is not configured (no retry).
    Exception
        The last exception raised by ``work_fn`` after retries are
        exhausted, or any non-retryable exception immediately.
    """
    cfg = _PROFILES.get(profile)
    if cfg is None:
        raise ValueError(f"Unknown magento_run profile: {profile!r}")

    engine = db_module.engine_magento
    if engine is None:
        raise MagentoEngineUnavailable("engine_magento não configurado")

    max_attempts = int(cfg["max_attempts"])
    backoff_base = float(cfg["backoff_base"])
    max_backoff = float(cfg["max_backoff"])

    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            with engine.connect() as conn:
                result = work_fn(conn)
                if attempt > 1:
                    logger.info(
                        f"[Magento][{label}] OK na tentativa {attempt}/{max_attempts}"
                    )
                return result
        except MagentoEngineUnavailable:
            raise
        except Exception as e:
            last_exc = e
            retryable = _is_retryable_magento_error(e)
            if not retryable or attempt >= max_attempts:
                if attempt > 1:
                    logger.error(
                        f"[Magento][{label}] desistiu após {attempt}/{max_attempts} "
                        f"tentativas: {type(e).__name__}: {str(e)[:200]}"
                    )
                raise
            backoff = min(backoff_base * (2 ** (attempt - 1)), max_backoff)
            logger.warning(
                f"[Magento][{label}] tentativa {attempt}/{max_attempts} falhou "
                f"({type(e).__name__}: {str(e)[:160]}), retry em {backoff:.1f}s"
            )
            time.sleep(backoff)

    # Defensive — loop above always returns or raises
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"[Magento][{label}] estado inesperado em magento_run")
