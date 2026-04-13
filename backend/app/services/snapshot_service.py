from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from ..models.vendas_snapshot import VendasDiariaSnapshot, CurvaHistoricaSnapshot, MargemBundleRevSnapshot
from ..models.dimensoes import SkuMapping, DimProjeto
import logging

logger = logging.getLogger(__name__)


def get_snapshot_vendas(db: Session, evento_grupo: str, data_inicio: date = None, data_fim: date = None) -> dict:
    query = db.query(VendasDiariaSnapshot).filter(
        VendasDiariaSnapshot.evento_grupo == evento_grupo
    )
    if data_inicio:
        query = query.filter(VendasDiariaSnapshot.data_venda >= data_inicio)
    if data_fim:
        query = query.filter(VendasDiariaSnapshot.data_venda <= data_fim)

    rows = query.all()
    daily = {}
    for r in rows:
        daily[r.data_venda] = daily.get(r.data_venda, 0) + r.quantidade
    return daily


def get_snapshot_vendas_com_receita(db: Session, evento_grupo: str, data_inicio: date = None, data_fim: date = None) -> list:
    query = db.query(VendasDiariaSnapshot).filter(
        VendasDiariaSnapshot.evento_grupo == evento_grupo
    )
    if data_inicio:
        query = query.filter(VendasDiariaSnapshot.data_venda >= data_inicio)
    if data_fim:
        query = query.filter(VendasDiariaSnapshot.data_venda <= data_fim)

    rows = query.all()
    daily = {}
    for r in rows:
        d = r.data_venda
        if d not in daily:
            daily[d] = {"qtd": 0, "receita": 0.0}
        daily[d]["qtd"] += r.quantidade
        daily[d]["receita"] += (r.receita or 0.0)

    return [{"dia": d.isoformat(), "qtd": v["qtd"], "receita": v["receita"]} for d, v in sorted(daily.items())]


def has_snapshot_for_date(db: Session, evento_grupo: str, data: date) -> bool:
    count = db.query(VendasDiariaSnapshot).filter(
        VendasDiariaSnapshot.evento_grupo == evento_grupo,
        VendasDiariaSnapshot.data_venda == data
    ).count()
    return count > 0


def get_latest_snapshot_date(db: Session, evento_grupo: str) -> date:
    from sqlalchemy import func
    result = db.query(func.max(VendasDiariaSnapshot.data_venda)).filter(
        VendasDiariaSnapshot.evento_grupo == evento_grupo
    ).scalar()
    return result


def get_curva_historica_snapshot(db: Session, evento_grupo: str, ano_referencia: int) -> dict:
    rows = db.query(CurvaHistoricaSnapshot).filter(
        CurvaHistoricaSnapshot.evento_grupo == evento_grupo,
        CurvaHistoricaSnapshot.ano_referencia == ano_referencia
    ).all()

    if not rows:
        return None

    pattern = {}
    for r in rows:
        pattern[r.d_minus] = r.percentual_acumulado
    return pattern


def get_curva_historica_snapshot_with_meta(db: Session, evento_grupo: str, ano_referencia: int) -> tuple:
    rows = db.query(CurvaHistoricaSnapshot).filter(
        CurvaHistoricaSnapshot.evento_grupo == evento_grupo,
        CurvaHistoricaSnapshot.ano_referencia == ano_referencia
    ).all()

    if not rows:
        return None, None

    pattern = {}
    origem = None
    for r in rows:
        pattern[r.d_minus] = r.percentual_acumulado
        if r.origem and not origem:
            origem = r.origem
    return pattern, origem


