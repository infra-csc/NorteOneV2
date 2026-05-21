"""Snapshot persistente do Mapeamento de Kits.

Centraliza o ciclo de rebuild + leitura para que a tela de Mapeamento de
Kits não dependa do Magento ao vivo a cada request, e para que o botão
"Atualizar" aplique apenas o diff (novos / alterados / removidos).

Convenções
----------
* Snapshot guarda APENAS os campos vindos de Magento/Ativo (id_evento,
  nome_evento, nome_kit, tipo_categoria, lote_atual, price, special_price,
  status_kit, fonte). KitConfig (multiplicador, custo, kit básico, etc.)
  é sempre lido em tempo real para que edições do usuário apareçam
  imediatamente.
* Rebuild reaproveita a função existente
  :func:`app.api.routes.kit_config._build_kit_rows_internal` para evitar
  duplicar a lógica complexa de cruzamento Magento↔Ativo.
* Falhas parciais (Magento OK, Ativo fora — ou vice-versa) NÃO removem
  linhas da fonte indisponível, evitando que a tela "perca" eventos
  durante uma instabilidade temporária.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from datetime import datetime
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..models.kit_mapping_snapshot import KitMappingSnapshot
from ..schemas.kit_config import KitRow

# Chave fixa para pg_try_advisory_lock — garante que apenas UM rebuild rode
# por cluster Postgres, mesmo em deployment multi-worker/multi-processo.
_PG_ADVISORY_LOCK_KEY = 871234567

logger = logging.getLogger(__name__)

_REBUILD_LOCK = threading.Lock()


def _normalize_tipo_cat(v) -> str:
    return (str(v).strip() if v not in (None, "") else "")


def _content_hash(row: KitRow) -> str:
    """Hash determinístico das colunas source-of-truth da linha."""
    payload = "|".join(str(x) for x in (
        row.id_evento or "",
        row.nome_evento or "",
        row.nome_kit or "",
        _normalize_tipo_cat(row.tipo_categoria),
        row.lote_atual or "",
        f"{row.price:.2f}" if row.price is not None else "",
        f"{row.special_price:.2f}" if row.special_price is not None else "",
        row.status_kit or "",
        row.fonte or "",
    ))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def rebuild_kit_snapshot(db: Session) -> dict:
    """Roda Magento+Ativo, faz diff contra o snapshot persistido e devolve
    o resumo da operação.

    Retorno
    -------
    dict com chaves:
        status: 'ok' | 'partial' | 'error'
        novos, alterados, sem_mudanca, removidos: int
        total_atual: int
        magento_ok, ativo_ok: bool
        duration_ms: int
        msg: str (quando status != 'ok')
    """
    if not _REBUILD_LOCK.acquire(blocking=False):
        return {
            "status": "error",
            "msg": "Outra atualização já está em andamento. Aguarde alguns segundos.",
            "novos": 0, "alterados": 0, "sem_mudanca": 0, "removidos": 0,
            "total_atual": db.query(KitMappingSnapshot).count(),
            "magento_ok": False, "ativo_ok": False, "duration_ms": 0,
        }
    # Cross-process: advisory lock impede que outro worker rode rebuild em
    # paralelo. Usa CONEXÃO DEDICADA (independente da sessão ORM ``db``)
    # para que o ciclo lock/unlock NÃO compartilhe transação com o diff —
    # caso contrário, um commit do unlock poderia persistir mudanças
    # parciais se uma exceção ocorresse no meio do diff.
    lock_conn = None
    got_pg_lock = False
    try:
        lock_conn = db.get_bind().connect()
        got_pg_lock = bool(lock_conn.execute(
            text("SELECT pg_try_advisory_lock(:k)"),
            {"k": _PG_ADVISORY_LOCK_KEY},
        ).scalar())
    except Exception as e:
        logger.warning(f"[KitSnapshot] pg_try_advisory_lock falhou: {e}")
    if not got_pg_lock:
        if lock_conn is not None:
            try: lock_conn.close()
            except Exception: pass
        _REBUILD_LOCK.release()
        return {
            "status": "error",
            "msg": "Outra atualização já está em andamento em outro processo. Aguarde alguns segundos.",
            "novos": 0, "alterados": 0, "sem_mudanca": 0, "removidos": 0,
            "total_atual": db.query(KitMappingSnapshot).count(),
            "magento_ok": False, "ativo_ok": False, "duration_ms": 0,
        }
    started_at = datetime.utcnow()
    t0 = time.time()
    try:
        # Import tardio para evitar ciclos (kit_config -> service -> kit_config).
        from ..api.routes.kit_config import _build_kit_rows_internal

        try:
            # ``local_fallback_allowed=False`` garante que linhas vindas do
            # fallback local NUNCA contaminem o snapshot (que deve refletir
            # apenas Magento+Ativo).
            rows, magento_ok, ativo_ok = _build_kit_rows_internal(
                db, force_refresh=True, local_fallback_allowed=False,
            )
        except Exception as e:
            logger.error(f"[KitSnapshot] rebuild falhou na coleta de fontes: {e}")
            return {
                "status": "error",
                "msg": f"Falha ao consultar fontes: {type(e).__name__}",
                "novos": 0, "alterados": 0, "sem_mudanca": 0, "removidos": 0,
                "total_atual": db.query(KitMappingSnapshot).count(),
                "magento_ok": False, "ativo_ok": False,
                "duration_ms": int((time.time() - t0) * 1000),
            }

        if not magento_ok and not ativo_ok:
            return {
                "status": "error",
                "msg": "Magento e Ativo indisponíveis no momento. Tente em alguns minutos.",
                "novos": 0, "alterados": 0, "sem_mudanca": 0, "removidos": 0,
                "total_atual": db.query(KitMappingSnapshot).count(),
                "magento_ok": False, "ativo_ok": False,
                "duration_ms": int((time.time() - t0) * 1000),
            }

        # Indexa existentes por (bundle_entity_id, tipo_categoria_normalizado).
        existing = {
            (r.bundle_entity_id, r.tipo_categoria or ""): r
            for r in db.query(KitMappingSnapshot).all()
        }

        seen_keys: set = set()
        novos = alterados = sem_mudanca = 0

        for row in rows:
            tcat = _normalize_tipo_cat(row.tipo_categoria)
            key = (int(row.bundle_entity_id), tcat)
            seen_keys.add(key)
            h = _content_hash(row)
            ex = existing.get(key)
            if ex is None:
                db.add(KitMappingSnapshot(
                    bundle_entity_id=int(row.bundle_entity_id),
                    tipo_categoria=tcat,
                    fonte=row.fonte or "",
                    id_evento=row.id_evento,
                    nome_evento=row.nome_evento,
                    nome_kit=row.nome_kit,
                    lote_atual=row.lote_atual,
                    price=row.price,
                    special_price=row.special_price,
                    status_kit=row.status_kit,
                    content_hash=h,
                    atualizado_em=started_at,
                    visto_em=started_at,
                ))
                novos += 1
            elif ex.content_hash != h:
                ex.fonte         = row.fonte or ex.fonte
                ex.id_evento     = row.id_evento
                ex.nome_evento   = row.nome_evento
                ex.nome_kit      = row.nome_kit
                ex.lote_atual    = row.lote_atual
                ex.price         = row.price
                ex.special_price = row.special_price
                ex.status_kit    = row.status_kit
                ex.content_hash  = h
                ex.atualizado_em = started_at
                ex.visto_em      = started_at
                alterados += 1
            else:
                ex.visto_em = started_at
                sem_mudanca += 1

        # Remoções: só apaga linhas de uma fonte se essa fonte respondeu OK
        # nesta rodada. Evita "sumir" eventos durante uma instabilidade.
        removidos = 0
        for key, ex in existing.items():
            if key in seen_keys:
                continue
            fonte = (ex.fonte or "").lower()
            if fonte == "magento" and not magento_ok:
                continue
            if fonte == "ativo" and not ativo_ok:
                continue
            db.delete(ex)
            removidos += 1

        db.commit()

        status = "ok" if (magento_ok and ativo_ok) else "partial"
        total = db.query(KitMappingSnapshot).count()
        duration_ms = int((time.time() - t0) * 1000)
        logger.info(
            f"[KitSnapshot] rebuild concluído status={status} "
            f"novos={novos} alterados={alterados} sem_mudanca={sem_mudanca} "
            f"removidos={removidos} total={total} "
            f"magento_ok={magento_ok} ativo_ok={ativo_ok} duration_ms={duration_ms}"
        )
        return {
            "status": status,
            "novos": novos,
            "alterados": alterados,
            "sem_mudanca": sem_mudanca,
            "removidos": removidos,
            "total_atual": total,
            "magento_ok": magento_ok,
            "ativo_ok": ativo_ok,
            "duration_ms": duration_ms,
            "msg": (
                "Atualização concluída." if status == "ok"
                else f"Atualização parcial: {'Magento' if not magento_ok else 'Ativo'} indisponível — linhas dessa fonte foram preservadas."
            ),
        }
    except Exception as e:
        # Qualquer exceção não tratada acima descarta o diff inteiro —
        # snapshot é all-or-nothing.
        logger.exception(f"[KitSnapshot] rebuild interrompido por exceção: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        raise
    finally:
        if got_pg_lock and lock_conn is not None:
            try:
                lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"),
                                  {"k": _PG_ADVISORY_LOCK_KEY})
            except Exception as e:
                logger.warning(f"[KitSnapshot] pg_advisory_unlock falhou: {e}")
        if lock_conn is not None:
            try: lock_conn.close()
            except Exception: pass
        _REBUILD_LOCK.release()


def read_kit_snapshot(db: Session) -> Optional[List[dict]]:
    """Lê todas as linhas persistidas. Retorna lista de dicts no formato
    aceito pelo cruzamento de overlay (KitConfig) feito no endpoint.

    Devolve ``None`` se o snapshot está vazio OU se a tabela ainda não
    existe (cold start sem migração) — caller cai no caminho legado.
    """
    try:
        rows = db.query(KitMappingSnapshot).all()
    except Exception as e:
        # UndefinedTable / migração ausente: degrada silenciosamente
        # para o caminho legado em vez de devolver 500.
        logger.warning(f"[KitSnapshot] read_kit_snapshot falhou ({type(e).__name__}); caindo no caminho legado")
        try: db.rollback()
        except Exception: pass
        return None
    if not rows:
        return None
    return [
        {
            "bundle_entity_id": int(r.bundle_entity_id),
            "tipo_categoria": (r.tipo_categoria or None) or None,
            "fonte": r.fonte,
            "id_evento": r.id_evento,
            "nome_evento": r.nome_evento,
            "nome_kit": r.nome_kit,
            "lote_atual": r.lote_atual,
            "price": float(r.price) if r.price is not None else None,
            "special_price": float(r.special_price) if r.special_price is not None else None,
            "status_kit": r.status_kit,
        }
        for r in rows
    ]


def snapshot_is_stale(db: Session, max_age_hours: int = 24) -> bool:
    """True se snapshot está vazio, ausente (tabela não existe) ou mais
    velho que ``max_age_hours``."""
    from sqlalchemy import func
    try:
        most_recent = db.query(func.max(KitMappingSnapshot.atualizado_em)).scalar()
    except Exception as e:
        logger.warning(f"[KitSnapshot] snapshot_is_stale: tabela ausente/erro ({type(e).__name__})")
        try: db.rollback()
        except Exception: pass
        return True
    if most_recent is None:
        return True
    age = datetime.utcnow() - most_recent
    return age.total_seconds() > max_age_hours * 3600
