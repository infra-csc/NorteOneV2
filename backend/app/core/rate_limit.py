import re
import time
from collections import deque, defaultdict
from threading import Lock
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
import jwt

WINDOW_SECONDS = 60

_HEAVY_PATH_RE = re.compile(
    r"^/api/marketing/eventos(/|$)"
)
_FORCE_REFRESH_RE = re.compile(r"force_refresh=true", re.IGNORECASE)

LIMIT_NORMAL = 60
LIMIT_HEAVY = 10
LIMIT_FORCE_REFRESH = 3

SKIP_PATHS = {"/api/auth/login", "/api/auth/logout"}


def _resolve_limit(path: str, query_string: str) -> int:
    if _FORCE_REFRESH_RE.search(query_string):
        return LIMIT_FORCE_REFRESH
    if _HEAVY_PATH_RE.match(path):
        return LIMIT_HEAVY
    return LIMIT_NORMAL


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, secret_key: str, algorithm: str = "HS256"):
        super().__init__(app)
        self._secret_key = secret_key
        self._algorithm = algorithm
        self._buckets: dict[str, deque] = defaultdict(deque)
        self._lock = Lock()

    def _identify(self, request: Request) -> str:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            try:
                payload = jwt.decode(
                    auth[7:],
                    self._secret_key,
                    algorithms=[self._algorithm],
                )
                sub = payload.get("sub")
                if sub:
                    return f"user:{sub}"
            except Exception:
                pass
        host = request.client.host if request.client else "unknown"
        return f"ip:{host}"

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if not path.startswith("/api/") or path in SKIP_PATHS:
            return await call_next(request)

        key = self._identify(request)
        limit = _resolve_limit(path, str(request.url.query))
        now = time.monotonic()
        window_start = now - WINDOW_SECONDS

        with self._lock:
            bucket = self._buckets[key]
            while bucket and bucket[0] < window_start:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(bucket[0] - window_start) + 1)
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": (
                            f"Muitas requisições. Aguarde {retry_after}s "
                            "antes de tentar novamente."
                        ),
                        "retry_after": retry_after,
                    },
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.append(now)

        return await call_next(request)