def save_curva_historica_snapshot(db: Session, evento_grupo: str, ano_referencia: int, pattern: dict, total_vendas: int = None, origem: str = None):
    db.query(CurvaHistoricaSnapshot).filter(
        CurvaHistoricaSnapshot.evento_grupo == evento_grupo,
        CurvaHistoricaSnapshot.ano_referencia == ano_referencia
    ).delete()

    for d_minus, pct in pattern.items():
        entry = CurvaHistoricaSnapshot(
            evento_grupo=evento_grupo,
            ano_referencia=ano_referencia,
            d_minus=d_minus,
            percentual_acumulado=pct,
            total_vendas_referencia=total_vendas,
            origem=origem or "historico"
        )
        db.add(entry)

    db.commit()
    logger.info(f"Curva histórica salva: grupo='{evento_grupo}', ano_ref={ano_referencia}, {len(pattern)} pontos D-minus, origem={origem or 'historico'}")


def consolidar_vendas_grupo(db: Session, evento_grupo: str, ano: int, data_inicio: date = None, data_fim: date = None):
    from ..api.routes.marketing import (
        _fetch_daily_sales_ativo_by_ids, _fetch_daily_sales_magento_by_ids
    )

    mappings = db.query(SkuMapping).filter(
        SkuMapping.evento_grupo == evento_grupo,
        SkuMapping.ano == ano,
        SkuMapping.ativo == True
    ).all()

    if not mappings:
        logger.warning(f"Nenhum SKU mapping para grupo='{evento_grupo}', ano={ano}")
        return 0

    ativo_ids = [str(m.id_externo) for m in mappings if m.fonte == 'ATIVO' and m.id_externo]
    magento_ids = [str(m.id_externo) for m in mappings if m.fonte == 'MAGENTO' and m.id_externo]

    all_daily = {}

    if ativo_ids:
        rows = _fetch_daily_sales_ativo_by_ids(list(set(ativo_ids)))
        for row in rows:
            d = date.fromisoformat(row['dia']) if isinstance(row['dia'], str) else row['dia']
            if d not in all_daily:
                all_daily[d] = {"qtd": 0, "receita": 0.0}
            all_daily[d]["qtd"] += row['qtd']
            all_daily[d]["receita"] += row.get('receita', 0.0)

    if magento_ids:
        rows = _fetch_daily_sales_magento_by_ids(list(set(magento_ids)))
        for row in rows:
            d = date.fromisoformat(row['dia']) if isinstance(row['dia'], str) else row['dia']
            if d not in all_daily:
                all_daily[d] = {"qtd": 0, "receita": 0.0}
            all_daily[d]["qtd"] += row['qtd']
            all_daily[d]["receita"] += row.get('receita', 0.0)

    yesterday = date.today() - timedelta(days=1)

    if data_inicio is None:
        delete_q = db.query(VendasDiariaSnapshot).filter(
            VendasDiariaSnapshot.evento_grupo == evento_grupo,
            VendasDiariaSnapshot.fonte == 'CONSOLIDADO',
        )
        if data_fim:
            delete_q = delete_q.filter(VendasDiariaSnapshot.data_venda <= data_fim)
        deleted = delete_q.delete(synchronize_session=False)
        if deleted:
            logger.debug(f"Snapshot full refresh: deleted {deleted} old rows for '{evento_grupo}'")

    if not all_daily:
        db.commit()
        logger.info(f"Nenhuma venda encontrada para grupo='{evento_grupo}', ano={ano}")
        return 0

    saved = 0

    for d, data in sorted(all_daily.items()):
        if data_inicio and d < data_inicio:
            continue
        if data_fim and d > data_fim:
            continue
        if d > yesterday:
            continue

        stmt = pg_insert(VendasDiariaSnapshot).values(
            evento_grupo=evento_grupo,
            fonte='CONSOLIDADO',
            data_venda=d,
            quantidade=data["qtd"],
            receita=data["receita"],
            ano=ano,
        ).on_conflict_do_update(
            index_elements=['evento_grupo', 'fonte', 'data_venda'],
            set_={'quantidade': data["qtd"], 'receita': data["receita"], 'ano': ano}
        )
        db.execute(stmt)
        saved += 1

    db.commit()
    logger.info(f"Snapshot consolidado: grupo='{evento_grupo}', ano={ano}, {saved} dias salvos")
    return saved


