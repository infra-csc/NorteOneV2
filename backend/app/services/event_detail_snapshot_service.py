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

    # --- dMinus / dMinusInscricoes overlay ---
    # O snapshot persiste D- calculado no dia em que foi gravado. Sem este
    # overlay, após 1+ dia(s) o detalhe do evento exibe D- defasado (mesma
    # classe de bug do Dash ISC/Nori). Recalcula a partir de evento.date.
    try:
        evt_cur = out.get("evento")
        if isinstance(evt_cur, dict):
            ev_date_raw = evt_cur.get("date")
            if isinstance(ev_date_raw, str) and ev_date_raw:
                try:
                    ev_date_parsed = date.fromisoformat(ev_date_raw[:10])
                except Exception:
                    ev_date_parsed = None
                if ev_date_parsed is not None:
                    d_ins_old = evt_cur.get("dMinusInscricoes")
                    d_evt_old = evt_cur.get("dMinus")
                    if isinstance(d_ins_old, int) and isinstance(d_evt_old, int) and d_evt_old >= d_ins_old:
                        dias_enc = d_evt_old - d_ins_old
                    else:
                        dias_enc = 2
                    d_evt_raw = (ev_date_parsed - today).days
                    d_ins_raw = d_evt_raw - dias_enc
                    d_evt_new = max(0, d_evt_raw)
                    d_ins_new = max(0, d_ins_raw)
                    if d_evt_new != d_evt_old or d_ins_new != d_ins_old:
                        evt_cur = dict(evt_cur)
                        evt_cur["dMinus"] = d_evt_new
                        evt_cur["dMinusInscricoes"] = d_ins_new
                        out["evento"] = evt_cur
    except Exception as e:
        logger.debug(f"[Overlay] could not refresh dMinus for '{evento_id}': {e}")

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


