"""Persistência do snapshot completo do detalhe de evento.

Permite que GET /marketing/eventos/{id} responda em ~50ms a partir do banco,
mesmo após restart do servidor (o cache em memória é volátil).

Uso:
- get_persisted_detail(db, evento_id, ano) -> dict | None
- save_persisted_detail(db, evento_id, ano, payload, data_evento, is_completed)
- apply_today_overlay(db, payload, evento_id) — sobrepõe ao payload do snapshot
  apenas os campos voláteis de hoje (currentSales, dailySales[hoje], averageTicket)
  lendo de vendas_diaria_snapshot (mantido fresco por sincronizar_hoje_batch).
- refresh_active_event_details(...) — chamado pelo scheduler para manter
  todos os eventos ativos sempre frescos.
"""
from __future__ import annotations

import logging
from datetime import datetime, date
from typing import Any
from zoneinfo import ZoneInfo

from fastapi.encoders import jsonable_encoder
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..models.evento_detail_snapshot import EventoDetailSnapshot
from ..models.vendas_snapshot import VendasDiariaSnapshot

logger = logging.getLogger(__name__)


def apply_today_overlay(db: Session, payload: dict, evento_id: str) -> dict:
    """Sobrepõe campos voláteis de HOJE no payload do snapshot.

    Apenas para eventos agrupados (prefixo 'grp_'). Lê hoje de vendas_diaria_snapshot
    (atualizado por sincronizar_hoje_batch a cada 30 min + ao clicar em Sincronizar Hoje).

    Substitui no payload (sem mutar o snapshot persistido):
      - dailySales: garante linha de hoje com qty/receita atualizadas
      - evento.currentSales: incrementado pelas vendas de hoje
      - evento.averageTicket: recomputado se houver receita
      - ultima_atualizacao_inscricoes: timestamp do último sync_hoje
      - ultima_atualizacao: timestamp do último sync_hoje (compat. frontend antigo)

    Não toca em: ISC, kits, margem orçada, curvas históricas, comparativo anual.
    Esses campos só mudam no recompute completo (a cada 30 min em background).

    Retorna o payload modificado (cópia rasa) ou o payload original em caso de erro.
    """
    if not isinstance(payload, dict):
        return payload
    if not evento_id or not evento_id.startswith("grp_"):
        # Standalone events (numeric ID) não têm overlay simples — snapshot do
        # scheduler (a cada 30 min) é suficiente. Retorna sem alterar.
        return payload

    grupo_nome = evento_id[4:]
    # Usa data BRT para evitar off-by-one em torno de meia-noite UTC.
    today = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    today_str = today.isoformat()

    try:
        row = (
            db.query(VendasDiariaSnapshot)
            .filter(
                VendasDiariaSnapshot.evento_grupo == grupo_nome,
                VendasDiariaSnapshot.fonte == "CONSOLIDADO",
                VendasDiariaSnapshot.data_venda == today,
            )
            .first()
        )
    except Exception as e:
        logger.warning(f"[Overlay] read vendas_diaria_snapshot falhou para '{grupo_nome}': {e}")
        return payload

    today_qty_db = int(row.quantidade) if row else 0
    today_rev_db = float(row.receita or 0.0) if row else 0.0

    # Cópia rasa para não mutar o dict original (que pode estar referenciado em cache).
    out = dict(payload)

    # --- dailySales overlay (delta-based para preservar consistência) ---
    daily = list(out.get("dailySales") or [])
    # Identifica a linha de hoje no payload (se já existir).
    old_today_qty = 0
    today_idx = -1
    if daily:
        for i in range(len(daily) - 1, max(-1, len(daily) - 4), -1):
            row_d = daily[i]
            if isinstance(row_d, dict) and row_d.get("date") == today_str:
                today_idx = i
                old_today_qty = int(row_d.get("sales") or 0)
                break
    if today_idx >= 0:
        # Substitui sales preservando campos auxiliares (expected, cumulativeExpected, etc).
        new_today = dict(daily[today_idx])
        new_today["sales"] = today_qty_db
        daily[today_idx] = new_today
        out["dailySales"] = daily
    elif row is not None and today_qty_db > 0:
        daily.append({
            "date": today_str,
            "sales": today_qty_db,
            "expected": 0,
            "cumulativeExpected": 0,
        })
        out["dailySales"] = daily

    # --- evento.currentSales / averageTicket (delta-based, sempre consistente
    # com o valor atualizado de hoje em vendas_diaria_snapshot) ---
    qty_delta = today_qty_db - old_today_qty
    evt = out.get("evento")
    if isinstance(evt, dict) and qty_delta != 0:
        evt = dict(evt)
        base_qty = int(evt.get("currentSales") or 0)
        new_qty = max(0, base_qty + qty_delta)
        evt["currentSales"] = new_qty
        # Estima receita anterior pelo ticket médio do payload.
        base_avg = float(evt.get("averageTicket") or 0.0)
        base_rev = base_avg * base_qty if base_qty > 0 else 0.0
        # Aproxima delta de receita: usa receita real do row de hoje vs receita
        # estimada anterior pelo ticket médio para os old_today_qty.
        old_today_rev_est = base_avg * old_today_qty if (base_avg > 0 and old_today_qty > 0) else 0.0
        new_rev = max(0.0, base_rev - old_today_rev_est + today_rev_db)
        if new_qty > 0 and new_rev > 0:
            evt["averageTicket"] = round(new_rev / new_qty, 2)
        out["evento"] = evt

    # --- timestamps ---
    try:
        from ..core.cache import get_last_sync_hoje
        _lsh = get_last_sync_hoje()
        if _lsh:
            _lsh_iso = datetime.fromtimestamp(_lsh, tz=ZoneInfo("America/Sao_Paulo")).isoformat()
            out["ultima_atualizacao_inscricoes"] = _lsh_iso
            # Atualiza ultima_atualizacao para refletir o sync_hoje (compat frontend).
            # O frontend lê este campo para o badge "Dados de hoje/ontem às HH:MM".
            out["ultima_atualizacao"] = _lsh_iso
    except Exception as e:
        logger.debug(f"[Overlay] could not inject last_sync_hoje: {e}")

    return out