def snapshot_diario_batch(db: Session):
    from ..api.routes.marketing import _build_sku_to_grupo_map, normalize_sku

    today = date.today()
    yesterday = today - timedelta(days=1)
    ano = today.year

    sku_to_grupo = _build_sku_to_grupo_map(db, ano)
    if not sku_to_grupo:
        logger.warning("Nenhum sku_to_grupo encontrado para consolidação diária")
        return

    grupos_processados = set()
    projetos = db.query(DimProjeto).all()

    for p in projetos:
        if not p.data_evento or not p.codigo:
            continue
        if p.data_evento.year != ano:
            continue

        sku_norm = normalize_sku(str(p.codigo))
        grupo = sku_to_grupo.get(sku_norm)
        if not grupo or grupo in grupos_processados:
            continue

        grupos_processados.add(grupo)

        latest = get_latest_snapshot_date(db, grupo)
        if latest and latest >= yesterday:
            continue

        try:
            consolidar_vendas_grupo(db, grupo, ano, data_inicio=None, data_fim=yesterday)
        except Exception as e:
            logger.error(f"Erro ao consolidar snapshot para grupo='{grupo}': {e}")

    logger.info(f"Consolidação diária concluída: {len(grupos_processados)} grupos processados")
    return len(grupos_processados)


def consolidar_curvas_historicas_batch(db: Session):
    from ..api.routes.marketing import (
        _build_sku_to_grupo_map, _fetch_previous_year_cumulative_pattern,
        _resolve_hist_pattern
    )

    today = date.today()
    ano = today.year
    prev_ano = ano - 1

    sku_to_grupo = _build_sku_to_grupo_map(db, ano)
    if not sku_to_grupo:
        return

    grupos_unicos = set(sku_to_grupo.values())
    saved = 0
    derived = 0

    for grupo in grupos_unicos:
        existing = get_curva_historica_snapshot(db, grupo, prev_ano)
        if existing:
            continue

        try:
            pattern = _fetch_previous_year_cumulative_pattern(db, grupo, ano)
            if pattern:
                save_curva_historica_snapshot(db, grupo, prev_ano, pattern, len(pattern), origem="historico")
                saved += 1
        except Exception as e:
            logger.error(f"Erro ao consolidar curva histórica para grupo='{grupo}': {e}")

    from ..models.dimensoes import SkuMapping as SkuMappingModel, DimProjeto
    grupo_estado_map = {}
    for grupo in grupos_unicos:
        estado_row = db.query(DimProjeto.estado).join(
            SkuMappingModel, SkuMappingModel.sku == DimProjeto.codigo
        ).filter(
            SkuMappingModel.evento_grupo == grupo,
            DimProjeto.estado.isnot(None)
        ).first()
        if estado_row:
            grupo_estado_map[grupo] = estado_row[0]

    for grupo in grupos_unicos:
        existing = get_curva_historica_snapshot(db, grupo, prev_ano)
        if existing:
            continue

        try:
            estado = grupo_estado_map.get(grupo)
            fb_pattern, fb_info = _resolve_hist_pattern(db, grupo, ano, estado=estado)
            if fb_pattern and fb_info.get("tipo_curva") != "linear":
                save_curva_historica_snapshot(
                    db, grupo, prev_ano, fb_pattern,
                    len(fb_pattern),
                    origem=fb_info.get("tipo_curva", "derivado")
                )
                derived += 1
                logger.info(f"Curva derivada salva para '{grupo}': tipo={fb_info.get('tipo_curva')}, fonte={fb_info.get('fonte_curva')}")
        except Exception as e:
            logger.error(f"Erro ao gerar curva derivada para grupo='{grupo}': {e}")

    logger.info(f"Curvas históricas consolidadas: {saved} próprias, {derived} derivadas")
    return saved + derived


