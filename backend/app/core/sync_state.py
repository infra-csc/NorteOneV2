"""Estado leve e in-process compartilhado entre o scheduler (main.py) e
endpoints (admin.py).

Mantém aqui apenas timestamps de jobs que NÃO valem persistir (perdem sentido
fora da sessão atual). Para idade de snapshots use as tabelas dedicadas.

Vive em app.core (e não em main) pra evitar ambiguidade de import:
- main.py raiz é um stub do Replit
- backend/main.py é o app FastAPI, mas o nome 'main' colide se importado de
  outro contexto. Colocando aqui, o import é sempre inequívoco.
"""

from __future__ import annotations
import time
from threading import Lock

_lock = Lock()
_last_safety_tick: float | None = None


def mark_safety_tick() -> None:
    """Marca o término do tick atual do margem safety check."""
    global _last_safety_tick
    with _lock:
        _last_safety_tick = time.time()


def get_last_safety_tick() -> float | None:
    """Retorna epoch seg do último tick, ou None se ainda não rodou."""
    with _lock:
        return _last_safety_tick
