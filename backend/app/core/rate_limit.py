import re
import time
from collections import deque, defaultdict
from threading import Lock
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
import jwt

WINDOW_SECONDS = 60

# Endpoints caros que fazem queries pesadas no Magento/Ativo por requisição
_FORCE_REFRESH_RE = re.compile(r"force_refresh=true", re.IGNORECASE)

LIMIT_NORMAL = 120          # 120 req/min: comporta polling de UI sem bloquear
LIMIT_FORCE_REFRESH = 6     # 6 req/min: força atualização completa (query pesada)
LIMIT_LOGIN = 10            # tentativas de login por IP/min

# Nunca aplicar rate limit nestes paths — são críticos para a sessão ou
# são endpoints leves de polling que devem sempre responder.
SKIP_PATHS = {
    "/api/auth/logout",
    "/api/auth/me",               # verificação de sessão — nunca bloquear
    "/api/marketing/cache/status", # polled a cada 2s durante warmup
}

# Prefixos de path que nunca devem ser bloqueados
_SKIP_PREFIXES = (
    "/api/projecao/pendencias",   # polled frequentemente pelo layout
)


# Endpoints onde force_refresh é barato (só lê PostgreSQL, não toca Magento).
# Mesmo com force_refresh=true devem cair no limite normal, não no agressivo
# de 6/min — caso contrário o usuário clica "Atualizar" 7x e fica bloqueado.
_FORCE_REFRESH_CHEAP_PATHS = (
    "/api/marketing/diagnostico-curvas",
    "/api/projecao/consolidado",   # força só recomputa do PostgreSQL, sem Magento
)


def _resolve_limit(path: str, query_string: str) -> int:
    if path == "/api/auth/login":
        return LIMIT_LOGIN
    if _FORCE_REFRESH_RE.search(query_string) and not path.startswith(_FORCE_REFRESH_CHEAP_PATHS):
        return LIMIT_FORCE_REFRESH
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

        if not path.startswith("/api/"):
            return await call_next(request)

        if path in SKIP_PATHS:
            return await call_next(request)

        if path.startswith(_SKIP_PREFIXES):
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