def sincronizar_hoje_batch(db: Session) -> int:
    """
    Syncs today's sales to vendas_diaria_snapshot for all active event groups
    using efficient single-batch MySQL queries (one per source).
    Only live/hybrid groups are synced (regime != "consolidated"), i.e., groups
    that have at least one event with data_evento >= today + 1 (D- >= -1).

    Also backfills historical data for live groups that have no snapshot rows at
    all (calls consolidar_vendas_grupo with data_fim=yesterday before syncing today).

    Returns the number of groups whose today row was successfully upserted.
    """
    from ..api.routes.marketing import (
        _fetch_today_sales_ativo_grouped,
        _fetch_today_sales_magento_grouped,
        _build_sku_to_grupo_map,
        normalize_sku,
    )

    today = date.today()
    yesterday = today - timedelta(days=1)
    ano = today.year

    # D- >= -1 (not consolidated) means data_evento >= today + 1.
    # registration_close = data_evento - 2, D- = registration_close - today.
    # D- = -1 → registration_close = today - 1 → data_evento = today + 1.
    min_live_date = today + timedelta(days=1)

    # --- Build map of live/hybrid grupos ---
    # A grupo is live/hybrid if it has at least one DimProjeto with
    # data_evento >= min_live_date in the current year.
    sku_to_grupo = _build_sku_to_grupo_map(db, ano)
    live_grupos: set = set()
    # Only consider events in the current year that are live/hybrid (not consolidated).
    max_date = date(ano + 1, 1, 1)
    projetos = db.query(DimProjeto).filter(
        DimProjeto.data_evento >= min_live_date,
        DimProjeto.data_evento < max_date,
    ).all()
    for p in projetos:
        if not p.data_evento or not p.codigo:
            continue
        sku_norm = normalize_sku(str(p.codigo))
        grupo = sku_to_grupo.get(sku_norm)
        if grupo:
            live_grupos.add(grupo)

    if not live_grupos:
        logger.info("sincronizar_hoje_batch: nenhum grupo live/hybrid encontrado")
        return 0

    mappings = db.query(SkuMapping).filter(
        SkuMapping.ano == ano,
        SkuMapping.ativo == True,
        SkuMapping.id_externo.isnot(None)
    ).all()

    if not mappings:
        logger.info("sincronizar_hoje_batch: nenhum SkuMapping ativo para o ano corrente")
        return 0

    grupos: dict = {}
    all_ativo_ids: list = []
    all_magento_ids: list = []

    for m in mappings:
        if not m.evento_grupo or m.evento_grupo not in live_grupos:
            continue
        g = m.evento_grupo
        if g not in grupos:
            grupos[g] = {"ativo_ids": [], "magento_ids": []}
        if m.fonte == "ATIVO":
            id_str = str(m.id_externo)
            if id_str not in grupos[g]["ativo_ids"]:
                grupos[g]["ativo_ids"].append(id_str)
                all_ativo_ids.append(id_str)
        elif m.fonte == "MAGENTO":
            id_str = str(m.id_externo)
            if id_str not in grupos[g]["magento_ids"]:
                grupos[g]["magento_ids"].append(id_str)
                all_magento_ids.append(id_str)

    if not grupos:
        logger.info("sincronizar_hoje_batch: nenhum grupo live/hybrid com mappings encontrado")
        return 0

    logger.info(f"sincronizar_hoje_batch: {len(grupos)} grupos live/hybrid para sincronizar")

    # --- Step 1: Backfill historical data for groups with no snapshot rows ---
    backfilled = 0
    for grupo in list(grupos.keys()):
        latest = get_latest_snapshot_date(db, grupo)
        if latest is None:
            try:
                logger.info(f"sincronizar_hoje_batch: backfill histórico para '{grupo}'")
                consolidar_vendas_grupo(db, grupo, ano, data_fim=yesterday)
                backfilled += 1
            except Exception as e:
                logger.warning(f"sincronizar_hoje_batch: backfill falhou para '{grupo}': {e}")

    # --- Step 2: Fetch today's data in batch (2 MySQL queries total) ---
    ativo_today: dict = {}
    magento_today: dict = {}

    if all_ativo_ids:
        try:
            ativo_today = _fetch_today_sales_ativo_grouped(list(set(all_ativo_ids)))
            logger.info(f"sincronizar_hoje_batch: Ativo retornou {len(ativo_today)} IDs com vendas hoje")
        except Exception as e:
            logger.error(f"sincronizar_hoje_batch: erro Ativo grouped: {e}")

    if all_magento_ids:
        try:
            magento_today = _fetch_today_sales_magento_grouped(list(set(all_magento_ids)))
            logger.info(f"sincronizar_hoje_batch: Magento retornou {len(magento_today)} IDs com vendas hoje")
        except Exception as e:
            logger.error(f"sincronizar_hoje_batch: erro Magento grouped: {e}")

    # --- Step 3: Aggregate by grupo and UPSERT today's row ---
    synced = 0
    failed = 0
    for grupo, ids in grupos.items():
        try:
            qtd_total = 0
            receita_total = 0.0

            for eid in ids["ativo_ids"]:
                entry = ativo_today.get(eid)
                if entry:
                    qtd_total += entry["qtd"]
                    receita_total += entry["receita"]

            for eid in ids["magento_ids"]:
                entry = magento_today.get(eid)
                if entry:
                    qtd_total += entry["qtd"]
                    receita_total += entry["receita"]

            stmt = pg_insert(VendasDiariaSnapshot).values(
                evento_grupo=grupo,
                fonte="CONSOLIDADO",
                data_venda=today,
                quantidade=qtd_total,
                receita=receita_total,
                ano=ano,
            ).on_conflict_do_update(
                index_elements=["evento_grupo", "fonte", "data_venda"],
                set_={
                    "quantidade": qtd_total,
                    "receita": receita_total,
                    "ano": ano,
                }
            )
            db.execute(stmt)
            db.commit()
            synced += 1
        except Exception as e:
            failed += 1
            logger.error(f"sincronizar_hoje_batch: erro para grupo='{grupo}': {e}")
            try:
                db.rollback()
            except Exception:
                pass

    logger.info(
        f"sincronizar_hoje_batch: {synced}/{len(grupos)} grupos sincronizados para {today}"
        f" (backfills={backfilled}, falhas={failed})"
    )

    # Invalidate event_detail and ISC caches so next dashboard request gets fresh
    # snapshot data without waiting for the 22h/5min SmartCache TTL to expire.
    if synced > 0:
        try:
            from ..core.cache import event_detail_cache, isc_cache
            from ..api.routes.marketing import eventos_list_cache
            event_detail_cache.invalidate()
            isc_cache.invalidate()
            eventos_list_cache.invalidate()
            logger.info("sincronizar_hoje_batch: event_detail, ISC and eventos_list caches invalidated")
        except Exception as _ce:
            logger.warning(f"sincronizar_hoje_batch: cache invalidation failed: {_ce}")

    return synced