def aggregate_eventos_list_from_snapshots(
    db: Session,
    ano: int,
    status: str | None = None,
    categoria: str | None = None,
    busca: str | None = None,
    min_coverage: float = 0.97,
) -> dict | None:
    """Monta a resposta de GET /marketing/eventos a partir dos snapshots
    persistidos por evento, aplicando o overlay de HOJE em cada um.

    Permite que a lista abra instantaneamente após restarts (mesmo motivo
    do detalhe). Retorna None quando a cobertura de snapshots é baixa,
    para que o caller faça fallback para o caminho lento.
    """
    from ..models.cadastro_evento import CadastroEvento
    from ..models.dimensoes import DimProjeto, SkuMapping

    try:
        rows = (
            db.query(EventoDetailSnapshot)
            .filter(EventoDetailSnapshot.ano == ano)
            .all()
        )
    except Exception as e:
        logger.warning(f"[EventosListSnap] read snapshots falhou: {e}")
        return None

    if not rows:
        return None

    # Cobertura é avaliada na mesma granularidade que o endpoint da lista
    # produz: 1 entrada por evento_grupo ativo (ano) + 1 entrada por projeto
    # standalone (cadastro cujo SKU não pertence a nenhum grupo no ano).
    expected = 0
    try:
        from ..api.routes.inscricoes_consolidado import normalize_sku as _ns

        grupo_names_q = (
            db.query(SkuMapping.evento_grupo)
            .filter(
                SkuMapping.ano == ano,
                SkuMapping.ativo == True,  # noqa: E712
                SkuMapping.evento_grupo.isnot(None),
            )
            .distinct()
            .all()
        )
        grupo_names = {g[0] for g in grupo_names_q if g[0]}
        expected_grouped = len(grupo_names)

        sku_to_grupo: dict[str, str] = {}
        if grupo_names:
            sm_rows = (
                db.query(SkuMapping.sku, SkuMapping.evento_grupo)
                .filter(
                    SkuMapping.ano == ano,
                    SkuMapping.ativo == True,  # noqa: E712
                    SkuMapping.evento_grupo.in_(list(grupo_names)),
                )
                .all()
            )
            for s, g in sm_rows:
                if s and g:
                    sku_to_grupo[_ns(str(s))] = g

        cad_codigos = (
            db.query(DimProjeto.codigo)
            .join(CadastroEvento, CadastroEvento.projeto_id == DimProjeto.id)
            .filter(DimProjeto.codigo.isnot(None))
            .all()
        )
        expected_standalone = sum(
            1 for (codigo,) in cad_codigos
            if _ns(str(codigo)) not in sku_to_grupo
        )
        expected = expected_grouped + expected_standalone
    except Exception as e:
        logger.debug(f"[EventosListSnap] expected count falhou: {e}")
        expected = 0

    coverage = (len(rows) / float(expected)) if expected > 0 else 1.0
    logger.info(
        f"[EventosListSnap] ano={ano} snapshots={len(rows)} expected={expected} "
        f"coverage={coverage:.2f} threshold={min_coverage}"
    )
    if expected > 0 and coverage < min_coverage:
        return None

    eventos: list[dict] = []
    categorias_set: set[str] = set()
    events_green = events_yellow = events_red = active_count = 0

    busca_lower = (busca or "").strip().lower()

    for r in rows:
        payload = r.payload if isinstance(r.payload, dict) else {}
        try:
            payload = apply_today_overlay(db, payload, r.evento_id)
        except Exception as e:
            logger.debug(f"[EventosListSnap] overlay falhou {r.evento_id}: {e}")

        evt = payload.get("evento") if isinstance(payload, dict) else None
        if not isinstance(evt, dict):
            continue
        if "currentSales" not in evt or "salesGoal" not in evt:
            continue

        is_active = bool(evt.get("isActive"))
        if status == "active" and not is_active:
            continue
        if status == "closed" and is_active:
            continue
        cat = evt.get("category")
        if categoria and categoria != "all" and cat != categoria:
            continue
        if busca_lower and busca_lower not in (evt.get("name") or "").lower():
            continue

        if cat:
            categorias_set.add(cat)
        if is_active:
            active_count += 1
            isc_status = evt.get("iscStatus")
            if isc_status == "accelerating":
                events_green += 1
            elif isc_status == "stable":
                events_yellow += 1
            else:
                events_red += 1

        eventos.append(evt)

    eventos.sort(key=lambda e: (not e.get("isActive"), e.get("dMinus", 0)))

    try:
        from ..core.cache import get_last_full_refresh
        lfr = get_last_full_refresh()
    except Exception:
        lfr = None
    if lfr:
        ts = datetime.fromtimestamp(lfr, tz=ZoneInfo("America/Sao_Paulo")).isoformat()
    else:
        ts = datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat()

    avisos: list[str] = []
    try:
        from ..api.routes.marketing import get_isc_warnings as _giw
        avisos = list(_giw() or [])
    except Exception:
        pass

    return {
        "status": "success",
        "eventos": eventos,
        "resumo": {
            "totalActiveEvents": active_count,
            "eventsGreen": events_green,
            "eventsYellow": events_yellow,
            "eventsRed": events_red,
        },
        "categorias": sorted(categorias_set),
        "ultima_atualizacao": ts,
        "avisos": avisos,
    }


def _to_jsonable(payload: Any) -> Any:
    """Converte payload (incluindo modelos Pydantic) em estrutura JSON-safe."""
    return jsonable_encoder(payload)


