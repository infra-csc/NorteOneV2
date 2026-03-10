from datetime import date, timedelta
from sqlalchemy.orm import Session
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

        entry = VendasDiariaSnapshot(
            evento_grupo=evento_grupo,
            fonte='CONSOLIDADO',
            data_venda=d,
            quantidade=data["qtd"],
            receita=data["receita"]
        )
        db.add(entry)
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