def get_isc_totals_from_snapshot(db: Session, ano: int) -> dict:
    """
    Returns ISC metrics aggregated from vendas_diaria_snapshot for the given year.
    Includes rolling 7d/14d/30d sales averages based on today's date.

    Returns {grupo_name: {qtd_site, receita_liquida_site, inscricao_liquida,
                          ticket_medio, media_7d, media_14d, media_30d}}
    Grupos with no snapshot rows for the given year are not included.
    """
    from sqlalchemy import func
    from sqlalchemy import case as sa_case

    today = date.today()
    yesterday = today - timedelta(days=1)
    d7  = today - timedelta(days=7)
    d14 = today - timedelta(days=14)
    d30 = today - timedelta(days=30)

    # Filter by event edition year using the `ano` column (written as event edition year,
    # not calendar year of the order). Falls back to a broad data_venda range that
    # includes typical pre-sale windows (up to 4 months before Jan 1) for rows written
    # by older code that stored ano=d.year instead of ano=event_edition_year.
    year_start     = date(ano, 1, 1)
    year_end       = date(ano + 1, 1, 1)
    presale_start  = date(ano - 1, 9, 1)   # Sep 1 of previous year covers ~4-month pre-sale

    from sqlalchemy import or_, and_

    rows = db.query(
        VendasDiariaSnapshot.evento_grupo,
        func.sum(VendasDiariaSnapshot.quantidade).label("qtd_total"),
        func.sum(VendasDiariaSnapshot.receita).label("receita_total"),
        func.sum(sa_case(
            (and_(VendasDiariaSnapshot.data_venda >= d7,  VendasDiariaSnapshot.data_venda <= yesterday), VendasDiariaSnapshot.quantidade),
            else_=0
        )).label("qtd_7d"),
        func.sum(sa_case(
            (and_(VendasDiariaSnapshot.data_venda >= d14, VendasDiariaSnapshot.data_venda <= yesterday), VendasDiariaSnapshot.quantidade),
            else_=0
        )).label("qtd_14d"),
        func.sum(sa_case(
            (and_(VendasDiariaSnapshot.data_venda >= d30, VendasDiariaSnapshot.data_venda <= yesterday), VendasDiariaSnapshot.quantidade),
            else_=0
        )).label("qtd_30d"),
    ).filter(
        or_(
            VendasDiariaSnapshot.ano == ano,
            and_(
                VendasDiariaSnapshot.data_venda >= presale_start,
                VendasDiariaSnapshot.data_venda <  year_end,
            )
        )
    ).group_by(VendasDiariaSnapshot.evento_grupo).all()

    result = {}
    for r in rows:
        qtd     = int(r.qtd_total   or 0)
        receita = float(r.receita_total or 0.0)
        q7      = int(r.qtd_7d  or 0)
        q14     = int(r.qtd_14d or 0)
        q30     = int(r.qtd_30d or 0)
        result[r.evento_grupo] = {
            "qtd_site":            qtd,
            "receita_liquida_site": receita,
            "inscricao_liquida":   receita,
            "ticket_medio":        round(receita / qtd, 2) if qtd > 0 else 0.0,
            "media_7d":            round(q7  / 7.0,  2),
            "media_14d":           round(q14 / 14.0, 2),
            "media_30d":           round(q30 / 30.0, 2),
        }
    return result


