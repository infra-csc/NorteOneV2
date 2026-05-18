from datetime import date, datetime, timedelta
from typing import Optional
import os
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from ..models.vendas_snapshot import VendasDiariaSnapshot, CurvaHistoricaSnapshot, MargemBundleRevSnapshot
from ..models.dimensoes import SkuMapping, DimProjeto
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Congelamento de eventos finalizados
# ---------------------------------------------------------------------------
# Eventos cuja data_evento + EVENTO_FREEZE_AFTER_DAYS < hoje são considerados
# "finalizados" e ficam fora dos jobs de sincronização incremental que vão ao
# Magento (job de margem por bundle das 04h e snapshot_diario_batch). O snapshot
# já gravado segue sendo lido normalmente — apenas paramos de regravar dados
# que não mudam mais.
#
# 30 dias é a janela típica de refunds/ajustes pós-evento; depois disso o
# upside de re-sincronizar não compensa o custo Magento e o risco de partial
# response. Configurável via env var para emergências.
def _freeze_after_days() -> int:
    try:
        return max(0, int(os.getenv("EVENTO_FREEZE_AFTER_DAYS", "30")))
    except (TypeError, ValueError):
        return 30


def is_event_frozen(data_evento: Optional[date], freeze_days: Optional[int] = None) -> bool:
    """Retorna True quando data_evento + freeze_days < hoje.

    Conservador: data_evento=None NUNCA é frozen (mesma regra do write-side).
    """
    if data_evento is None:
        return False
    fd = freeze_days if freeze_days is not None else _freeze_after_days()
    return data_evento < (date.today() - timedelta(days=fd))


def _load_data_evento_by_magento_id(db: Session, magento_ids) -> dict:
    """Map id_evento_magento (str) -> data_evento. None quando ausente do cadastro."""
    from ..models.cadastro_evento import CadastroEvento
    if not magento_ids:
        return {}
    norm = {str(int(i)) for i in magento_ids if str(i).isdigit()}
    if not norm:
        return {}
    rows = db.query(
        CadastroEvento.id_evento_magento,
        CadastroEvento.data_evento,
    ).filter(
        CadastroEvento.deleted_at.is_(None),
        CadastroEvento.id_evento_magento.in_(list(norm)),
    ).all()
    out: dict = {}
    for mag_id, dt in rows:
        if mag_id is None:
            continue
        # se houver múltiplos cadastros (caso raro), prefere data mais recente
        key = str(mag_id)
        if key not in out or (dt and (out[key] is None or dt > out[key])):
            out[key] = dt
    return out


def partition_magento_ids_by_freeze(
    db: Session,
    magento_ids,
    force_magento_refresh: bool = False,
    freeze_days: Optional[int] = None,
) -> tuple:
    """Divide a lista de magento_ids em (active_ids, frozen_ids) baseado em
    `data_evento + freeze_days`. IDs sem cadastro são tratados como ativos
    (conservador). Quando ``force_magento_refresh=True``, retorna tudo como ativo.

    Guarda anti-dupla-contagem: o snapshot é gravado por evento_grupo
    (não por id_externo individual), portanto se um grupo tem IDs tanto ativos
    quanto frozen, ler o snapshot daquele grupo retornaria também as vendas
    dos IDs ativos — que depois seriam somadas novamente pela consulta live ao
    Magento. Para evitar isso, sempre que um grupo é "misto", todos os seus IDs
    são forçados para ATIVO (ou seja, vão ao Magento e o snapshot é ignorado
    para esse grupo). Apenas grupos 100% frozen são servidos pelo snapshot.

    Retorna listas de strings (preserva ordem da entrada, sem duplicar).
    """
    seen = set()
    ordered = []
    for i in magento_ids:
        s = str(i)
        if s not in seen and s.lstrip("-").isdigit():
            seen.add(s)
            ordered.append(s)
    if force_magento_refresh or not ordered:
        return ordered, []
    fd = freeze_days if freeze_days is not None else _freeze_after_days()
    cutoff = date.today() - timedelta(days=fd)
    dt_map = _load_data_evento_by_magento_id(db, ordered)
    # 1ª passada: classificação individual
    initial_frozen: set = set()
    for s in ordered:
        dt = dt_map.get(s)
        if dt is not None and dt < cutoff:
            initial_frozen.add(s)
    # 2ª passada: guarda por grupo — se um grupo tem misto frozen+ativo,
    # todos os seus IDs viram ativos para evitar dupla contagem.
    if initial_frozen:
        try:
            grupo_rows = db.query(SkuMapping.id_externo, SkuMapping.evento_grupo).filter(
                SkuMapping.fonte == "MAGENTO",
                SkuMapping.id_externo.in_(ordered),
                SkuMapping.ativo == True,
                SkuMapping.evento_grupo.isnot(None),
            ).all()
            grupo_by_id: dict = {str(r[0]): r[1] for r in grupo_rows if r[1]}
            grupos_to_ids: dict = {}
            for s in ordered:
                g = grupo_by_id.get(s)
                if g:
                    grupos_to_ids.setdefault(g, set()).add(s)
            grupos_mistos = {
                g for g, ids in grupos_to_ids.items()
                if (ids & initial_frozen) and (ids - initial_frozen)
            }
            if grupos_mistos:
                # Rebaixa frozen → ativo para todos os IDs de grupos mistos
                downgrade = {s for g in grupos_mistos for s in grupos_to_ids[g]}
                initial_frozen -= downgrade
                logger.info(
                    f"[partition_freeze] {len(grupos_mistos)} grupo(s) misto(s) "
                    f"({len(downgrade)} IDs rebaixados para ATIVO) — anti-dupla-contagem"
                )
        except Exception as _eg:
            logger.warning(
                f"[partition_freeze] guarda anti-dupla-contagem falhou (conservador: tudo ativo): {_eg}"
            )
            initial_frozen.clear()
    active, frozen = [], []
    for s in ordered:
        if s in initial_frozen:
            frozen.append(s)
        else:
            active.append(s)
    return active, frozen


def compute_data_floor_for_magento_ids(
    db: Session,
    magento_ids,
    lookback_days: int = 365,
) -> Optional[date]:
    """Calcula o piso de data ideal para uma query Magento por IDs.

    Regra: floor = min(data_evento dos IDs) - lookback_days.
    - Se nenhum ID tem cadastro com data_evento → retorna None (sem floor).
    - Limita o floor a no máximo (hoje - 24 meses) por segurança.
    """
    dt_map = _load_data_evento_by_magento_id(db, magento_ids)
    datas = [d for d in dt_map.values() if d is not None]
    if not datas:
        return None
    floor = min(datas) - timedelta(days=lookback_days)
    safety_cap = date.today() - timedelta(days=730)
    return max(floor, safety_cap)


def read_daily_sales_snapshot_by_magento_ids(
    db: Session,
    magento_ids,
    ano: Optional[int] = None,
    data_floor: Optional[date] = None,
) -> dict:
    """Lê vendas diárias do snapshot (VendasDiariaSnapshot) agregadas por dia
    para um conjunto de magento_ids — usado para servir eventos congelados sem
    bater no Magento.

    Bridge: magento_id → SkuMapping(fonte='MAGENTO').evento_grupo → snapshot.
    Soma por data. Considera fonte 'MAGENTO' e fallback 'CONSOLIDADO' quando
    presente, escolhendo o maior por (grupo, data) para evitar dupla contagem.

    Retorna: dict {date -> int(qtd)}.
    """
    if not magento_ids:
        return {}
    norm = [str(int(i)) for i in magento_ids if str(i).isdigit()]
    if not norm:
        return {}
    grupo_by_id: dict = {}
    grupo_filter = db.query(SkuMapping).filter(
        SkuMapping.fonte == 'MAGENTO',
        SkuMapping.id_externo.in_(norm),
        SkuMapping.ativo == True,
    )
    if ano is not None:
        grupo_filter = grupo_filter.filter(SkuMapping.ano == ano)
    for mm in grupo_filter.all():
        if mm.evento_grupo:
            grupo_by_id[str(mm.id_externo)] = mm.evento_grupo
    grupos = set(grupo_by_id.values())
    if not grupos:
        return {}
    q = db.query(
        VendasDiariaSnapshot.evento_grupo,
        VendasDiariaSnapshot.data_venda,
        VendasDiariaSnapshot.fonte,
        VendasDiariaSnapshot.quantidade,
        VendasDiariaSnapshot.receita,
    ).filter(
        VendasDiariaSnapshot.evento_grupo.in_(list(grupos)),
        VendasDiariaSnapshot.fonte.in_(['MAGENTO', 'CONSOLIDADO']),
    )
    if ano is not None:
        q = q.filter(VendasDiariaSnapshot.ano == ano)
    if data_floor is not None:
        q = q.filter(VendasDiariaSnapshot.data_venda >= data_floor)
    # Para evitar dupla contagem quando há linhas MAGENTO e CONSOLIDADO para o
    # mesmo (grupo, dia): preferimos a fonte com MAIOR quantidade.
    by_key: dict = {}
    for grupo, dia, fonte, qtd, rec in q.all():
        key = (grupo, dia)
        v = int(qtd or 0)
        r = float(rec or 0.0)
        cur = by_key.get(key)
        if cur is None or v > cur[0]:
            by_key[key] = (v, r)
    out: dict = {}
    for (grupo, dia), (v, r) in by_key.items():
        prev_q, prev_r = out.get(dia, (0, 0.0))
        out[dia] = (prev_q + v, prev_r + r)
    return out