def _extract_margem_total(payload: Any) -> float | None:
    """Extrai a soma de margemTotal das linhas não-CONSOLIDADO de margemPorKit.

    Retorna None quando os dados são insuficientes para comparação (lista vazia,
    sem vendas, payload malformado). Retorna 0.0 explicitamente apenas quando há
    linhas com qtd > 0 mas margemTotal = 0 (evento com custo = receita).
    """
    try:
        if not isinstance(payload, dict):
            return None
        evt = payload.get("evento")
        if not isinstance(evt, dict):
            return None
        mpk = evt.get("margemPorKit")
        if not isinstance(mpk, list) or not mpk:
            return None
        rows_real = [
            r for r in mpk
            if isinstance(r, dict) and r.get("tipoKit") != "CONSOLIDADO"
        ]
        if not rows_real:
            return None
        qtd_total = sum(int(r.get("qtd") or 0) for r in rows_real)
        if qtd_total <= 0:
            return None
        return sum(float(r.get("margemTotal") or 0.0) for r in rows_real)
    except Exception:
        return None


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
    """UPSERT do snapshot. Retorna True se gravou, False em caso de erro.

    Para eventos já concluídos (is_completed=True) aplica uma salvaguarda
    de margem: se a nova margem for inferior a 95% da margem persistida,
    o snapshot existente é preservado. Isso evita que quedas de conexão
    com o Magento (respostas parciais com menos bundles) sobrescrevam o
    valor final correto de um evento encerrado.
    """
    try:
        json_safe = _to_jsonable(payload)
        # Remove campos voláteis que devem ser injetados a cada request
        if isinstance(json_safe, dict):
            json_safe = {
                k: v for k, v in json_safe.items()
                if k not in ("commercialActions", "__is_completed")
            }

        # ── Salvaguarda para eventos concluídos ─────────────────────────────
        # Lê o snapshot existente UMA VEZ e compara a margem antes de gravar.
        # Executa apenas quando ambos (existente e novo) são is_completed=True,
        # garantindo que a correção nunca bloqueie um evento ainda ativo nem
        # impeça a gravação inicial do snapshot de um evento recém-encerrado.
        if is_completed:
            try:
                existing_row = (
                    db.query(EventoDetailSnapshot)
                    .filter(
                        EventoDetailSnapshot.evento_id == evento_id,
                        EventoDetailSnapshot.ano == ano,
                        EventoDetailSnapshot.is_completed == True,  # noqa: E712
                    )
                    .first()
                )
                if existing_row and isinstance(existing_row.payload, dict):
                    existing_margem = _extract_margem_total(existing_row.payload)
                    new_margem = _extract_margem_total(json_safe)
                    # Protege apenas quando temos os dois valores e o novo é
                    # significativamente menor (limiar 95% → tolera correções
                    # legítimas de até 5% sem bloquear).
                    if (
                        existing_margem is not None
                        and new_margem is not None
                        and existing_margem > 0
                        and new_margem < existing_margem * 0.95
                    ):
                        logger.warning(
                            f"[EventDetailSnapshot] Preservando snapshot '{evento_id}/{ano}' — "
                            f"nova margem ({new_margem:,.0f}) < 95% da existente ({existing_margem:,.0f}). "
                            f"Possível resposta parcial do Magento. Snapshot anterior mantido."
                        )
                        return True
            except Exception as _guard_e:
                logger.debug(f"[EventDetailSnapshot] margem guard falhou para '{evento_id}/{ano}': {_guard_e}")

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
    """Recomputa o detalhe de todos os eventos ATIVOS (ano corrente) e persiste.

    Chamado pelo scheduler em background após sincronizar_hoje_batch.
    Eventos já marcados como concluídos (is_completed=True) no banco são
    pulados: seus dados são finais e não precisam ser reprocessados a cada
    30 min — evitando consultas desnecessárias ao Magento e eliminando a
    janela em que uma queda de conexão poderia sobrescrever a margem final
    de um evento encerrado com dados parciais.

    Retorna a quantidade de eventos atualizados.
    """
    from ..core.database import SessionLocal
    from ..models.dimensoes import EventoGrupo as EventoGrupoModel
    from ..api.routes.marketing import get_marketing_event_by_id

    count = 0
    skipped_completed = 0
    db = SessionLocal()
    try:
        ano = datetime.now().year

        # Pré-carrega IDs de eventos já concluídos para evitar reprocessamento
        # desnecessário e proteger a integridade da margem final.
        completed_ids: set[str] = set()
        try:
            completed_rows = (
                db.query(EventoDetailSnapshot.evento_id)
                .filter(
                    EventoDetailSnapshot.ano == ano,
                    EventoDetailSnapshot.is_completed == True,  # noqa: E712
                )
                .all()
            )
            completed_ids = {r.evento_id for r in completed_rows}
            if completed_ids:
                logger.info(
                    f"[EventDetailSnapshot] {len(completed_ids)} eventos concluídos "
                    f"serão pulados no refresh (dados finais — sem consulta ao Magento)"
                )
        except Exception as _cid_e:
            logger.warning(f"[EventDetailSnapshot] falha ao carregar completed_ids: {_cid_e}")

        q = db.query(EventoGrupoModel)
        if max_events is not None:
            q = q.limit(max_events)
        grupos = q.all()

        for g in grupos:
            evento_id = f"grp_{g.nome}"

            # Pula eventos já concluídos — dados finais, não mudam mais.
            if evento_id in completed_ids:
                skipped_completed += 1
                continue

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
    logger.info(
        f"[EventDetailSnapshot] refresh_active_event_details: {count} eventos atualizados, "
        f"{skipped_completed} concluídos pulados"
    )
    return count
