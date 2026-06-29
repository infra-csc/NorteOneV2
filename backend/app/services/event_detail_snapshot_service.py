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
from datetime import datetime, date, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi.encoders import jsonable_encoder
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..models.evento_detail_snapshot import EventoDetailSnapshot
from ..models.vendas_snapshot import VendasDiariaSnapshot

logger = logging.getLogger(__name__)


def apply_today_overlay(db: Session, payload: dict, evento_id: str, ano: int | None = None) -> dict:
    """Sobrepõe campos voláteis recentes no payload do snapshot.

    Apenas para eventos agrupados (prefixo 'grp_'). Lê os últimos OVERLAY_LOOKBACK_DAYS
    dias de vendas_diaria_snapshot (atualizado pelo job noturno + "Atualizar Hoje").

    Isso garante que, mesmo quando o Magento está indisponível para recompute completo,
    o gráfico de vendas exibe dados recentes que já estão no PostgreSQL local — populados
    pelo job noturno incremental (last N days) e pelo botão "Atualizar Hoje" (hoje).

    Substitui no payload (sem mutar o snapshot persistido):
      - dailySales: sobrepõe os últimos OVERLAY_LOOKBACK_DAYS dias com dados do PG local
      - evento.currentSales: ajustado pelo delta total dos dias sobrepostos
      - evento.averageTicket: recomputado a partir do delta de hoje
      - ultima_atualizacao_inscricoes: timestamp do último sync_hoje
      - ultima_atualizacao: timestamp do último sync_hoje (compat. frontend antigo)

    Não toca em: ISC, kits, margem orçada, curvas históricas, comparativo anual.
    Esses campos só mudam no recompute completo (a cada 30 min em background).

    Retorna o payload modificado (cópia rasa) ou o payload original em caso de erro.
    """
    if not isinstance(payload, dict):
        return payload

    if evento_id and evento_id.startswith("grp_"):
        grupo_nome = evento_id[4:]
    else:
        # Standalone events (numeric ID): resolve grupo_nome via DimProjeto → SkuMapping
        grupo_nome = None
        try:
            numeric_id = int(evento_id)
            from ..models.dimensoes import DimProjeto as _DP_ov, SkuMapping as _SM_ov
            _proj_ov = db.query(_DP_ov).filter(_DP_ov.id == numeric_id).first()
            if _proj_ov and _proj_ov.codigo:
                _sm_ov = (
                    db.query(_SM_ov)
                    .filter(
                        _SM_ov.sku == str(_proj_ov.codigo),
                        _SM_ov.evento_grupo.isnot(None),
                        _SM_ov.ativo == True,  # noqa: E712
                    )
                    .order_by(_SM_ov.ano.desc())
                    .first()
                )
                if _sm_ov:
                    grupo_nome = _sm_ov.evento_grupo
        except Exception as _e_ov:
            logger.debug(f"[Overlay] standalone lookup failed for '{evento_id}': {_e_ov}")
        if not grupo_nome:
            return payload
    # Usa data BRT para evitar off-by-one em torno de meia-noite UTC.
    today = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    today_str = today.isoformat()

    # Janela de sobreposição: últimos N dias do VendasDiariaSnapshot (PostgreSQL local).
    # Isso garante que dados recentes (preenchidos pelo job noturno e "Atualizar Hoje")
    # sejam exibidos mesmo quando o Magento está indisponível para recompute completo.
    OVERLAY_LOOKBACK_DAYS = 90
    lookback_start = today - timedelta(days=OVERLAY_LOOKBACK_DAYS)

    try:
        from sqlalchemy import or_, and_
        # `.with_entities()` evita hidratação ORM completa (até ~10x mais rápido em
        # eventos com janela de 90 dias e tabela grande).
        q = (
            db.query(
                VendasDiariaSnapshot.data_venda,
                VendasDiariaSnapshot.quantidade,
                VendasDiariaSnapshot.receita,
            )
            .filter(
                VendasDiariaSnapshot.evento_grupo == grupo_nome,
                VendasDiariaSnapshot.fonte == "CONSOLIDADO",
                VendasDiariaSnapshot.data_venda >= lookback_start,
                VendasDiariaSnapshot.data_venda <= today,
            )
        )
        # Restringe ao ano-edição quando informado: para grupos recorrentes,
        # sem esse filtro o overlay de "hoje" misturava dias da edição atual
        # com dias da edição anterior (ex.: 2025 + 2026 do mesmo grupo).
        # Aceita também legado com ano=NULL para preservar compatibilidade.
        if ano is not None:
            q = q.filter(
                or_(
                    VendasDiariaSnapshot.ano == ano,
                    VendasDiariaSnapshot.ano.is_(None),
                )
            )
        recent_rows = (
            q.order_by(VendasDiariaSnapshot.data_venda.asc()).all()
        )
    except Exception as e:
        logger.warning(f"[Overlay] read vendas_diaria_snapshot falhou para '{grupo_nome}': {e}")
        return payload

    # Mapa de dias disponíveis no PG local: {date_str: {qty, revenue}}
    db_days: dict = {
        r[0].isoformat(): {
            "qty": int(r[1] or 0),
            "revenue": float(r[2] or 0.0),
        }
        for r in recent_rows
    }
    # Dados de hoje para o cálculo do averageTicket (mantém lógica existente).
    today_qty_db = db_days.get(today_str, {}).get("qty", 0)
    today_rev_db = db_days.get(today_str, {}).get("revenue", 0.0)

    # Cópia rasa para não mutar o dict original (que pode estar referenciado em cache).
    out = dict(payload)

    if db_days:
        # --- dailySales overlay multi-dia (delta-based para preservar consistência) ---
        daily = list(out.get("dailySales") or [])

        # Mapa de índice: date_str -> posição na lista daily (para update in-place).
        daily_idx_map: dict = {}
        for i, row_d in enumerate(daily):
            if isinstance(row_d, dict) and row_d.get("date"):
                daily_idx_map[row_d["date"]] = i

        # old_today_qty para o cálculo de averageTicket (lógica original preservada).
        old_today_qty = int(
            daily[daily_idx_map[today_str]].get("sales") or 0
        ) if today_str in daily_idx_map else 0

        # Detecta payload sem dailySales de base (ex.: caminho "PAYLOAD PARCIAL"
        # do get_marketing_event_by_id, quando o snapshot persistido tem
        # currentSales preenchido mas dailySales=[]). Nesse caso, os dias vindos
        # do VendasDiariaSnapshot REPRESENTAM o total — não são um delta sobre
        # currentSales, pois currentSales já contabiliza esses mesmos dias.
        # Sem essa detecção, currentSales é somado a si mesmo (duplicação ~2x).
        _no_base_daily = not daily_idx_map

        # Âncora: último dia presente no dailySales do snapshot.
        # Dias do VendasDiariaSnapshot com date > max_snapshot_date são genuinamente
        # novos (não contabilizados no currentSales base) e devem incrementar o delta.
        # Dias <= max_snapshot_date que não estão no daily_idx_map são "buracos"
        # históricos — já estavam no currentSales do snapshot; inserimos no gráfico
        # para visualização mas NÃO somamos ao delta (evita duplicação do total).
        max_snapshot_date = max(daily_idx_map.keys()) if daily_idx_map else ""

        # Aplica sobreposição para cada dia disponível no PG local.
        # Delta acumulado = soma de (novo - antigo) em todos os dias sobrepostos.
        total_qty_delta = 0
        for day_str, db_data in db_days.items():
            new_qty = db_data["qty"]
            if day_str in daily_idx_map:
                idx = daily_idx_map[day_str]
                old_qty = int(daily[idx].get("sales") or 0)
                delta = new_qty - old_qty
                if delta != 0:
                    updated = dict(daily[idx])
                    updated["sales"] = new_qty
                    daily[idx] = updated
                    total_qty_delta += delta
            elif new_qty > 0:
                # Dia ausente no snapshot: adiciona como nova entrada para o gráfico.
                daily.append({
                    "date": day_str,
                    "sales": new_qty,
                    "expected": 0,
                    "cumulativeExpected": 0,
                })
                # Só ajusta currentSales para dias APÓS o último dia do snapshot.
                # Dias históricos dentro do range do snapshot mas ausentes do dailySales
                # (ex.: quando a query Magento usa data_floor recente e o dailySales
                # é truncado) já estão contabilizados no currentSales base — somá-los
                # novamente causaria duplicação do total exibido.
                if day_str > max_snapshot_date:
                    total_qty_delta += new_qty

        # Garante ordem cronológica — gráficos e reduções cumulativas no
        # frontend dependem de dailySales ordenado por data ascendente.
        try:
            daily.sort(key=lambda r: (r.get("date") or "") if isinstance(r, dict) else "")
        except Exception:
            pass
        out["dailySales"] = daily

        # --- evento.currentSales / averageTicket (delta-based) ---
        evt = out.get("evento")
        if isinstance(evt, dict) and total_qty_delta != 0:
            evt = dict(evt)
            base_qty = int(evt.get("currentSales") or 0)
            if _no_base_daily:
                # Sem dailySales de base: total_qty_delta JÁ representa o total
                # agregado dos dias carregados — não pode ser somado ao base_qty,
                # que já contabiliza esses mesmos dias (evita duplicação ~2x).
                # Conserva o base_qty como piso de segurança caso o VendasDiaria
                # esteja truncado (snapshot parcial > sum de dias = não baixar).
                new_qty = max(base_qty, total_qty_delta)
            else:
                new_qty = max(0, base_qty + total_qty_delta)
            evt["currentSales"] = new_qty
            # averageTicket: usa delta de receita de HOJE especificamente
            # (mantém lógica original — receitas de dias anteriores já estão
            # capturadas no ticket médio base do snapshot).
            base_avg = float(evt.get("averageTicket") or 0.0)
            if _no_base_daily:
                # Sem dailySales de base, base_rev já contém a receita de hoje
                # (foi consolidada em currentSales). Recomputar adicionando
                # today_rev_db causaria viés para cima. Mantém ticket médio base.
                pass
            else:
                base_rev = base_avg * base_qty if base_qty > 0 else 0.0
                old_today_rev_est = (
                    base_avg * old_today_qty
                    if (base_avg > 0 and old_today_qty > 0) else 0.0
                )
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
    min_coverage: float = 0.90,
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
    valid_evento_ids: set[str] | None = None
    try:
        from ..api.routes.inscricoes_consolidado import normalize_sku as _ns

        # Apenas grupos *ativos* contam — snapshots de grupos inativos/removidos
        # são órfãos e devem ser filtrados/limpos.
        from ..models.dimensoes import EventoGrupo as _EventoGrupo

        active_grupo_names_q = (
            db.query(_EventoGrupo.nome)
            .filter(_EventoGrupo.ativo == True)  # noqa: E712
            .all()
        )
        active_grupo_names = {n for (n,) in active_grupo_names_q if n}

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
        # Só consideramos grupos que estão mapeados E estão ativos em evento_grupos.
        grupo_names = {g[0] for g in grupo_names_q if g[0] and g[0] in active_grupo_names}
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

        cad_rows = (
            db.query(DimProjeto.id, DimProjeto.codigo)
            .join(CadastroEvento, CadastroEvento.projeto_id == DimProjeto.id)
            .filter(DimProjeto.codigo.isnot(None))
            .all()
        )
        standalone_projeto_ids = {
            str(pid) for (pid, codigo) in cad_rows
            if _ns(str(codigo)) not in sku_to_grupo
        }
        expected_standalone = len(standalone_projeto_ids)
        expected = expected_grouped + expected_standalone

        # IDs válidos esperados pelo endpoint *agora*. Snapshots com IDs fora
        # desse conjunto são órfãos (ex.: ficaram do tempo em que o evento era
        # standalone e depois ganhou mapeamento de grupo, ou vice-versa).
        valid_evento_ids = {f"grp_{n}" for n in grupo_names} | standalone_projeto_ids
    except Exception as e:
        logger.debug(f"[EventosListSnap] expected count falhou: {e}")
        expected = 0
        valid_evento_ids = None

    # Filtra snapshots órfãos antes de avaliar cobertura e montar a lista.
    # Sem isso, um mesmo evento físico podia aparecer duas vezes (uma como
    # standalone "<projeto.id>" e outra como agrupado "grp_<nome>") quando o
    # mapeamento de SKU é criado/alterado depois do primeiro snapshot.
    # A limpeza no banco é feita ao final, em sessão separada, para não
    # expirar os objetos ORM ainda em uso neste caminho de leitura.
    stale_ids_to_cleanup: list[str] = []
    if valid_evento_ids is not None:
        stale_ids_to_cleanup = [r.evento_id for r in rows if r.evento_id not in valid_evento_ids]
        if stale_ids_to_cleanup:
            rows = [r for r in rows if r.evento_id in valid_evento_ids]

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
            payload = apply_today_overlay(db, payload, r.evento_id, ano=r.ano)
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

    # Limpeza dos snapshots órfãos detectados acima — feita em sessão própria
    # para não comprometer o estado ORM da sessão de leitura (evita expirar
    # objetos via commit). Falhas aqui são apenas logadas: a deduplicação
    # já foi aplicada em memória acima.
    if stale_ids_to_cleanup:
        try:
            from ..core.database import SessionLocal as _SL
            _cleanup_db = _SL()
            try:
                (
                    _cleanup_db.query(EventoDetailSnapshot)
                    .filter(
                        EventoDetailSnapshot.ano == ano,
                        EventoDetailSnapshot.evento_id.in_(stale_ids_to_cleanup),
                    )
                    .delete(synchronize_session=False)
                )
                _cleanup_db.commit()
                logger.info(
                    f"[EventosListSnap] removidos {len(stale_ids_to_cleanup)} snapshot(s) "
                    f"órfão(s) ano={ano}: {stale_ids_to_cleanup[:5]}"
                    f"{'...' if len(stale_ids_to_cleanup) > 5 else ''}"
                )
            finally:
                _cleanup_db.close()
        except Exception as _del_e:
            logger.warning(f"[EventosListSnap] falha ao remover snapshots órfãos: {_del_e}")

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
    bypass_completed_guard: bool = False,
) -> bool:
    """UPSERT do snapshot. Retorna True se gravou, False em caso de erro.

    Para eventos já concluídos (is_completed=True) aplica uma salvaguarda
    de margem: se a nova margem for inferior a 95% da margem persistida,
    o snapshot existente é preservado. Isso evita que quedas de conexão
    com o Magento (respostas parciais com menos bundles) sobrescrevam o
    valor final correto de um evento encerrado.

    `bypass_completed_guard=True` desativa essa salvaguarda de 95% para esta
    gravação. É usado SOMENTE pela correção autoritativa de inscritos (botão
    "Atualizar" + auto-heal noturno), quando a leitura ao vivo já foi verificada
    completa upstream — nesse caso queremos justamente permitir a baixa do
    valor. Todos os fluxos automáticos normais continuam com a guarda ativa.
    """
    try:
        json_safe = _to_jsonable(payload)
        # Apenas remove o marker interno; commercialActions e faixas_preco_site
        # agora são persistidos no snapshot (foram pré-calculados pelo recompute)
        # para evitar N+1 queries e chamadas a Magento no GET.
        if isinstance(json_safe, dict):
            json_safe = {
                k: v for k, v in json_safe.items()
                if k != "__is_completed"
            }

        # ── Salvaguarda para eventos concluídos ─────────────────────────────
        # Lê o snapshot existente UMA VEZ e compara a margem antes de gravar.
        # Executa apenas quando ambos (existente e novo) são is_completed=True,
        # garantindo que a correção nunca bloqueie um evento ainda ativo nem
        # impeça a gravação inicial do snapshot de um evento recém-encerrado.
        if is_completed and bypass_completed_guard:
            logger.warning(
                f"[EventDetailSnapshot] Correção autoritativa '{evento_id}/{ano}' — "
                f"salvaguarda de 95% desativada (leitura ao vivo verificada completa). "
                f"Gravando valor corrigido mesmo que inferior ao anterior."
            )
        if is_completed and not bypass_completed_guard:
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
        # Invalida o TTL cache (60s) do payload final em marketing.py para que o
        # próximo GET veja imediatamente o snapshot recém-gravado.
        try:
            from ..api.routes.marketing import invalidate_detail_final_cache as _inv
            _inv(evento_id, ano)
        except Exception:
            pass
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