def _load_active_event_magento_ids(db: Session, freeze_days: int) -> tuple:
    """Retorna (active_ids: set, all_ids: set) de id_evento_magento.

    'active' = data_evento >= hoje - freeze_days OU data_evento NULL.
    'all_ids' inclui todos os ids cadastrados (para sabermos o que é
    realmente "frozen" vs "sem cadastro"). Bundles com id_evento ausente do
    cadastro permanecem sendo sincronizados (conservador — não dá pra
    classificar como frozen sem data).
    """
    from ..models.cadastro_evento import CadastroEvento
    cutoff = date.today() - timedelta(days=freeze_days)
    active: set = set()
    all_ids: set = set()
    rows = db.query(
        CadastroEvento.id_evento_magento,
        CadastroEvento.data_evento,
    ).filter(
        CadastroEvento.deleted_at.is_(None),
        CadastroEvento.id_evento_magento.isnot(None),
    ).all()
    for mag_id, dt in rows:
        if mag_id is None:
            continue
        all_ids.add(mag_id)
        if dt is None or dt >= cutoff:
            active.add(mag_id)
    return active, all_ids


def _load_active_grupos(db: Session, freeze_days: int) -> set:
    """Retorna conjunto de evento_grupo com pelo menos um evento ativo.

    Junta DimProjeto e CadastroEvento (mesma união do snapshot_diario_batch).
    Grupo entra como ativo se ALGUM evento dele tem data_evento >= hoje -
    freeze_days OU data_evento nulo.
    """
    from ..api.routes.marketing import _build_sku_to_grupo_map, normalize_sku
    from ..models.cadastro_evento import CadastroEvento

    cutoff = date.today() - timedelta(days=freeze_days)
    sku_to_grupo = _build_sku_to_grupo_map(db, date.today().year)
    active: set = set()

    for p in db.query(DimProjeto).all():
        if not p.codigo:
            continue
        if p.data_evento is not None and p.data_evento < cutoff:
            continue
        grupo = sku_to_grupo.get(normalize_sku(str(p.codigo)))
        if grupo:
            active.add(grupo)

    magento_id_to_grupo: dict = {}
    try:
        for mm in db.query(SkuMapping).filter(
            SkuMapping.ativo == True,
            SkuMapping.fonte == "MAGENTO",
            SkuMapping.id_externo.isnot(None),
            SkuMapping.evento_grupo.isnot(None),
        ).all():
            magento_id_to_grupo[str(mm.id_externo)] = mm.evento_grupo
    except Exception:
        pass

    cadastros = db.query(CadastroEvento).filter(
        CadastroEvento.deleted_at.is_(None),
    ).all()
    projeto_ids = {c.projeto_id for c in cadastros if getattr(c, "projeto_id", None)}
    projeto_codigo_by_id: dict = {}
    if projeto_ids:
        try:
            for pj in db.query(DimProjeto.id, DimProjeto.codigo).filter(
                DimProjeto.id.in_(projeto_ids)
            ).all():
                if pj.codigo:
                    projeto_codigo_by_id[pj.id] = str(pj.codigo)
        except Exception:
            pass

    for c in cadastros:
        if c.data_evento is not None and c.data_evento < cutoff:
            continue
        grupo = None
        if getattr(c, "sku", None):
            grupo = sku_to_grupo.get(normalize_sku(str(c.sku)))
        if not grupo and getattr(c, "projeto_id", None):
            cod = projeto_codigo_by_id.get(c.projeto_id)
            if cod:
                grupo = sku_to_grupo.get(normalize_sku(cod))
        if not grupo and getattr(c, "id_evento_magento", None):
            grupo = magento_id_to_grupo.get(str(c.id_evento_magento))
        if grupo:
            active.add(grupo)

    return active


def get_snapshot_vendas(db: Session, evento_grupo: str, data_inicio: Optional[date] = None, data_fim: Optional[date] = None) -> dict:
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


def get_snapshot_vendas_com_receita(db: Session, evento_grupo: str, data_inicio: Optional[date] = None, data_fim: Optional[date] = None) -> list:
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


def save_curva_historica_snapshot(db: Session, evento_grupo: str, ano_referencia: int, pattern: dict, total_vendas: Optional[int] = None, origem: Optional[str] = None):
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


