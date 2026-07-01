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
import os
import socket
import threading
import time
from collections import deque
from typing import Any, Callable, Dict, Optional

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


# ---------------------------------------------------------------------------
# Semáforo de concorrência Magento — limita quantas queries podem rodar ao
# MESMO TEMPO contra o MySQL externo (conexão TCP/IP direta, sem SSH tunnel).
# Sem isso, basta o usuário abrir 5 grupos diferentes em sequência para
# saturar o servidor remoto (cada grupo fan-out 3-7 queries pesadas via
# force_magento_refresh).
#
# Política por profile (TODOS passam pelo slot único — concorrência=1):
#   - "request"/"once" (interativos: clicks do usuário, "Atualizar Hoje",
#     today-sales): adquirem o slot com PRIORIDADE. Acquire com timeout
#     generoso (default 180s) — preferimos esperar na fila a derrubar a
#     request com snapshot stale.
#   - "background" (scheduler/warmup/job noturno, kit_cost_batch, curvas):
#     também gated pelo mesmo slot, MAS CEDE a vez enquanto houver interativo
#     na fila. À noite (sem usuários) roda serializado sem perda de throughput
#     — o túnel não paraleliza mesmo. De dia, não inunda mais o Magento nem
#     starva o "Atualizar Hoje". (Antes "background" ignorava o semáforo e o
#     batch das 17h + kit_cost saturavam o túnel, zerando as vendas de hoje.)
#
# Configurável via env: MAGENTO_MAX_CONCURRENCY (default 1) controla o slot.
# MAGENTO_ACQUIRE_TIMEOUT_S (default 60) é o tempo máximo na fila antes de
# cair pra snapshot piso. Baixado de 180→60 porque a thread que espera fica
# PRESA no threadpool compartilhado do FastAPI; segurá-la por 180s starva
# /auth/login e demais rotas síncronas sob carga.
# IMPORTANTE: o gargalo NÃO é rede/túnel — o Magento é conexão TCP/IP direta
# ao MySQL. É o próprio servidor MySQL do Magento que NÃO suporta queries
# pesadas em paralelo: subir a concorrência (já tentamos 3) satura o servidor
# e o MySQL mata as queries com erro 3024 (max statement execution time),
# gerando 429s e vendas de "hoje" zeradas. Mantenha a concorrência em 1.
# ---------------------------------------------------------------------------
_MAGENTO_MAX_CONCURRENCY = max(1, int(os.getenv("MAGENTO_MAX_CONCURRENCY", "1")))
_MAGENTO_ACQUIRE_TIMEOUT_S = float(os.getenv("MAGENTO_ACQUIRE_TIMEOUT_S", "60"))
_magento_concurrency_sem = threading.BoundedSemaphore(_MAGENTO_MAX_CONCURRENCY)

# Prioridade interativa sobre background.
# O slot do túnel é único (concorrência=1) e TODOS os profiles passam por ele
# — inclusive "background", porque queries de background disparadas durante o
# dia (kit_cost_batch, curvas, e o batch das 17h sincronizar_hoje) inundavam o
# túnel em paralelo, saturavam o servidor Magento e faziam a query interativa
# ("Atualizar Hoje", today-sales) estourar timeout mesmo com concorrência=1.
# Para o usuário não ficar preso atrás do batch, uma query "background" CEDE a
# vez enquanto houver qualquer thread interativa (request/once) esperando o
# slot. Não há preempção de query em execução (não dá pra matar um SQL no meio),
# então o pior caso de espera interativa é ~1 query de background em andamento.
_interactive_waiting_lock = threading.Lock()
_interactive_waiting = 0
_BG_YIELD_POLL_S = 0.25  # de quanto em quanto o background re-checa se há interativo na fila

