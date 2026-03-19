import time
import json
import threading
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Optional, Callable
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CURRENT_YEAR_TTL = 79200
HISTORICAL_TTL = None
MAX_STALE_AGE = 86400
NIGHTLY_CACHE_TTL = 79200

_last_full_refresh_timestamp = None
_full_refresh_in_progress = False
_full_refresh_lock = threading.Lock()
_full_warmup_fn = None
_warmup_progress = {"step": 0, "total_steps": 3, "label": "", "started_at": None, "sub_current": 0, "sub_total": 0}
_last_refresh_error = None

_db_persist_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cache_persist")
_swr_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="cache_swr")
_swr_in_flight: set = set()
_swr_lock = threading.Lock()


def register_full_warmup_fn(fn: Callable):
    global _full_warmup_fn
    _full_warmup_fn = fn


def trigger_full_warmup_async():
    global _full_warmup_fn, _full_refresh_in_progress
    with _full_refresh_lock:
        if _full_warmup_fn is None:
            logger.warning("No full warmup function registered")
            return False
        if _full_refresh_in_progress:
            return False
        _full_refresh_in_progress = True
    thread = threading.Thread(target=_full_warmup_fn, daemon=True)
    thread.start()
    return True


def get_last_full_refresh():
    global _last_full_refresh_timestamp
    return _last_full_refresh_timestamp


def set_last_full_refresh(ts=None):
    global _last_full_refresh_timestamp
    _last_full_refresh_timestamp = ts or time.time()


def is_full_refresh_in_progress():
    global _full_refresh_in_progress
    return _full_refresh_in_progress


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


def _persist_to_db(cache_name: str, cache_key: str, data: Any):
    db = None
    try:
        db = _get_db_session()
        if db is None:
            return
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from app.models.cache_entry import CacheEntry

        safe_data = _stringify_keys(data)
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
                        if is_hist or is_completed or db_age < MAX_STALE_AGE:
                            self._data[key] = data
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


isc_cache = SmartCache("isc_pricing", ttl=NIGHTLY_CACHE_TTL)
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


def set_gap_detection_result(result: dict):
    with _gap_detection_lock:
        _gap_detection_store.clear()
        _gap_detection_store.update(result)


def get_gap_detection_result() -> dict:
    with _gap_detection_lock:
        return dict(_gap_detection_store)


def warm_all_caches_from_db():
    logger.info("Warming all caches from PostgreSQL...")
    start = time.time()
    for cache in ALL_CACHES:
        try:
            cache.warm_from_db()
        except Exception as e:
            logger.error(f"Failed to warm cache '{cache.name}' from DB: {e}")
    elapsed = time.time() - start
    logger.info(f"All caches warmed from DB in {elapsed:.1f}s")


class CacheRefreshScheduler:
    def __init__(self):
        self._timer = None
        self._daily_timer = None
        self._snapshot_timer = None
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
        logger.info(f"Cache refresh scheduler started (interval: {interval}s, daily snapshot at 04:00 BRT, daily refresh at 05:00 BRT)")

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
        target = now.replace(hour=5, minute=0, second=0, microsecond=0)
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
        target = now.replace(hour=4, minute=0, second=0, microsecond=0)
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

        logger.info("=== DAILY SNAPSHOT CONSOLIDATION STARTED (04:00 BRT) ===")
        try:
            from app.core.database import SessionLocal
            from app.services.snapshot_service import snapshot_diario_batch, consolidar_curvas_historicas_batch
            db = SessionLocal()
            try:
                snapshot_diario_batch(db)
                consolidar_curvas_historicas_batch(db)
                logger.info("=== DAILY SNAPSHOT CONSOLIDATION COMPLETED ===")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Daily snapshot consolidation error: {e}")

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
            except Exception as e:
                logger.error(f"Daily full cache refresh error: {e}")
        else:
            for callback in self._refresh_callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Daily cache refresh callback error: {e}")

        self._schedule_daily_refresh()

    def _run_refresh(self, interval: int):
        with self._lock:
            if not self._running:
                return
        logger.info("Running scheduled cache refresh for current year data...")
        for callback in self._refresh_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Cache refresh callback error: {e}")
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


cache_scheduler = CacheRefreshScheduler()
