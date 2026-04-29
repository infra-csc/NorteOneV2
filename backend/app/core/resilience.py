"""
Resilience primitives shared by Magento/Ativo data fetchers.

- `CircuitBreaker`: trips after N failures within a sliding window and rejects
  calls for a cooldown period, giving the upstream DB time to recover instead
  of being hammered by retries while it is already saturated.

- `CoalescingCache`: thread-safe per-key TTL cache with single-flight semantics.
  When many concurrent callers ask for the same key, only the first executes
  the fetch; the rest wait and reuse the same result. Eliminates the
  "thundering herd" problem when multiple users click the same button at once.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitOpenError(Exception):
    """Raised by CircuitBreaker.call when the breaker is open."""


class CircuitBreaker:
    """Sliding-window circuit breaker.

    States:
      - CLOSED: requests pass through; failures are tracked.
      - OPEN: all calls raise CircuitOpenError until cooldown elapses.
      - HALF-OPEN (implicit): after cooldown, the next call is allowed; if it
        succeeds the breaker fully closes, if it fails the breaker re-opens.

    Thread-safe.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        cooldown_s: float = 60.0,
        window_s: float = 120.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_s = cooldown_s
        self.window_s = window_s
        self._lock = threading.Lock()
        self._failures: list[float] = []  # timestamps of recent failures
        self._opened_at: Optional[float] = None

    def _prune_locked(self, now: float) -> None:
        cutoff = now - self.window_s
        self._failures = [t for t in self._failures if t >= cutoff]

    def is_open(self) -> bool:
        """True if calls should be rejected right now."""
        with self._lock:
            if self._opened_at is None:
                return False
            if time.time() - self._opened_at < self.cooldown_s:
                return True
            # Cooldown elapsed → half-open; allow next call.
            self._opened_at = None
            self._failures = []
            logger.info(f"CircuitBreaker '{self.name}' half-open: allowing trial call")
            return False

    def record_success(self) -> None:
        with self._lock:
            if self._opened_at is not None or self._failures:
                logger.info(f"CircuitBreaker '{self.name}' reset after success")
            self._opened_at = None
            self._failures = []

    def record_failure(self) -> None:
        with self._lock:
            now = time.time()
            self._prune_locked(now)
            self._failures.append(now)
            if (
                self._opened_at is None
                and len(self._failures) >= self.failure_threshold
            ):
                self._opened_at = now
                logger.warning(
                    f"CircuitBreaker '{self.name}' OPEN — {len(self._failures)} "
                    f"falhas em {self.window_s:.0f}s; bloqueando chamadas por "
                    f"{self.cooldown_s:.0f}s"
                )

    def call(self, fn: Callable[..., T], *args, **kwargs) -> T:
        """Execute fn() through the breaker. Raises CircuitOpenError if open."""
        if self.is_open():
            raise CircuitOpenError(
                f"Circuit '{self.name}' aberto (cooldown ativo de "
                f"{self.cooldown_s:.0f}s)"
            )
        try:
            result = fn(*args, **kwargs)
        except Exception:
            self.record_failure()
            raise
        else:
            self.record_success()
            return result

    def status(self) -> dict:
        with self._lock:
            now = time.time()
            self._prune_locked(now)
            return {
                "name": self.name,
                "open": self._opened_at is not None
                and now - self._opened_at < self.cooldown_s,
                "recent_failures": len(self._failures),
                "opened_at": self._opened_at,
                "cooldown_s": self.cooldown_s,
            }


class CoalescingCache:
    """Thread-safe TTL cache with single-flight (request coalescing).

    When N concurrent callers ask for the same key while no fresh value exists,
    exactly one runs the fetch function; the others block on a per-key lock and
    return the same result without executing the fetch themselves.

    This protects the upstream MySQL pool when many users click the same
    "Atualizar Hoje" button (or load the same dashboard tile) at the same time.
    """

    def __init__(self, ttl_s: float, name: str = ""):
        self.ttl_s = ttl_s
        self.name = name
        self._global_lock = threading.Lock()
        self._data: dict[Any, tuple[float, Any]] = {}  # key -> (ts, value)
        self._key_locks: dict[Any, threading.Lock] = {}

    def _get_key_lock(self, key: Any) -> threading.Lock:
        with self._global_lock:
            lk = self._key_locks.get(key)
            if lk is None:
                lk = threading.Lock()
                self._key_locks[key] = lk
            return lk

    def get_fresh(self, key: Any) -> Optional[Any]:
        """Return the cached value for key if it's still within TTL, else None."""
        with self._global_lock:
            entry = self._data.get(key)
            if entry and time.time() - entry[0] < self.ttl_s:
                return entry[1]
            return None

    def set(self, key: Any, value: Any) -> None:
        with self._global_lock:
            self._data[key] = (time.time(), value)

    def invalidate(self, key: Any = None) -> None:
        with self._global_lock:
            if key is None:
                self._data.clear()
            else:
                self._data.pop(key, None)

    def get_or_compute(self, key: Any, fn: Callable[[], T]) -> T:
        """Return cached value if fresh, otherwise compute it (single-flight)."""
        # Fast path — no lock contention if value is already fresh.
        fresh = self.get_fresh(key)
        if fresh is not None:
            return fresh

        # Slow path: acquire per-key lock so only one caller computes.
        key_lock = self._get_key_lock(key)
        wait_started = time.time()
        with key_lock:
            waited = time.time() - wait_started
            # Re-check after acquiring the lock — the leader may have just
            # populated the cache while we were waiting.
            fresh = self.get_fresh(key)
            if fresh is not None:
                if waited > 0.05 and self.name:
                    logger.debug(
                        f"CoalescingCache[{self.name}] coalesced wait={waited:.2f}s "
                        f"key={key}"
                    )
                return fresh
            value = fn()
            self.set(key, value)
            return value
