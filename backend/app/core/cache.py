import os
import time
import json
import threading
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Optional, Callable
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def _scheduler_in_quiet_hours() -> bool:
    """Retorna True se o horário BRT atual cai na janela silenciosa do scheduler.

    Configurável via env SCHEDULER_QUIET_HOURS_START (default 22) e
    SCHEDULER_QUIET_HOURS_END (default 6). Durante a janela, callbacks do
    scheduler de 45/90 min são pulados (re-agendamento normal continua),
    cortando carga no Magento em horários sem usuários. Jobs por horário
    fixo (02h consolidação, 05h refresh, 17h refresh) NÃO são afetados —
    eles têm timers próprios.

    Se start == end, janela desabilitada (sempre False).
    """
    try:
        _start = int(os.getenv("SCHEDULER_QUIET_HOURS_START", "22"))
        _end = int(os.getenv("SCHEDULER_QUIET_HOURS_END", "6"))
    except (TypeError, ValueError):
        return False
    if _start == _end:
        return False
    _now_h = datetime.now(ZoneInfo("America/Sao_Paulo")).hour
    if _start < _end:
        return _start <= _now_h < _end
    # Janela atravessa meia-noite (ex.: 22→6)
    return _now_h >= _start or _now_h < _end

CURRENT_YEAR_TTL = 79200
HISTORICAL_TTL = None
MAX_STALE_AGE = 172800
NIGHTLY_CACHE_TTL = 79200

_last_full_refresh_timestamp = None
_last_sync_hoje_timestamp = None
_last_sync_hoje_lock = threading.Lock()
_full_refresh_in_progress = False

# ---------------------------------------------------------------------------
# Global "sincronizar hoje" mutex
# Garante que apenas UMA operação de sync-hoje rode por vez, seja via
# endpoint manual, por evento, ou pelo loop automático de 20 minutos.
# ---------------------------------------------------------------------------
_SYNC_HOJE_GLOBAL_LOCK = threading.Lock()
_SYNC_HOJE_RUNNING_BY: Optional[str] = None


def try_acquire_sync_hoje(caller: str = "sistema") -> bool:
    """Tenta adquirir o lock global de sync-hoje (batch/sistema).
    Retorna True se o lock foi adquirido, False se já está em uso."""
    global _SYNC_HOJE_RUNNING_BY
    acquired = _SYNC_HOJE_GLOBAL_LOCK.acquire(blocking=False)
    if acquired:
        _SYNC_HOJE_RUNNING_BY = caller
    return acquired


def release_sync_hoje() -> None:
    """Libera o lock global de sync-hoje."""
    global _SYNC_HOJE_RUNNING_BY
    _SYNC_HOJE_RUNNING_BY = None
    try:
        _SYNC_HOJE_GLOBAL_LOCK.release()
    except RuntimeError:
        pass


def is_sync_hoje_running() -> bool:
    """Retorna True se uma sincronização de hoje (batch) está em andamento."""
    return _SYNC_HOJE_GLOBAL_LOCK.locked()


def get_sync_hoje_running_by() -> Optional[str]:
    """Retorna o identificador de quem está rodando o sync-hoje atual."""
    return _SYNC_HOJE_RUNNING_BY


# ---------------------------------------------------------------------------
# Lock global para sincronizações forçadas por usuário ("Atualizar Hoje")
# Garante que apenas UMA requisição manual rode por vez, independente de
# qual evento ou usuário. Enquanto este lock estiver ativo, qualquer outro
# pedido de sync recebe 409 com a mensagem de quem está ocupado.
# ---------------------------------------------------------------------------
_USER_SYNC_LOCK = threading.Lock()
_USER_SYNC_RUNNING_BY: Optional[str] = None
_USER_SYNC_EVENTO: Optional[str] = None
_USER_SYNC_STARTED_AT: Optional[float] = None
_USER_SYNC_MAX_S = 120  # auto-expira em 2 min como safety net


def try_acquire_user_sync(caller: str, evento: str = "") -> bool:
    """Tenta adquirir o lock global de sync manual.
    Retorna True se adquirido, False se já em uso por outra requisição."""
    global _USER_SYNC_RUNNING_BY, _USER_SYNC_EVENTO, _USER_SYNC_STARTED_AT
    import time as _t
    # Safety net: se o lock expirou (processo morreu sem liberar), força reset.
    if _USER_SYNC_LOCK.locked() and _USER_SYNC_STARTED_AT is not None:
        if _t.time() - _USER_SYNC_STARTED_AT > _USER_SYNC_MAX_S:
            try:
                _USER_SYNC_LOCK.release()
            except RuntimeError:
                pass
    acquired = _USER_SYNC_LOCK.acquire(blocking=False)
    if acquired:
        _USER_SYNC_RUNNING_BY = caller
        _USER_SYNC_EVENTO = evento
        _USER_SYNC_STARTED_AT = _t.time()
    return acquired


def release_user_sync() -> None:
    """Libera o lock global de sync manual."""
    global _USER_SYNC_RUNNING_BY, _USER_SYNC_EVENTO, _USER_SYNC_STARTED_AT
    _USER_SYNC_RUNNING_BY = None
    _USER_SYNC_EVENTO = None
    _USER_SYNC_STARTED_AT = None
    try:
        _USER_SYNC_LOCK.release()
    except RuntimeError:
        pass


def is_user_sync_running() -> bool:
    """Retorna True se alguma sincronização manual está em andamento."""
    return _USER_SYNC_LOCK.locked()


def get_user_sync_info() -> dict:
    """Retorna informações sobre o sync manual em andamento."""
    return {
        "running": _USER_SYNC_LOCK.locked(),
        "by": _USER_SYNC_RUNNING_BY,
        "evento": _USER_SYNC_EVENTO,
        "started_at": _USER_SYNC_STARTED_AT,
    }


# ---------------------------------------------------------------------------
# Global sync pause flag
# Quando ativo, os batch jobs verificam este flag entre iterações de grupo
# e interrompem antecipadamente, registrando status "interrompido".
# ---------------------------------------------------------------------------
_SYNC_PAUSED: bool = False
_SYNC_PAUSED_BY: Optional[str] = None
_SYNC_PAUSED_AT: Optional[datetime] = None
_sync_paused_lock = threading.Lock()


def pause_sync(by: str = "usuario") -> None:
    """Ativa o flag de pausa global dos jobs de sincronização."""
    global _SYNC_PAUSED, _SYNC_PAUSED_BY, _SYNC_PAUSED_AT
    with _sync_paused_lock:
        _SYNC_PAUSED = True
        _SYNC_PAUSED_BY = by
        _SYNC_PAUSED_AT = datetime.now(ZoneInfo("America/Sao_Paulo"))
    logger.warning(f"[SyncPause] Execuções de sync pausadas por '{by}'")


def resume_sync(by: str = "usuario") -> None:
    """Desativa o flag de pausa global dos jobs de sincronização."""
    global _SYNC_PAUSED, _SYNC_PAUSED_BY, _SYNC_PAUSED_AT
    with _sync_paused_lock:
        _SYNC_PAUSED = False
        _SYNC_PAUSED_BY = None
        _SYNC_PAUSED_AT = None
    logger.info(f"[SyncPause] Execuções de sync retomadas por '{by}'")


def is_sync_paused() -> bool:
    """Retorna True se os jobs de sincronização estão pausados."""
    return _SYNC_PAUSED


def get_sync_pause_info() -> dict:
    """Retorna informações sobre o estado de pausa atual."""
    with _sync_paused_lock:
        return {
            "paused": _SYNC_PAUSED,
            "by": _SYNC_PAUSED_BY,
            "since": _SYNC_PAUSED_AT.isoformat() if _SYNC_PAUSED_AT else None,
        }


_full_refresh_pending = False  # outra rodada enfileirada enquanto a atual estiver em andamento
_full_refresh_lock = threading.Lock()
_full_warmup_fn = None
_warmup_progress = {"step": 0, "total_steps": 4, "label": "", "started_at": None, "sub_current": 0, "sub_total": 0}
_last_refresh_error = None

