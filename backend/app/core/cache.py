import time
import threading
import logging
from datetime import datetime
from typing import Any, Optional, Callable

logger = logging.getLogger(__name__)

CURRENT_YEAR_TTL = 3600
HISTORICAL_TTL = None


class SmartCache:
    def __init__(self, name: str):
        self.name = name
        self._data = {}
        self._timestamps = {}
        self._lock = threading.Lock()
    
    def _is_historical(self, cache_key: str) -> bool:
        try:
            year_part = cache_key.split("_")[0]
            year = int(year_part)
            return year < datetime.now().year
        except (ValueError, IndexError):
            return False
    
    def get(self, cache_key: str) -> Optional[Any]:
        with self._lock:
            if cache_key not in self._data:
                return None
            
            ts = self._timestamps.get(cache_key)
            if ts is None:
                return None
            
            if self._is_historical(cache_key):
                return self._data[cache_key]
            
            elapsed = time.time() - ts
            if elapsed < CURRENT_YEAR_TTL:
                return self._data[cache_key]
            
            return None
    
    def set(self, cache_key: str, data: Any):
        with self._lock:
            self._data[cache_key] = data
            self._timestamps[cache_key] = time.time()
    
    def invalidate(self, cache_key: str = None):
        with self._lock:
            if cache_key:
                self._data.pop(cache_key, None)
                self._timestamps.pop(cache_key, None)
            else:
                current_year = datetime.now().year
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


isc_cache = SmartCache("isc_pricing")
event_detail_cache = SmartCache("event_detail")
daily_sales_cache = SmartCache("daily_sales")
curva_cache = SmartCache("curva_comparativa")
medias_cache = SmartCache("medias_vendas")


class CacheRefreshScheduler:
    def __init__(self):
        self._timer = None
        self._refresh_callbacks = []
        self._running = False
        self._lock = threading.Lock()
    
    def register(self, callback: Callable):
        self._refresh_callbacks.append(callback)
    
    def start(self, interval: int = CURRENT_YEAR_TTL):
        with self._lock:
            if self._running:
                return
            self._running = True
        self._schedule(interval)
        logger.info(f"Cache refresh scheduler started (interval: {interval}s)")
    
    def _schedule(self, interval: int):
        self._timer = threading.Timer(interval, self._run_refresh, args=[interval])
        self._timer.daemon = True
        self._timer.start()
    
    def _run_refresh(self, interval: int):
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


cache_scheduler = CacheRefreshScheduler()