def consolidar_vendas_grupo(db: Session, evento_grupo: str, ano: int, data_inicio: Optional[date] = None, data_fim: Optional[date] = None, incremental: bool = False, ciclo_id: Optional[str] = None, parent_job_name: Optional[str] = None):
    """Reconstrói o snapshot diário de vendas de um grupo.

    Modo padrão (incremental=False): varre histórico completo no Magento/Ativo
    e DELETA snapshots existentes antes de reinserir. Usado em rebuilds
    manuais e na primeira construção do snapshot.

    Modo incremental (incremental=True): lê MAX(data_venda) do snapshot
    existente e pede ao Magento/Ativo apenas as vendas a partir desse dia
    (re-busca o último dia pra capturar atualizações tardias). NÃO deleta
    snapshots existentes — só faz UPSERT dos dias novos/refrescados.
    Vantagens: query muito mais leve no Magento e, se a fonte devolver
    resposta parcial, o histórico anterior fica preservado.
    """
    from ..api.routes.marketing import (
        _fetch_daily_sales_ativo_by_ids, _fetch_daily_sales_magento_by_ids,
        _get_cortesia_magento_ids
    )
    from .sync_log_service import log_evento, new_ciclo_id, classify_motivo
    import time as _t_log

    _standalone = ciclo_id is None
    if ciclo_id is None:
        ciclo_id = new_ciclo_id()
    # Quando rodando dentro de um batch pai, usar o job_name do pai para que
    # todas as linhas do mesmo ciclo compartilhem o mesmo job_name (consistência
    # de filtro/derivação na UI).
    _job_name = parent_job_name or "consolidar_vendas_grupo"
    _t0 = _t_log.time()
    if _standalone:
        log_evento(
            ciclo_id, _job_name, "iniciado",
            nivel="ciclo", grupo=evento_grupo,
            detalhes=f"incremental={incremental} ano={ano}",
        )

    mappings = db.query(SkuMapping).filter(
        SkuMapping.evento_grupo == evento_grupo,
        SkuMapping.ano == ano,
        SkuMapping.ativo == True
    ).all()

    if not mappings:
        logger.warning(f"Nenhum SKU mapping para grupo='{evento_grupo}', ano={ano}")
        log_evento(
            ciclo_id, _job_name, "pulado",
            grupo=evento_grupo, motivo="sem_mapeamento",
            duracao_ms=int((_t_log.time() - _t0) * 1000),
        )
        return 0

    ativo_ids = [str(m.id_externo) for m in mappings if m.fonte == 'ATIVO' and m.id_externo]
    magento_ids = [str(m.id_externo) for m in mappings if m.fonte == 'MAGENTO' and m.id_externo]

    cortesia_ids = _get_cortesia_magento_ids(db)

    # Snapshot atual (para reportar qtd_antes no log)
    try:
        _qtd_antes = int(
            db.query(sa_func.coalesce(sa_func.sum(VendasDiariaSnapshot.quantidade), 0))
            .filter(
                VendasDiariaSnapshot.evento_grupo == evento_grupo,
                VendasDiariaSnapshot.fonte == 'CONSOLIDADO',
                VendasDiariaSnapshot.ano == ano,
            ).scalar() or 0
        )
    except Exception:
        _qtd_antes = None

    # Modo incremental: calcula o piso de data baseado no maior dia já
    # gravado no snapshot. Se não existe snapshot ainda, cai pra modo full.
    data_floor: Optional[date] = None
    if incremental:
        from sqlalchemy import func as _sa_func
        max_dia = db.query(_sa_func.max(VendasDiariaSnapshot.data_venda)).filter(
            VendasDiariaSnapshot.evento_grupo == evento_grupo,
            VendasDiariaSnapshot.fonte == 'CONSOLIDADO',
        ).scalar()
        if max_dia:
            # Re-busca a partir do último dia gravado (não +1) pra capturar
            # pedidos inseridos tardiamente naquele dia.
            data_floor = max_dia
        else:
            # Sem snapshot anterior: força modo full nessa execução.
            incremental = False
            logger.info(
                f"[Snapshot] grupo='{evento_grupo}' sem snapshot prévio — caindo pra rebuild completo"
            )

    # Best-effort: if upstream engines went idle / disposed (common in autoscale
    # deployments after the SSH tunnel times out), try to re-establish them
    # synchronously here. Without this, the abort below would just preserve a
    # stale snapshot and the daily-sales chart would silently miss recent days.
    try:
        from ..core import database as db_module
        if ativo_ids:
            try:
                db_module.ensure_ssh_engine_ready()
            except Exception as _ee:
                logger.warning(f"[Snapshot] ensure_ssh_engine_ready falhou: {_ee}")
        if magento_ids:
            try:
                db_module.ensure_magento_engine_ready()
            except Exception as _ee:
                logger.warning(f"[Snapshot] ensure_magento_engine_ready falhou: {_ee}")
    except Exception as _imp_e:
        logger.warning(f"[Snapshot] não foi possível garantir engines antes do fetch: {_imp_e}")

    # CRITICAL: Fetch BOTH sources BEFORE any delete. If a required source fails
    # (SSH tunnel down, MySQL timeout, Magento connection lost), we must abort
    # without deleting — otherwise the snapshot ends up with only the surviving
    # source's data and the chart "loses" the other source's days.
    # Using raise_on_error=True so silently-swallowed exceptions surface here.
    all_daily = {}
    ativo_ok = True
    magento_ok = True

    if ativo_ids:
        try:
            rows = _fetch_daily_sales_ativo_by_ids(list(set(ativo_ids)), raise_on_error=True, data_floor=data_floor)
            for row in rows:
                d = date.fromisoformat(row['dia']) if isinstance(row['dia'], str) else row['dia']
                if d not in all_daily:
                    all_daily[d] = {"qtd": 0, "receita": 0.0}
                all_daily[d]["qtd"] += row['qtd']
                all_daily[d]["receita"] += row.get('receita', 0.0)
        except Exception as _e:
            ativo_ok = False
            logger.error(
                f"[Snapshot] Ativo fetch falhou para grupo='{evento_grupo}', ano={ano}: {_e}"
            )
            log_evento(
                ciclo_id, _job_name, "falha",
                grupo=evento_grupo, fonte="ativo",
                motivo=classify_motivo(_e), detalhes=str(_e),
            )

    if magento_ids:
        try:
            mag_cortesia = set(magento_ids) & cortesia_ids if cortesia_ids else None
            rows = _fetch_daily_sales_magento_by_ids(
                list(set(magento_ids)),
                cortesia_magento_ids=mag_cortesia if mag_cortesia else None,
                raise_on_error=True,
                data_floor=data_floor,
            )
            for row in rows:
                d = date.fromisoformat(row['dia']) if isinstance(row['dia'], str) else row['dia']
                if d not in all_daily:
                    all_daily[d] = {"qtd": 0, "receita": 0.0}
                all_daily[d]["qtd"] += row['qtd']
                all_daily[d]["receita"] += row.get('receita', 0.0)
        except Exception as _e:
            magento_ok = False
            logger.error(
                f"[Snapshot] Magento fetch falhou para grupo='{evento_grupo}', ano={ano}: {_e}"
            )
            log_evento(
                ciclo_id, _job_name, "falha",
                grupo=evento_grupo, fonte="magento",
                motivo=classify_motivo(_e), detalhes=str(_e),
            )

    # Abort if any required source failed — preserves existing snapshot intact.
    # Next scheduled rebuild will retry once the source is healthy again.
    if (ativo_ids and not ativo_ok) or (magento_ids and not magento_ok):
        logger.warning(
            f"[Snapshot] Abortando consolidação para grupo='{evento_grupo}', ano={ano} "
            f"(ativo_ok={ativo_ok}, magento_ok={magento_ok}) — snapshot existente preservado"
        )
        try:
            db.rollback()
        except Exception:
            pass
        log_evento(
            ciclo_id, _job_name, "pulado",
            grupo=evento_grupo,
            fonte=("ambas" if (ativo_ids and not ativo_ok and magento_ids and not magento_ok) else ("magento" if not magento_ok else "ativo")),
            motivo="fonte_indisponivel",
            detalhes=f"ativo_ok={ativo_ok} magento_ok={magento_ok} — snapshot preservado",
            qtd_antes=_qtd_antes, qtd_depois=_qtd_antes,
            data_floor=data_floor,
            duracao_ms=int((_t_log.time() - _t0) * 1000),
        )
        return 0

    yesterday = date.today() - timedelta(days=1)

    # Em modo incremental NUNCA deletamos: o objetivo é exatamente preservar
    # o histórico antigo intacto e só fazer UPSERT dos dias novos.
    if not incremental and data_inicio is None:
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
        log_evento(
            ciclo_id, _job_name, "ok",
            grupo=evento_grupo,
            motivo="sem_vendas_novas" if incremental else "sem_vendas",
            qtd_antes=_qtd_antes, qtd_depois=_qtd_antes,
            data_floor=data_floor,
            duracao_ms=int((_t_log.time() - _t0) * 1000),
        )
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

    try:
        _qtd_depois = int(
            db.query(sa_func.coalesce(sa_func.sum(VendasDiariaSnapshot.quantidade), 0))
            .filter(
                VendasDiariaSnapshot.evento_grupo == evento_grupo,
                VendasDiariaSnapshot.fonte == 'CONSOLIDADO',
                VendasDiariaSnapshot.ano == ano,
            ).scalar() or 0
        )
    except Exception:
        _qtd_depois = None
    log_evento(
        ciclo_id, _job_name, "ok",
        grupo=evento_grupo,
        detalhes=f"{saved} dias gravados (incremental={incremental})",
        qtd_antes=_qtd_antes, qtd_depois=_qtd_depois,
        data_floor=data_floor,
        duracao_ms=int((_t_log.time() - _t0) * 1000),
    )
    if _standalone:
        # Fecha o ciclo standalone para que a UI não rotule como "interrompido".
        log_evento(
            ciclo_id, _job_name, "concluido",
            nivel="ciclo", grupo=evento_grupo,
            detalhes=f"{saved} dias gravados (incremental={incremental} ano={ano})",
            qtd_depois=_qtd_depois,
            duracao_ms=int((_t_log.time() - _t0) * 1000),
        )
    return saved


