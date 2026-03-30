from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from ..models.vendas_snapshot import VendasDiariaSnapshot, CurvaHistoricaSnapshot
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


def save_curva_historica_snapshot(db: Session, evento_grupo: str, ano_referencia: int, pattern: dict, total_vendas: int = None):
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
            total_vendas_referencia=total_vendas
        )
        db.add(entry)

    db.commit()
    logger.info(f"Curva histórica salva: grupo='{evento_grupo}', ano_ref={ano_referencia}, {len(pattern)} pontos D-minus")


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
            receita=data["receita"]
        ).on_conflict_do_update(
            index_elements=['evento_grupo', 'fonte', 'data_venda'],
            set_={'quantidade': data["qtd"], 'receita': data["receita"]}
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
        _build_sku_to_grupo_map, _fetch_previous_year_cumulative_pattern
    )

    today = date.today()
    ano = today.year

    sku_to_grupo = _build_sku_to_grupo_map(db, ano)
    if not sku_to_grupo:
        return

    grupos_unicos = set(sku_to_grupo.values())
    saved = 0

    for grupo in grupos_unicos:
        existing = get_curva_historica_snapshot(db, grupo, ano - 1)
        if existing:
            continue

        try:
            pattern = _fetch_previous_year_cumulative_pattern(db, grupo, ano)
            if pattern:
                save_curva_historica_snapshot(db, grupo, ano - 1, pattern, len(pattern))
                saved += 1
        except Exception as e:
            logger.error(f"Erro ao consolidar curva histórica para grupo='{grupo}': {e}")

    logger.info(f"Curvas históricas consolidadas: {saved} novos grupos")
    return saved


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
    projetos = db.query(DimProjeto).filter(
        DimProjeto.data_evento >= min_live_date,
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
    for grupo in list(grupos.keys()):
        latest = get_latest_snapshot_date(db, grupo)
        if latest is None:
            try:
                logger.info(f"sincronizar_hoje_batch: backfill histórico para '{grupo}'")
                consolidar_vendas_grupo(db, grupo, ano, data_fim=yesterday)
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
            logger.error(f"sincronizar_hoje_batch: erro para grupo='{grupo}': {e}")
            try:
                db.rollback()
            except Exception:
                pass

    logger.info(f"sincronizar_hoje_batch: {synced}/{len(grupos)} grupos sincronizados para {today}")
    return synced


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