_db_persist_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cache_persist")
_swr_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="cache_swr")
_swr_in_flight: set = set()
_swr_lock = threading.Lock()


def register_full_warmup_fn(fn: Callable):
    global _full_warmup_fn
    _full_warmup_fn = fn


def trigger_full_warmup_async():
    """Inicia uma rodada de aquecimento completo.

    Retorna:
      - "started"     : nova rodada iniciada agora.
      - "queued"      : já tem rodada em andamento; outra foi enfileirada para
                        rodar logo em seguida.
      - "unavailable" : função de warmup não registrada.
    """
    global _full_warmup_fn, _full_refresh_in_progress, _full_refresh_pending
    with _full_refresh_lock:
        if _full_warmup_fn is None:
            logger.warning("No full warmup function registered")
            return "unavailable"
        if _full_refresh_in_progress:
            _full_refresh_pending = True
            logger.info("[Cache] Refresh-all já em andamento — próxima rodada enfileirada")
            return "queued"
        _full_refresh_in_progress = True

    def _wrapper():
        try:
            _full_warmup_fn()
        finally:
            # Re-trigger se houve clique enquanto a rodada atual rodava.
            global _full_refresh_pending
            should_chain = False
            with _full_refresh_lock:
                if _full_refresh_pending:
                    _full_refresh_pending = False
                    should_chain = True
            if should_chain:
                logger.info("[Cache] Iniciando rodada enfileirada de refresh-all")
                trigger_full_warmup_async()

    thread = threading.Thread(target=_wrapper, daemon=True)
    thread.start()
    return "started"


def is_full_refresh_pending():
    global _full_refresh_pending
    return _full_refresh_pending


def get_last_full_refresh():
    global _last_full_refresh_timestamp
    return _last_full_refresh_timestamp


def set_last_full_refresh(ts=None):
    global _last_full_refresh_timestamp
    _last_full_refresh_timestamp = ts or time.time()
    # Persist to DB so the timestamp survives server restarts and deploys.
    try:
        _persist_to_db("__meta__", "last_full_refresh", {"ts": _last_full_refresh_timestamp})
    except Exception as _lfr_err:
        logger.warning(f"set_last_full_refresh: could not persist to DB: {_lfr_err}")


def get_last_sync_hoje():
    global _last_sync_hoje_timestamp
    with _last_sync_hoje_lock:
        return _last_sync_hoje_timestamp


def set_last_sync_hoje(ts=None):
    global _last_sync_hoje_timestamp
    with _last_sync_hoje_lock:
        _last_sync_hoje_timestamp = ts or time.time()
    # Persist so the timestamp survives server restarts and deploys.
    try:
        _persist_to_db("__meta__", "last_sync_hoje", {"ts": _last_sync_hoje_timestamp})
    except Exception as _lsh_err:
        logger.warning(f"set_last_sync_hoje: could not persist to DB: {_lsh_err}")


def is_full_refresh_in_progress():
    global _full_refresh_in_progress
    if not _full_refresh_in_progress:
        return False
    # Safety: auto-reset if the warmup flag has been stuck for more than 45 minutes.
    # This prevents permanent "Iniciando" lockout if a warmup thread crashes without
    # clearing the flag in its finally block.
    _started = _warmup_progress.get("started_at")
    if _started and (time.time() - _started) > 45 * 60:
        logger.warning("[Cache] _full_refresh_in_progress stuck for >45min — auto-resetting flag")
        with _full_refresh_lock:
            _full_refresh_in_progress = False
            _warmup_progress["step"] = 0
            _warmup_progress["label"] = ""
            _warmup_progress["started_at"] = None
        try:
            from app.services.health_alert_service import log_and_alert as _ha
            _ha("WARMUP_STUCK", "HIGH", "Atualização de dados travada por mais de 45 minutos", "O flag de refresh foi resetado automaticamente. Verifique os logs do servidor.")
        except Exception:
            pass
        return False
    return True


def set_full_refresh_in_progress(val: bool):
    global _full_refresh_in_progress
    with _full_refresh_lock:
        _full_refresh_in_progress = val
        if not val:
            _warmup_progress["step"] = 0
            _warmup_progress["label"] = ""
            _warmup_progress["started_at"] = None
            _warmup_progress["sub_current"] = 0
            _warmup_progress["sub_total"] = 0


def get_last_refresh_error():
    global _last_refresh_error
    return _last_refresh_error


def set_last_refresh_error(error_msg: Optional[str]):
    global _last_refresh_error
    _last_refresh_error = error_msg


def set_warmup_progress(step: int, label: str, sub_current: int = 0, sub_total: int = 0):
    global _warmup_progress
    with _full_refresh_lock:
        _warmup_progress["step"] = step
        _warmup_progress["label"] = label
        _warmup_progress["sub_current"] = sub_current
        _warmup_progress["sub_total"] = sub_total
        if step == 1 and _warmup_progress["started_at"] is None:
            _warmup_progress["started_at"] = time.time()


def get_warmup_progress() -> dict:
    with _full_refresh_lock:
        elapsed = None
        if _warmup_progress["started_at"]:
            elapsed = round(time.time() - _warmup_progress["started_at"], 1)
        return {
            "step": _warmup_progress["step"],
            "total_steps": _warmup_progress["total_steps"],
            "label": _warmup_progress["label"],
            "elapsed_seconds": elapsed,
            "sub_current": _warmup_progress.get("sub_current", 0),
            "sub_total": _warmup_progress.get("sub_total", 0),
        }


def update_warmup_sub_progress(sub_current: int):
    with _full_refresh_lock:
        _warmup_progress["sub_current"] = sub_current


def _get_db_session():
    from app.core.database import SessionLocal
    if SessionLocal is None:
        return None
    return SessionLocal()