def snapshot_diario_batch(db: Session):
    from ..api.routes.marketing import _build_sku_to_grupo_map, normalize_sku
    from ..models.cadastro_evento import CadastroEvento
    from .sync_log_service import log_evento, new_ciclo_id
    import time as _t_batch

    _ciclo = new_ciclo_id()
    _t_start = _t_batch.time()
    log_evento(_ciclo, "snapshot_diario_batch", "iniciado", nivel="ciclo")

    today = date.today()
    yesterday = today - timedelta(days=1)
    ano = today.year

    sku_to_grupo = _build_sku_to_grupo_map(db, ano)
    if not sku_to_grupo:
        logger.warning("Nenhum sku_to_grupo encontrado para consolidação diária")
        return

    # Build the set of candidate grupos using BOTH dim_projeto AND
    # cadastro_evento (union), to avoid silently dropping grupos that exist
    # in cadastro_evento but are missing from dim_projeto. See
    # `sincronizar_hoje_batch` for the same rationale.
    grupos_candidatos: set = set()

    # Source 1: DimProjeto
    projetos = db.query(DimProjeto).all()
    for p in projetos:
        if not p.data_evento or not p.codigo:
            continue
        if p.data_evento.year != ano:
            continue
        grupo = sku_to_grupo.get(normalize_sku(str(p.codigo)))
        if grupo:
            grupos_candidatos.add(grupo)

    # Source 2: CadastroEvento (with magento id fallback)
    magento_id_to_grupo: dict = {}
    try:
        for mm in db.query(SkuMapping).filter(
            SkuMapping.ano == ano,
            SkuMapping.ativo == True,
            SkuMapping.fonte == "MAGENTO",
            SkuMapping.id_externo.isnot(None),
            SkuMapping.evento_grupo.isnot(None),
        ).all():
            magento_id_to_grupo[str(mm.id_externo)] = mm.evento_grupo
    except Exception:
        pass

    cadastros = db.query(CadastroEvento).filter(
        CadastroEvento.deleted_at.is_(None),
    ).all()
    projeto_ids = {c.projeto_id for c in cadastros if getattr(c, "projeto_id", None)}
    projeto_codigo_by_id: dict = {}
    if projeto_ids:
        try:
            for pj in db.query(DimProjeto.id, DimProjeto.codigo).filter(DimProjeto.id.in_(projeto_ids)).all():
                if pj.codigo:
                    projeto_codigo_by_id[pj.id] = str(pj.codigo)
        except Exception:
            pass

    cadastro_added = 0
    for c in cadastros:
        if not c.data_evento or c.data_evento.year != ano:
            continue
        grupo = None
        if getattr(c, "sku", None):
            grupo = sku_to_grupo.get(normalize_sku(str(c.sku)))
        if not grupo and getattr(c, "projeto_id", None):
            cod = projeto_codigo_by_id.get(c.projeto_id)
            if cod:
                grupo = sku_to_grupo.get(normalize_sku(cod))
        if not grupo and getattr(c, "id_evento_magento", None):
            grupo = magento_id_to_grupo.get(str(c.id_evento_magento))
        if grupo and grupo not in grupos_candidatos:
            grupos_candidatos.add(grupo)
            cadastro_added += 1

    if cadastro_added:
        logger.info(
            f"snapshot_diario_batch: +{cadastro_added} grupos recuperados de cadastro_evento"
        )

    # Filtra grupos cujos eventos já foram finalizados há > freeze_days.
    # Snapshot já gravado continua sendo lido — só paramos de re-sincronizar
    # dados que não mudam mais.
    freeze_days = _freeze_after_days()
    active_grupos = _load_active_grupos(db, freeze_days)
    grupos_frozen = grupos_candidatos - active_grupos
    if grupos_frozen:
        logger.info(
            f"snapshot_diario_batch: {len(grupos_frozen)} grupos pulados (finalizados há > {freeze_days} dias)"
        )
    grupos_candidatos = grupos_candidatos & active_grupos

    grupos_processados = set()
    for grupo in grupos_candidatos:
        if grupo in grupos_processados:
            continue
        grupos_processados.add(grupo)

        latest = get_latest_snapshot_date(db, grupo)
        if latest and latest >= yesterday:
            continue

        try:
            # Job agendado usa modo incremental: só busca dias novos desde
            # a última sincronização, reduzindo drasticamente a carga no
            # Magento e protegendo o histórico de gravações parciais.
            consolidar_vendas_grupo(db, grupo, ano, data_inicio=None, data_fim=yesterday, incremental=True, ciclo_id=_ciclo, parent_job_name="snapshot_diario_batch")
        except Exception as e:
            logger.error(f"Erro ao consolidar snapshot para grupo='{grupo}': {e}")
            try:
                from .sync_log_service import log_evento as _le_err, classify_motivo as _cm_err
                _le_err(_ciclo, "snapshot_diario_batch", "falha", grupo=grupo,
                        motivo=_cm_err(e), detalhes=str(e))
            except Exception:
                pass

    logger.info(f"Consolidação diária concluída: {len(grupos_processados)} grupos processados")
    log_evento(
        _ciclo, "snapshot_diario_batch", "concluido", nivel="ciclo",
        detalhes=f"{len(grupos_processados)} grupos processados, {len(grupos_frozen)} congelados",
        duracao_ms=int((_t_batch.time() - _t_start) * 1000),
    )
    return len(grupos_processados)


def consolidar_curvas_historicas_batch(db: Session):
    from ..api.routes.marketing import (
        _build_sku_to_grupo_map, _fetch_previous_year_cumulative_pattern,
        _resolve_hist_pattern
    )
    from ..models.vendas_snapshot import VendasDiariaSnapshot
    from sqlalchemy import func as _func

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

    orphan_repair = _repair_orphan_curva_historica(db)
    if orphan_repair:
        logger.info(f"Curvas históricas órfãs reparadas: {orphan_repair}")

    return saved + derived


