import time
import json
import threading
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Optional, Callable
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CURRENT_YEAR_TTL = 7200
HISTORICAL_TTL = None

_last_full_refresh_timestamp = None
_full_refresh_in_progress = False
_full_refresh_lock = threading.Lock()
_full_warmup_fn = None

_db_persist_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cache_persist")


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
    def __init__(self, name: str):
        self.name = name
        self._data = {}
        self._timestamps = {}
        self._lock = threading.Lock()
        self._db_loaded = False

    def _is_historical(self, cache_key: str) -> bool:
        try:
            year_part = cache_key.split("_")[0]
            year = int(year_part)
            return year < datetime.now().year
        except (ValueError, IndexError):
            return False

    def warm_from_db(self):
        loaded = _load_all_from_db(self.name)
        if loaded:
            with self._lock:
                for key, val in loaded.items():
                    if key not in self._data:
                        self._data[key] = val["data"]
                        self._timestamps[key] = val["updated_at"]
            logger.info(f"Cache '{self.name}' warmed from DB: {len(loaded)} entries loaded")
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

                if self._is_historical(cache_key):
                    return self._data[cache_key]

                elapsed = time.time() - ts
                if elapsed < CURRENT_YEAR_TTL:
                    return self._data[cache_key]

                if stale_ok:
                    logger.debug(f"Cache '{self.name}' serving stale data for key={cache_key} (age={elapsed:.0f}s)")
                    return self._data[cache_key]

                return None

        db_result = _load_from_db(self.name, cache_key)
        if db_result is not None:
            with self._lock:
                self._data[cache_key] = db_result["data"]
                self._timestamps[cache_key] = db_result["updated_at"]
            logger.info(f"Cache '{self.name}' loaded from DB for key={cache_key}")
            return db_result["data"]

        return None

    def set(self, cache_key: str, data: Any):
        with self._lock:
            self._data[cache_key] = data
            self._timestamps[cache_key] = time.time()

        try:
            _db_persist_executor.submit(_persist_to_db, self.name, cache_key, data)
        except RuntimeError:
            logger.warning(f"DB persist executor shutdown, skipping persist for {self.name}/{cache_key}")

    def invalidate(self, cache_key: str = None):
        with self._lock:
            if cache_key:
                self._data.pop(cache_key, None)
                self._timestamps.pop(cache_key, None)
            else:
                keys_to_remove = [
                    k for k in self._data
                    if not self._is_historical(k)
                ]
                for k in keys_to_remove:
                    self._data.pop(k, None)
                    self._timestamps.pop(k, None)

    def invalidate_all(self):
        with self._lock:
            self._data.clear()
            self._timestamps.clear()

    def get_info(self, cache_key: str = None) -> dict:
        with self._lock:
            if cache_key and cache_key in self._timestamps:
                ts = self._timestamps[cache_key]
                is_hist = self._is_historical(cache_key)
                return {
                    "cached": True,
                    "cached_at": datetime.fromtimestamp(ts).isoformat(),
                    "is_historical": is_hist,
                    "ttl": "permanent" if is_hist else f"{CURRENT_YEAR_TTL}s",
                    "age_seconds": round(time.time() - ts, 1)
                }
            return {"cached": False}

    def get_all_keys(self) -> list:
        with self._lock:
            return list(self._data.keys())

    def entry_count(self) -> int:
        with self._lock:
            return len(self._data)


isc_cache = SmartCache("isc_pricing")
event_detail_cache = SmartCache("event_detail")
daily_sales_cache = SmartCache("daily_sales")
curva_cache = SmartCache("curva_comparativa")
medias_cache = SmartCache("medias_vendas")

ALL_CACHES = [isc_cache, event_detail_cache, daily_sales_cache, curva_cache, medias_cache]


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
        logger.info(f"Cache refresh scheduler started (interval: {interval}s, daily at 07:00 BRT)")

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
        target = now.replace(hour=7, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)

        delay = (target - now).total_seconds()
        logger.info(f"Next daily full refresh scheduled in {delay:.0f}s ({target.isoformat()})")

        self._daily_timer = threading.Timer(delay, self._run_daily_refresh)
        self._daily_timer.daemon = True
        self._daily_timer.start()

    def _run_daily_refresh(self):
        with self._lock:
            if not self._running:
                return

        logger.info("=== DAILY FULL CACHE REFRESH STARTED (07:00 BRT) ===")
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


cache_scheduler = CacheRefreshScheduler()