def reconcile_completed_event_details(max_events: int | None = None) -> int:
    """Auto-heal noturno: reconcilia PARA BAIXO a foto de eventos CONCLUÍDOS
    recentes quando a leitura ao vivo do Magento vem verificada completa.

    Diferente de `refresh_active_event_details` (que PULA concluídos para não
    reprocessá-los), esta função processa exatamente os concluídos recentes
    (data_evento dentro da janela de freeze) chamando
    `get_marketing_event_by_id(force_magento_refresh=True)`. Essa flag aciona o
    caminho de "correção autoritativa" no recompute: se — e somente se — a
    leitura ao vivo for verificada completa, o valor inflado é baixado e a foto
    reescrita; caso contrário o piso é preservado (comportamento atual). Assim a
    maioria dos eventos inflados se corrige sozinha, sem o usuário clicar em
    "Atualizar".

    Limita-se à janela de freeze (`EVENTO_FREEZE_AFTER_DAYS`, default 30 dias)
    para não martelar o Magento com todo o histórico — eventos antigos demais
    raramente mudam e seriam pulados pelo sync de margem de qualquer forma.

    Retorna a quantidade de eventos reconciliados (leituras disparadas).
    """
    from ..core.database import SessionLocal
    from ..api.routes.marketing import get_marketing_event_by_id
    from .snapshot_service import _freeze_after_days

    count = 0
    db = SessionLocal()
    try:
        ano = datetime.now().year
        freeze_days = _freeze_after_days()
        cutoff = date.today() - timedelta(days=freeze_days)

        # Concluídos recentes: data_evento >= hoje - freeze_days. Eventos sem
        # data_evento registrada ficam de fora (não dá para classificar a janela
        # com segurança).
        rows = (
            db.query(EventoDetailSnapshot.evento_id)
            .filter(
                EventoDetailSnapshot.ano == ano,
                EventoDetailSnapshot.is_completed == True,  # noqa: E712
                EventoDetailSnapshot.data_evento.isnot(None),
                EventoDetailSnapshot.data_evento >= cutoff,
            )
            .all()
        )
        evento_ids = [r.evento_id for r in rows]
        if max_events is not None:
            evento_ids = evento_ids[:max_events]

        logger.info(
            f"[EventDetailSnapshot] reconcile_completed: {len(evento_ids)} eventos "
            f"concluídos recentes (>= {cutoff}) candidatos a correção para baixo"
        )

        for evento_id in evento_ids:
            try:
                _db_iter = SessionLocal()
                try:
                    get_marketing_event_by_id(
                        evento_id=evento_id,
                        ano=ano,
                        force_refresh=True,
                        force_magento_refresh=True,
                        db=_db_iter,
                        current_user=None,
                        response=None,
                    )
                    count += 1
                finally:
                    _db_iter.close()
            except Exception as e:
                logger.warning(f"[EventDetailSnapshot] reconcile '{evento_id}' falhou: {e}")
    except Exception as e:
        logger.error(f"[EventDetailSnapshot] reconcile_completed_event_details falhou: {e}")
    finally:
        db.close()
    logger.info(
        f"[EventDetailSnapshot] reconcile_completed_event_details: {count} eventos reconciliados"
    )
    return count