def _repair_orphan_curva_historica(db: Session) -> int:
    """Rebuild CurvaHistoricaSnapshot for groups that have VendasDiariaSnapshot
    data but are missing any CurvaHistoricaSnapshot entry.  This covers groups
    created or re-synced outside the normal nightly batch (e.g. manually added
    historical groups like 'Vibra Riders')."""
    from ..api.routes.marketing import _fetch_previous_year_cumulative_pattern
    from ..models.vendas_snapshot import VendasDiariaSnapshot, CurvaHistoricaSnapshot
    from sqlalchemy import func as _func

    vendas_anos = db.query(
        VendasDiariaSnapshot.evento_grupo,
        _func.max(VendasDiariaSnapshot.ano).label("max_ano")
    ).group_by(VendasDiariaSnapshot.evento_grupo).all()

    curva_grupos = {
        row[0] for row in db.query(CurvaHistoricaSnapshot.evento_grupo).distinct().all()
    }

    repaired = 0
    for row in vendas_anos:
        grupo = row.evento_grupo
        max_ano = row.max_ano
        if grupo in curva_grupos:
            continue
        try:
            pattern = _fetch_previous_year_cumulative_pattern(db, grupo, max_ano + 1)
            if pattern:
                save_curva_historica_snapshot(db, grupo, max_ano, pattern, len(pattern), origem="historico")
                repaired += 1
                logger.info(f"[RepairOrphan] CurvaHistoricaSnapshot criada para '{grupo}' ano_referencia={max_ano}")
        except Exception as e:
            logger.warning(f"[RepairOrphan] Falha ao reparar '{grupo}': {e}")

    return repaired


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
        _get_cortesia_magento_ids,
    )
    from .sync_log_service import log_evento as _le_hj, new_ciclo_id as _ncid_hj, classify_motivo as _cm_hj
    import time as _t_hj

    _ciclo_hj = _ncid_hj()
    _t_hj_start = _t_hj.time()
    _le_hj(_ciclo_hj, "sincronizar_hoje_batch", "iniciado", nivel="ciclo")

    today = date.today()
    yesterday = today - timedelta(days=1)
    ano = today.year

    # D- >= -1 (not consolidated) means data_evento >= today + 1.
    # registration_close = data_evento - 2, D- = registration_close - today.
    # D- = -1 → registration_close = today - 1 → data_evento = today + 1.
    min_live_date = today + timedelta(days=1)

    # --- Build map of live/hybrid grupos ---
    # A grupo is live/hybrid if it has at least one event with
    # data_evento >= min_live_date in the current year.
    #
    # IMPORTANT: We use BOTH `dim_projeto` AND `cadastro_evento` as sources of
    # truth, taking the union. Either table can be incomplete in production
    # (e.g. dim_projeto missing freshly-created events, or cadastro_evento
    # entries with id_evento_magento=NULL). Falling back to the union ensures
    # a grupo is never silently excluded from today's sync — which would cause
    # the dashboard to show 0 sales today even though sales exist.
    from ..models.cadastro_evento import CadastroEvento

    sku_to_grupo = _build_sku_to_grupo_map(db, ano)
    live_grupos: set = set()
    max_date = date(ano + 1, 1, 1)

    # Source 1: DimProjeto (codigo → SKU mapping)
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

    # Source 2: CadastroEvento — covers events that exist in the operational
    # cadastro but haven't been propagated to dim_projeto yet. We resolve the
    # grupo via either: (a) the cadastro's own SKU, (b) the related projeto's
    # codigo, or (c) by joining its id_evento_magento to a SkuMapping row.
    #
    # Build helper lookups once.
    magento_id_to_grupo: dict = {}
    try:
        mag_mappings = db.query(SkuMapping).filter(
            SkuMapping.ano == ano,
            SkuMapping.ativo == True,
            SkuMapping.fonte == "MAGENTO",
            SkuMapping.id_externo.isnot(None),
            SkuMapping.evento_grupo.isnot(None),
        ).all()
        for mm in mag_mappings:
            magento_id_to_grupo[str(mm.id_externo)] = mm.evento_grupo
    except Exception as _mml:
        logger.warning(f"sincronizar_hoje_batch: falha ao construir magento_id_to_grupo: {_mml}")

    cadastros = db.query(CadastroEvento).filter(
        CadastroEvento.deleted_at.is_(None),
        CadastroEvento.data_evento >= min_live_date,
        CadastroEvento.data_evento < max_date,
    ).all()

    # Pre-load all DimProjeto rows referenced by these cadastros in a single
    # query to avoid an N+1 lookup inside the loop below.
    projeto_ids = {c.projeto_id for c in cadastros if getattr(c, "projeto_id", None)}
    projeto_codigo_by_id: dict = {}
    if projeto_ids:
        try:
            for pj in db.query(DimProjeto.id, DimProjeto.codigo).filter(DimProjeto.id.in_(projeto_ids)).all():
                if pj.codigo:
                    projeto_codigo_by_id[pj.id] = str(pj.codigo)
        except Exception as _pl_e:
            logger.warning(f"sincronizar_hoje_batch: pré-carga de projetos falhou: {_pl_e}")

    cadastro_added = 0
    for c in cadastros:
        if not c.data_evento:
            continue
        grupo = None
        # (a) cadastro.sku
        if getattr(c, "sku", None):
            grupo = sku_to_grupo.get(normalize_sku(str(c.sku)))
        # (b) related projeto codigo (lookup via pre-loaded map)
        if not grupo and getattr(c, "projeto_id", None):
            cod = projeto_codigo_by_id.get(c.projeto_id)
            if cod:
                grupo = sku_to_grupo.get(normalize_sku(cod))
        # (c) magento id
        if not grupo and getattr(c, "id_evento_magento", None):
            grupo = magento_id_to_grupo.get(str(c.id_evento_magento))
        if grupo and grupo not in live_grupos:
            live_grupos.add(grupo)
            cadastro_added += 1

    if cadastro_added:
        logger.info(
            f"sincronizar_hoje_batch: +{cadastro_added} grupos live recuperados de "
            f"cadastro_evento (não estavam em dim_projeto)"
        )

    if not live_grupos:
        logger.info("sincronizar_hoje_batch: nenhum grupo live/hybrid encontrado")
        from .sync_log_service import log_evento as _le_empty
        _le_empty(_ciclo_hj, "sincronizar_hoje_batch", "concluido", nivel="ciclo",
                  motivo="sem_grupos_live", duracao_ms=int((_t_hj.time() - _t_hj_start) * 1000))
        return 0

    mappings = db.query(SkuMapping).filter(
        SkuMapping.ano == ano,
        SkuMapping.ativo == True,
        SkuMapping.id_externo.isnot(None)
    ).all()

    if not mappings:
        logger.info("sincronizar_hoje_batch: nenhum SkuMapping ativo para o ano corrente")
        from .sync_log_service import log_evento as _le_nm
        _le_nm(_ciclo_hj, "sincronizar_hoje_batch", "concluido", nivel="ciclo",
               motivo="sem_mapeamento", duracao_ms=int((_t_hj.time() - _t_hj_start) * 1000))
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

    # Best-effort: ensure upstream engines are alive before we even try the
    # batched queries. In autoscale deployments the SSH tunnel and the Magento
    # engine may have gone idle since the previous cycle.
    try:
        from ..core import database as db_module
        if all_ativo_ids:
            try:
                db_module.ensure_ssh_engine_ready()
            except Exception as _ee:
                logger.warning(f"sincronizar_hoje_batch: ensure_ssh_engine_ready falhou: {_ee}")
        if all_magento_ids:
            try:
                db_module.ensure_magento_engine_ready()
            except Exception as _ee:
                logger.warning(f"sincronizar_hoje_batch: ensure_magento_engine_ready falhou: {_ee}")
    except Exception as _imp_e:
        logger.warning(f"sincronizar_hoje_batch: ensure engines pré-fetch falhou: {_imp_e}")

    # --- Step 1: Backfill historical data for groups with no snapshot rows ---
    backfilled = 0
    for grupo in list(grupos.keys()):
        latest = get_latest_snapshot_date(db, grupo)
        if latest is None:
            try:
                logger.info(f"sincronizar_hoje_batch: backfill histórico para '{grupo}'")
                consolidar_vendas_grupo(db, grupo, ano, data_fim=yesterday, ciclo_id=_ciclo_hj, parent_job_name="sincronizar_hoje_batch")
                backfilled += 1
            except Exception as e:
                logger.warning(f"sincronizar_hoje_batch: backfill falhou para '{grupo}': {e}")
                _le_hj(_ciclo_hj, "sincronizar_hoje_batch", "falha", grupo=grupo,
                       motivo=_cm_hj(e), detalhes=f"backfill: {e}")

    # --- Step 2: Fetch today's data in batch (2 MySQL queries total) ---
    # Track *health* of each source separately so we can skip the UPSERT for
    # grupos whose required source failed — otherwise we'd overwrite a healthy
    # snapshot row for "today" with quantity=0 just because a source went down.
    ativo_today: dict = {}
    magento_today: dict = {}
    ativo_ok = True
    magento_ok = True

    # Lazy-import the breakers to avoid a circular import at module load.
    try:
        from ..api.routes.marketing import ativo_breaker, magento_breaker, CircuitOpenError as _CircuitOpenError
    except Exception as _br_imp_e:
        ativo_breaker = None
        magento_breaker = None
        _CircuitOpenError = Exception
        logger.warning(f"sincronizar_hoje_batch: breakers indisponíveis: {_br_imp_e}")

    if all_ativo_ids:
        if ativo_breaker is not None and ativo_breaker.is_open():
            ativo_ok = False
            logger.warning("sincronizar_hoje_batch: Ativo circuit aberto — pulando fetch para preservar pool")
        else:
            ativo_fetch_ok = False
            try:
                if ativo_breaker is not None:
                    ativo_today = ativo_breaker.call(
                        _fetch_today_sales_ativo_grouped, list(set(all_ativo_ids)), raise_on_error=True
                    )
                else:
                    ativo_today = _fetch_today_sales_ativo_grouped(list(set(all_ativo_ids)), raise_on_error=True)
                logger.info(f"sincronizar_hoje_batch: Ativo retornou {len(ativo_today)} IDs com vendas hoje")
                ativo_fetch_ok = True
            except _CircuitOpenError:
                ativo_ok = False
                _le_hj(_ciclo_hj, "sincronizar_hoje_batch", "falha", fonte="ativo",
                       motivo="circuit_aberto", detalhes="Ativo circuit aberto durante fetch")
            except Exception as e:
                ativo_ok = False
                logger.error(f"sincronizar_hoje_batch: erro Ativo grouped: {e}")
                _le_hj(_ciclo_hj, "sincronizar_hoje_batch", "falha", fonte="ativo",
                       motivo=_cm_hj(e), detalhes=str(e))
            if ativo_fetch_ok:
                # An empty result with engine_ssh down is indistinguishable from
                # "no sales today" at this layer; treat missing engine explicitly.
                try:
                    from ..core import database as db_module
                    if db_module.engine_ssh is None:
                        ativo_ok = False
                        logger.warning(
                            "sincronizar_hoje_batch: engine_ssh indisponível no momento do fetch — "
                            "ATIVO marcado como não saudável (não vamos UPSERT zerado)"
                        )
                except Exception:
                    pass

    if all_magento_ids:
        if magento_breaker is not None and magento_breaker.is_open():
            magento_ok = False
            logger.warning("sincronizar_hoje_batch: Magento circuit aberto — pulando fetch para preservar pool")
        else:
            magento_fetch_ok = False
            try:
                _cort_ids = _get_cortesia_magento_ids(db)
                if magento_breaker is not None:
                    magento_today = magento_breaker.call(
                        _fetch_today_sales_magento_grouped,
                        list(set(all_magento_ids)),
                        cortesia_magento_ids=_cort_ids if _cort_ids else None,
                        raise_on_error=True,
                    )
                else:
                    magento_today = _fetch_today_sales_magento_grouped(
                        list(set(all_magento_ids)),
                        cortesia_magento_ids=_cort_ids if _cort_ids else None,
                        raise_on_error=True,
                    )
                logger.info(f"sincronizar_hoje_batch: Magento retornou {len(magento_today)} IDs com vendas hoje")
                magento_fetch_ok = True
            except _CircuitOpenError:
                magento_ok = False
                _le_hj(_ciclo_hj, "sincronizar_hoje_batch", "falha", fonte="magento",
                       motivo="circuit_aberto", detalhes="Magento circuit aberto durante fetch")
            except Exception as e:
                magento_ok = False
                logger.error(f"sincronizar_hoje_batch: erro Magento grouped: {e}")
                _le_hj(_ciclo_hj, "sincronizar_hoje_batch", "falha", fonte="magento",
                       motivo=_cm_hj(e), detalhes=str(e))
            if magento_fetch_ok:
                try:
                    from ..core import database as db_module
                    if db_module.engine_magento is None:
                        magento_ok = False
                        logger.warning(
                            "sincronizar_hoje_batch: engine_magento indisponível no momento do fetch — "
                            "MAGENTO marcado como não saudável (não vamos UPSERT zerado)"
                        )
                except Exception:
                    pass

    # --- Step 3: Aggregate by grupo and UPSERT today's row ---
    # Strategy:
    #   - Both sources OK → full UPSERT (overwrite with complete value)
    #   - One source down, other OK → partial UPSERT using GREATEST() so we
    #     always surface the healthy source's data without ever lowering a
    #     previously-known total from a full sync. This avoids the scenario
    #     where Magento goes down mid-day and today's Ativo sales (e.g. 20
    #     inscriptions) remain invisible because the UPSERT was skipped entirely.
    #   - Both sources down → skip entirely (preserve whatever is in the DB)
    synced = 0
    partial_synced = 0
    failed = 0
    skipped_unhealthy = 0
    for grupo, ids in grupos.items():
        grupo_needs_ativo = bool(ids["ativo_ids"])
        grupo_needs_magento = bool(ids["magento_ids"])

        ativo_healthy_for_grupo = not grupo_needs_ativo or ativo_ok
        magento_healthy_for_grupo = not grupo_needs_magento or magento_ok
        all_sources_ok = ativo_healthy_for_grupo and magento_healthy_for_grupo
        # Can we do at least a partial UPSERT with one healthy source?
        can_partial = (not all_sources_ok) and (ativo_healthy_for_grupo or magento_healthy_for_grupo)

        if not all_sources_ok and not can_partial:
            skipped_unhealthy += 1
            logger.warning(
                f"sincronizar_hoje_batch: pulando UPSERT de hoje para '{grupo}' — "
                f"ambas fontes indisponíveis (ativo_ok={ativo_ok}, magento_ok={magento_ok}); "
                f"snapshot existente preservado"
            )
            _le_hj(_ciclo_hj, "sincronizar_hoje_batch", "pulado", grupo=grupo,
                   fonte="ambas", motivo="fonte_indisponivel",
                   detalhes=f"ativo_ok={ativo_ok} magento_ok={magento_ok}")
            continue

        try:
            qtd_total = 0
            receita_total = 0.0

            if ativo_healthy_for_grupo:
                for eid in ids["ativo_ids"]:
                    entry = ativo_today.get(eid)
                    if entry:
                        qtd_total += entry["qtd"]
                        receita_total += entry["receita"]

            if magento_healthy_for_grupo:
                for eid in ids["magento_ids"]:
                    entry = magento_today.get(eid)
                    if entry:
                        qtd_total += entry["qtd"]
                        receita_total += entry["receita"]

            if all_sources_ok:
                # Full UPSERT: overwrite with complete consolidated value
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
            else:
                # Partial UPSERT: use GREATEST() so we never lower a value
                # that was previously persisted from a successful full sync.
                # On INSERT (no existing row), the VALUES clause wins directly.
                missing = "magento" if (grupo_needs_magento and not magento_ok) else "ativo"
                logger.warning(
                    f"sincronizar_hoje_batch: UPSERT parcial para '{grupo}' "
                    f"({missing} indisponível) — usando GREATEST() para preservar total anterior"
                )
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
                        "quantidade": sa_func.greatest(
                            VendasDiariaSnapshot.__table__.c.quantidade, qtd_total
                        ),
                        "receita": sa_func.greatest(
                            VendasDiariaSnapshot.__table__.c.receita, receita_total
                        ),
                        "ano": ano,
                    }
                )

            db.execute(stmt)
            db.commit()
            if all_sources_ok:
                synced += 1
                _le_hj(_ciclo_hj, "sincronizar_hoje_batch", "ok", grupo=grupo,
                       qtd_depois=qtd_total)
            else:
                partial_synced += 1
                _le_hj(_ciclo_hj, "sincronizar_hoje_batch", "parcial", grupo=grupo,
                       fonte=("magento" if (grupo_needs_magento and not magento_ok) else "ativo"),
                       motivo="fonte_indisponivel",
                       detalhes=f"GREATEST() aplicado — ativo_ok={ativo_ok} magento_ok={magento_ok}",
                       qtd_depois=qtd_total)
        except Exception as e:
            failed += 1
            logger.error(f"sincronizar_hoje_batch: erro para grupo='{grupo}': {e}")
            _le_hj(_ciclo_hj, "sincronizar_hoje_batch", "falha", grupo=grupo,
                   motivo=_cm_hj(e), detalhes=str(e))
            try:
                db.rollback()
            except Exception:
                pass

    logger.info(
        f"sincronizar_hoje_batch: {synced}/{len(grupos)} grupos sincronizados para {today}"
        f" (parciais={partial_synced}, backfills={backfilled}, falhas={failed},"
        f" pulados={skipped_unhealthy})"
    )
    _le_hj(
        _ciclo_hj, "sincronizar_hoje_batch", "concluido", nivel="ciclo",
        detalhes=(
            f"total={len(grupos)} ok={synced} parciais={partial_synced} "
            f"falhas={failed} pulados={skipped_unhealthy} backfills={backfilled} "
            f"ativo_ok={ativo_ok} magento_ok={magento_ok}"
        ),
        qtd_depois=synced + partial_synced,
        duracao_ms=int((_t_hj.time() - _t_hj_start) * 1000),
    )

    # Invalidate event_detail and ISC caches so next dashboard request gets fresh
    # snapshot data without waiting for the 22h/5min SmartCache TTL to expire.
    # Only invalidate when Magento actually returned real data (synced > 0).
    # Partial-only runs mean Magento was unavailable; blowing the cache in that
    # case causes a MISS loop where every subsequent request tries Magento live
    # and also fails, leaving users with a perpetual loading screen.
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

    # Persist the "last_sync_hoje" timestamp HERE (inside the function) instead of
    # relying on each outer caller to do it. Em produção o servidor reinicia com
    # frequência (deploys, health checks) e os threads daemon que envolvem este
    # batch são mortos antes de chegar na linha que persiste o carimbo. Como o
    # trabalho real (UPSERT + invalidação de cache) já terminou neste ponto,
    # gravar o timestamp aqui garante que o badge "Sinc. dd/mm às HH:MM" reflita
    # a sincronização que de fato aconteceu, mesmo se o caller for interrompido
    # logo depois do return.
    if synced > 0 or backfilled > 0:
        try:
            import time as _t_lsh
            from ..core.cache import set_last_sync_hoje as _set_lsh
            _set_lsh(_t_lsh.time())
        except Exception as _lsh_e:
            logger.warning(f"sincronizar_hoje_batch: falha ao atualizar last_sync_hoje: {_lsh_e}")

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
    """Pré-computa receita E quantidade Magento por bundle_entity_id e persiste em margem_bundle_rev_snapshot.

    Executa as mesmas duas queries de get_margem_por_kit (count + revenue), mas
    de forma centralizada para todos os bundles mapeados, com timeout maior
    (5 min) por ser job de background. O resultado elimina timeouts na tela
    Margem por Kit para eventos de alto volume e — mais importante — serve como
    fallback persistente para a contagem de inscrições por bundle quando o
    Magento ao vivo cai ou responde parcial. Sem isso o currentSales do detalhe
    fica oscilando para baixo a cada falha de conexão.

    Chamado pelo job de consolidação das 4h (antes do full warmup das 5h).
    """
    from ..core.database import engine_magento
    from ..models.kit_config import KitConfig
    from ..models.dimensoes import DimProjeto, SkuMapping, EventoGrupo
    from sqlalchemy import text, bindparam
    from datetime import timezone

    if engine_magento is None:
        logger.warning("[MargemRevSync] engine_magento não disponível — sync ignorado")
        return {"status": "skipped", "motivo": "engine_magento indisponível"}

    # Carrega bundles com id_evento para podermos filtrar por evento finalizado.
    # Bundles sem id_evento (legacy) ficam por padrão — não dá pra classificar
    # como frozen sem ter data.
    bundle_rows = (
        db.query(KitConfig.bundle_entity_id, KitConfig.id_evento)
        .filter(KitConfig.tipo_kit.isnot(None))
        .distinct()
        .all()
    )

    if not bundle_rows:
        logger.info("[MargemRevSync] Nenhum bundle_entity_id encontrado em kit_config")
        return {"status": "ok", "bundles_processados": 0}

    # Filtro de eventos finalizados — economia de janela Magento.
    freeze_days = _freeze_after_days()
    active_event_ids, all_event_ids = _load_active_event_magento_ids(db, freeze_days)
    bundle_ids_all = []
    skipped_frozen = 0
    for bid, evt_id in bundle_rows:
        if evt_id is not None and evt_id in all_event_ids and evt_id not in active_event_ids:
            skipped_frozen += 1
            continue
        bundle_ids_all.append(bid)
    if skipped_frozen:
        logger.info(
            f"[MargemRevSync] {skipped_frozen} bundles pulados (eventos finalizados há > {freeze_days} dias)"
        )

    if not bundle_ids_all:
        logger.info("[MargemRevSync] Todos os bundles estão congelados — nada a sincronizar")
        return {"status": "ok", "bundles_processados": 0, "bundles_pulados_frozen": skipped_frozen}

    cortesia_bundle_set: set = set()
    try:
        cortesia_skus: set = set()
        for proj in db.query(DimProjeto).filter(DimProjeto.incluir_cortesias == True).all():
            if proj.codigo:
                cortesia_skus.add(proj.codigo.upper().strip())
        for grupo in db.query(EventoGrupo).filter(EventoGrupo.incluir_cortesias == True).all():
            grp_mappings = db.query(SkuMapping).filter(
                SkuMapping.evento_grupo == grupo.nome,
                SkuMapping.ativo == True,
            ).all()
            for sm in grp_mappings:
                if sm.sku:
                    cortesia_skus.add(sm.sku.upper().strip())
        if cortesia_skus:
            from ..models.cadastro_evento import CadastroEvento
            for cs in cortesia_skus:
                proj = db.query(DimProjeto).filter(DimProjeto.codigo == cs).first()
                if not proj:
                    continue
                cadastro = db.query(CadastroEvento).filter(CadastroEvento.projeto_id == proj.id).first()
                if not cadastro or not cadastro.id_evento_magento:
                    continue
                bundle_rows = db.query(KitConfig.bundle_entity_id).filter(
                    KitConfig.id_evento == cadastro.id_evento_magento,
                    KitConfig.bundle_entity_id.isnot(None),
                ).all()
                for (bid,) in bundle_rows:
                    cortesia_bundle_set.add(bid)
    except Exception as _e_cort:
        logger.warning(f"[MargemRevSync] Erro ao buscar cortesia bundles: {_e_cort}")

    logger.info(f"[MargemRevSync] Iniciando sync de receita para {len(bundle_ids_all)} bundles ({len(cortesia_bundle_set)} com cortesias)")

    def _build_rev_query(include_cortesias: bool):
        # Cortesia filters use a SQL-level boolean parameter so the query string is
        # static — no f-strings or concatenation inside text(), following SQLAlchemy
        # best practices. :skip_cortesia_filter=True short-circuits the OR, skipping
        # the filter; False enforces it.
        return text(
            "SELECT /*+ MAX_EXECUTION_TIME(300000) */\n"
            "    soi_parent.product_id                                                              AS bundle_entity_id,\n"
            "    ROUND(SUM(soi_child.price - soi_child.discount_amount), 2)                        AS receita_liquida\n"
            "FROM sales_order so\n"
            "INNER JOIN sales_order_item soi_parent\n"
            "       ON soi_parent.order_id     = so.entity_id\n"
            "      AND soi_parent.product_type = 'bundle'\n"
            "      AND soi_parent.product_id   IN :bundle_ids\n"
            "INNER JOIN sales_order_item soi_child\n"
            "       ON soi_child.parent_item_id = soi_parent.item_id\n"
            "      AND soi_child.product_type   = 'simple'\n"
            "      AND (:skip_cortesia_filter OR (soi_child.price > 0 AND soi_child.price - soi_child.discount_amount > 0))\n"
            "      AND (\n"
            "            soi_child.name LIKE '%%Distância%%'\n"
            "         OR soi_child.name LIKE '%%Distancia%%'\n"
            "         OR soi_child.name LIKE '%%Distâncias%%'\n"
            "         OR soi_child.name LIKE '%%Modalidade%%'\n"
            "         OR soi_child.name REGEXP '-[0-9]+[Kk]m$'\n"
            "         OR soi_child.name REGEXP '^[0-9]+[Kk]m?$'\n"
            "         OR soi_child.name LIKE 'Kit Participação%%'\n"
            "         OR soi_child.name LIKE 'Olímpico%%'\n"
            "         OR soi_child.name LIKE 'Yoga%%'\n"
            "      )\n"
            "WHERE\n"
            "    so.created_at >= DATE_SUB(CURDATE(), INTERVAL 2 YEAR)\n"
            "AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')\n"
            "AND so.state != 'canceled'\n"
            "AND (:skip_cortesia_filter OR so.base_grand_total > 0)\n"
            "AND (:skip_cortesia_filter OR NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50))\n"
            "AND so.created_at < CURDATE() + INTERVAL 1 DAY\n"
            "AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')\n"
            "AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')\n"
            "AND so.increment_id NOT REGEXP '-[0-9]'\n"
            "GROUP BY soi_parent.product_id"
        ).bindparams(
            bindparam("bundle_ids", expanding=True),
            skip_cortesia_filter=bool(include_cortesias),
        )

    rev_query_normal = _build_rev_query(False)
    rev_query_cortesia = _build_rev_query(True) if cortesia_bundle_set else None

    def _build_cnt_query(include_cortesias: bool):
        # Mesma lógica do count_query inline em get_margem_por_kit, com timeout
        # elevado para 5 min (background). Retorna {bundle_entity_id: qtd}.
        return text(
            "SELECT /*+ MAX_EXECUTION_TIME(300000) */\n"
            "    soi_parent.product_id                  AS bundle_entity_id,\n"
            "    COUNT(DISTINCT soi_parent.item_id)     AS qtd\n"
            "FROM sales_order so\n"
            "INNER JOIN sales_order_item soi_parent\n"
            "       ON soi_parent.order_id     = so.entity_id\n"
            "      AND soi_parent.product_type = 'bundle'\n"
            "      AND soi_parent.product_id   IN :bundle_ids\n"
            "WHERE\n"
            "    so.created_at >= DATE_SUB(CURDATE(), INTERVAL 2 YEAR)\n"
            "AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')\n"
            "AND so.state != 'canceled'\n"
            "AND (:skip_cortesia_filter OR so.base_grand_total > 0)\n"
            "AND (:skip_cortesia_filter OR NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50))\n"
            "AND so.created_at < CURDATE() + INTERVAL 1 DAY\n"
            "AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')\n"
            "AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')\n"
            "AND so.increment_id NOT REGEXP '-[0-9]'\n"
            "GROUP BY soi_parent.product_id"
        ).bindparams(
            bindparam("bundle_ids", expanding=True),
            skip_cortesia_filter=bool(include_cortesias),
        )

    cnt_query_normal = _build_cnt_query(False)
    cnt_query_cortesia = _build_cnt_query(True) if cortesia_bundle_set else None

    rev_by_bid: dict = {}
    qtd_by_bid: dict = {}
    BATCH_SIZE = 80
    upserted_total = 0
    persist_failures = 0

    from app.core.db_retry import magento_run
    from app.core.database import SessionLocal as _PgSession

    def _persist_batch(rev_rows: dict, cnt_rows: dict) -> int:
        """Grava um lote (receita + qtd) no Postgres usando session NOVA por chamada.

        Sessão nova evita o problema de SSL fechado por inatividade enquanto as
        queries pesadas no Magento rodavam. Em caso de falha de persistência,
        loga e segue (próximo batch tenta de novo, sem perder os já gravados).
        Faz upsert para todos os bundles que apareceram em receita OU contagem.
        Usa GREATEST() para nunca rebaixar receita ou qtd já gravadas — o sync
        é piso de segurança contra Magento parcial, não fonte de variações
        negativas (essas vêm via sincronizar_hoje no vendas_diaria_snapshot).
        """
        from sqlalchemy import func as _sa_func
        all_bids = set(rev_rows.keys()) | set(cnt_rows.keys())
        if not all_bids:
            return 0
        agora_utc = datetime.now(timezone.utc)
        _s = _PgSession()
        try:
            count = 0
            for bid in all_bids:
                receita = float(rev_rows.get(bid, 0) or 0)
                qtd = int(cnt_rows.get(bid, 0) or 0)
                stmt = pg_insert(MargemBundleRevSnapshot).values(
                    bundle_entity_id=bid,
                    receita_liquida=receita,
                    qtd_inscricoes=qtd,
                    calculado_em=agora_utc,
                )
                # SAFEGUARD: nunca sobrescrever um valor positivo já gravado
                # com 0. Cenário: Magento devolve resposta parcial para alguns
                # bundles (sem lançar exceção), o sync gravaria 0 e o snapshot
                # viraria piso baixo. GREATEST() preserva o maior valor entre
                # o que já está gravado e o que está chegando agora.
                # Receita e qtd têm o mesmo tratamento — ambas só "crescem".
                # Cancelamentos e refunds reais aparecem via sincronizar_hoje
                # (que atualiza vendas_diaria_snapshot, não este snapshot por
                # bundle). Este snapshot é piso de segurança contra falha do
                # Magento, não fonte primária de variações negativas.
                stmt = stmt.on_conflict_do_update(
                    index_elements=["bundle_entity_id"],
                    set_={
                        "receita_liquida": _sa_func.greatest(
                            stmt.excluded.receita_liquida,
                            MargemBundleRevSnapshot.receita_liquida,
                        ),
                        "qtd_inscricoes": _sa_func.greatest(
                            stmt.excluded.qtd_inscricoes,
                            MargemBundleRevSnapshot.qtd_inscricoes,
                        ),
                        "calculado_em": agora_utc,
                    },
                )
                _s.execute(stmt)
                count += 1
            _s.commit()
            return count
        except Exception as _e_pg:
            _s.rollback()
            raise _e_pg
        finally:
            _s.close()

    for i in range(0, len(bundle_ids_all), BATCH_SIZE):
        batch = bundle_ids_all[i:i + BATCH_SIZE]
        normal_batch = [b for b in batch if b not in cortesia_bundle_set]
        cortesia_batch = [b for b in batch if b in cortesia_bundle_set]
        batch_rev_rows: dict = {}
        batch_cnt_rows: dict = {}

        def _sync_batch_work(conn):
            collected_rev = 0
            collected_cnt = 0
            # Receita (lenta — join com filhos por nome)
            if normal_batch:
                _rows_n = conn.execute(rev_query_normal, {"bundle_ids": normal_batch}).fetchall()
                for row in _rows_n:
                    val = float(row[1] or 0)
                    batch_rev_rows[int(row[0])] = val
                    rev_by_bid[int(row[0])] = val
                collected_rev += len(_rows_n)
            if cortesia_batch and rev_query_cortesia:
                _rows_c = conn.execute(rev_query_cortesia, {"bundle_ids": cortesia_batch}).fetchall()
                for row in _rows_c:
                    val = float(row[1] or 0)
                    batch_rev_rows[int(row[0])] = val
                    rev_by_bid[int(row[0])] = val
                collected_rev += len(_rows_c)
            # Contagem (rápida — só sales_order_item parent)
            if normal_batch:
                _rows_cn = conn.execute(cnt_query_normal, {"bundle_ids": normal_batch}).fetchall()
                for row in _rows_cn:
                    val = int(row[1] or 0)
                    batch_cnt_rows[int(row[0])] = val
                    qtd_by_bid[int(row[0])] = val
                collected_cnt += len(_rows_cn)
            if cortesia_batch and cnt_query_cortesia:
                _rows_cc = conn.execute(cnt_query_cortesia, {"bundle_ids": cortesia_batch}).fetchall()
                for row in _rows_cc:
                    val = int(row[1] or 0)
                    batch_cnt_rows[int(row[0])] = val
                    qtd_by_bid[int(row[0])] = val
                collected_cnt += len(_rows_cc)
            return collected_rev, collected_cnt

        try:
            collected = magento_run(_sync_batch_work, label=f"margem-rev-sync:batch{i // BATCH_SIZE + 1}", profile="background")
            _crev, _ccnt = collected if isinstance(collected, tuple) else (collected, 0)
            logger.info(
                f"[MargemRevSync] Batch {i // BATCH_SIZE + 1}: {len(batch)} bundles → "
                f"{_crev} com receita, {_ccnt} com qtd"
            )
        except Exception as e:
            logger.error(f"[MargemRevSync] Erro no batch {i // BATCH_SIZE + 1} (bundles {i}–{i + len(batch)}): {e}")
            continue

        # Persiste imediatamente (session nova) para que parcial sempre fique.
        try:
            persisted = _persist_batch(batch_rev_rows, batch_cnt_rows)
            upserted_total += persisted
        except Exception as _e_persist:
            persist_failures += 1
            logger.error(
                f"[MargemRevSync] Falha ao gravar batch {i // BATCH_SIZE + 1} no Postgres: {_e_persist}"
            )

    if upserted_total == 0:
        if not rev_by_bid:
            logger.warning("[MargemRevSync] Nenhuma receita retornada do Magento — snapshot não atualizado")
            return {"status": "sem_dados", "bundles_processados": len(bundle_ids_all)}
        logger.error(
            f"[MargemRevSync] Magento retornou {len(rev_by_bid)} bundles, mas TODAS as gravações falharam"
        )
        return {
            "status": "falha_persistencia",
            "bundles_processados": len(bundle_ids_all),
            "bundles_com_receita": len(rev_by_bid),
            "persist_failures": persist_failures,
        }

    logger.info(
        f"[MargemRevSync] Snapshot atualizado: {upserted_total} bundles gravados "
        f"em margem_bundle_rev_snapshot ({persist_failures} batches com falha de persistência)"
    )
    return {
        "status": "ok",
        "bundles_processados": len(bundle_ids_all),
        "bundles_com_receita": upserted_total,
        "persist_failures": persist_failures,
    }


def backfill_historico(db: Session, ano: int, data_inicio: Optional[date] = None, data_fim: Optional[date] = None):
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