def _to_jsonable(payload: Any) -> Any:
    """Converte payload (incluindo modelos Pydantic) em estrutura JSON-safe."""
    return jsonable_encoder(payload)


def get_persisted_detail(db: Session, evento_id: str, ano: int) -> dict | None:
    """Lê o snapshot persistido. Retorna dict com payload/computed_at/is_completed ou None."""
    try:
        row = (
            db.query(EventoDetailSnapshot)
            .filter(
                EventoDetailSnapshot.evento_id == evento_id,
                EventoDetailSnapshot.ano == ano,
            )
            .first()
        )
        if not row:
            return None
        return {
            "payload": row.payload,
            "computed_at": row.computed_at,
            "is_completed": bool(row.is_completed),
            "data_evento": row.data_evento,
        }
    except Exception as e:
        logger.warning(f"[EventDetailSnapshot] read failed for {evento_id}/{ano}: {e}")
        return None


def save_persisted_detail(
    db: Session,
    evento_id: str,
    ano: int,
    payload: Any,
    data_evento: date | None = None,
    is_completed: bool = False,
) -> bool:
    """UPSERT do snapshot. Retorna True se gravou, False em caso de erro."""
    try:
        json_safe = _to_jsonable(payload)
        # Remove campos voláteis que devem ser injetados a cada request
        if isinstance(json_safe, dict):
            json_safe = {
                k: v for k, v in json_safe.items()
                if k not in ("commercialActions", "__is_completed")
            }
        stmt = pg_insert(EventoDetailSnapshot).values(
            evento_id=evento_id,
            ano=ano,
            payload=json_safe,
            data_evento=data_evento,
            is_completed=is_completed,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=['evento_id', 'ano'],
            set_={
                'payload': stmt.excluded.payload,
                'data_evento': stmt.excluded.data_evento,
                'is_completed': stmt.excluded.is_completed,
                'computed_at': datetime.now(),
            },
        )
        db.execute(stmt)
        db.commit()
        return True
    except Exception as e:
        logger.warning(f"[EventDetailSnapshot] save failed for {evento_id}/{ano}: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return False


def refresh_active_event_details(max_events: int | None = None) -> int:
    """Recomputa o detalhe de todos os eventos ativos (ano corrente) e persiste.

    Chamado pelo scheduler em background após sincronizar_hoje_batch.
    Por padrão recomputa todos os EventoGrupo (sem limite) para garantir
    cobertura completa. Retorna a quantidade de eventos atualizados.
    """
    from ..core.database import SessionLocal
    from ..models.dimensoes import EventoGrupo as EventoGrupoModel
    from ..api.routes.marketing import get_marketing_event_by_id

    count = 0
    db = SessionLocal()
    try:
        ano = datetime.now().year
        q = db.query(EventoGrupoModel)
        if max_events is not None:
            q = q.limit(max_events)
        grupos = q.all()
        for g in grupos:
            evento_id = f"grp_{g.nome}"
            try:
                # force_refresh=True força recomputo + persistência via save_persisted_detail
                _db_iter = SessionLocal()
                try:
                    get_marketing_event_by_id(
                        evento_id=evento_id,
                        ano=ano,
                        force_refresh=True,
                        db=_db_iter,
                        current_user=None,
                        response=None,
                    )
                    count += 1
                finally:
                    _db_iter.close()
            except Exception as e:
                logger.warning(f"[EventDetailSnapshot] refresh '{evento_id}' falhou: {e}")
    except Exception as e:
        logger.error(f"[EventDetailSnapshot] refresh_active_event_details falhou: {e}")
    finally:
        db.close()
    logger.info(f"[EventDetailSnapshot] refresh_active_event_details: {count} eventos atualizados")
    return count
