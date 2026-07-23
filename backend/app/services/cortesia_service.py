"""Integração somente-leitura com o app externo de Cortesias.

A API externa (CORTESIA_API_BASE_URL) expõe:
  - GET /api/metrics?sku=... | ?userId=... | ?area=...  (exatamente UM filtro)
      -> {"filter": {...}, "solicitados", "aprovados", "utilizados", "disponiveis", "source"}
  - GET /api/users
      -> {"total", "users": [{id, name, email, role, roleLabel, area, createdAt}]}

Autenticação por token Bearer (CORTESIA_API_TOKEN, secret — nunca chega ao
navegador; o frontend consome apenas as rotas proxy autenticadas do DW).

Falhas da API externa viram erro HTTP explícito (502/504) — nunca fallback
silencioso para zeros. Sucessos têm cache curto em memória (60s por chave)
para não martelar a API externa com a tela de Projeção aberta.
"""

import logging
import threading
import time

import httpx
from fastapi import HTTPException

from ..core.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10.0
_CACHE_TTL_SECONDS = 60.0

_cache: dict = {}  # key -> (ts, data)
_cache_lock = threading.Lock()


def _cache_get(key: str):
    now = time.time()
    with _cache_lock:
        entry = _cache.get(key)
        if entry and (now - entry[0]) < _CACHE_TTL_SECONDS:
            return entry[1]
    return None


def _cache_put(key: str, data):
    now = time.time()
    with _cache_lock:
        expired = [k for k, (ts, _d) in _cache.items() if now - ts >= _CACHE_TTL_SECONDS]
        for k in expired:
            _cache.pop(k, None)
        _cache[key] = (now, data)


def _base_url() -> str:
    return (settings.CORTESIA_API_BASE_URL or "").rstrip("/")


def _ensure_configured():
    if not settings.CORTESIA_API_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="Integração com o app de Cortesias não configurada (token ausente). Contate um administrador.",
        )
    if not _base_url():
        raise HTTPException(
            status_code=503,
            detail="Integração com o app de Cortesias não configurada (URL ausente). Contate um administrador.",
        )


def ensure_configured():
    """Valida a configuração da integração (token + URL). Levanta 503 se ausente."""
    _ensure_configured()


def _extract_error_message(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict):
            msg = data.get("error") or data.get("message") or data.get("detail")
            if isinstance(msg, str) and msg.strip():
                return msg.strip()
    except Exception:
        pass
    return ""


def _fetch(path: str, params: dict | None = None):
    """GET na API externa com tratamento explícito de erros. Retorna o JSON."""
    _ensure_configured()
    url = f"{_base_url()}{path}"
    headers = {"Authorization": f"Bearer {settings.CORTESIA_API_TOKEN}"}
    try:
        resp = httpx.get(url, params=params or {}, headers=headers, timeout=_TIMEOUT_SECONDS)
    except httpx.TimeoutException:
        logger.warning("Cortesia API timeout em %s", path)
        raise HTTPException(
            status_code=504,
            detail="O app de Cortesias demorou para responder. Tente novamente em instantes.",
        )
    except httpx.HTTPError as e:
        logger.warning("Cortesia API erro de conexão em %s: %s", path, e)
        raise HTTPException(
            status_code=502,
            detail="Não foi possível consultar o app de Cortesias (falha de conexão).",
        )

    if resp.status_code in (401, 403):
        logger.error("Cortesia API recusou o token (HTTP %s)", resp.status_code)
        raise HTTPException(
            status_code=502,
            detail="O app de Cortesias recusou o token da integração. Contate um administrador.",
        )
    if resp.status_code in (400, 404, 422):
        msg = _extract_error_message(resp) or "Consulta inválida para o app de Cortesias."
        raise HTTPException(status_code=resp.status_code if resp.status_code != 422 else 400, detail=msg)
    if resp.status_code >= 500:
        logger.warning("Cortesia API HTTP %s em %s", resp.status_code, path)
        raise HTTPException(
            status_code=502,
            detail="O app de Cortesias está com problemas no momento. Tente novamente em instantes.",
        )
    try:
        return resp.json()
    except ValueError:
        logger.warning("Cortesia API retornou corpo não-JSON em %s", path)
        raise HTTPException(
            status_code=502,
            detail="Resposta inesperada do app de Cortesias.",
        )


VALID_FILTER_TYPES = ("sku", "userId", "area")


def get_metrics(filtro_tipo: str, filtro_valor: str) -> dict:
    """Métricas de cortesias filtradas por exatamente um critério."""
    if filtro_tipo not in VALID_FILTER_TYPES:
        raise HTTPException(status_code=400, detail="Filtro inválido. Use sku, userId ou area.")
    valor = (filtro_valor or "").strip()
    if not valor:
        raise HTTPException(status_code=400, detail="Informe o valor do filtro.")

    cache_key = f"metrics:{filtro_tipo}:{valor.lower()}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    data = _fetch("/api/metrics", params={filtro_tipo: valor})
    if not isinstance(data, dict) or "solicitados" not in data:
        raise HTTPException(status_code=502, detail="Resposta inesperada do app de Cortesias.")
    _cache_put(cache_key, data)
    return data


def get_users() -> dict:
    """Lista de usuários do app de Cortesias (para filtros por usuário/área)."""
    cached = _cache_get("users")
    if cached is not None:
        return cached

    data = _fetch("/api/users")
    if not isinstance(data, dict) or "users" not in data:
        raise HTTPException(status_code=502, detail="Resposta inesperada do app de Cortesias.")
    _cache_put("users", data)
    return data