# Teto de chamadas que podem estar OCUPANDO uma thread dentro de magento_run
# ao mesmo tempo (esperando o slot único OU executando). O Magento roda no
# MESMO threadpool do FastAPI que serve TODAS as rotas síncronas — inclusive
# /auth/login. Sem esse teto, uma rajada de queries Magento, cada uma segurando
# a thread por até MAGENTO_ACQUIRE_TIMEOUT_S, esgota o pool e trava o login e o
# resto do sistema (mesmo para usuários que nem abrem telas de Magento). Ao
# estourar o teto, a chamada cai NA HORA para o snapshot piso (mesmo
# comportamento do timeout de fila), sem segurar a thread. Configurável via env.
_MAGENTO_MAX_PENDING = max(1, int(os.getenv("MAGENTO_MAX_PENDING", "12")))
# Teto MENOR para profiles "background" (scheduler/warmup/jobs): reserva as
# vagas restantes (_MAGENTO_MAX_PENDING - _MAGENTO_MAX_PENDING_BG) exclusivamente
# para chamadas interativas (clicks do usuário, "Atualizar Hoje"). Assim uma
# rajada de background não impede a admissão de uma request interativa nem a
# empurra cedo demais para snapshot. Default 8 (reserva 4 vagas p/ interativo).
_MAGENTO_MAX_PENDING_BG = min(
    _MAGENTO_MAX_PENDING,
    max(1, int(os.getenv("MAGENTO_MAX_PENDING_BG", "8"))),
)
_magento_pending_lock = threading.Lock()
_magento_pending = 0

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
    acquire_timeout: Optional[float] = None,
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

    # TODOS os profiles passam pelo slot único do túnel (concorrência=1) — ver
    # nota no topo do arquivo sobre por que background também é gated. Profiles
    # interativos (request/once) têm prioridade: background cede a vez enquanto
    # houver interativo na fila.
    global _interactive_waiting, _magento_pending
    _is_interactive = profile in ("request", "once")
    # Timeout de fila por chamada: o caller (ex.: "Atualizar Hoje") pode passar
    # um teto curto alinhado ao seu próprio orçamento de thread, evitando query
    # "zumbi" que continua ocupando o slot (e, sendo interativa, segura o
    # background) muito depois do endpoint já ter caído para snapshot.
    _acq_to = acquire_timeout if acquire_timeout is not None else _MAGENTO_ACQUIRE_TIMEOUT_S

    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        _sem_acquired = False
        _iw_incremented = False
        _pending_incremented = False
        _wait_started = time.time()
        try:
            # Teto de ocupação do threadpool compartilhado: se já há chamadas
            # Magento demais bloqueadas/ativas (esperando o slot único ou
            # executando), NÃO segura mais uma thread — cai já para o snapshot
            # piso. Sem isso, uma rajada de queries Magento esgota o threadpool
            # do FastAPI e trava /auth/login e todas as rotas síncronas.
            _pending_cap = _MAGENTO_MAX_PENDING if _is_interactive else _MAGENTO_MAX_PENDING_BG
            with _magento_pending_lock:
                if _magento_pending >= _pending_cap:
                    logger.warning(
                        f"[Magento][{label}] saturado: {_magento_pending} chamada(s) "
                        f"em andamento ≥ teto {_pending_cap} (profile={profile}) — não "
                        f"enfileira, cai para snapshot (protege threadpool/login)."
                    )
                    raise MagentoEngineUnavailable(
                        f"Magento saturado ({_magento_pending} em andamento ≥ {_pending_cap})"
                    )
                _magento_pending += 1
                _pending_incremented = True
            # Serializa o acesso ao MySQL externo do Magento (conexão TCP/IP
            # direta). Sem isso, queries em paralelo saturam o servidor remoto e
            # geram timeouts em cascata (erro 3024).
            if _is_interactive:
                # Sinaliza presença na fila para que o background ceda a vez.
                with _interactive_waiting_lock:
                    _interactive_waiting += 1
                _iw_incremented = True
            else:
                # Background cede enquanto houver interativo esperando, até o
                # deadline de aquisição (depois prossegue para não travar jobs).
                _yield_deadline = _wait_started + _acq_to
                while True:
                    with _interactive_waiting_lock:
                        _iw = _interactive_waiting
                    if _iw == 0 or time.time() >= _yield_deadline:
                        break
                    time.sleep(_BG_YIELD_POLL_S)

            try:
                _sem_acquired = _magento_concurrency_sem.acquire(
                    timeout=_acq_to
                )
            finally:
                # Assim que adquirimos (ou desistimos) não estamos mais "na
                # fila" — liberamos o background a competir pelo próximo slot.
                if _iw_incremented:
                    with _interactive_waiting_lock:
                        _interactive_waiting -= 1
                    _iw_incremented = False

            if not _sem_acquired:
                logger.warning(
                    f"[Magento][{label}] fila cheia — desistiu após "
                    f"{_acq_to:.0f}s aguardando vaga. "
                    f"Cai para snapshot."
                )
                raise MagentoEngineUnavailable(
                    f"Fila Magento cheia ({_MAGENTO_MAX_CONCURRENCY} concorrentes ocupados)"
                )
            _waited = time.time() - _wait_started
            if _waited > 1.0:
                logger.info(
                    f"[Magento][{label}] esperou {_waited:.1f}s na fila "
                    f"(concorrência={_MAGENTO_MAX_CONCURRENCY}, profile={profile})"
                )
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
        finally:
            if _pending_incremented:
                with _magento_pending_lock:
                    _magento_pending -= 1
                _pending_incremented = False
            if _sem_acquired:
                try:
                    _magento_concurrency_sem.release()
                except ValueError:
                    # BoundedSemaphore lança se release for chamado a mais.
                    # Não deve acontecer (acquire/release pareados), mas
                    # protegemos pra não derrubar o caller.
                    logger.debug(f"[Magento][{label}] semaphore release a mais — ignorado")

    # Defensive — loop above always returns or raises
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"[Magento][{label}] estado inesperado em magento_run")
