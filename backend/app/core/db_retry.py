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
import threading
import time
from collections import deque
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
# Circuit breaker — protege Magento de avalanches de queries quando o servidor
# remoto está degradado. Quando _CIRCUIT_THRESHOLD falhas acontecem na janela
# _CIRCUIT_WINDOW_S para o mesmo label, o circuito abre por
# _CIRCUIT_OPEN_DURATION_S e novas tentativas falham imediatamente com
# MagentoCircuitOpen (subclasse de MagentoEngineUnavailable) — os callers
# existentes já tratam essa exceção servindo snapshot persistido.
# ---------------------------------------------------------------------------
_CIRCUIT_WINDOW_S = 60.0
_CIRCUIT_THRESHOLD = 5
_CIRCUIT_OPEN_DURATION_S = 60.0

_circuit_lock = threading.Lock()
_circuit_failures: Dict[str, deque] = {}
_circuit_open_until: Dict[str, float] = {}


def _circuit_remaining_open(label: str) -> float:
    """Retorna segundos restantes se o circuito está aberto para `label`, senão 0.0."""
    with _circuit_lock:
        open_until = _circuit_open_until.get(label)
        if open_until is None:
            return 0.0
        now = time.monotonic()
        if now >= open_until:
            _circuit_open_until.pop(label, None)
            return 0.0
        return open_until - now


def _circuit_record_failure(label: str) -> None:
    """Registra uma falha; abre o circuito se atingir o threshold na janela."""
    now = time.monotonic()
    with _circuit_lock:
        if label in _circuit_open_until:
            # já aberto — não conta falhas adicionais
            return
        dq = _circuit_failures.setdefault(label, deque())
        cutoff = now - _CIRCUIT_WINDOW_S
        while dq and dq[0] < cutoff:
            dq.popleft()
        dq.append(now)
        if len(dq) >= _CIRCUIT_THRESHOLD:
            _circuit_open_until[label] = now + _CIRCUIT_OPEN_DURATION_S
            dq.clear()
            logger.warning(
                f"[Magento][{label}] CIRCUIT OPEN: {_CIRCUIT_THRESHOLD} falhas em "
                f"{_CIRCUIT_WINDOW_S:.0f}s — pausando chamadas por "
                f"{_CIRCUIT_OPEN_DURATION_S:.0f}s (snapshots vão servir como piso)"
            )


def _circuit_record_success(label: str) -> None:
    """Limpa o histórico de falhas e fecha o circuito após sucesso."""
    with _circuit_lock:
        had_open = _circuit_open_until.pop(label, None)
        _circuit_failures.pop(label, None)
    if had_open:
        logger.info(f"[Magento][{label}] CIRCUIT CLOSED: chamada bem-sucedida, retomando normal")


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
    # Single-attempt profile for interactive/real-time paths (e.g. "Atualizar Hoje").
    # No retry: if the query fails it fails fast. MAX_EXECUTION_TIME on the SQL side
    # caps execution at 12s; combined with read_timeout=90s this guarantees the thread
    # never blocks longer than ~90s regardless of MySQL behaviour.
    "once": {
        "max_attempts": 1,
        "backoff_base": 0.0,
        "max_backoff": 0.0,
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
        # Error 3024 = MAX_EXECUTION_TIME exceeded — the server processed the
        # query but killed it because it was too slow.  Retrying immediately
        # will produce the same result and wastes another full timeout window.
        # Treat it as non-retryable so we fail fast.
        _orig = getattr(exc, "orig", None)
        if _orig is not None:
            _code = getattr(_orig, "args", (None,))[0]
            if _code == 3024:
                return False
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


class MagentoCircuitOpen(MagentoEngineUnavailable):
    """Raised when too many recent Magento failures opened the circuit breaker.

    Herda de MagentoEngineUnavailable para que callers existentes que já
    tratam o engine indisponível (servindo snapshot persistido) façam a
    coisa certa automaticamente, sem necessidade de novo handler.
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

    # Circuit breaker: se está aberto para este label, falha imediato.
    # Callers já tratam MagentoEngineUnavailable servindo snapshot.
    _remaining = _circuit_remaining_open(label)
    if _remaining > 0:
        logger.info(
            f"[Magento][{label}] circuito aberto ({_remaining:.0f}s restantes) — "
            "pulando chamada, snapshot vai responder"
        )
        raise MagentoCircuitOpen(
            f"Magento circuit breaker aberto para '{label}' ({_remaining:.0f}s restantes)"
        )

    # Release any idle local PG connections held by this request thread
    # before we start waiting on Magento. Magento queries can block for
    # tens of seconds on slow plans / timeouts; holding a local pool slot
    # the whole time has caused QueuePool exhaustion under load and made
    # unrelated endpoints (e.g. /api/admin/sku-mappings/grupos) return 500.
    try:
        released = db_module.release_local_db_connections()
        if released:
            logger.debug(
                f"[Magento][{label}] liberou {released} conexão(ões) PG local(is) antes da chamada"
            )
    except Exception as _re:
        logger.debug(f"[Magento][{label}] release_local_db_connections falhou: {_re}")

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
                _circuit_record_success(label)
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
                _circuit_record_failure(label)
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