def _stringify_keys(obj):
    if isinstance(obj, dict):
        return {str(k): _stringify_keys(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_stringify_keys(i) for i in obj]
    return obj


def _make_json_safe(obj):
    """Recursively convert Pydantic models and other non-JSON-native objects to dicts/primitives.
    This is essential before json.dumps — without this, Pydantic models get serialized as
    their string representation (via default=str), making them unreadable when loaded back."""
    # Pydantic v2
    if hasattr(obj, 'model_dump'):
        return _make_json_safe(obj.model_dump(mode='json'))
    # Pydantic v1
    elif hasattr(obj, 'dict') and callable(obj.dict) and not isinstance(obj, dict):
        return _make_json_safe(obj.dict())
    elif isinstance(obj, dict):
        return {str(k): _make_json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_make_json_safe(i) for i in obj]
    return obj


def _persist_to_db(cache_name: str, cache_key: str, data: Any):
    # Guard: for event_detail, refuse to persist entries with empty evento.date
    # to prevent corrupt records from accumulating in the DB.
    if cache_name == "event_detail" and isinstance(data, dict):
        _evt = data.get("evento", {})
        _evt_date = (
            _evt.get("date", "") if isinstance(_evt, dict)
            else getattr(_evt, "date", "")
        )
        if not _evt_date:
            logger.warning(f"_persist_to_db: refusing to persist {cache_name}/{cache_key} — evento.date is empty")
            return

    db = None
    try:
        db = _get_db_session()
        if db is None:
            return
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from app.models.cache_entry import CacheEntry

        # Use _make_json_safe (not _stringify_keys) so Pydantic models are properly
        # converted to dicts instead of being serialized as their string representation.
        safe_data = _make_json_safe(data)
        serialized = json.dumps(safe_data, default=str, ensure_ascii=False)

        now = datetime.utcnow()
        stmt = pg_insert(CacheEntry).values(
            cache_name=cache_name,
            cache_key=cache_key,
            data=serialized,
            created_at=now,
            updated_at=now
        ).on_conflict_do_update(
            index_elements=['cache_name', 'cache_key'],
            set_=dict(data=serialized, updated_at=now)
        )
        db.execute(stmt)
        db.commit()
    except Exception as e:
        logger.warning(f"Failed to persist cache {cache_name}/{cache_key} to DB: {e}")
        if db:
            try:
                db.rollback()
            except Exception:
                pass
    finally:
        if db:
            try:
                db.close()
            except Exception:
                pass


def _delete_from_db(cache_name: str, cache_key: str):
    db = None
    try:
        db = _get_db_session()
        if db is None:
            return
        from app.models.cache_entry import CacheEntry
        db.query(CacheEntry).filter(
            CacheEntry.cache_name == cache_name,
            CacheEntry.cache_key == cache_key
        ).delete()
        db.commit()
        logger.info(f"Deleted persisted cache {cache_name}/{cache_key} from DB")
    except Exception as e:
        logger.warning(f"Failed to delete cache {cache_name}/{cache_key} from DB: {e}")
        if db:
            try:
                db.rollback()
            except Exception:
                pass
    finally:
        if db:
            try:
                db.close()
            except Exception:
                pass


def _load_from_db(cache_name: str, cache_key: str) -> Optional[dict]:
    db = None
    try:
        db = _get_db_session()
        if db is None:
            return None
        from app.models.cache_entry import CacheEntry

        entry = db.query(CacheEntry).filter(
            CacheEntry.cache_name == cache_name,
            CacheEntry.cache_key == cache_key
        ).first()

        if entry and entry.data:
            return {
                "data": json.loads(entry.data),
                "updated_at": entry.updated_at.timestamp() if entry.updated_at else time.time()
            }
        return None
    except Exception as e:
        logger.warning(f"Failed to load cache {cache_name}/{cache_key} from DB: {e}")
        return None
    finally:
        if db:
            try:
                db.close()
            except Exception:
                pass


def _load_all_from_db(cache_name: str) -> dict:
    db = None
    try:
        db = _get_db_session()
        if db is None:
            return {}
        from app.models.cache_entry import CacheEntry

        entries = db.query(CacheEntry).filter(
            CacheEntry.cache_name == cache_name
        ).all()

        result = {}
        for entry in entries:
            if entry.data:
                try:
                    result[entry.cache_key] = {
                        "data": json.loads(entry.data),
                        "updated_at": entry.updated_at.timestamp() if entry.updated_at else time.time()
                    }
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON in cache entry {cache_name}/{entry.cache_key}")
        return result
    except Exception as e:
        logger.warning(f"Failed to load all cache entries for {cache_name} from DB: {e}")
        return {}
    finally:
        if db:
            try:
                db.close()
            except Exception:
                pass


class SmartCache:
    def __init__(self, name: str, ttl: Optional[int] = None):
        self.name = name
        self.ttl = ttl if ttl is not None else CURRENT_YEAR_TTL
        self._data = {}
        self._timestamps = {}
        self._lock = threading.Lock()
        self._db_loaded = False
        self._permanent_keys: set = set()

    def _is_historical(self, cache_key: str) -> bool:
        try:
            year_part = cache_key.split("_")[0]
            year = int(year_part)
            return year < datetime.now().year
        except (ValueError, IndexError):
            return False

    def _is_permanent(self, cache_key: str) -> bool:
        return self._is_historical(cache_key) or cache_key in self._permanent_keys

    def warm_from_db(self):
        loaded = _load_all_from_db(self.name)
        if loaded:
            now = time.time()
            loaded_count = 0
            expired_count = 0
            with self._lock:
                for key, val in loaded.items():
                    if key not in self._data:
                        is_hist = self._is_historical(key)
                        data = val["data"]
                        is_completed = isinstance(data, dict) and data.get("__is_completed", False)
                        db_age = now - val["updated_at"]
                        # event_detail: reject entries with empty evento.date (corrupt data),
                        # but load ALL entries with a valid date regardless of age — SWR will
                        # refresh stale data in the background. This prevents a cold-start after
                        # any restart where entries happen to be older than MAX_STALE_AGE.
                        if self.name == "event_detail" and isinstance(data, dict):
                            _evt = data.get("evento", {})
                            _evt_date = (
                                _evt.get("date", "") if isinstance(_evt, dict)
                                else getattr(_evt, "date", "")
                            )
                            if not _evt_date:
                                expired_count += 1
                                # Purge the corrupt entry from DB so it cannot accumulate
                                try:
                                    _db_persist_executor.submit(_delete_from_db, self.name, key)
                                except RuntimeError:
                                    pass
                                continue
                            # Valid date → always load (bypass MAX_STALE_AGE for event_detail).
                            # Timestamp reset to now so get() serves it immediately; the
                            # normal TTL + SWR cycle will refresh it in the background.
                            self._data[key] = data
                            self._timestamps[key] = now
                            if is_completed:
                                self._permanent_keys.add(key)
                            loaded_count += 1
                            continue
                        if is_hist or is_completed or db_age < MAX_STALE_AGE:
                            self._data[key] = data
                            # isc_pricing has a short TTL (5 min). After a restart the DB
                            # entry is always older than that, so get(stale_ok=False) would
                            # return None and force a full 40-second recompute on the first
                            # user request. Resetting the timestamp to now lets the
                            # DB-restored entry be served immediately while the background
                            # startup refresh updates it with fresh Magento data.
                            if self.name == "isc_pricing":
                                self._timestamps[key] = now
                            else:
                                self._timestamps[key] = val["updated_at"]
                            if is_completed:
                                self._permanent_keys.add(key)
                            loaded_count += 1
                        else:
                            expired_count += 1
            if expired_count > 0:
                logger.info(f"Cache '{self.name}' warmed from DB: {loaded_count} entries loaded, {expired_count} expired entries skipped")
            else:
                logger.info(f"Cache '{self.name}' warmed from DB: {loaded_count} entries loaded")
            self._db_loaded = True
        else:
            logger.info(f"Cache '{self.name}' warm from DB: no entries found")
            self._db_loaded = True

    def get(self, cache_key: str, stale_ok: bool = True) -> Optional[Any]:
        with self._lock:
            if cache_key in self._data:
                ts = self._timestamps.get(cache_key)
                if ts is None:
                    return None

                if self._is_permanent(cache_key):
                    return self._data[cache_key]

                elapsed = time.time() - ts
                if elapsed < self.ttl:
                    return self._data[cache_key]

                if stale_ok and elapsed < MAX_STALE_AGE:
                    logger.debug(f"Cache '{self.name}' serving stale data for key={cache_key} (age={elapsed:.0f}s)")
                    return self._data[cache_key]

                if elapsed >= MAX_STALE_AGE:
                    logger.warning(f"Cache '{self.name}' discarding expired data for key={cache_key} (age={elapsed:.0f}s > max {MAX_STALE_AGE}s)")
                    self._data.pop(cache_key, None)
                    self._timestamps.pop(cache_key, None)

                return None

        db_result = _load_from_db(self.name, cache_key)
        if db_result is not None:
            is_hist = self._is_historical(cache_key)
            db_age = time.time() - db_result["updated_at"]
            if is_hist or db_age < MAX_STALE_AGE:
                with self._lock:
                    self._data[cache_key] = db_result["data"]
                    self._timestamps[cache_key] = db_result["updated_at"]
                logger.info(f"Cache '{self.name}' loaded from DB for key={cache_key}")
                return db_result["data"]
            else:
                logger.warning(f"Cache '{self.name}' discarding expired DB entry for key={cache_key} (age={db_age:.0f}s)")
                _delete_from_db(self.name, cache_key)

        return None

    def get_or_revalidate(self, cache_key: str, refresh_fn: Optional[Callable] = None) -> tuple:
        with self._lock:
            if cache_key in self._data:
                ts = self._timestamps.get(cache_key)
                if ts is None:
                    return None, False

                if self._is_permanent(cache_key):
                    return self._data[cache_key], False

                elapsed = time.time() - ts
                if elapsed < self.ttl:
                    return self._data[cache_key], False

                if elapsed < MAX_STALE_AGE:
                    data = self._data[cache_key]
                    if refresh_fn is not None:
                        swr_key = f"{self.name}:{cache_key}"
                        with _swr_lock:
                            if swr_key not in _swr_in_flight:
                                _swr_in_flight.add(swr_key)
                                try:
                                    _swr_executor.submit(self._swr_refresh, cache_key, refresh_fn, swr_key)
                                    logger.info(f"Cache '{self.name}' SWR: serving stale key={cache_key} (age={elapsed:.0f}s), refresh started")
                                except RuntimeError:
                                    _swr_in_flight.discard(swr_key)
                            else:
                                logger.debug(f"Cache '{self.name}' SWR: refresh already in flight for key={cache_key}")
                    return data, True

                logger.warning(f"Cache '{self.name}' discarding expired data for key={cache_key} (age={elapsed:.0f}s)")
                self._data.pop(cache_key, None)
                self._timestamps.pop(cache_key, None)

        return None, False

    def _swr_refresh(self, cache_key: str, refresh_fn: Callable, swr_key: str):
        try:
            refresh_fn()
            logger.info(f"Cache '{self.name}' SWR: background refresh completed for key={cache_key}")
        except Exception as e:
            logger.error(f"Cache '{self.name}' SWR: background refresh failed for key={cache_key}: {e}")
        finally:
            with _swr_lock:
                _swr_in_flight.discard(swr_key)

    def set(self, cache_key: str, data: Any):
        with self._lock:
            self._data[cache_key] = data
            self._timestamps[cache_key] = time.time()

        try:
            _db_persist_executor.submit(_persist_to_db, self.name, cache_key, data)
        except RuntimeError:
            logger.warning(f"DB persist executor shutdown, skipping persist for {self.name}/{cache_key}")

    def set_permanent(self, cache_key: str, data: Any):
        """Store data that never expires (for completed current-year events)."""
        with self._lock:
            self._data[cache_key] = data
            self._timestamps[cache_key] = time.time()
            self._permanent_keys.add(cache_key)
        try:
            _db_persist_executor.submit(_persist_to_db, self.name, cache_key, data)
        except RuntimeError:
            logger.warning(f"DB persist executor shutdown, skipping persist for {self.name}/{cache_key}")

    def invalidate(self, cache_key: str = None):
        keys_removed = []
        with self._lock:
            if cache_key:
                self._data.pop(cache_key, None)
                self._timestamps.pop(cache_key, None)
                self._permanent_keys.discard(cache_key)
                keys_removed.append(cache_key)
            else:
                keys_to_remove = [
                    k for k in self._data
                    if not self._is_permanent(k)
                ]
                for k in keys_to_remove:
                    self._data.pop(k, None)
                    self._timestamps.pop(k, None)
                    keys_removed.append(k)
        for k in keys_removed:
            try:
                _delete_from_db(self.name, k)
            except Exception as e:
                logger.warning(f"Failed to delete cache {self.name}/{k} from DB during invalidation: {e}")

    def invalidate_all(self):
        with self._lock:
            all_keys = list(self._data.keys())
            self._data.clear()
            self._timestamps.clear()
        for k in all_keys:
            try:
                _delete_from_db(self.name, k)
            except Exception as e:
                logger.warning(f"Failed to delete cache {self.name}/{k} from DB during invalidate_all: {e}")

    def invalidate_all_except(self, keep_keys: set):
        """Remove all cache entries except the ones listed in keep_keys.
        Used for atomic cache refresh: populate new keys first, then purge stale others."""
        with self._lock:
            keys_to_remove = [k for k in self._data if k not in keep_keys]
            for k in keys_to_remove:
                self._data.pop(k, None)
                self._timestamps.pop(k, None)
        for k in keys_to_remove:
            try:
                _delete_from_db(self.name, k)
            except Exception as e:
                logger.warning(f"Failed to delete cache {self.name}/{k} from DB during invalidate_all_except: {e}")

    def get_info(self, cache_key: str = None) -> dict:
        with self._lock:
            if cache_key and cache_key in self._timestamps:
                ts = self._timestamps[cache_key]
                is_perm = self._is_permanent(cache_key)
                return {
                    "cached": True,
                    "cached_at": datetime.fromtimestamp(ts).isoformat(),
                    "is_historical": is_perm,
                    "ttl": "permanent" if is_perm else f"{self.ttl}s",
                    "age_seconds": round(time.time() - ts, 1)
                }
            return {"cached": False}

    def get_all_keys(self) -> list:
        with self._lock:
            return list(self._data.keys())

    def get_all_timestamps(self) -> dict:
        with self._lock:
            return dict(self._timestamps)

    def entry_count(self) -> int:
        with self._lock:
            return len(self._data)


ISC_CACHE_TTL = 300  # 5 min — ISC now reads from fast PostgreSQL, no need for 22h TTL
isc_cache = SmartCache("isc_pricing", ttl=ISC_CACHE_TTL)
event_detail_cache = SmartCache("event_detail", ttl=NIGHTLY_CACHE_TTL)
daily_sales_cache = SmartCache("daily_sales")
curva_cache = SmartCache("curva_comparativa")
medias_cache = SmartCache("medias_vendas")
eventos_list_cache = SmartCache("eventos_list")

_warmup_metadata_cache: dict = {}
_warmup_metadata_lock = threading.Lock()


def set_warmup_metadata_cache(sku_mappings_by_grupo: dict, sku_mappings_by_sku: dict,
                               dim_projetos_by_codigo: dict, dim_projetos_by_id: dict,
                               cadastros_by_projeto_id: dict, all_dim_projetos: list = None):
    with _warmup_metadata_lock:
        _warmup_metadata_cache.clear()
        _warmup_metadata_cache["sku_by_grupo"] = sku_mappings_by_grupo
        _warmup_metadata_cache["sku_by_sku"] = sku_mappings_by_sku
        _warmup_metadata_cache["proj_by_codigo"] = dim_projetos_by_codigo
        _warmup_metadata_cache["proj_by_id"] = dim_projetos_by_id
        _warmup_metadata_cache["cad_by_proj"] = cadastros_by_projeto_id
        if all_dim_projetos is not None:
            _warmup_metadata_cache["all_projetos"] = all_dim_projetos


def clear_warmup_metadata_cache():
    with _warmup_metadata_lock:
        _warmup_metadata_cache.clear()


def get_warmup_sku_mappings_by_grupo(grupo: str, anos: list) -> Optional[list]:
    with _warmup_metadata_lock:
        idx = _warmup_metadata_cache.get("sku_by_grupo")
        if idx is None:
            return None
        result = []
        for a in anos:
            key = f"{grupo}_{a}"
            result.extend(idx.get(key, []))
        return result


def get_warmup_sku_mappings_by_sku(sku: str, anos: list = None, active_only: bool = True) -> Optional[list]:
    with _warmup_metadata_lock:
        idx = _warmup_metadata_cache.get("sku_by_sku")
        if idx is None:
            return None
        items = idx.get(sku.upper().strip(), [])
        if anos:
            items = [m for m in items if m.ano in anos]
        return items


def get_warmup_dim_projetos_by_codigos(codigos: list) -> Optional[list]:
    with _warmup_metadata_lock:
        idx = _warmup_metadata_cache.get("proj_by_codigo")
        if idx is None:
            return None
        result = []
        for c in codigos:
            key = str(c).upper().strip()
            if key in idx:
                result.extend(idx[key])
        return result


def get_warmup_dim_projeto_by_id(proj_id: int) -> Optional[Any]:
    with _warmup_metadata_lock:
        idx = _warmup_metadata_cache.get("proj_by_id")
        if idx is None:
            return None
        return idx.get(proj_id)


def get_warmup_cadastro_by_projeto_id(projeto_id: int) -> Optional[Any]:
    with _warmup_metadata_lock:
        idx = _warmup_metadata_cache.get("cad_by_proj")
        if idx is None:
            return None
        return idx.get(projeto_id, None)


def get_warmup_all_dim_projetos() -> Optional[list]:
    with _warmup_metadata_lock:
        return _warmup_metadata_cache.get("all_projetos")

ALL_CACHES = [isc_cache, event_detail_cache, daily_sales_cache, curva_cache, medias_cache, eventos_list_cache]

_warmup_event_results_store: dict = {}
_warmup_event_results_lock = threading.Lock()
_warmup_summary_store: dict = {}
_warmup_summary_lock = threading.Lock()


def set_warmup_event_results(results: dict):
    with _warmup_event_results_lock:
        _warmup_event_results_store.clear()
        _warmup_event_results_store.update(results)


def get_warmup_event_results() -> dict:
    with _warmup_event_results_lock:
        return dict(_warmup_event_results_store)


def set_warmup_summary(summary: dict):
    with _warmup_summary_lock:
        _warmup_summary_store.clear()
        _warmup_summary_store.update(summary)


def get_warmup_summary() -> dict:
    with _warmup_summary_lock:
        return dict(_warmup_summary_store)


_gap_detection_store: dict = {}
_gap_detection_lock = threading.Lock()

_known_tier1_ids: list = []
_known_tier1_ids_lock = threading.Lock()


def set_gap_detection_result(result: dict):
    with _gap_detection_lock:
        _gap_detection_store.clear()
        _gap_detection_store.update(result)


def get_gap_detection_result() -> dict:
    with _gap_detection_lock:
        return dict(_gap_detection_store)


def set_known_tier1_ids(ids: list):
    with _known_tier1_ids_lock:
        _known_tier1_ids.clear()
        _known_tier1_ids.extend(ids)


def get_known_tier1_ids() -> list:
    with _known_tier1_ids_lock:
        return list(_known_tier1_ids)


def warm_all_caches_from_db():
    global _last_full_refresh_timestamp, _last_sync_hoje_timestamp
    logger.info("Warming all caches from PostgreSQL...")
    start = time.time()
    for cache in ALL_CACHES:
        try:
            cache.warm_from_db()
        except Exception as e:
            logger.error(f"Failed to warm cache '{cache.name}' from DB: {e}")
    # Restore the last_full_refresh and last_sync_hoje timestamps from DB so they survive restarts.
    try:
        db = _get_db_session()
        if db is not None:
            try:
                from app.models.cache_entry import CacheEntry
                from datetime import datetime as _dt_meta
                row = db.query(CacheEntry).filter_by(cache_name="__meta__", cache_key="last_full_refresh").first()
                if row:
                    data = json.loads(row.data) if isinstance(row.data, str) else row.data
                    _last_full_refresh_timestamp = float(data.get("ts", 0)) or None
                    if _last_full_refresh_timestamp:
                        _hr = _dt_meta.fromtimestamp(_last_full_refresh_timestamp).strftime('%Y-%m-%d %H:%M:%S')
                        logger.info(f"Restored last_full_refresh from DB: {_hr}")
                row_lsh = db.query(CacheEntry).filter_by(cache_name="__meta__", cache_key="last_sync_hoje").first()
                if row_lsh:
                    data_lsh = json.loads(row_lsh.data) if isinstance(row_lsh.data, str) else row_lsh.data
                    _ts_lsh = float(data_lsh.get("ts", 0)) or None
                    if _ts_lsh:
                        with _last_sync_hoje_lock:
                            _last_sync_hoje_timestamp = _ts_lsh
                        _hr_lsh = _dt_meta.fromtimestamp(_ts_lsh).strftime('%Y-%m-%d %H:%M:%S')
                        logger.info(f"Restored last_sync_hoje from DB: {_hr_lsh}")
            finally:
                db.close()
    except Exception as _lfr_load_err:
        logger.warning(f"warm_all_caches_from_db: could not load meta timestamps: {_lfr_load_err}")
    elapsed = time.time() - start
    logger.info(f"All caches warmed from DB in {elapsed:.1f}s")


class CacheRefreshScheduler:
    def __init__(self):
        self._timer = None
        self._daily_timer = None
        self._snapshot_timer = None
        self._evening_timer = None
        self._refresh_callbacks = []
        self._full_refresh_callback = None
        self._running = False
        self._lock = threading.Lock()

    def register(self, callback: Callable):
        self._refresh_callbacks.append(callback)

    def register_full_refresh(self, callback: Callable):
        self._full_refresh_callback = callback

    def start(self, interval: int = CURRENT_YEAR_TTL):
        with self._lock:
            if self._running:
                return
            self._running = True
        self._schedule(interval)
        self._schedule_daily_refresh()
        self._schedule_snapshot_consolidation()
        self._schedule_evening_refresh()
        logger.info(f"Cache refresh scheduler started (interval: {interval}s, daily snapshot at 02:00 BRT, daily refresh at 05:00 BRT, evening refresh at 17:00 BRT)")

    def _schedule(self, interval: int):
        with self._lock:
            if not self._running:
                return
        self._timer = threading.Timer(interval, self._run_refresh, args=[interval])
        self._timer.daemon = True
        self._timer.start()

    def _schedule_daily_refresh(self):
        with self._lock:
            if not self._running:
                return

        now = datetime.now(ZoneInfo('America/Sao_Paulo'))
        today_target = now.replace(hour=5, minute=0, second=0, microsecond=0)

        # Detect missed daily refresh: past 05:00 BRT today but last_full_refresh predates it
        if now >= today_target:
            last_refresh = _last_full_refresh_timestamp
            if last_refresh:
                last_refresh_dt = datetime.fromtimestamp(last_refresh, tz=ZoneInfo('America/Sao_Paulo'))
            else:
                last_refresh_dt = None

            if last_refresh_dt is None or last_refresh_dt < today_target:
                logger.warning(
                    f"[Scheduler] Missed daily refresh detected "
                    f"(last={last_refresh_dt}, today_target={today_target.isoformat()}). "
                    f"Triggering catch-up refresh in 90s."
                )
                self._daily_timer = threading.Timer(90, self._run_daily_refresh)
                self._daily_timer.daemon = True
                self._daily_timer.start()
                return

        target = today_target
        if now >= target:
            target += timedelta(days=1)

        delay = (target - now).total_seconds()
        logger.info(f"Next daily full refresh scheduled in {delay:.0f}s ({target.isoformat()})")

        self._daily_timer = threading.Timer(delay, self._run_daily_refresh)
        self._daily_timer.daemon = True
        self._daily_timer.start()

    def _schedule_snapshot_consolidation(self):
        with self._lock:
            if not self._running:
                return

        now = datetime.now(ZoneInfo('America/Sao_Paulo'))
        today_target = now.replace(hour=2, minute=0, second=0, microsecond=0)

        # Rede de segurança + retry intra-dia. Lê o estado dos ciclos de hoje
        # (a partir das 02h BRT) e decide:
        #   (a) NENHUMA tentativa hoje + já passou das 02h → catch-up em 90s
        #       (cobre o caso "backend subiu de manhã e perdeu o 02h").
        #   (b) Última tentativa terminou em 'parcial' ou 'falha' E ainda há
        #       quota de retry (< MAX_RETRIES_PER_DAY tentativas terminais
        #       hoje) → re-tenta em RETRY_DELAY_MINUTES. A idempotência por
        #       sub-passo garante que o retry só re-roda o que faltou.
        #   (c) Ciclo 'iniciado' ainda recente (< 60min, sem terminal): já
        #       está rodando, não agenda nada extra.
        #   (d) Concluído OK hoje, OU estourou retries, OU ainda não deu 04h:
        #       agenda normalmente para o próximo 04h BRT (amanhã ou hoje).
        MAX_RETRIES_PER_DAY = 3            # tentativas terminais adicionais após a 1ª
        RETRY_DELAY_MINUTES = 30
        _last_terminal_status = None
        _terminal_count_today = 0
        _running_recent = False
        try:
            from app.core.database import SessionLocal as _SL_chk
            from app.models.sync_event_log import SyncEventLog as _SEL_chk
            from sqlalchemy import and_ as _and_chk, or_ as _or_chk
            _db_chk = _SL_chk()
            try:
                _today_start_utc = today_target.astimezone(ZoneInfo('UTC'))
                _terminal_rows = _db_chk.query(_SEL_chk.status, _SEL_chk.created_at).filter(
                    _and_chk(
                        _SEL_chk.job_name == "consolidacao_diaria_04h",
                        _SEL_chk.nivel == "ciclo",
                        _or_chk(
                            _SEL_chk.status == "concluido",
                            _SEL_chk.status == "parcial",
                            _SEL_chk.status == "falha",
                        ),
                        _SEL_chk.created_at >= _today_start_utc,
                    )
                ).order_by(_SEL_chk.created_at.asc()).all()
                _terminal_count_today = len(_terminal_rows)
                if _terminal_rows:
                    _last_terminal_status = _terminal_rows[-1][0]
                # Ciclo realmente em execução = último evento ciclo do job é
                # 'iniciado' e foi há < 60min. NÃO basta "existir um iniciado
                # recente": após um ciclo terminar normalmente, o próprio
                # 'iniciado' que o abriu continua < 60min — se contássemos
                # apenas presença, cairíamos em (c) e sairíamos sem agendar
                # nada, deixando o scheduler morto até o próximo restart.
                _recent_start_utc = (now - timedelta(minutes=60)).astimezone(ZoneInfo('UTC'))
                _last_ciclo_row = _db_chk.query(_SEL_chk.status, _SEL_chk.created_at).filter(
                    _and_chk(
                        _SEL_chk.job_name == "consolidacao_diaria_04h",
                        _SEL_chk.nivel == "ciclo",
                    )
                ).order_by(_SEL_chk.created_at.desc()).first()
                if _last_ciclo_row is not None:
                    _last_status, _last_ts = _last_ciclo_row
                    if _last_status == "iniciado" and _last_ts >= _recent_start_utc:
                        _running_recent = True
            finally:
                _db_chk.close()
        except Exception as _e_chk:
            logger.warning(f"[Scheduler] Falha ao checar execução prévia do 04h: {_e_chk}")

        # (c) Já está rodando — re-checa em 10min ao invés de retornar vazio.
        # IMPORTANTE: não usar `return` puro aqui. _schedule_snapshot_consolidation
        # só é chamado no start() e no fim de _run_snapshot_consolidation; se o
        # ciclo em execução crashar sem chegar ao fim, ninguém mais re-armaria
        # o timer e o scheduler ficaria morto até o próximo restart. A re-check
        # de 10min garante que ao expirar o ciclo (ou ele realmente terminar)
        # caímos numa das outras branches e agendamos retry/próximo dia.
        if _running_recent:
            logger.info("[Scheduler] Ciclo 04h em execução (iniciado < 60min). Re-checa em 10min.")
            self._snapshot_timer = threading.Timer(10 * 60, self._schedule_snapshot_consolidation)
            self._snapshot_timer.daemon = True
            self._snapshot_timer.start()
            return

        # (a) Catch-up: passou das 04h e nenhuma tentativa terminal hoje.
        if now >= today_target and _terminal_count_today == 0:
            logger.warning(
                f"[Scheduler] Missed daily snapshot consolidation detected "
                f"(today_target={today_target.isoformat()}). Triggering catch-up in 90s."
            )
            self._snapshot_timer = threading.Timer(90, self._run_snapshot_consolidation)
            self._snapshot_timer.daemon = True
            self._snapshot_timer.start()
            return

        # (b) Retry intra-dia: última tentativa terminou parcial/falha e ainda
        # cabe re-tentar hoje. Conta-se a 1ª como "tentativa inicial", logo
        # permite-se até MAX_RETRIES_PER_DAY tentativas adicionais.
        if (
            _last_terminal_status in ("parcial", "falha")
            and _terminal_count_today <= MAX_RETRIES_PER_DAY
        ):
            _delay_s = RETRY_DELAY_MINUTES * 60
            logger.warning(
                f"[Scheduler] Última tentativa do 04h hoje terminou em '{_last_terminal_status}' "
                f"({_terminal_count_today}/{MAX_RETRIES_PER_DAY + 1} tentativas). "
                f"Agendando retry em {RETRY_DELAY_MINUTES}min — idempotência cuida do que já deu OK."
            )
            self._snapshot_timer = threading.Timer(_delay_s, self._run_snapshot_consolidation)
            self._snapshot_timer.daemon = True
            self._snapshot_timer.start()
            return

        # (d-extra) Esgotou retries hoje após várias falhas — segue pro próximo 04h.
        if _last_terminal_status in ("parcial", "falha"):
            logger.error(
                f"[Scheduler] Cota diária de retries esgotada para 04h "
                f"({_terminal_count_today} tentativas, última='{_last_terminal_status}'). "
                f"Próxima tentativa só amanhã às 04h BRT."
            )

        target = today_target
        if now >= target:
            target += timedelta(days=1)

        delay = (target - now).total_seconds()
        logger.info(f"Next snapshot consolidation scheduled in {delay:.0f}s ({target.isoformat()})")

        self._snapshot_timer = threading.Timer(delay, self._run_snapshot_consolidation)
        self._snapshot_timer.daemon = True
        self._snapshot_timer.start()

    def _run_snapshot_consolidation(self):
        with self._lock:
            if not self._running:
                return

        logger.info("=== DAILY SNAPSHOT CONSOLIDATION STARTED (02:00 BRT) ===")
        # Ciclo guarda-chuva: agrupa todos os sub-passos sob o mesmo ciclo_id
        # para que o painel de Sincronizações mostre o resumo do job das 04h
        # (o que rodou, o que falhou, o que foi pulado).
        from app.services.sync_log_service import (
            log_evento as _le_root,
            new_ciclo_id as _ncid_root,
            classify_motivo as _cm_root,
            acquire_consolidation_lock as _acq_root,
            release_consolidation_lock as _rel_root,
        )
        import time as _t_root

        # ADVISORY LOCK cross-process — se endpoint /scheduled-jobs/... ou
        # catch-up de startup já estiver rodando, pulamos esta execução
        # interna (evita jobs paralelos). Re-agenda em 10min como branch (c).
        _lock_conn_root = _acq_root()
        if _lock_conn_root is None:
            logger.warning("[Daily 02:00] Advisory lock NÃO obtido — outro processo já consolidando. Re-agendando em 10min.")
            self._snapshot_timer = threading.Timer(10 * 60, self._schedule_snapshot_consolidation)
            self._snapshot_timer.daemon = True
            self._snapshot_timer.start()
            return

        # Marcador para o finally lá embaixo saber que o lock foi adquirido nesta
        # execução (e não numa anterior). Garante release sob qualquer exception.
        _lock_acquired_here = True

        _root_ciclo = _ncid_root()
        _root_job = "consolidacao_diaria_04h"
        _root_t0 = _t_root.time()
        _root_steps = {"ok": 0, "falha": 0, "pulado": 0}
        logger.info(
            f"[DailyJob] job_name legado='{_root_job}' (mantido para compat com SyncEventLog); "
            f"execução real agendada para 02:00 BRT"
        )
        _le_root(_root_ciclo, _root_job, "iniciado", nivel="ciclo",
                 detalhes="Job agendado das 02h BRT: snapshot diário, curvas históricas, sync hoje e margem por bundle")

        # TRY/FINALLY top-level — release do advisory lock garantido sob
        # qualquer exception (mesmo inesperada). Bloco originalmente terminava
        # em self._schedule_snapshot_consolidation(); mantemos esse re-agendamento
        # tanto em sucesso quanto em erro (mesma semântica original).
        try:
            # Idempotência por sub-passo: se este sub-passo JÁ concluiu hoje BRT
            # em qualquer ciclo (ex.: backend reiniciou no meio do job das 04h e
            # o catch-up está rodando de novo), pular para não duplicar trabalho
            # pesado de Magento.
            def _step_already_done_today(step_name: str) -> bool:
                try:
                    from app.core.database import SessionLocal as _SL_idem
                    from app.models.sync_event_log import SyncEventLog as _SEL_idem
                    from sqlalchemy import and_ as _and_idem
                    _now_brt = datetime.now(ZoneInfo('America/Sao_Paulo'))
                    _today_brt_start = _now_brt.replace(hour=0, minute=0, second=0, microsecond=0)
                    _today_utc = _today_brt_start.astimezone(ZoneInfo('UTC'))
                    _db_idem = _SL_idem()
                    try:
                        _hit = _db_idem.query(_SEL_idem.id).filter(
                            _and_idem(
                                _SEL_idem.job_name == _root_job,
                                _SEL_idem.nivel == "grupo",
                                _SEL_idem.grupo == step_name,
                                _SEL_idem.status == "ok",
                                _SEL_idem.created_at >= _today_utc,
                            )
                        ).first()
                        return _hit is not None
                    finally:
                        _db_idem.close()
                except Exception as _e_idem:
                    logger.warning(f"[Daily 02:00] Falha ao checar idempotência de {step_name}: {_e_idem}")
                    return False

            def _run_step(step_name: str, fn, *, optional: bool = False) -> bool:
                """Executa um sub-passo logando início/fim no ciclo guarda-chuva.

                Quando o sub-job retorna um `dict` com chave `status`, ela é
                interpretada para evitar que retornos do tipo `{"status": "skipped"}`
                ou `{"status": "falha_persistencia"}` apareçam falsamente como `ok`
                no resumo do ciclo (visto no painel).
                """
                # Idempotência: pula se já concluiu OK hoje em outro ciclo.
                if _step_already_done_today(step_name):
                    _le_root(_root_ciclo, _root_job, "pulado", nivel="grupo", grupo=step_name,
                             motivo="ja_executado_hoje",
                             detalhes=f"{step_name} já concluído hoje BRT — pulado (idempotência)")
                    _root_steps["pulado"] += 1
                    logger.info(f"[Daily 02:00] {step_name} pulado: já concluiu hoje BRT em outro ciclo")
                    return True
                _t0 = _t_root.time()
                _le_root(_root_ciclo, _root_job, "iniciado", nivel="grupo", grupo=step_name,
                         detalhes=f"Iniciando {step_name}")
                try:
                    _ret = fn()
                    _status_log = "ok"
                    _motivo_log = None
                    if isinstance(_ret, dict):
                        _raw = str(_ret.get("status") or "").lower()
                        if _raw in ("ok", "concluido", "concluído", "sucesso", "success"):
                            _status_log = "ok"
                        elif _raw in ("skipped", "pulado", "ignorado", "sem_dados", "no_data"):
                            _status_log = "pulado"
                            _motivo_log = _raw or "sem_dados"
                        elif _raw.startswith("falha") or _raw in ("erro", "error", "failed", "failure"):
                            _status_log = "falha"
                            _motivo_log = _raw or "falha_runtime"
                        elif _raw == "parcial":
                            _status_log = "parcial"
                            _motivo_log = "parcial"
                    _le_root(_root_ciclo, _root_job, _status_log, nivel="grupo", grupo=step_name,
                             motivo=_motivo_log,
                             detalhes=str(_ret) if _ret is not None else None,
                             duracao_ms=int((_t_root.time() - _t0) * 1000))
                    if _status_log == "ok":
                        _root_steps["ok"] += 1
                    elif _status_log == "pulado":
                        _root_steps["pulado"] += 1
                    else:
                        _root_steps["falha"] += 1
                        if not optional:
                            logger.error(f"[Daily 02:00] {step_name} retornou status='{_motivo_log}' (não exceção)")
                    return _status_log == "ok"
                except Exception as _exc:
                    _status = "falha"
                    _motivo = _cm_root(_exc)
                    _le_root(_root_ciclo, _root_job, _status, nivel="grupo", grupo=step_name,
                             motivo=_motivo, detalhes=str(_exc)[:1500],
                             duracao_ms=int((_t_root.time() - _t0) * 1000))
                    _root_steps["falha"] += 1
                    if optional:
                        logger.error(f"[Daily 02:00] {step_name} falhou (não bloqueante): {_exc}")
                        return False
                    logger.error(f"[Daily 02:00] {step_name} falhou: {_exc}")
                    return False

            _final_status = "concluido"
            _final_motivo = None
            _final_detalhes = None
            try:
                from app.core.database import SessionLocal
                from app.services.snapshot_service import snapshot_diario_batch, consolidar_curvas_historicas_batch, sincronizar_hoje_batch, sincronizar_margem_bundle_rev_batch, congelar_cortes_projecao_batch
                db = SessionLocal()
                try:
                    def _auto_concluir():
                        from app.services.event_status_service import auto_concluir_eventos_passados
                        _n = auto_concluir_eventos_passados(db)
                        return f"{_n} evento(s) concluído(s) por data"
                    _run_step("auto_concluir_eventos_passados", _auto_concluir, optional=True)

                    _run_step("snapshot_diario_batch", lambda: snapshot_diario_batch(db))
                    _run_step("consolidar_curvas_historicas_batch", lambda: consolidar_curvas_historicas_batch(db))

                    def _sync_hoje():
                        _c = sincronizar_hoje_batch(db)
                        # Atualiza o carimbo "Inscrições às HH:MM" exibido no detalhe do
                        # evento. Sem isso, mesmo após o sync das 04:00 ter rodado, o
                        # badge continua mostrando o último horário do agendador da
                        # noite anterior — o que dá a falsa impressão de dado velho.
                        set_last_sync_hoje(_t_root.time())
                        logger.info(f"[Daily 02:00] sincronizar_hoje_batch: {_c} grupos — last_sync_hoje atualizado")
                        return f"{_c} grupos sincronizados"
                    _run_step("sincronizar_hoje_batch", _sync_hoje)

                    _run_step("sincronizar_margem_bundle_rev_batch",
                              lambda: sincronizar_margem_bundle_rev_batch(db),
                              optional=True)

                    _run_step("congelar_cortes_projecao_batch",
                              lambda: congelar_cortes_projecao_batch(db),
                              optional=True)

                    def _cleanup():
                        from app.services.sync_log_service import cleanup_old as _sync_cleanup
                        removed = _sync_cleanup(days=30)
                        if removed:
                            logger.info(f"[Daily 02:00] sync_event_log cleanup: {removed} linhas removidas (>30 dias)")
                        return f"{removed or 0} linhas removidas (>30 dias)"
                    _run_step("sync_event_log_cleanup", _cleanup, optional=True)
                    logger.info("=== DAILY SNAPSHOT CONSOLIDATION COMPLETED ===")
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"Daily snapshot consolidation error: {e}")
                _final_status = "falha"
                _final_motivo = _cm_root(e)
                _final_detalhes = str(e)[:1500]

            # Se algum sub-passo obrigatório falhou e nada explodiu acima, marca parcial.
            if _final_status == "concluido" and _root_steps["falha"] > 0:
                _final_status = "parcial"
                _final_motivo = "sub_passo_falhou"

            _le_root(
                _root_ciclo, _root_job, _final_status, nivel="ciclo",
                motivo=_final_motivo,
                detalhes=(
                    _final_detalhes
                    or f"Sub-passos — ok: {_root_steps['ok']}, falha: {_root_steps['falha']}"
                ),
                duracao_ms=int((_t_root.time() - _root_t0) * 1000),
            )


        finally:
            try:
                _rel_root(_lock_conn_root)
                logger.info("[Daily 02:00] Advisory lock liberado.")
            except Exception as _rel_err:
                logger.warning(f"[Daily 02:00] Falha ao liberar advisory lock: {_rel_err}")
            self._schedule_snapshot_consolidation()

    def _run_daily_refresh(self):
        with self._lock:
            if not self._running:
                return

        logger.info("=== DAILY FULL CACHE REFRESH STARTED (05:00 BRT) ===")
        if self._full_refresh_callback:
            try:
                self._full_refresh_callback()
                logger.info("=== DAILY FULL CACHE REFRESH COMPLETED ===")
                try:
                    from app.services.health_alert_service import log_event as _le
                    _le("DAILY_REFRESH_COMPLETED", "INFO", "Refresh diário completo concluído com sucesso (05:00 BRT)", None)
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Daily full cache refresh error: {e}")
                try:
                    from app.services.health_alert_service import log_and_alert as _ha
                    _ha("DAILY_REFRESH_FAILED", "CRITICAL", "Falha no refresh diário completo dos dados (05:00 BRT)", str(e))
                except Exception:
                    pass
        else:
            for callback in self._refresh_callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Daily cache refresh callback error: {e}")

        # Rede de segurança: depois do warmup completo, força um sync_hoje
        # adicional. O warmup das 05:00 não chama sincronizar_hoje_batch e o
        # job das 04:00 frequentemente falha para grupos cujo Magento via SSH
        # tunnel está instável nesse horário. Rodar o sync de novo às 05:00
        # garante que, ao usuário abrir o sistema de manhã, a tabela já mostre
        # o número correto de hoje (ex.: 6 vendas no lugar do valor de ontem).
        try:
            from app.core.database import SessionLocal as _SL_morning
            from app.services.snapshot_service import sincronizar_hoje_batch as _shb_morning
            _db_morning = _SL_morning()
            try:
                _morning_count = _shb_morning(_db_morning)
                set_last_sync_hoje(time.time())
                logger.info(f"[Daily 05:00] sincronizar_hoje_batch (rede de segurança): {_morning_count} grupos — last_sync_hoje atualizado")
            finally:
                _db_morning.close()
        except Exception as _e_morning:
            logger.error(f"[Daily 05:00] sincronizar_hoje_batch (rede de segurança) falhou: {_e_morning}")

        self._schedule_daily_refresh()

    def _schedule_evening_refresh(self):
        with self._lock:
            if not self._running:
                return

        now = datetime.now(ZoneInfo('America/Sao_Paulo'))
        target = now.replace(hour=17, minute=0, second=0, microsecond=0)
        if now >= target:
            # 17:00 BRT already passed today — check if the refresh was missed.
            # A missed refresh means: it's still "today evening" (before midnight)
            # AND the last full refresh happened before 17:00 today.
            today_17h = target  # already set to today 17:00
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            if now < midnight:  # still today evening (17:00–23:59)
                _lfr = _last_full_refresh_timestamp
                _lfr_dt = datetime.fromtimestamp(_lfr, tz=ZoneInfo('America/Sao_Paulo')) if _lfr else None
                if _lfr_dt is None or _lfr_dt < today_17h:
                    # Evening refresh was missed — run a catch-up in 60s (let startup settle)
                    logger.info(f"[Scheduler] Evening refresh was missed (last refresh: {_lfr_dt or 'never'}) — scheduling catch-up in 60s")
                    self._evening_timer = threading.Timer(60, self._run_evening_refresh)
                    self._evening_timer.daemon = True
                    self._evening_timer.start()
                    return
            target += timedelta(days=1)

        delay = (target - now).total_seconds()
        logger.info(f"Next evening refresh scheduled in {delay:.0f}s ({target.isoformat()})")

        self._evening_timer = threading.Timer(delay, self._run_evening_refresh)
        self._evening_timer.daemon = True
        self._evening_timer.start()

    def _run_evening_refresh(self):
        with self._lock:
            if not self._running:
                return

        logger.info("=== EVENING LIGHTWEIGHT REFRESH STARTED (17:00 BRT) — sincronizar_hoje + ISC only ===")
        for callback in self._refresh_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Evening refresh callback error: {e}")
        logger.info("=== EVENING LIGHTWEIGHT REFRESH COMPLETED (17:00 BRT) ===")

        self._schedule_evening_refresh()

    def _check_daily_consolidation_health(self):
        """CAMADA 3: monitor de saúde do job 02h BRT.

        A cada tick do scheduler de 45min, verifica se houve uma execução
        bem-sucedida (`consolidacao_diaria_04h` nivel='ciclo' status='concluido')
        nas últimas 26h. Se não, dispara alerta HIGH `SYNC_DIARIA_MISSING`
        (com throttle de 5min via health_alert_service). Garante que se as
        camadas 1 (Scheduled Deployment) e 2 (catch-up startup) falharem,
        operadores são notificados em até 45min.
        """
        try:
            from app.core.database import SessionLocal as _HSL
            from app.models.sync_event_log import SyncEventLog as _SEL_h
            from sqlalchemy import and_ as _and_h
            from datetime import datetime as _dt_h, timedelta as _td_h, timezone as _tz_h
            from zoneinfo import ZoneInfo as _ZI_h

            _now_brt = _dt_h.now(_ZI_h('America/Sao_Paulo'))
            _today_02h = _now_brt.replace(hour=2, minute=0, second=0, microsecond=0)
            if _now_brt < _today_02h:
                return  # antes das 02h BRT, ainda não é hora — não alerta

            _cutoff = _dt_h.now(_tz_h.utc) - _td_h(hours=26)
            _db_h = _HSL()
            try:
                _last_ok = _db_h.query(_SEL_h.created_at).filter(
                    _and_h(
                        _SEL_h.job_name == "consolidacao_diaria_04h",
                        _SEL_h.nivel == "ciclo",
                        _SEL_h.status == "concluido",
                        _SEL_h.created_at >= _cutoff,
                    )
                ).order_by(_SEL_h.created_at.desc()).first()

                if _last_ok is None:
                    _last_any = _db_h.query(_SEL_h.created_at, _SEL_h.status).filter(
                        _SEL_h.job_name == "consolidacao_diaria_04h",
                        _SEL_h.nivel == "ciclo",
                    ).order_by(_SEL_h.created_at.desc()).first()
                    _last_str = (
                        f"última execução: {_last_any.created_at.isoformat()} status={_last_any.status}"
                        if _last_any else "nunca executou"
                    )
                    try:
                        from app.services.health_alert_service import log_and_alert as _laa_h
                        _laa_h(
                            event_type="SYNC_DIARIA_MISSING",
                            severity="HIGH",
                            message="Consolidação diária 02h BRT não rodou nas últimas 26h",
                            detail=(
                                f"Nenhum ciclo 'consolidacao_diaria_04h' concluído desde {_cutoff.isoformat()}. "
                                f"{_last_str}. Verificar Scheduled Deployment e logs do backend."
                            ),
                        )
                        logger.warning("[HealthMonitor] SYNC_DIARIA_MISSING alertado (>26h sem consolidação 02h BRT)")
                    except Exception as _ae:
                        logger.warning(f"[HealthMonitor] Falha ao disparar alerta SYNC_DIARIA_MISSING: {_ae}")
            finally:
                _db_h.close()
        except Exception as _hc_err:
            logger.warning(f"[HealthMonitor] _check_daily_consolidation_health falhou: {_hc_err}")

    def _run_refresh(self, interval: int):
        with self._lock:
            if not self._running:
                return
        if _scheduler_in_quiet_hours():
            logger.info(
                "[Scheduler] Quiet hours BRT — pulando callbacks deste tick "
                "(reduz carga Magento em horário sem usuários). Próximo tick "
                f"em {interval//60} min."
            )
            self._schedule(interval)
            return
        logger.info("Running scheduled cache refresh for current year data...")
        for callback in self._refresh_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Cache refresh callback error: {e}")
        # CAMADA 3: monitor de saúde do 02h BRT — roda em cada tick
        try:
            self._check_daily_consolidation_health()
        except Exception as _hce:
            logger.warning(f"[HealthMonitor] check_daily_consolidation_health raised: {_hce}")
        self._schedule(interval)

    def stop(self):
        with self._lock:
            self._running = False
        if self._timer:
            self._timer.cancel()
        if self._daily_timer:
            self._daily_timer.cancel()
        if self._snapshot_timer:
            self._snapshot_timer.cancel()
        if self._evening_timer:
            self._evening_timer.cancel()


cache_scheduler = CacheRefreshScheduler()