def sincronizar_margem_bundle_rev_batch(db: Session) -> dict:
    """Pré-computa receita Magento por bundle_entity_id e persiste em margem_bundle_rev_snapshot.

    Executa a mesma revenue query de get_margem_por_kit, mas de forma centralizada
    para todos os bundles mapeados, com timeout maior (5 min) por ser job de background.
    O resultado elimina timeouts na tela Margem por Kit para eventos de alto volume.

    Chamado pelo job de consolidação das 4h (antes do full warmup das 5h).
    """
    from ..core.database import engine_magento
    from ..models.kit_config import KitConfig
    from sqlalchemy import text, bindparam
    from datetime import timezone

    if engine_magento is None:
        logger.warning("[MargemRevSync] engine_magento não disponível — sync ignorado")
        return {"status": "skipped", "motivo": "engine_magento indisponível"}

    bundle_ids_all = [
        row[0] for row in
        db.query(KitConfig.bundle_entity_id)
        .filter(KitConfig.tipo_kit.isnot(None))
        .distinct()
        .all()
    ]

    if not bundle_ids_all:
        logger.info("[MargemRevSync] Nenhum bundle_entity_id encontrado em kit_config")
        return {"status": "ok", "bundles_processados": 0}

    logger.info(f"[MargemRevSync] Iniciando sync de receita para {len(bundle_ids_all)} bundles")

    # Mesma lógica de receita do get_margem_por_kit, timeout elevado para background (5 min)
    rev_query = text("""
SELECT /*+ MAX_EXECUTION_TIME(300000) */
    soi_parent.product_id                                                              AS bundle_entity_id,
    ROUND(SUM(soi_child.price - soi_child.discount_amount), 2)                        AS receita_liquida
FROM sales_order so
INNER JOIN sales_order_item soi_parent
       ON soi_parent.order_id     = so.entity_id
      AND soi_parent.product_type = 'bundle'
      AND soi_parent.product_id   IN :bundle_ids
INNER JOIN sales_order_item soi_child
       ON soi_child.parent_item_id = soi_parent.item_id
      AND soi_child.product_type   = 'simple'
      AND soi_child.price          > 0
      AND soi_child.price - soi_child.discount_amount > 0
      AND (
            soi_child.name LIKE '%%Distância%%'
         OR soi_child.name LIKE '%%Distancia%%'
         OR soi_child.name LIKE '%%Distâncias%%'
         OR soi_child.name LIKE '%%Modalidade%%'
      )
WHERE
    so.created_at >= DATE_SUB(CURDATE(), INTERVAL 2 YEAR)
AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
AND so.state != 'canceled'
AND so.base_grand_total > 0
AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
AND so.created_at < CURDATE() + INTERVAL 1 DAY
AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')
AND so.increment_id NOT REGEXP '-[0-9]'
GROUP BY soi_parent.product_id
""").bindparams(bindparam("bundle_ids", expanding=True))

    rev_by_bid: dict = {}
    BATCH_SIZE = 80

    for i in range(0, len(bundle_ids_all), BATCH_SIZE):
        batch = bundle_ids_all[i:i + BATCH_SIZE]
        try:
            with engine_magento.connect() as conn:
                rows = conn.execute(rev_query, {"bundle_ids": batch}).fetchall()
                for row in rows:
                    rev_by_bid[int(row[0])] = float(row[1] or 0)
            logger.info(f"[MargemRevSync] Batch {i // BATCH_SIZE + 1}: {len(batch)} bundles → {len(rows)} com receita")
        except Exception as e:
            logger.error(f"[MargemRevSync] Erro no batch {i // BATCH_SIZE + 1} (bundles {i}–{i + len(batch)}): {e}")

    if not rev_by_bid:
        logger.warning("[MargemRevSync] Nenhuma receita retornada do Magento — snapshot não atualizado")
        return {"status": "sem_dados", "bundles_processados": len(bundle_ids_all)}

    agora = datetime.now(timezone.utc)
    upserted = 0
    for bid, receita in rev_by_bid.items():
        stmt = pg_insert(MargemBundleRevSnapshot).values(
            bundle_entity_id=bid,
            receita_liquida=receita,
            calculado_em=agora,
        ).on_conflict_do_update(
            index_elements=["bundle_entity_id"],
            set_={"receita_liquida": receita, "calculado_em": agora},
        )
        db.execute(stmt)
        upserted += 1

    db.commit()
    logger.info(f"[MargemRevSync] Snapshot atualizado: {upserted} bundles gravados em margem_bundle_rev_snapshot")
    return {"status": "ok", "bundles_processados": len(bundle_ids_all), "bundles_com_receita": upserted}


def backfill_historico(db: Session, ano: int, data_inicio: date = None, data_fim: date = None):
    from ..api.routes.marketing import _build_sku_to_grupo_map

    sku_to_grupo = _build_sku_to_grupo_map(db, ano)
    if not sku_to_grupo:
        logger.warning(f"Nenhum sku_to_grupo para ano={ano}")
        return {"total_grupos": 0, "total_dias": 0}

    grupos_unicos = set(sku_to_grupo.values())
    total_dias = 0
    erros = []

    for grupo in grupos_unicos:
        try:
            dias = consolidar_vendas_grupo(db, grupo, ano, data_inicio=data_inicio, data_fim=data_fim)
            total_dias += dias
        except Exception as e:
            logger.error(f"Erro no backfill para grupo='{grupo}': {e}")
            erros.append({"grupo": grupo, "erro": str(e)})

    result = {
        "total_grupos": len(grupos_unicos),
        "total_dias": total_dias,
        "erros": erros if erros else None
    }
    logger.info(f"Backfill concluído: {result}")
    return result
