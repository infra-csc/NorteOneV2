
import os
import time as _time
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import text, bindparam, func
from sqlalchemy.exc import IntegrityError
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from ...core.database import get_db
from ...core import database as db_module
from ...core.db_retry import magento_run, MagentoEngineUnavailable
from ...core.security import get_current_user, require_admin, require_permission
from ...models.dimensoes import DimProjeto, SkuMapping, EventoGrupo as EventoGrupoModel, MarketingSettings
from ...models.user import Usuario
from ...models.cadastro_evento import CadastroEvento, CadastroKitProduto, CadastroKitProdutoItem, CadastroFaixaPrecoSite
from .inscricoes_consolidado import normalize_sku
import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

_TZ_BRAZIL = ZoneInfo("America/Sao_Paulo")

def today_brazil() -> date:
    """Returns the current date in Brazil's timezone (America/Sao_Paulo = UTC-3).
    Using date.today() on a UTC server causes off-by-one errors for D- calculations
    after 21:00 UTC (18:00 BRT), because the server has already ticked to the next day.
    """
    return datetime.now(_TZ_BRAZIL).date()

_rolling_avg_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mkt_io")

_cadastro_cache: dict = {}

def invalidate_cadastro_caches(projeto_id: int):
    """Limpa caches relacionados a um cadastro de evento específico.
    Deve ser chamado sempre que atletas_site_pago ou outros campos críticos forem atualizados.
    """
    if projeto_id in _cadastro_cache:
        del _cadastro_cache[projeto_id]
    try:
        from ...core.cache import event_detail_cache, eventos_list_cache, curva_cache
        event_detail_cache.invalidate()
        eventos_list_cache.invalidate()
        curva_cache.invalidate()
    except Exception:
        pass

import threading as _threading
_warmup_daily_cache: dict = {}
_warmup_daily_cache_lock = _threading.Lock()
_warmup_thread_ids: set = set()
_warmup_thread_ids_lock = _threading.Lock()

def register_warmup_thread(thread_id: int):
    with _warmup_thread_ids_lock:
        _warmup_thread_ids.add(thread_id)

def unregister_warmup_thread(thread_id: int):
    with _warmup_thread_ids_lock:
        _warmup_thread_ids.discard(thread_id)

def _is_warmup_thread() -> bool:
    with _warmup_thread_ids_lock:
        return _threading.current_thread().ident in _warmup_thread_ids

def set_warmup_daily_cache(ativo_grouped: dict, magento_grouped: dict,
                           cat_ativo_grouped: Optional[dict] = None, cat_magento_grouped: Optional[dict] = None):
    with _warmup_daily_cache_lock:
        _warmup_daily_cache.clear()
        if ativo_grouped:
            _warmup_daily_cache["ativo"] = ativo_grouped
        if magento_grouped:
            _warmup_daily_cache["magento"] = magento_grouped
        if cat_ativo_grouped:
            _warmup_daily_cache["cat_ativo"] = cat_ativo_grouped
        if cat_magento_grouped:
            _warmup_daily_cache["cat_magento"] = cat_magento_grouped

def clear_warmup_daily_cache():
    with _warmup_daily_cache_lock:
        _warmup_daily_cache.clear()
    with _warmup_thread_ids_lock:
        _warmup_thread_ids.clear()


def _wq_sku_mappings_by_grupo(db: Session, grupo_nome: str, anos: list):
    if _is_warmup_thread():
        from app.core.cache import get_warmup_sku_mappings_by_grupo
        cached = get_warmup_sku_mappings_by_grupo(grupo_nome, anos)
        if cached is not None:
            return cached
    return db.query(SkuMapping).filter(
        SkuMapping.evento_grupo == grupo_nome,
        SkuMapping.ano.in_(anos),
        SkuMapping.ativo == True
    ).all()


def _wq_sku_mappings_by_grupo_single_year(db: Session, grupo_nome: str, ano: int):
    if _is_warmup_thread():
        from app.core.cache import get_warmup_sku_mappings_by_grupo
        cached = get_warmup_sku_mappings_by_grupo(grupo_nome, [ano])
        if cached is not None:
            return cached
    return db.query(SkuMapping).filter(
        SkuMapping.evento_grupo == grupo_nome,
        SkuMapping.ano == ano,
        SkuMapping.ativo == True
    ).all()


def _wq_sku_mappings_by_sku(db: Session, sku: str, anos: Optional[list] = None):
    if _is_warmup_thread():
        from app.core.cache import get_warmup_sku_mappings_by_sku
        cached = get_warmup_sku_mappings_by_sku(sku, anos)
        if cached is not None:
            return cached
    q = db.query(SkuMapping).filter(
        SkuMapping.sku == sku.upper().strip(),
        SkuMapping.ativo == True
    )
    if anos:
        q = q.filter(SkuMapping.ano.in_(anos))
    return q.all()


def _wq_sku_mappings_by_skus(db: Session, skus: list, anos: Optional[list] = None):
    if _is_warmup_thread():
        from app.core.cache import get_warmup_sku_mappings_by_sku
        result = []
        for s in skus:
            cached = get_warmup_sku_mappings_by_sku(s, anos)
            if cached is not None:
                result.extend(cached)
            else:
                return None
        return result
    q = db.query(SkuMapping).filter(
        SkuMapping.sku.in_([s.upper().strip() for s in skus]),
        SkuMapping.ativo == True
    )
    if anos:
        q = q.filter(SkuMapping.ano.in_(anos))
    return q.all()


def _wq_dim_projeto_by_id(db: Session, projeto_id: int):
    if _is_warmup_thread():
        from app.core.cache import get_warmup_dim_projeto_by_id
        cached = get_warmup_dim_projeto_by_id(projeto_id)
        if cached is not None:
            return cached
    return db.query(DimProjeto).filter(DimProjeto.id == projeto_id).first()


def _wq_dim_projetos_by_codigos(db: Session, codigos: list):
    if _is_warmup_thread():
        from app.core.cache import get_warmup_dim_projetos_by_codigos
        cached = get_warmup_dim_projetos_by_codigos(codigos)
        if cached is not None:
            return cached
    return db.query(DimProjeto).filter(DimProjeto.codigo.in_(codigos)).all() if codigos else []


def _wq_cadastro_by_projeto_id(db: Session, projeto_id: int):
    if _is_warmup_thread():
        from app.core.cache import get_warmup_cadastro_by_projeto_id
        cached = get_warmup_cadastro_by_projeto_id(projeto_id)
        if cached is not None:
            return cached
    return db.query(CadastroEvento).filter(CadastroEvento.projeto_id == projeto_id).first()


def _wq_all_dim_projetos(db: Session):
    if _is_warmup_thread():
        from app.core.cache import get_warmup_all_dim_projetos
        cached = get_warmup_all_dim_projetos()
        if cached is not None:
            return cached
    return db.query(DimProjeto).all()

def get_meta_orcada(db: Session, projeto_id: int) -> int:
    if projeto_id in _cadastro_cache:
        return _cadastro_cache[projeto_id]
    cadastro = _wq_cadastro_by_projeto_id(db, projeto_id)
    if cadastro and cadastro.atletas_site_pago and cadastro.atletas_site_pago > 0:
        _cadastro_cache[projeto_id] = int(cadastro.atletas_site_pago)
        return int(cadastro.atletas_site_pago)
    _cadastro_cache[projeto_id] = 0
    return 0

def get_meta_from_cadastro(cadastro: CadastroEvento) -> int:
    if cadastro.atletas_site_pago and cadastro.atletas_site_pago > 0:
        return int(cadastro.atletas_site_pago)
    return 0

def get_meta_orcada_projetos(db: Session, projetos: list) -> int:
    total = 0
    for p in projetos:
        total += get_meta_orcada(db, p.id)
    return total


def fetch_daily_sales_ativo(id_evento: str, start_date: date, end_date: date) -> dict:
    """
    Busca vendas diárias do Ativo para um evento específico dentro de um período.
    Retorna um dicionário {data: quantidade_vendida}
    """
    if db_module.engine_ssh is None:
        return {}
    
    try:
        query = text("""
        SELECT 
            DATE(c.dt_pedido) AS data_venda,
            COUNT(a.id_pedido_evento) AS quantidade
        FROM sa_pedido_evento AS a
        INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
        INNER JOIN sa_pedido AS c ON c.id_pedido = a.id_pedido
        WHERE 
            b.id_evento = :id_evento
            AND c.id_pedido_status IN (2)
            AND (b.id_campanha_salesforce IS NULL OR b.id_campanha_salesforce NOT LIKE '701d0000000%')
            AND DATE(c.dt_pedido) >= :start_date
            AND DATE(c.dt_pedido) <= :end_date
        GROUP BY DATE(c.dt_pedido)
        ORDER BY data_venda
        """)
        
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(query, {"id_evento": id_evento, "start_date": start_date.isoformat(), "end_date": end_date.isoformat()})
            rows = result.fetchall()
            
        daily_sales = {}
        for row in rows:
            data_venda = row[0]
            quantidade = row[1]
            if isinstance(data_venda, str):
                data_venda = datetime.strptime(data_venda, '%Y-%m-%d').date()
            daily_sales[data_venda] = quantidade
            
        return daily_sales
    except Exception as e:
        logger.error(f"Erro ao buscar vendas diárias do Ativo: {e}")
        return {}


def get_id_evento_from_projeto(db: Session, projeto_id: int) -> Optional[str]:
    projeto = _wq_dim_projeto_by_id(db, projeto_id)
    if not projeto or not projeto.codigo:
        return None
    
    sku = projeto.codigo.upper().strip()
    
    mappings = _wq_sku_mappings_by_sku(db, sku)
    for m in mappings:
        if m.fonte == 'ATIVO' and m.id_externo:
            return str(m.id_externo)
    return None


def _calculate_action_impact_from_warmup_cache(acao, projeto) -> dict:
    if not acao.data_acao or not projeto or not projeto.codigo:
        return {"vendas_antes": None, "vendas_depois": None, "impacto_percentual": None}

    data_acao = acao.data_acao
    if isinstance(data_acao, datetime):
        data_acao = data_acao.date()

    start_before = data_acao - timedelta(days=7)
    end_before = data_acao - timedelta(days=1)
    start_after = data_acao + timedelta(days=1)
    end_after = data_acao + timedelta(days=7)

    today = today_brazil()
    if end_after > today:
        return {"vendas_antes": None, "vendas_depois": None, "impacto_percentual": None,
                "status": "aguardando_dados"}

    sku = projeto.codigo.upper().strip()
    from app.core.cache import get_warmup_sku_mappings_by_sku
    all_sku_maps = get_warmup_sku_mappings_by_sku(sku)
    if not all_sku_maps:
        return {"vendas_antes": None, "vendas_depois": None, "impacto_percentual": None}

    ano = data_acao.year if isinstance(data_acao, date) else acao.data_acao.year if acao.data_acao else today_brazil().year
    sku_maps = [m for m in all_sku_maps if getattr(m, 'ano', None) == ano and getattr(m, 'ativo', False)]
    if not sku_maps:
        sku_maps = [m for m in all_sku_maps if getattr(m, 'ativo', False)]

    ativo_ids = [str(m.id_externo) for m in sku_maps if getattr(m, 'fonte', '') == 'ATIVO' and m.id_externo]
    magento_ids = [str(m.id_externo) for m in sku_maps if getattr(m, 'fonte', '') == 'MAGENTO' and m.id_externo]

    if not ativo_ids and not magento_ids:
        return {"vendas_antes": None, "vendas_depois": None, "impacto_percentual": None}

    all_daily = []
    if ativo_ids:
        all_daily.extend(_fetch_daily_sales_ativo_by_ids(ativo_ids))
    if magento_ids:
        all_daily.extend(_fetch_daily_sales_magento_by_ids(magento_ids))

    vendas_antes = 0
    vendas_depois = 0
    for row in all_daily:
        try:
            dia = date.fromisoformat(row["dia"]) if isinstance(row["dia"], str) else row["dia"]
        except (ValueError, KeyError):
            continue
        if start_before <= dia <= end_before:
            vendas_antes += row.get("qtd", 0)
        elif start_after <= dia <= end_after:
            vendas_depois += row.get("qtd", 0)

    if vendas_antes > 0:
        impacto_percentual = ((vendas_depois - vendas_antes) / vendas_antes) * 100
    elif vendas_depois > 0:
        impacto_percentual = 100.0
    else:
        impacto_percentual = 0.0

    return {
        "vendas_antes": vendas_antes,
        "vendas_depois": vendas_depois,
        "impacto_percentual": round(impacto_percentual, 1)
    }


def calculate_action_impact(db: Session, acao) -> dict:
    if not acao.data_acao:
        return {"vendas_antes": None, "vendas_depois": None, "impacto_percentual": None}

    projeto = _wq_dim_projeto_by_id(db, acao.projeto_id)
    if not projeto or not projeto.codigo:
        return {"vendas_antes": None, "vendas_depois": None, "impacto_percentual": None}

    if _is_warmup_thread():
        return _calculate_action_impact_from_warmup_cache(acao, projeto)

    sku = projeto.codigo.upper().strip()
    mappings = _wq_sku_mappings_by_sku(db, sku)
    if not mappings:
        return {"vendas_antes": None, "vendas_depois": None, "impacto_percentual": None}

    data_acao = acao.data_acao
    if isinstance(data_acao, datetime):
        data_acao = data_acao.date()

    start_before = data_acao - timedelta(days=7)
    end_before = data_acao - timedelta(days=1)
    start_after = data_acao + timedelta(days=1)
    end_after = data_acao + timedelta(days=7)

    today = today_brazil()
    if end_after > today:
        return {"vendas_antes": None, "vendas_depois": None, "impacto_percentual": None,
                "status": "aguardando_dados"}

    ano = data_acao.year
    sku_maps = [m for m in mappings if getattr(m, 'ano', None) == ano and getattr(m, 'ativo', False)]
    if not sku_maps:
        sku_maps = [m for m in mappings if getattr(m, 'ativo', False)]

    ativo_ids = [str(m.id_externo) for m in sku_maps if getattr(m, 'fonte', '') == 'ATIVO' and m.id_externo]
    magento_ids = [str(m.id_externo) for m in sku_maps if getattr(m, 'fonte', '') == 'MAGENTO' and m.id_externo]

    if not ativo_ids and not magento_ids:
        return {"vendas_antes": None, "vendas_depois": None, "impacto_percentual": None}

    all_daily = []
    if ativo_ids:
        all_daily.extend(_fetch_daily_sales_ativo_by_ids(ativo_ids))
    if magento_ids:
        _cort = _get_cortesia_magento_ids(db)
        _mag_cort = set(magento_ids) & _cort if _cort else None
        all_daily.extend(_fetch_daily_sales_magento_by_ids(magento_ids, cortesia_magento_ids=_mag_cort if _mag_cort else None))

    vendas_antes = 0
    vendas_depois = 0
    for row in all_daily:
        try:
            dia = date.fromisoformat(row["dia"]) if isinstance(row["dia"], str) else row["dia"]
        except (ValueError, KeyError):
            continue
        if start_before <= dia <= end_before:
            vendas_antes += row.get("qtd", 0)
        elif start_after <= dia <= end_after:
            vendas_depois += row.get("qtd", 0)

    if vendas_antes > 0:
        impacto_percentual = ((vendas_depois - vendas_antes) / vendas_antes) * 100
    elif vendas_depois > 0:
        impacto_percentual = 100.0
    else:
        impacto_percentual = 0.0

    return {
        "vendas_antes": vendas_antes,
        "vendas_depois": vendas_depois,
        "impacto_percentual": round(impacto_percentual, 1)
    }

_ticket_atual_cache: dict = {}
_ticket_atual_cache_ts: float = 0.0
_TICKET_ATUAL_TTL = 1800  # 30 minutos — tickets mudam com muito menos frequência que 2 min;
                           # TTL curto causava query Magento síncrona (~15s) a cada 2 min na lista ISC
_ticket_atual_cache_lock = _threading.Lock()

def clear_ticket_atual_cache():
    global _ticket_atual_cache_ts
    with _ticket_atual_cache_lock:
        _ticket_atual_cache.clear()
        _ticket_atual_cache_ts = 0.0

def _resolve_ticket_for_event(
    bundle_data: dict,
    basico_cfg,
    promo_principal_cfg,
    promo_configs: list,
    require_status_active: bool,
) -> Optional[dict]:
    """Aplica a regra de prioridade promo_principal → promo → básico para um evento.

    bundle_data deve mapear bundle_entity_id → {sp_base, status_kit, nome_kit}.
    Retorna {"value": float, "nome_kit": str} ou None.
    """
    # 1. Promo principal explícito
    if promo_principal_cfg:
        bd = bundle_data.get(promo_principal_cfg.bundle_entity_id)
        if bd and (bd.get("sp_base") or 0) > 0:
            return {
                "value": round(bd["sp_base"] * promo_principal_cfg.multiplicador, 2),
                "nome_kit": bd.get("nome_kit"),
            }

    # 2. Kit promo (fallback)
    # Ordem determinística: bundle mais NOVO primeiro (entity_id DESC). Eventos
    # acumulam kits promocionais de campanhas sucessivas (ex.: "R$ 50 OFF"
    # encerrada + "R$70 OFF" vigente); sem ordenação, a ordem arbitrária da
    # query decidia qual promo virava o Ticket Atual.
    _promos_sorted = sorted(
        promo_configs or [],
        key=lambda c: (c.bundle_entity_id or 0),
        reverse=True,
    )
    if require_status_active:
        # Duas passadas: primeiro só kits com status confirmado "ativo"; se
        # nenhum, aceita status DESCONHECIDO (leitura ao vivo indisponível e
        # sem snapshot de mapeamento). Kit explicitamente "inativo" nunca é
        # elegível — promoção encerrada não pode virar o Ticket Atual.
        _status_passes = (
            lambda st: st == "ativo",
            lambda st: not st,  # None/"" = desconhecido
        )
    else:
        _status_passes = (lambda st: True,)
    for _status_ok in _status_passes:
        for promo_cfg in _promos_sorted:
            bd = bundle_data.get(promo_cfg.bundle_entity_id)
            if not bd or not (bd.get("sp_base") or 0) > 0:
                continue
            if not _status_ok(bd.get("status_kit")):
                continue
            return {
                "value": round(bd["sp_base"] * promo_cfg.multiplicador, 2),
                "nome_kit": bd.get("nome_kit"),
            }

    # 3. Kit básico (fallback final)
    if basico_cfg:
        bd = bundle_data.get(basico_cfg.bundle_entity_id)
        if bd and (bd.get("sp_base") or 0) > 0:
            return {
                "value": round(bd["sp_base"] * basico_cfg.multiplicador, 2),
                "nome_kit": bd.get("nome_kit"),
            }

    return None


def _bucket_configs_by_evento(configs):
    """Separa configs em básico, promo_principal e promo (heurística por tipo_kit)."""
    basico_by_evento: dict = {}
    promo_principal_by_evento: dict = {}
    promo_by_evento: dict = {}
    for cfg in configs:
        evt_key = str(cfg.id_evento)
        if cfg.is_kit_basico:
            basico_by_evento[evt_key] = cfg
        if getattr(cfg, "is_promo_principal", False):
            promo_principal_by_evento[evt_key] = cfg
        elif cfg.tipo_kit and "promo" in cfg.tipo_kit.lower():
            promo_by_evento.setdefault(evt_key, []).append(cfg)
    return basico_by_evento, promo_principal_by_evento, promo_by_evento


def _fetch_ticket_atual_map(db: Session) -> dict:
    from ...models.kit_config import KitConfig
    from ...models.cadastro_evento import CadastroEvento, CadastroKitProduto
    from ..routes.kit_config import (
        _fetch_magento_kits_cached,
        fetch_ativo_kits_indexed,
        _normalize_kit_name,
    )

    all_configs = db.query(KitConfig).filter(
        KitConfig.id_evento.isnot(None),
        KitConfig.ignorado == False,
    ).all()
    if not all_configs:
        return {}

    # Não processar eventos já CONCLUÍDOS (congelados): o ticket de um evento
    # finalizado não muda mais, então re-resolvê-lo a cada 30 min (incl. os
    # fetches de kits do Ativo por config) só desperdiça trabalho e alonga a
    # fila do slot único do Magento que trava as requests interativas.
    # Conservador: kits sem cadastro/sem data continuam sendo processados
    # (não dá pra classificar como concluído sem a data).
    try:
        from ...services.snapshot_service import (
            _load_data_evento_by_magento_id,
            is_event_frozen,
        )
        _mag_ids = {c.id_evento for c in all_configs if c.id_evento is not None}
        _dt_map = _load_data_evento_by_magento_id(db, _mag_ids)
        _before_n = len(all_configs)
        all_configs = [
            c for c in all_configs
            if not is_event_frozen(_dt_map.get(str(c.id_evento)))
        ]
        _skipped_frozen = _before_n - len(all_configs)
        if _skipped_frozen:
            logger.info(
                f"[ticket_atual] {_skipped_frozen} kit(s) de eventos concluídos "
                f"pulados (sem processamento/consulta)"
            )
        if not all_configs:
            return {}
    except Exception as _fe:
        logger.warning(
            f"[ticket_atual] filtro de freeze falhou (conservador: processa tudo): {_fe}"
        )

    # Synthetic bundle (negativo) = evento Ativo-only. Magento = positivo.
    magento_configs = [c for c in all_configs if c.bundle_entity_id is not None and c.bundle_entity_id >= 0]
    ativo_configs = [c for c in all_configs if c.bundle_entity_id is not None and c.bundle_entity_id < 0]

    # ───────────────────────── MAGENTO ─────────────────────────
    magento_projeto_tickets: dict = {}
    if magento_configs and db_module.engine_magento is not None:
        try:
            rows, columns = _fetch_magento_kits_cached(label="ticket_atual")
        except Exception as e:
            logger.error(f"Erro ao buscar ticket_atual do Magento: {e}")
            rows, columns = [], []

        bundle_data: dict = {}
        for row in rows:
            row_dict = dict(zip(columns, row))
            bundle_id = int(row_dict["bundle_entity_id"])
            # Prioridade para ticket ISC:
            # 0. pi_pai_min_price = min_price do índice do bundle pai (catalog_product_index_price)
            #    — fonte mais autoritativa, reflete price rules ativas do Magento. Quando
            #    disponível, usada DIRETAMENTE sem passar pelo filtro >= price (Regra B),
            #    pois o índice pode legitimamente ter min_price > soma de componentes EAV
            #    (ex.: Troféu Brasil 2ª Etapa: índice=1299,99; componentes EAV=999,99).
            # 1. special_price = COALESCE(pi_pai.min_price, fallback soma componentes)
            #    — coincide com pi_pai_min_price quando o bundle está no índice.
            # 2. current_price = lote corrente (MAX record_id) — fallback se special_price ausente.
            # 3. price = soma dos componentes (atributo 77) — último recurso.
            pi_pai_min_price_val = float(row_dict["pi_pai_min_price"]) if row_dict.get("pi_pai_min_price") is not None else None
            special_price_val = float(row_dict["special_price"]) if row_dict.get("special_price") is not None else None
            current_price_val = float(row_dict["current_price"]) if row_dict.get("current_price") is not None else None
            price_val = float(row_dict["price"]) if row_dict.get("price") is not None else None

            if pi_pai_min_price_val and pi_pai_min_price_val > 0:
                # Índice autoritativo — não aplica Regra B (>= price).
                sp_base = pi_pai_min_price_val
            else:
                # Regra B (mai/2026): se special_price/current_price >= price,
                # não é uma promoção real — o fallback SQL traz MIN(lot_value) / lote corrente
                # >= preço do componente EAV, indicando lot_value fantasma maior que o ticket real.
                # Descarta ambos para não inflar o ticket atual.
                # Sem isso, kits como "Night Run João Pessoa Kit Básico" mostravam ticket de
                # R$ 129,99 (lot_value fantasma) em vez de R$ 99,99 (preço real do componente).
                if price_val is not None and price_val > 0:
                    if special_price_val is not None and special_price_val >= price_val:
                        special_price_val = None
                    if current_price_val is not None and current_price_val >= price_val:
                        current_price_val = None
                sp_base = (
                    special_price_val if (special_price_val is not None and special_price_val > 0)
                    else current_price_val if (current_price_val is not None and current_price_val > 0)
                    else price_val if (price_val is not None and price_val > 0)
                    else None
                )
            bundle_data[bundle_id] = {
                "sp_base": sp_base,
                "status_kit": row_dict.get("status_kit"),
                "nome_kit": row_dict.get("nome_kit"),
            }

        # Fallback para bundles com sp_base ausente/nulo (Magento fora do ar ou
        # kit sem preço/índice). Duas fontes persistidas, na ordem:
        #   1. kit_mapping_snapshot — preço E status reais do último sync do
        #      Mapeamento de Kits (mesma prioridade do caminho ao vivo:
        #      pi_pai_min_price direto; senão special_price com Regra B; senão price).
        #   2. MargemBundleRevSnapshot — estimativa receita_liquida/qtd (job 4h),
        #      último recurso quando nem o mapeamento tem preço.
        # IMPORTANTE: nunca fabricar status "ativo". Um kit DESATIVADO no Magento
        # (ex.: promo antiga "R$ 50 OFF") não pode voltar a ser elegível como
        # Ticket Atual só porque a leitura ao vivo falhou — era exatamente isso
        # que fazia o ticket regredir para o preço médio da promoção encerrada.
        try:
            from ...models.vendas_snapshot import MargemBundleRevSnapshot as _MBRS
            from ...models.kit_mapping_snapshot import KitMappingSnapshot as _KMS
            # Bundles que precisam de fallback: ausentes em bundle_data OU sp_base None
            all_bundle_ids = [
                c.bundle_entity_id for c in magento_configs
                if c.bundle_entity_id is not None and c.bundle_entity_id >= 0
            ]
            missing_ids = [
                bid for bid in all_bundle_ids
                if bid not in bundle_data
                or bundle_data[bid].get("sp_base") is None
                or bundle_data[bid].get("sp_base") <= 0
            ]
            if missing_ids:
                kms_by_bid: dict = {}
                try:
                    _kms_rows = (
                        db.query(_KMS)
                        .filter(_KMS.bundle_entity_id.in_(missing_ids))
                        .order_by(_KMS.bundle_entity_id, _KMS.atualizado_em.desc())
                        .all()
                    )
                    for _kr in _kms_rows:
                        kms_by_bid.setdefault(_kr.bundle_entity_id, _kr)
                except Exception as _kms_e:
                    logger.warning(f"[ticket_atual] leitura kit_mapping_snapshot falhou: {_kms_e}")

                est_by_bid: dict = {}
                snap_rows = db.query(_MBRS).filter(_MBRS.bundle_entity_id.in_(missing_ids)).all()
                for sr in snap_rows:
                    if sr.qtd_inscricoes and sr.qtd_inscricoes > 0 and sr.receita_liquida:
                        est_by_bid[sr.bundle_entity_id] = round(
                            float(sr.receita_liquida) / int(sr.qtd_inscricoes), 2
                        )

                filled = 0
                for bid in missing_ids:
                    _kms = kms_by_bid.get(bid)
                    sp_base = None
                    if _kms is not None:
                        _pi = float(_kms.pi_pai_min_price) if _kms.pi_pai_min_price is not None else None
                        _sp = float(_kms.special_price) if _kms.special_price is not None else None
                        _pr = float(_kms.price) if _kms.price is not None else None
                        if _pi and _pi > 0:
                            sp_base = _pi  # índice autoritativo — sem Regra B
                        else:
                            if _pr is not None and _pr > 0 and _sp is not None and _sp >= _pr:
                                _sp = None  # Regra B: lote fantasma >= componente
                            sp_base = (
                                _sp if (_sp is not None and _sp > 0)
                                else _pr if (_pr is not None and _pr > 0)
                                else None
                            )
                    _fonte_fb = "kit_mapping_snapshot"
                    if sp_base is None or sp_base <= 0:
                        sp_base = est_by_bid.get(bid)
                        _fonte_fb = "snapshot"
                    if sp_base is None or sp_base <= 0:
                        continue
                    existing = bundle_data.get(bid, {})
                    _status_fb = existing.get("status_kit") or (
                        (_kms.status_kit or None) if _kms is not None else None
                    )
                    bundle_data[bid] = {
                        "sp_base": sp_base,
                        "status_kit": _status_fb,
                        "nome_kit": existing.get("nome_kit") or (
                            _kms.nome_kit if _kms is not None else None
                        ),
                        "fonte": _fonte_fb,
                    }
                    filled += 1
                if filled:
                    logger.warning(
                        f"[ticket_atual] {filled} bundle(s) sem preço no Magento — "
                        f"usando snapshots persistidos (mapeamento de kits / receita 4h) como fallback"
                    )
        except Exception as _fb_e:
            logger.warning(f"[ticket_atual] Fallback snapshot falhou: {_fb_e}")

        basico_by_evento, promo_principal_by_evento, promo_by_evento = _bucket_configs_by_evento(magento_configs)
        evento_tickets: dict = {}
        all_evt_keys = set(basico_by_evento) | set(promo_principal_by_evento) | set(promo_by_evento)

        for evt_key in all_evt_keys:
            ticket = _resolve_ticket_for_event(
                bundle_data,
                basico_by_evento.get(evt_key),
                promo_principal_by_evento.get(evt_key),
                promo_by_evento.get(evt_key, []),
                require_status_active=True,
            )
            if ticket is not None:
                evento_tickets[evt_key] = ticket

        # Diagnóstico: Básico configurado mas sem preço resolvido
        for evt_key, cfg in basico_by_evento.items():
            if evt_key not in evento_tickets:
                bd = bundle_data.get(cfg.bundle_entity_id, {})
                sp = bd.get("sp_base")
                promo_p = promo_principal_by_evento.get(evt_key)
                promo_list = promo_by_evento.get(evt_key, [])
                logger.warning(
                    f"[ticket_atual] Básico sem preço: bundle={cfg.bundle_entity_id}, "
                    f"id_evento={evt_key}, sp_base={sp}, "
                    f"status={bd.get('status_kit')}, fonte={bd.get('fonte', 'magento')}, "
                    f"promo_principal={promo_p.bundle_entity_id if promo_p else None}, "
                    f"promos={[p.bundle_entity_id for p in promo_list]}"
                )

        if evento_tickets:
            magento_evt_ids = [int(k) for k in evento_tickets if k.isdigit()]

            # Caminho primário: id_evento → CadastroEvento.id_evento_magento → projeto_id (2 hops)
            already_mapped: set = set()
            try:
                cad_direct = db.query(
                    CadastroEvento.id_evento_magento,
                    CadastroEvento.projeto_id,
                ).filter(
                    CadastroEvento.id_evento_magento.in_(magento_evt_ids),
                    CadastroEvento.projeto_id.isnot(None),
                ).all()
                for cad in cad_direct:
                    evt_key = str(cad.id_evento_magento)
                    ticket_data = evento_tickets.get(evt_key)
                    if ticket_data and cad.projeto_id:
                        magento_projeto_tickets[cad.projeto_id] = ticket_data
                        already_mapped.add(evt_key)
            except Exception as _e:
                logger.warning(f"[ticket_atual] Erro no path direto CadastroEvento: {_e}")

            # Caminho fallback: SkuMapping (4 hops) para eventos sem CadastroEvento.id_evento_magento
            remaining_ids = [eid for eid in magento_evt_ids if str(eid) not in already_mapped]
            if remaining_ids:
                magento_sms = db.query(SkuMapping.sku, SkuMapping.id_externo).filter(
                    SkuMapping.fonte == 'MAGENTO',
                    SkuMapping.ativo == True,
                    SkuMapping.id_externo.in_(remaining_ids),
                ).all()
                evt_id_to_sku = {str(sm.id_externo): sm.sku for sm in magento_sms}
                matched_skus = list(evt_id_to_sku.values())
                if matched_skus:
                    cad_rows = db.query(CadastroEvento.projeto_id, CadastroEvento.sku).filter(
                        CadastroEvento.sku.in_(matched_skus),
                        CadastroEvento.projeto_id.isnot(None),
                    ).all()
                    sku_to_projeto = {c.sku: c.projeto_id for c in cad_rows}
                    for rid in remaining_ids:
                        evt_key = str(rid)
                        ticket_data = evento_tickets.get(evt_key)
                        if not ticket_data:
                            continue
                        sku = evt_id_to_sku.get(evt_key)
                        if not sku:
                            continue
                        pid = sku_to_projeto.get(sku)
                        if pid:
                            magento_projeto_tickets[pid] = ticket_data

    # ───────────────────────── ATIVO (somente eventos não-Magento) ─────────────────────────
    # Synthetic bundle_entity_id = -kp.id; cfg.id_evento aqui é o id do
    # evento no Ativo. Cobertura intencional: eventos que existem no banco
    # do Ativo e NÃO têm kit equivalente no Magento. Quando o mesmo projeto
    # já tem ticket vindo do Magento, o Magento prevalece.
    ativo_projeto_tickets: dict = {}
    if ativo_configs:
        kp_ids = [-c.bundle_entity_id for c in ativo_configs]
        kps = db.query(CadastroKitProduto).filter(CadastroKitProduto.id.in_(kp_ids)).all()
        kp_by_id = {kp.id: kp for kp in kps}
        cadastro_ids = list({kp.cadastro_id for kp in kps if kp.cadastro_id})
        cads = db.query(
            CadastroEvento.id, CadastroEvento.projeto_id, CadastroEvento.ano_evento
        ).filter(CadastroEvento.id.in_(cadastro_ids)).all() if cadastro_ids else []
        cadastro_to_projeto = {c.id: c.projeto_id for c in cads if c.projeto_id}

        ativo_kits_index = fetch_ativo_kits_indexed()  # marketing usa só o índice — não precisa do flag

        # bundle_data sintético para reusar _resolve_ticket_for_event.
        # Para Ativo não temos status_kit, então tratamos como sempre 'ativo'.
        bundle_data_ativo: dict = {}
        for cfg in ativo_configs:
            kp = kp_by_id.get(-cfg.bundle_entity_id)
            if not kp:
                continue
            try:
                evt_id_int = int(cfg.id_evento) if cfg.id_evento is not None else None
            except (TypeError, ValueError):
                evt_id_int = None
            if evt_id_int is None:
                continue
            variants = ativo_kits_index.get((evt_id_int, _normalize_kit_name(kp.kit)), [])
            if not variants:
                continue
            # Múltiplas categorias (combo): pega o menor special_price (= mais
            # barato do lote vigente), espelhando o ORDER BY ASC da query.
            sp_values = [
                v["special_price"] if v.get("special_price") is not None else v.get("price")
                for v in variants
            ]
            sp_values = [v for v in sp_values if v is not None]
            if not sp_values:
                continue
            bundle_data_ativo[cfg.bundle_entity_id] = {
                "sp_base": min(sp_values),
                "status_kit": "ativo",
                "nome_kit": kp.kit,
            }

        basico_a, promo_principal_a, promo_a = _bucket_configs_by_evento(ativo_configs)
        evento_tickets_ativo: dict = {}
        all_evt_keys_a = set(basico_a) | set(promo_principal_a) | set(promo_a)
        for evt_key in all_evt_keys_a:
            ticket = _resolve_ticket_for_event(
                bundle_data_ativo,
                basico_a.get(evt_key),
                promo_principal_a.get(evt_key),
                promo_a.get(evt_key, []),
                require_status_active=False,
            )
            if ticket is not None:
                evento_tickets_ativo[evt_key] = ticket

        # Mapeia evt_key (id_evento Ativo) → projeto_id via cfg → kp → cadastro.
        # Aplica precedência Magento: pula se o projeto já tem ticket do Magento.
        cfg_by_evt_key: dict = {}
        for cfg in ativo_configs:
            cfg_by_evt_key.setdefault(str(cfg.id_evento), []).append(cfg)

        for evt_key, ticket_data in evento_tickets_ativo.items():
            for cfg in cfg_by_evt_key.get(evt_key, []):
                kp = kp_by_id.get(-cfg.bundle_entity_id)
                if not kp:
                    continue
                pid = cadastro_to_projeto.get(kp.cadastro_id)
                if not pid:
                    continue
                if pid in magento_projeto_tickets:
                    # Magento prevalece — evento existe nas duas bases.
                    continue
                ativo_projeto_tickets[pid] = ticket_data
                break

    # Magento sobrescreve Ativo (defensivo; no caminho acima Ativo já
    # foi filtrado para não tocar projetos com ticket Magento).
    return {**ativo_projeto_tickets, **magento_projeto_tickets}




def _get_ticket_atual_map(db: Session) -> dict:
    global _ticket_atual_cache_ts
    now = _time.time()
    with _ticket_atual_cache_lock:
        if _ticket_atual_cache and (now - _ticket_atual_cache_ts) < _TICKET_ATUAL_TTL:
            return dict(_ticket_atual_cache)

    result = _fetch_ticket_atual_map(db)

    with _ticket_atual_cache_lock:
        if result:
            # Merge inteligente: preserva entradas do cache antigo que NÃO vieram
            # no fetch atual. Cobre o caso em que o Magento devolve bundle_data
            # parcial (alguns kits inativos/sem preço ficam de fora do result),
            # evitando que o ticket de um evento suma após TTL mesmo que estivesse
            # correto antes. Entradas novas/atualizadas do fetch sobrescrevem o stale.
            stale_keys_kept = 0
            if _ticket_atual_cache:
                merged = dict(_ticket_atual_cache)   # começa com valores antigos
                merged.update(result)                # novos sobrescrevem
                stale_keys_kept = len(merged) - len(result)
                if stale_keys_kept > 0:
                    logger.debug(
                        f"[ticket_atual] Merge: {len(result)} novos + "
                        f"{stale_keys_kept} preservados do cache anterior"
                    )
                _ticket_atual_cache.clear()
                _ticket_atual_cache.update(merged)
            else:
                _ticket_atual_cache.update(result)
            _ticket_atual_cache_ts = _time.time()
        else:
            # Fetch retornou vazio (Magento + snapshot indisponíveis): preserva cache
            # anterior por completo para não mostrar "Não encontrado".
            if not _ticket_atual_cache:
                # Cache também vazio (primeiro acesso após restart com Magento indisponível).
                # Usa TTL de retry curto (10s) para tentar de novo em breve,
                # evitando que event details sejam computados e persistidos com ticketAtual=None
                # por até 120s após o Magento voltar.
                _ticket_atual_cache_ts = _time.time() - (_TICKET_ATUAL_TTL - 10)
                logger.warning("[ticket_atual] Fetch vazio com cache vazio — retry em 10s")
            else:
                logger.warning(
                    "[ticket_atual] Fetch retornou vazio — "
                    f"mantendo cache anterior com {len(_ticket_atual_cache)} entradas (stale-on-error)"
                )

    return result if result else dict(_ticket_atual_cache)


def _get_ticket_atual_for_event(ticket_map: dict, projeto_ids) -> float:
    if not ticket_map:
        return 0.0

    if not isinstance(projeto_ids, list):
        projeto_ids = [projeto_ids] if projeto_ids is not None else []

    for pid in projeto_ids:
        if pid is not None and pid in ticket_map:
            val = ticket_map[pid]
            if isinstance(val, dict):
                return val.get("value", 0.0) or 0.0
            return float(val) if val is not None else 0.0

    return 0.0


def _get_ticket_atual_kit_nome_for_event(ticket_map: dict, projeto_ids) -> Optional[str]:
    if not ticket_map:
        return None

    if not isinstance(projeto_ids, list):
        projeto_ids = [projeto_ids] if projeto_ids is not None else []

    for pid in projeto_ids:
        if pid is not None and pid in ticket_map:
            val = ticket_map[pid]
            if isinstance(val, dict):
                return val.get("nome_kit")
            return None

    return None


def _get_faixas_preco_site_for_projeto_ids(db: Session, projeto_ids: list) -> dict:
    """Returns faixas_preco_site aggregated across all cadastros for the given project IDs."""
    if not projeto_ids:
        return {"kit_basico": [], "kit_participacao": []}
    cadastros = db.query(CadastroEvento.id).filter(CadastroEvento.projeto_id.in_(projeto_ids)).all()
    cadastro_ids = [c.id for c in cadastros]
    if not cadastro_ids:
        return {"kit_basico": [], "kit_participacao": []}
    faixas = db.query(CadastroFaixaPrecoSite).filter(
        CadastroFaixaPrecoSite.cadastro_id.in_(cadastro_ids)
    ).order_by(CadastroFaixaPrecoSite.faixa).all()
    kit_basico = [
        {"faixa": f.faixa, "qtd": f.qtd or 0, "tkt_medio": float(f.tkt_medio or 0), "total": float(f.total or 0)}
        for f in faixas if f.tipo_kit == "kit_basico" and (f.qtd or 0) > 0
    ]
    kit_participacao = [
        {"faixa": f.faixa, "qtd": f.qtd or 0, "tkt_medio": float(f.tkt_medio or 0), "total": float(f.total or 0)}
        for f in faixas if f.tipo_kit == "kit_participacao" and (f.qtd or 0) > 0
    ]
    return {"kit_basico": kit_basico, "kit_participacao": kit_participacao}


router = APIRouter(prefix="/marketing", tags=["Marketing ISC"])

class ISCComponents(BaseModel):
    ia730: float
    curvaDPercent: float
    rolling14d: float
    tipoCurva: str = "linear"
    fonteCurva: Optional[str] = None
    anoReferencia: Optional[int] = None

class CommercialAction(BaseModel):
    id: str
    date: str
    type: str
    description: str
    impact: Optional[str] = None

class ActiveActionInfo(BaseModel):
    id: int
    tipo: str
    descricao: str
    data_acao: str
    dias_restantes: int

class PlaybookEntry(BaseModel):
    letter: str
    name: str
    stage: str
    stageName: str
    iscLabel: str
    iscState: Optional[str] = None
    objective: str
    narrative: str
    actions: List[str]
    kpis: List[str]
    cutoffs: List[str]

class MarketingEvent(BaseModel):
    id: str
    name: str
    date: str
    location: str
    category: str
    totalCapacity: int
    currentSales: int
    salesGoal: int
    averageTicket: float
    budgetTicket: float = 0.0
    dMinus: int
    dMinusInscricoes: int
    isc: float
    iscRaw: Optional[float] = None
    iscComponents: ISCComponents
    iscComponentsRaw: Optional[ISCComponents] = None
    iscComponentsNormalized: Optional[ISCComponents] = None
    iscStatus: str
    suggestedAction: PlaybookEntry
    lastAction: Optional[CommercialAction] = None
    activeAction: Optional[ActiveActionInfo] = None
    isActive: bool
    sku: Optional[str] = None
    kitCostPerUnit: float = 0.0
    receitaOrcadaTotal: float = 0.0
    currentReceita: float = 0.0
    margemOrcadaUnit: float = 0.0
    margemOrcadaTotal: float = 0.0
    margemOrcadaPct: float = 0.0
    margemRealizadaUnit: float = 0.0
    margemRealizadaTotal: float = 0.0
    margemRealizadaKitsTotal: Optional[float] = None
    margemRealizadaPct: float = 0.0
    margemRealizacaoRate: float = 0.0
    ticketAtual: float = 0.0
    ticketKitNome: Optional[str] = None
    margemPorKit: Optional[List[dict]] = None
    margemAvisos: Optional[List[str]] = None
    consistencyWarning: Optional[dict] = None
    detalheVendasPorKit: Optional[List[dict]] = None
    detalheVendasAtivoKit: Optional[List[dict]] = None
    kitQueryFailed: bool = False
    dataRegime: Optional[str] = None
    incluirCortesias: bool = False

class DashboardSummary(BaseModel):
    totalActiveEvents: int
    eventsGreen: int
    eventsYellow: int
    eventsRed: int

class MarketingEventsResponse(BaseModel):
    status: str
    eventos: List[MarketingEvent]
    resumo: DashboardSummary
    categorias: List[str]
    ultima_atualizacao: str
    avisos: List[str] = []

_isc_settings_cache: dict = {"value": None, "ts": 0}
_ISC_SETTINGS_TTL = 60

_DEFAULT_ISC_SETTINGS = {
    "ia730Weight": 20.0,
    "curvaDWeight": 40.0,
    "rolling14dWeight": 40.0,
    "greenThreshold": 1.10,
    "yellowThreshold": 0.90,
    "criticalWindowStart": 45,
    "criticalWindowEnd": 40,
    "promotionDeadline": 40,
    "useNormalizedCurveForISC": False,
}

def _get_isc_settings(db: Session) -> dict:
    import time
    now = time.time()
    if _isc_settings_cache["value"] is not None and (now - _isc_settings_cache["ts"]) < _ISC_SETTINGS_TTL:
        return _isc_settings_cache["value"]
    try:
        setting = db.query(MarketingSettings).filter(MarketingSettings.key == "isc_parameters").first()
        if setting and setting.value:
            merged = {**_DEFAULT_ISC_SETTINGS, **setting.value}
            _isc_settings_cache["value"] = merged
            _isc_settings_cache["ts"] = now
            return merged
    except Exception as exc:
        # Fix B1: não silenciar — incidente em ISC settings afeta o cálculo
        # do indicador de saúde comercial e precisa ser visível em logs.
        logger.warning(
            f"[ISC] _get_isc_settings: falha ao ler MarketingSettings, "
            f"usando defaults (ISC pode estar com pesos desatualizados): {exc}"
        )
    _isc_settings_cache["value"] = _DEFAULT_ISC_SETTINGS
    _isc_settings_cache["ts"] = now
    return _DEFAULT_ISC_SETTINGS

def get_isc_status(isc: float, green_threshold: float = 1.10, yellow_threshold: float = 0.90) -> str:
    if isc > green_threshold:
        return "accelerating"
    if isc >= yellow_threshold:
        return "stable"
    return "decelerating"

_PLAYBOOK: dict = {
    # (stage_key, isc_key) -> PlaybookEntry dict
    ("analitico", "forte"): {
        "letter": "A1", "name": "Subida Micro / Âncora de Valor",
        "stage": "analitico", "stageName": "D-90 → D-50 | Analítico",
        "iscLabel": "ISC Forte (>1,12)",
        "objective": "Fixar percepção de valor cedo sem gerar rejeição.",
        "narrative": "\"Quem se antecipa, vive a experiência completa.\"",
        "actions": ["Subir +R$2 a +R$3", "Conteúdo de experiência (vibe, percurso)", "Prova social leve e orgânica", "Zero urgência / zero cupom"],
        "kpis": ["Rolling 14 estável ou crescente"],
        "cutoffs": ["D-65", "D-50"],
    },
    ("analitico", "estavel"): {
        "letter": "A2", "name": "Consolidação de Narrativa",
        "stage": "analitico", "stageName": "D-90 → D-50 | Analítico",
        "iscLabel": "ISC Estável (0,90–1,12)",
        "objective": "Construir desejo antes de mexer em preço.",
        "narrative": "\"Esse é o evento que representa a cidade / comunidade.\"",
        "actions": ["Conteúdo de cultura, percurso e pertencimento", "Ativação com assessorias", "Presença consistente nos canais"],
        "kpis": ["IA 7/30 > 1,00"],
        "cutoffs": ["D-65", "D-50"],
    },
    ("analitico", "fraco"): {
        "letter": "A3", "name": "Socorro Precoce (sem desconto público)",
        "stage": "analitico", "stageName": "D-90 → D-50 | Analítico",
        "iscLabel": "ISC Fraco (<0,90)",
        "objective": "Reativar demanda sem educar o público a esperar desconto.",
        "narrative": "\"Você faz parte desse movimento.\"",
        "actions": ["Ativação com grupos / assessorias locais", "Embaixadores reais", "Incentivo privado (CRM / grupos)"],
        "kpis": ["IA 7/30 reage (>1,00)"],
        "cutoffs": ["D-65", "D-50"],
    },
    ("estrategico", "forte"): {
        "letter": "E1", "name": "Confirmação de Valor / Escala Moderada",
        "stage": "estrategico", "stageName": "D-50 → D-32 | Estratégico",
        "iscLabel": "ISC Forte (>1,12)",
        "objective": "Consolidar evento como premium e preparar rentabilização.",
        "narrative": "\"Esse é o evento referência. Quem corre, corre aqui.\"",
        "actions": ["Subir +R$4 a +R$8", "Prova social forte (vídeo, depoimentos)", "Amplificação com assessorias"],
        "kpis": ["Rolling 14 mantém ou sobe"],
        "cutoffs": ["D-45", "D-35"],
    },
    ("estrategico", "estavel"): {
        "letter": "E2", "name": "Ajuste Fino (sem preço)",
        "stage": "estrategico", "stageName": "D-50 → D-32 | Estratégico",
        "iscLabel": "ISC Estável (0,90–1,12)",
        "objective": "Melhorar conversão antes de mexer no preço.",
        "narrative": "\"Você está no momento certo para decidir.\"",
        "actions": ["Ajuste de mídia (segmentação)", "Otimização de copy e criativos", "Melhorias no site / checkout"],
        "kpis": ["IA 7/30 > 1,05"],
        "cutoffs": ["D-45", "D-35"],
    },
    ("estrategico", "fraco"): {
        "letter": "E3", "name": "Promoção Privada Controlada (última janela)",
        "stage": "estrategico", "stageName": "D-50 → D-32 | Estratégico",
        "iscLabel": "ISC Fraco (<0,90)",
        "objective": "Destravar vendas rápido sem quebrar percepção de valor.",
        "narrative": "\"Condição especial para quem está próximo do movimento.\"",
        "actions": ["Cupom privado (CRM / grupos / assessorias)", "Janela curta (24–72h)", "Nunca público", "Execução preferencial entre D-45 e D-40"],
        "kpis": ["IA 7/30 sobe forte em 48h"],
        "cutoffs": ["D-45", "D-35"],
    },
    ("operacional", "forte"): {
        "letter": "O1", "name": "Rentabilização Máxima",
        "stage": "operacional", "stageName": "D-32 → D-0 | Operacional",
        "iscLabel": "ISC Forte (>1,12)",
        "objective": "Maximizar margem (inclusive acima da meta).",
        "narrative": "\"Últimas vagas. Quem decidiu, já garantiu.\"",
        "actions": ["Subir +R$8 até +R$20", "Comunicação de escassez real", "Urgência legítima"],
        "kpis": ["Ticket Atual sobe sem queda relevante de volume"],
        "cutoffs": ["D-30", "D-15"],
    },
    ("operacional", "estavel"): {
        "letter": "O2", "name": "Conversão Final",
        "stage": "operacional", "stageName": "D-32 → D-0 | Operacional",
        "iscLabel": "ISC Estável (0,90–1,12)",
        "objective": "Converter indecisos sem distorcer preço.",
        "narrative": "\"Ainda dá tempo. Esse é o momento.\"",
        "actions": ["Remarketing forte", "Melhorias de conversão (checkout)", "Bundles (kit premium, experiência)"],
        "kpis": ["Taxa de conversão sobe"],
        "cutoffs": ["D-30", "D-15"],
    },
    ("operacional", "fraco"): {
        "letter": "O3", "name": "Giro Final Controlado (sem desconto aberto)",
        "stage": "operacional", "stageName": "D-32 → D-0 | Operacional",
        "iscLabel": "ISC Fraco (<0,90)",
        "objective": "Fechar volume sem destruir posicionamento.",
        "narrative": "\"Seu grupo estará lá. Não fique de fora.\"",
        "actions": ["Ação com grupos / empresas / assessorias", "Incentivos direcionados (não públicos)", "Foco em pertencimento"],
        "kpis": ["Volume sobe sem colapsar Ticket Atual"],
        "cutoffs": ["D-30", "D-15"],
    },
}

def get_suggested_action(isc: float, d_minus: int, green_threshold: float = 1.10, yellow_threshold: float = 0.90, promotion_deadline: int = 40) -> dict:
    status = get_isc_status(isc, green_threshold, yellow_threshold)
    
    if d_minus >= 50:
        stage_key = "analitico"
    elif d_minus >= 32:
        stage_key = "estrategico"
    else:
        stage_key = "operacional"

    if status == "accelerating":
        isc_key = "forte"
    elif status == "stable":
        isc_key = "estavel"
    else:
        isc_key = "fraco"

    entry = dict(_PLAYBOOK[(stage_key, isc_key)])
    # iscState is used by the frontend for color-coding; "estável" uses accent to match TS type
    entry["iscState"] = "forte" if isc_key == "forte" else ("estável" if isc_key == "estavel" else "fraco")
    return entry

def get_active_actions_for_projects(db: Session, projeto_ids: list) -> dict:
    """
    Retorna ações comerciais ativas (criadas nos últimos 7 dias) para uma lista de projeto_ids.
    Retorna um dict {projeto_id: ActiveActionInfo}
    """
    from ...models.dimensoes import AcaoComercial
    if not projeto_ids:
        return {}
    
    today = today_brazil()
    cutoff = today - timedelta(days=7)
    
    acoes = db.query(AcaoComercial).filter(
        AcaoComercial.projeto_id.in_(projeto_ids),
        AcaoComercial.data_acao >= cutoff
    ).order_by(AcaoComercial.data_acao.desc()).all()
    
    result = {}
    for a in acoes:
        if a.projeto_id not in result:
            data_acao = a.data_acao
            if isinstance(data_acao, datetime):
                data_acao = data_acao.date()
            dias_restantes = max(0, 7 - (today - data_acao).days)
            result[a.projeto_id] = ActiveActionInfo(
                id=a.id,
                tipo=a.tipo,
                descricao=a.descricao,
                data_acao=data_acao.isoformat(),
                dias_restantes=dias_restantes
            )
    return result


def check_duplicate_action(db: Session, projeto_id: int, tipo: str) -> dict:
    """
    Verifica se já existe uma ação do mesmo tipo para o projeto nos últimos 7 dias.
    Retorna None se não há duplicata, ou um dict com info da ação existente.
    """
    from ...models.dimensoes import AcaoComercial
    
    today = today_brazil()
    cutoff = today - timedelta(days=7)
    
    existing = db.query(AcaoComercial).filter(
        AcaoComercial.projeto_id == projeto_id,
        AcaoComercial.tipo == tipo,
        AcaoComercial.data_acao >= cutoff
    ).order_by(AcaoComercial.data_acao.desc()).first()
    
    if existing:
        data_acao = existing.data_acao
        if isinstance(data_acao, datetime):
            data_acao = data_acao.date()
        dias_restantes = max(0, 7 - (today - data_acao).days)
        return {
            "id": existing.id,
            "tipo": existing.tipo,
            "descricao": existing.descricao,
            "data_acao": data_acao.isoformat(),
            "dias_restantes": dias_restantes
        }
    return None


def get_dias_encerramento(db: Session, projeto_id: Optional[int] = None, cadastro: Optional[object] = None) -> int:
    if cadastro is not None:
        val = getattr(cadastro, 'dias_encerramento_inscricao', None)
        if val is not None:
            return val
        return 2
    if projeto_id is not None:
        try:
            cad = db.query(CadastroEvento).filter(CadastroEvento.projeto_id == projeto_id).first()
            if cad and cad.dias_encerramento_inscricao is not None:
                return cad.dias_encerramento_inscricao
        except Exception:
            pass
    return 2

def calculate_d_minus(event_date: date, reference_year: Optional[int] = None, dias_encerramento: int = 2) -> int:
    if not event_date:
        return 0
    registration_close = event_date - timedelta(days=dias_encerramento)
    today = today_brazil()
    if reference_year is not None and reference_year != today.year:
        try:
            today = today.replace(year=reference_year)
        except ValueError:
            today = today.replace(year=reference_year, day=28)
    delta = (registration_close - today).days
    return max(0, delta)


def get_event_regime(d_minus_raw: int) -> str:
    """
    Centralized function to determine data regime from raw (unclamped) D-.
    d_minus_raw = (registration_close - today).days, can be negative for past events.
    - 'consolidated' (D- < -1): event ended, use snapshot data only, no live queries
    - 'hybrid' (-1 ≤ D- ≤ 3): event is happening now or just ended, snapshot + live today
    - 'live' (D- > 3): upcoming event, full live queries as normal
    """
    if d_minus_raw < -1:
        return "consolidated"
    if d_minus_raw <= 3:
        return "hybrid"
    return "live"


def get_data_regime(event_date, dias_encerramento: int = 2) -> str:
    """Convenience wrapper: computes raw D- from event_date and delegates to get_event_regime."""
    if not event_date:
        return "live"
    registration_close = event_date - timedelta(days=dias_encerramento)
    real_d_minus = (registration_close - today_brazil()).days
    return get_event_regime(real_d_minus)


def _get_snapshot_metrics_for_grupo(db: Session, grupo_nome: str, ano: Optional[int] = None) -> Optional[dict]:
    """
    Returns ISC-like metrics from snapshot data for a consolidated event group.
    Returns None if no snapshot data exists (caller should fall back to live data).

    ``ano`` (ano-edição do evento) é OBRIGATÓRIO para grupos recorrentes — sem
    ele, edições diferentes do mesmo grupo (ex.: 2025 + 2026) são somadas e os
    totais aparecem dobrados na UI.
    """
    try:
        from ...services.snapshot_service import get_snapshot_vendas_com_receita
        rows = get_snapshot_vendas_com_receita(db, grupo_nome, ano=ano)
        if not rows:
            return None
        total_qtd = sum(r['qtd'] for r in rows)
        total_receita = sum(r['receita'] for r in rows)
        return {
            'qtd_site': total_qtd,
            'inscricao_liquida': total_receita,
            'receita_liquida_site': total_receita,
            'ticket_medio': round(total_receita / total_qtd, 2) if total_qtd > 0 else 0.0,
            'media_7d': 0.0,
            'media_14d': 0.0,
            'media_30d': 0.0,
        }
    except Exception as e:
        logger.warning(f"[Hybrid] Failed to get snapshot metrics for '{grupo_nome}': {e}")
        return None

def _interpolate_hist_pattern(hist_pattern: dict, d_minus: int) -> float:
    sorted_dms = sorted(hist_pattern.keys(), reverse=True)
    if d_minus in hist_pattern:
        return hist_pattern[d_minus]
    if d_minus >= sorted_dms[0]:
        return hist_pattern[sorted_dms[0]]
    if d_minus <= sorted_dms[-1]:
        return hist_pattern[sorted_dms[-1]]
    for i in range(len(sorted_dms) - 1):
        if sorted_dms[i] > d_minus > sorted_dms[i + 1]:
            upper_dm = sorted_dms[i]
            lower_dm = sorted_dms[i + 1]
            ratio = (upper_dm - d_minus) / (upper_dm - lower_dm) if upper_dm != lower_dm else 0
            return hist_pattern[upper_dm] + ratio * (hist_pattern[lower_dm] - hist_pattern[upper_dm])
    return hist_pattern.get(0, 1.0)


def _normalize_daily_dict_for_isc(daily_sales_dict: dict) -> dict:
    """Apply outlier normalization to a daily_sales_dict {date: qty} and return
    a dict of the same shape with smoothed values. Uses normalize_daily_sales_outliers."""
    if not daily_sales_dict:
        return daily_sales_dict
    sorted_dates = sorted(daily_sales_dict.keys())
    series = [{"date": d.isoformat() if hasattr(d, "isoformat") else str(d), "sales": daily_sales_dict[d]} for d in sorted_dates]
    series = normalize_daily_sales_outliers(series)
    return {d: series[i].get("normalizedSales", daily_sales_dict[d]) for i, d in enumerate(sorted_dates)}


def calculate_isc_components(current_sales: int, sales_goal: int, d_minus: int,
                              media_14d: Optional[float] = None, daily_sales_dict: Optional[dict] = None,
                              media_7d: Optional[float] = None, media_30d: Optional[float] = None,
                              hist_pattern: Optional[dict] = None,
                              registration_close_date=None,
                              curva_info: Optional[dict] = None,
                              use_normalized_curve: bool = False) -> ISCComponents:
    """
    registration_close_date: date of last day registrations were open (event_date - dias_enc).
    When provided and d_minus < 0 (past event), all rolling windows are anchored to this date
    so components are frozen at their final state rather than collapsing to zero.
    """
    _ci = curva_info or {}
    if sales_goal == 0:
        return ISCComponents(ia730=1.0, curvaDPercent=1.0, rolling14d=1.0,
                             tipoCurva=_ci.get("tipo_curva", "linear"),
                             fonteCurva=_ci.get("fonte_curva"),
                             anoReferencia=_ci.get("ano_referencia"))
    
    if daily_sales_dict:
        daily_sales_dict = {(date.fromisoformat(k) if isinstance(k, str) else k): v for k, v in daily_sales_dict.items()}
    
    from datetime import timedelta

    # For past events, anchor calculations to the registration close date.
    # This freezes components at the state they were when the event ended.
    # NOTE: d_minus may arrive clamped to 0 for consolidated events (dMinusInscricoes=0),
    # so we also check registration_close_date to correctly identify past events.
    is_past_event = d_minus < 0 or (
        registration_close_date is not None and registration_close_date < today_brazil()
    )
    if is_past_event and registration_close_date is not None:
        anchor_date = registration_close_date - timedelta(days=1)
        d_minus_effective = 0  # treat as D-0 for curvaDPercent and rolling window
    else:
        anchor_date = today_brazil() - timedelta(days=1)
        d_minus_effective = d_minus

    if daily_sales_dict and len(daily_sales_dict) > 0:
        # For past events anchor to close date; for live events anchor to yesterday
        cutoff = anchor_date if is_past_event and registration_close_date else today_brazil()
        current_sales = sum(v for k, v in daily_sales_dict.items() if k <= cutoff)
        if use_normalized_curve:
            normalized_dict = _normalize_daily_dict_for_isc(daily_sales_dict)
            normalized_current_sales = sum(v for k, v in normalized_dict.items() if k <= cutoff)
            progress_percent = normalized_current_sales / sales_goal
        else:
            progress_percent = current_sales / sales_goal
    else:
        progress_percent = current_sales / sales_goal

    tipo_curva = "linear"
    if hist_pattern and len(hist_pattern) > 0:
        hist_max_dm = max(hist_pattern.keys())
        if d_minus_effective > hist_max_dm:
            # Current D-minus is beyond the historical data range (campaign hadn't started
            # that early in the reference year). Fall back to linear 90-day ramp so we
            # don't divide by a near-zero historical percentage and inflate the component.
            total_days = 90
            elapsed_days = max(1, total_days - d_minus_effective)
            expected_progress = max(elapsed_days / total_days, 0.01)
            curva_d_percent = progress_percent / expected_progress
        else:
            tipo_curva = "historico"
            expected_progress = _interpolate_hist_pattern(hist_pattern, d_minus_effective)
            if expected_progress <= 0:
                expected_progress = 0.01
            curva_d_percent = progress_percent / expected_progress
    else:
        total_days = 90
        elapsed_days = max(1, total_days - d_minus_effective)
        expected_progress = elapsed_days / total_days
        if expected_progress == 0:
            expected_progress = 0.01
        curva_d_percent = progress_percent / expected_progress

    real_7d = None
    real_14d = None
    real_30d = None
    sum_14d_raw = None
    if daily_sales_dict and len(daily_sales_dict) > 0:
        s7 = sum(daily_sales_dict.get(anchor_date - timedelta(days=i), 0) for i in range(7))
        s14 = sum(daily_sales_dict.get(anchor_date - timedelta(days=i), 0) for i in range(14))
        s30 = sum(daily_sales_dict.get(anchor_date - timedelta(days=i), 0) for i in range(30))
        sum_14d_raw = s14
        real_7d = s7 / 7.0
        real_14d = s14 / 14.0
        real_30d = s30 / 30.0

    effective_7d = real_7d if real_7d is not None else media_7d
    effective_14d = real_14d if real_14d is not None else media_14d
    effective_30d = real_30d if real_30d is not None else media_30d

    ia730_calculated = False
    if effective_7d is not None and effective_30d is not None:
        if effective_30d > 0:
            raw_ia730 = effective_7d / effective_30d
            # For past events, ia730=0 means zero sales in the 7-day window before
            # registration close — use curva_d_percent fallback so the indicator
            # never shows a misleading 0 when there IS historical sales activity.
            if raw_ia730 == 0 and is_past_event:
                ia730_calculated = False  # fall through to curva_d_percent
            else:
                ia730 = raw_ia730
                ia730_calculated = True
        elif effective_7d > 0:
            ia730 = 1.2
            ia730_calculated = True
    
    if not ia730_calculated:
        ia730 = curva_d_percent

    # Use d_minus_effective (clamped to 0 for past events) so expected window is meaningful
    d_minus_anchor = d_minus_effective + 1

    expected_14d_sales = None
    if hist_pattern and len(hist_pattern) > 0 and sales_goal > 0:
        expected_at_anchor = _interpolate_hist_pattern(hist_pattern, d_minus_anchor)
        expected_14d_ago = _interpolate_hist_pattern(hist_pattern, d_minus_anchor + 14)
        expected_14d_sales = (expected_at_anchor - expected_14d_ago) * sales_goal
    elif sales_goal > 0:
        total_days = 90
        expected_14d_sales = (14 / total_days) * sales_goal

    if expected_14d_sales is not None and expected_14d_sales > 0 and sum_14d_raw is not None:
        rolling14d = sum_14d_raw / expected_14d_sales
    elif effective_14d is not None and effective_14d > 0 and expected_14d_sales is not None and expected_14d_sales > 0:
        rolling14d = (effective_14d * 14) / expected_14d_sales
    else:
        rolling14d = (curva_d_percent + ia730) / 2
    
    if _ci.get("tipo_curva"):
        tipo_curva = _ci["tipo_curva"]

    return ISCComponents(
        ia730=round(ia730, 4),
        curvaDPercent=round(curva_d_percent, 4),
        rolling14d=round(rolling14d, 4),
        tipoCurva=tipo_curva,
        fonteCurva=_ci.get("fonte_curva"),
        anoReferencia=_ci.get("ano_referencia")
    )

_ISC_DESVIO_CAP = 0.30

def calculate_isc(components: ISCComponents, ia_weight: float = 20.0, curva_weight: float = 40.0, rolling_weight: float = 40.0) -> float:
    cap = _ISC_DESVIO_CAP
    d_ia = max(-cap, min(cap, components.ia730 - 1))
    d_curva = max(-cap, min(cap, components.curvaDPercent - 1))
    d_rolling = max(-cap, min(cap, components.rolling14d - 1))

    weighted = (curva_weight / 100) * d_curva + (rolling_weight / 100) * d_rolling + (ia_weight / 100) * d_ia
    isc = 1.0 + weighted
    return round(isc, 2)


def _fetch_previous_year_cumulative_pattern(db: Session, evento_grupo: str, ano: int, use_normalized: bool = False) -> Optional[dict]:
    from ...services.snapshot_service import get_curva_historica_snapshot, save_curva_historica_snapshot
    prev_ano = ano - 1

    if not use_normalized:
        snapshot_pattern = get_curva_historica_snapshot(db, evento_grupo, prev_ano)
        if snapshot_pattern:
            logger.info(f"Using curva histórica snapshot for '{evento_grupo}' ano_ref={prev_ano}: {len(snapshot_pattern)} pontos D-minus")
            return snapshot_pattern

    prev_data_evento = _find_data_evento(db, evento_grupo, prev_ano)
    if not prev_data_evento:
        logger.info(f"No previous year event date found for '{evento_grupo}' ano={prev_ano}")
        return None

    prev_dias_enc = 2
    try:
        prev_proj = db.query(DimProjeto).filter(
            DimProjeto.data_evento == prev_data_evento
        ).first()
        if prev_proj:
            prev_dias_enc = get_dias_encerramento(db, projeto_id=prev_proj.id)
    except Exception:
        pass
    prev_data_inscricao = prev_data_evento - timedelta(days=prev_dias_enc)

    prev_mappings = _wq_sku_mappings_by_grupo_single_year(db, evento_grupo, prev_ano)

    if not prev_mappings:
        current_mappings = _wq_sku_mappings_by_grupo_single_year(db, evento_grupo, ano)
        prev_skus = list(set(m.sku for m in current_mappings if m.sku))
        if prev_skus:
            prev_mappings = _wq_sku_mappings_by_skus(db, prev_skus, [prev_ano])
            if prev_mappings is None:
                prev_mappings = []

    if not prev_mappings:
        logger.info(f"No SKU mappings found for '{evento_grupo}' ano={prev_ano}")
        return None

    prev_ativo_ids = []
    prev_magento_ids = []
    for m in prev_mappings:
        if m.id_externo:
            if m.fonte == 'ATIVO':
                prev_ativo_ids.append(str(m.id_externo))
            elif m.fonte == 'MAGENTO':
                prev_magento_ids.append(str(m.id_externo))

    prev_daily = {}
    if prev_ativo_ids:
        rows = _fetch_daily_sales_ativo_by_ids(list(set(prev_ativo_ids)))
        for row in rows:
            d = date.fromisoformat(row['dia']) if isinstance(row['dia'], str) else row['dia']
            prev_daily[d] = prev_daily.get(d, 0) + row['qtd']
    if prev_magento_ids:
        _cort = _get_cortesia_magento_ids(db)
        _mag_cort = set(prev_magento_ids) & _cort if _cort else None
        rows = _fetch_daily_sales_magento_by_ids(list(set(prev_magento_ids)), cortesia_magento_ids=_mag_cort if _mag_cort else None)
        for row in rows:
            d = date.fromisoformat(row['dia']) if isinstance(row['dia'], str) else row['dia']
            prev_daily[d] = prev_daily.get(d, 0) + row['qtd']

    if not prev_daily:
        logger.info(f"No sales data found for '{evento_grupo}' ano={prev_ano}")
        return None

    # Normalize outliers (campaign spikes) only when explicitly requested. Normalized
    # patterns are NOT cached so the snapshot table keeps the canonical raw curve.
    if use_normalized:
        try:
            prev_daily = _normalize_daily_dict_for_isc(prev_daily)
        except Exception as _ne:
            logger.warning(f"Falha ao normalizar curva histórica de '{evento_grupo}' ano={prev_ano}: {_ne}")

    total_prev_sales = sum(prev_daily.values())
    if total_prev_sales == 0:
        return None

    d_minus_sales = {}
    for sale_date, qty in prev_daily.items():
        dm = (prev_data_inscricao - sale_date).days
        d_minus_sales[dm] = d_minus_sales.get(dm, 0) + qty

    d_minus_sales = {dm: qty for dm, qty in d_minus_sales.items() if dm >= 0}
    if not d_minus_sales:
        logger.info(f"No sales data with positive D- for '{evento_grupo}' ano={prev_ano}")
        return None

    max_dm = max(d_minus_sales.keys())
    min_dm = min(d_minus_sales.keys())

    cumulative = 0
    pattern = {}
    for dm in range(max_dm, min_dm - 1, -1):
        cumulative += d_minus_sales.get(dm, 0)
        pattern[dm] = cumulative / total_prev_sales

    if 0 not in pattern:
        pattern[0] = 1.0
    if min_dm > 0:
        for dm in range(min_dm - 1, -1, -1):
            pattern[dm] = 1.0

    logger.info(f"Built historical pattern for '{evento_grupo}' from ano={prev_ano} (inscricao D-): {len(prev_daily)} sale days, total={total_prev_sales}, D- range [{min_dm}, {max_dm}]")

    # Guard contra curvas degeneradas: edições com baixíssimo volume produzem
    # padrões saturados (pct=1.0 em quase todo d_minus), gerando Meta Dia
    # zerada quando aplicados. Em vez de persistir lixo, retorna None para
    # que _resolve_hist_pattern siga o fallback (override → circuito →
    # regional → linear). Threshold de 20 inscrições é conservador — abaixo
    # disso a curva não tem base estatística.
    from ...services.snapshot_service import is_curve_saturated
    MIN_REF_TOTAL = 20
    if total_prev_sales < MIN_REF_TOTAL or is_curve_saturated(pattern):
        logger.warning(
            f"[CurvaHist] '{evento_grupo}' ano={prev_ano} curva descartada "
            f"(total={total_prev_sales}, saturated={is_curve_saturated(pattern)}) "
            f"— delegando ao fallback"
        )
        return None

    if not use_normalized:
        try:
            save_curva_historica_snapshot(db, evento_grupo, prev_ano, pattern, total_prev_sales)
        except Exception as e:
            logger.warning(f"Failed to save curva histórica snapshot for '{evento_grupo}': {e}")

    return pattern


def _fetch_current_year_realized_pattern(db: Session, evento_grupo: str, ano: int, use_normalized: bool = False) -> Optional[dict]:
    """Monta o padrão acumulado por D- a partir das vendas REAIS já realizadas
    do grupo no PRÓPRIO ano vigente (`ano`). Diferente de
    `_fetch_previous_year_cumulative_pattern` (que usa o ano anterior), esta
    função serve o caso "etapa anterior do mesmo ano que já fechou" — ex.: usar
    a curva realizada de uma etapa de Outono/2026 como referência para a etapa
    de Inverno/2026.

    Só retorna padrão quando o evento JÁ ENCERROU as inscrições
    (data_inscricao < hoje); caso contrário a curva seria parcial e satura
    prematuramente em pct=1.0. Lê exclusivamente de `vendas_diaria_snapshot`
    (PostgreSQL) — não toca em Magento/Ativo, portanto é seguro no caminho
    read-only e barato."""
    from ...models.vendas_snapshot import VendasDiariaSnapshot

    data_evento = _find_data_evento(db, evento_grupo, ano)
    if not data_evento:
        logger.info(f"[CurvaVigente] sem data_evento para '{evento_grupo}' ano={ano}")
        return None

    dias_enc = 2
    try:
        proj = db.query(DimProjeto).filter(DimProjeto.data_evento == data_evento).first()
        if proj:
            dias_enc = get_dias_encerramento(db, projeto_id=proj.id)
    except Exception:
        pass
    data_inscricao = data_evento - timedelta(days=dias_enc)

    # Exige evento encerrado: curva realizada só faz sentido completa.
    if data_inscricao >= today_brazil():
        logger.info(
            f"[CurvaVigente] '{evento_grupo}' ano={ano} ainda não encerrou "
            f"(data_inscricao={data_inscricao}) — não gera curva vigente"
        )
        return None

    rows = db.query(
        VendasDiariaSnapshot.data_venda,
        func.sum(VendasDiariaSnapshot.quantidade)
    ).filter(
        VendasDiariaSnapshot.evento_grupo == evento_grupo,
        VendasDiariaSnapshot.ano == ano
    ).group_by(VendasDiariaSnapshot.data_venda).all()

    daily = {}
    for d, q in rows:
        dd = date.fromisoformat(d) if isinstance(d, str) else d
        daily[dd] = daily.get(dd, 0) + int(q or 0)

    if not daily:
        logger.info(f"[CurvaVigente] sem vendas em snapshot para '{evento_grupo}' ano={ano}")
        return None

    if use_normalized:
        try:
            daily = _normalize_daily_dict_for_isc(daily)
        except Exception as _ne:
            logger.warning(f"[CurvaVigente] falha ao normalizar '{evento_grupo}' ano={ano}: {_ne}")

    total = sum(daily.values())
    if total <= 0:
        return None

    d_minus_sales = {}
    for sale_date, qty in daily.items():
        dm = (data_inscricao - sale_date).days
        if dm >= 0:
            d_minus_sales[dm] = d_minus_sales.get(dm, 0) + qty

    if not d_minus_sales:
        return None

    max_dm = max(d_minus_sales.keys())
    min_dm = min(d_minus_sales.keys())

    cumulative = 0
    pattern = {}
    for dm in range(max_dm, min_dm - 1, -1):
        cumulative += d_minus_sales.get(dm, 0)
        pattern[dm] = cumulative / total

    if 0 not in pattern:
        pattern[0] = 1.0
    if min_dm > 0:
        for dm in range(min_dm - 1, -1, -1):
            pattern[dm] = 1.0

    from ...services.snapshot_service import is_curve_saturated
    if total < 20 or is_curve_saturated(pattern):
        logger.warning(
            f"[CurvaVigente] '{evento_grupo}' ano={ano} curva descartada "
            f"(total={total}, saturated={is_curve_saturated(pattern)})"
        )
        return None

    logger.info(
        f"[CurvaVigente] curva realizada montada para '{evento_grupo}' ano={ano}: "
        f"{len(daily)} dias, total={total}, D- range [{min_dm}, {max_dm}]"
    )
    return pattern


def _fetch_current_year_realized_patterns_batch(
    db: Session, grupos: list, ano: int, use_normalized: bool = False
) -> dict:
    """Versão em lote de ``_fetch_current_year_realized_pattern``.

    Resolve a curva realizada do ano vigente para MUITOS grupos de uma vez,
    usando poucas consultas agregadas em vez de uma chamada (e várias queries)
    por grupo. Usada pelo endpoint ``available-curves`` para montar rapidamente
    a lista de candidatos de "ano vigente" mesmo em bases grandes.

    Retorna ``{evento_grupo: pattern}`` apenas para os grupos cuja curva pôde
    ser montada — a lógica de montagem, encerramento, total mínimo e descarte
    por saturação é idêntica à da função single para garantir paridade exata de
    resultados (nenhuma opção exibida cai no fallback ao ser selecionada).
    """
    from ...models.vendas_snapshot import VendasDiariaSnapshot
    from ...models.dimensoes import SkuMapping
    from ...services.snapshot_service import is_curve_saturated

    result: dict = {}
    grupos = list(dict.fromkeys(g for g in grupos if g))
    if not grupos:
        return result

    # (1) Projetos carregados UMA vez (em vez de uma query por grupo dentro de
    # _find_data_evento). Já filtrados para data_evento não-nula.
    projetos = [p for p in _wq_all_dim_projetos(db) if p.data_evento is not None]

    # (2) Datas do sku_mappings para o ano em UMA query (fallback de data_evento).
    sku_date_map: dict = {}
    for eg, de in db.query(
        SkuMapping.evento_grupo, SkuMapping.data_evento
    ).filter(
        SkuMapping.evento_grupo.in_(grupos),
        SkuMapping.ano == ano,
        SkuMapping.data_evento.isnot(None),
        SkuMapping.ativo == True
    ).all():
        sku_date_map.setdefault(eg, de)

    # (3) data_evento por grupo, reaproveitando a MESMA lógica de matching textual
    # de _find_data_evento, mas sem reconsultar projetos/sku a cada grupo.
    data_evento_map: dict = {}
    for g in grupos:
        de = _find_data_evento(
            db, g, ano,
            projetos=projetos,
            sku_mapping_date=sku_date_map.get(g),
        )
        if de:
            data_evento_map[g] = de

    if not data_evento_map:
        return result

    # (4) dias_encerramento em lote: DimProjeto por data_evento + CadastroEvento
    # por projeto_id (UMA query para os cadastros relevantes).
    distinct_dates = set(data_evento_map.values())
    proj_by_date: dict = {}
    for p in projetos:
        if p.data_evento in distinct_dates:
            proj_by_date.setdefault(p.data_evento, p)
    proj_ids = [p.id for p in proj_by_date.values()]
    dias_by_proj: dict = {}
    if proj_ids:
        for cad in db.query(CadastroEvento).filter(
            CadastroEvento.projeto_id.in_(proj_ids)
        ).all():
            if cad.dias_encerramento_inscricao is not None:
                dias_by_proj[cad.projeto_id] = cad.dias_encerramento_inscricao

    # (5) Filtra apenas eventos JÁ ENCERRADOS (mesma regra da função single).
    hoje = today_brazil()
    data_inscricao_map: dict = {}
    for g, de in data_evento_map.items():
        dias_enc = 2
        proj = proj_by_date.get(de)
        if proj is not None:
            dias_enc = dias_by_proj.get(proj.id, 2)
        data_inscricao = de - timedelta(days=dias_enc)
        if data_inscricao >= hoje:
            continue
        data_inscricao_map[g] = data_inscricao

    if not data_inscricao_map:
        return result

    # (6) Vendas diárias de TODOS os grupos candidatos em UMA query agregada.
    daily_by_grupo: dict = {}
    for eg, d, q in db.query(
        VendasDiariaSnapshot.evento_grupo,
        VendasDiariaSnapshot.data_venda,
        func.sum(VendasDiariaSnapshot.quantidade),
    ).filter(
        VendasDiariaSnapshot.evento_grupo.in_(list(data_inscricao_map.keys())),
        VendasDiariaSnapshot.ano == ano,
    ).group_by(
        VendasDiariaSnapshot.evento_grupo,
        VendasDiariaSnapshot.data_venda,
    ).all():
        dd = date.fromisoformat(d) if isinstance(d, str) else d
        m = daily_by_grupo.setdefault(eg, {})
        m[dd] = m.get(dd, 0) + int(q or 0)

    # (7) Monta o padrão acumulado por D- por grupo (lógica idêntica à single).
    for g, data_inscricao in data_inscricao_map.items():
        daily = daily_by_grupo.get(g)
        if not daily:
            continue
        if use_normalized:
            try:
                daily = _normalize_daily_dict_for_isc(daily)
            except Exception as _ne:
                logger.warning(f"[CurvaVigente] falha ao normalizar '{g}' ano={ano}: {_ne}")

        total = sum(daily.values())
        if total <= 0:
            continue

        d_minus_sales: dict = {}
        for sale_date, qty in daily.items():
            dm = (data_inscricao - sale_date).days
            if dm >= 0:
                d_minus_sales[dm] = d_minus_sales.get(dm, 0) + qty
        if not d_minus_sales:
            continue

        max_dm = max(d_minus_sales.keys())
        min_dm = min(d_minus_sales.keys())
        cumulative = 0
        pattern: dict = {}
        for dm in range(max_dm, min_dm - 1, -1):
            cumulative += d_minus_sales.get(dm, 0)
            pattern[dm] = cumulative / total
        if 0 not in pattern:
            pattern[0] = 1.0
        if min_dm > 0:
            for dm in range(min_dm - 1, -1, -1):
                pattern[dm] = 1.0

        if total < 20 or is_curve_saturated(pattern):
            continue

        result[g] = pattern

    return result


def _resolve_hist_pattern(db: Session, evento_grupo: str, ano: int, estado: Optional[str] = None, use_normalized: bool = False) -> tuple:
    """Resolve the best available historical curve for an event group using a fallback chain.
    
    Returns (pattern, curva_info) where curva_info is a dict with:
      - tipo_curva: 'historico' | 'circuito' | 'circuito_similar' | 'regional' | 'manual' | 'linear'
      - fonte_curva: name of the source grupo or region
      - ano_referencia: year the pattern data is from
    """
    from ...services.snapshot_service import get_curva_historica_snapshot, get_curva_historica_snapshot_with_meta, is_curve_saturated
    from ...models.vendas_snapshot import CurvaHistoricaSnapshot
    prev_ano = ano - 1

    # Origens "derivadas": padrões persistidos sob o nome do próprio evento que,
    # na verdade, vieram da cadeia de fallback (média regional/circuito) — NÃO
    # são histórico próprio. Ao ler de volta, o rótulo precisa refletir a origem
    # real gravada na coluna `origem`, e não ser mostrado como "Histórico Próprio".
    DERIVED_ORIGENS = {"regional", "circuito", "circuito_similar", "manual", "derivado"}
    DERIVED_FONTE_FALLBACK = {
        "regional": "Média Regional",
        "circuito": "Similar (Circuito)",
        "circuito_similar": "Média do Circuito",
        "derivado": "Derivada",
    }

    def _skip_if_saturated(pat: Optional[dict], src: str) -> Optional[dict]:
        """Descarta padrões saturados antes de usá-los como sibling/regional,
        impedindo cascata de degeneração nos blends de fallback."""
        if pat and is_curve_saturated(pat):
            logger.info(f"[CurvaResolve] sibling '{src}' está saturado — ignorando no blend")
            return None
        return pat

    # Detecta curvas "degeneradas": padrões que reflitam histórico de baixíssima
    # venda (ex.: Vitória Inverno 2025 com apenas 5 inscrições) ou que já estejam
    # saturados em ~100% no D- mais alto disponível (toda venda do ano anterior
    # ocorreu antes do início da janela observada). Ambos os casos produzem
    # meta_dia=0 em todos os dias úteis e meta_acum constante na meta final.
    # Preferimos cair no fallback (circuito / regional / linear) nesses casos.
    MIN_REF_SALES = 50
    SATURATION_PCT = 0.95

    def _ref_total_for(eg: str, ar: int) -> int:
        val = db.query(func.max(CurvaHistoricaSnapshot.total_vendas_referencia)).filter(
            CurvaHistoricaSnapshot.evento_grupo == eg,
            CurvaHistoricaSnapshot.ano_referencia == ar
        ).scalar()
        return int(val) if val else 0

    def _is_degenerate(pattern: Optional[dict], ref_total: int, label: str) -> bool:
        if ref_total > 0 and ref_total < MIN_REF_SALES:
            logger.info(f"[CurvaResolve] {label} descartado: total_vendas_ref={ref_total} < {MIN_REF_SALES}")
            return True
        if pattern:
            try:
                max_dm = max(pattern.keys())
                head_pct = pattern[max_dm]
                if max_dm >= 30 and head_pct >= SATURATION_PCT:
                    logger.info(f"[CurvaResolve] {label} descartado: saturado em D-{max_dm} (pct={head_pct:.2f} ≥ {SATURATION_PCT})")
                    return True
            except (ValueError, KeyError):
                pass
        return False

    grupo_obj = db.query(EventoGrupoModel).filter(EventoGrupoModel.nome == evento_grupo).first()

    if grupo_obj and grupo_obj.curva_override:
        override_modo = (getattr(grupo_obj, "curva_override_modo", None) or "historico")

        # Modo "vigente": usa a curva REAL já realizada do grupo-alvo no ano
        # corrente (etapa anterior do mesmo ano que já encerrou). Se a curva
        # vigente não puder ser montada (alvo não encerrou / sem dados), cai na
        # cadeia de fallback normal — NÃO usa o histórico do alvo.
        if override_modo == "vigente":
            vig_pattern = _fetch_current_year_realized_pattern(
                db, grupo_obj.curva_override, ano, use_normalized=use_normalized
            )
            if vig_pattern and not _is_degenerate(vig_pattern, 0, f"'{evento_grupo}' override vigente '{grupo_obj.curva_override}'"):
                logger.info(f"[CurvaResolve] '{evento_grupo}' using manual override (vigente): '{grupo_obj.curva_override}'")
                return vig_pattern, {
                    "tipo_curva": "manual_vigente",
                    "fonte_curva": grupo_obj.curva_override,
                    "ano_referencia": ano
                }
        else:
            override_ano_ref = prev_ano
            override_pattern = None if use_normalized else get_curva_historica_snapshot(db, grupo_obj.curva_override, prev_ano)
            if not override_pattern and not use_normalized:
                most_recent_ano = db.query(func.max(CurvaHistoricaSnapshot.ano_referencia)).filter(
                    CurvaHistoricaSnapshot.evento_grupo == grupo_obj.curva_override
                ).scalar()
                if most_recent_ano and most_recent_ano != prev_ano:
                    override_pattern = get_curva_historica_snapshot(db, grupo_obj.curva_override, most_recent_ano)
                    if override_pattern:
                        override_ano_ref = most_recent_ano
                        logger.info(f"[CurvaResolve] '{evento_grupo}' override '{grupo_obj.curva_override}': ano {prev_ano} não encontrado, usando ano_ref={most_recent_ano}")
            if not override_pattern:
                override_pattern = _fetch_previous_year_cumulative_pattern(db, grupo_obj.curva_override, ano, use_normalized=use_normalized)
            override_ref_total = _ref_total_for(grupo_obj.curva_override, override_ano_ref)
            if override_pattern and not _is_degenerate(override_pattern, override_ref_total, f"'{evento_grupo}' override '{grupo_obj.curva_override}'"):
                logger.info(f"[CurvaResolve] '{evento_grupo}' using manual override: '{grupo_obj.curva_override}'")
                return override_pattern, {
                    "tipo_curva": "manual",
                    "fonte_curva": grupo_obj.curva_override,
                    "ano_referencia": override_ano_ref
                }

    own_ref_total = _ref_total_for(evento_grupo, prev_ano)
    # Lê a origem do snapshot persistido sob o nome do próprio evento ANTES de
    # rotular como "histórico próprio". Um snapshot gravado em (evento, prev_ano)
    # pode, na verdade, ser uma curva derivada (média regional/circuito) que o
    # job de consolidação pré-computou e salvou sob o nome do evento. Nesse caso
    # o rótulo correto é a origem real, não "Histórico Próprio".
    own_snap_origem = None
    own_snap_fonte = None
    if not use_normalized:
        _osnap, own_snap_origem, own_snap_fonte = get_curva_historica_snapshot_with_meta(db, evento_grupo, prev_ano)
    own_pattern = _fetch_previous_year_cumulative_pattern(db, evento_grupo, ano, use_normalized=use_normalized)
    if own_pattern and not _is_degenerate(own_pattern, own_ref_total, f"'{evento_grupo}' próprio ano={prev_ano}"):
        if own_snap_origem and own_snap_origem in DERIVED_ORIGENS:
            logger.info(
                f"[CurvaResolve] '{evento_grupo}' snapshot em (próprio, {prev_ano}) é derivado "
                f"(origem={own_snap_origem}, fonte={own_snap_fonte}) — rotulando como tal, não como histórico próprio"
            )
            return own_pattern, {
                "tipo_curva": own_snap_origem,
                "fonte_curva": own_snap_fonte or DERIVED_FONTE_FALLBACK.get(own_snap_origem),
                "ano_referencia": prev_ano
            }
        return own_pattern, {
            "tipo_curva": "historico",
            "fonte_curva": evento_grupo,
            "ano_referencia": prev_ano
        }

    circuito = grupo_obj.circuito if grupo_obj else None
    cidade = grupo_obj.cidade_normalizada if grupo_obj else None

    if circuito and cidade:
        same_circuit_city = db.query(EventoGrupoModel).filter(
            EventoGrupoModel.circuito == circuito,
            EventoGrupoModel.cidade_normalizada == cidade,
            EventoGrupoModel.nome != evento_grupo,
            EventoGrupoModel.ativo == True
        ).all()
        for sibling in same_circuit_city:
            sib_pattern = None if use_normalized else get_curva_historica_snapshot(db, sibling.nome, prev_ano)
            sib_pattern = _skip_if_saturated(sib_pattern, sibling.nome)
            if not sib_pattern:
                sib_pattern = _fetch_previous_year_cumulative_pattern(db, sibling.nome, ano, use_normalized=use_normalized)
                sib_pattern = _skip_if_saturated(sib_pattern, sibling.nome)
            if sib_pattern:
                logger.info(f"[CurvaResolve] '{evento_grupo}' using circuit+city sibling: '{sibling.nome}'")
                return sib_pattern, {
                    "tipo_curva": "circuito",
                    "fonte_curva": sibling.nome,
                    "ano_referencia": prev_ano
                }

    if circuito:
        same_circuit = db.query(EventoGrupoModel).filter(
            EventoGrupoModel.circuito == circuito,
            EventoGrupoModel.nome != evento_grupo,
            EventoGrupoModel.ativo == True
        ).all()
        patterns_found = []
        source_names = []
        pattern_weights = []
        for sibling in same_circuit:
            sib_pattern = None if use_normalized else get_curva_historica_snapshot(db, sibling.nome, prev_ano)
            sib_pattern = _skip_if_saturated(sib_pattern, sibling.nome)
            sib_weight = 0
            if sib_pattern:
                weight_row = db.query(CurvaHistoricaSnapshot.total_vendas_referencia).filter(
                    CurvaHistoricaSnapshot.evento_grupo == sibling.nome,
                    CurvaHistoricaSnapshot.ano_referencia == prev_ano
                ).first()
                sib_weight = weight_row[0] if weight_row and weight_row[0] else 0
            if not sib_pattern:
                sib_pattern = _fetch_previous_year_cumulative_pattern(db, sibling.nome, ano, use_normalized=use_normalized)
                sib_pattern = _skip_if_saturated(sib_pattern, sibling.nome)
            if sib_pattern:
                patterns_found.append(sib_pattern)
                source_names.append(sibling.nome)
                pattern_weights.append(sib_weight if sib_weight > 0 else 1)

        if patterns_found:
            avg_pattern = _average_patterns(patterns_found, weights=pattern_weights)
            fonte_label = f"Média {circuito}" if len(patterns_found) > 1 else source_names[0]
            logger.info(f"[CurvaResolve] '{evento_grupo}' using circuit average from {len(patterns_found)} sibling(s): {source_names} (weights={pattern_weights})")
            return avg_pattern, {
                "tipo_curva": "circuito_similar",
                "fonte_curva": fonte_label,
                "ano_referencia": prev_ano
            }

    if estado:
        regional_grupos = db.query(EventoGrupoModel).join(
            SkuMapping, SkuMapping.evento_grupo == EventoGrupoModel.nome
        ).join(
            DimProjeto, DimProjeto.codigo == SkuMapping.sku
        ).filter(
            DimProjeto.estado == estado,
            EventoGrupoModel.nome != evento_grupo,
            EventoGrupoModel.ativo == True
        ).distinct().all()

        patterns_found = []
        pattern_weights = []
        for rg in regional_grupos:
            rg_pattern = (None if use_normalized
                          else get_curva_historica_snapshot(db, rg.nome, prev_ano))
            rg_pattern = _skip_if_saturated(rg_pattern, rg.nome)
            if not rg_pattern and use_normalized:
                rg_pattern = _fetch_previous_year_cumulative_pattern(db, rg.nome, ano, use_normalized=True)
                rg_pattern = _skip_if_saturated(rg_pattern, rg.nome)
            if rg_pattern:
                patterns_found.append(rg_pattern)
                weight_row = db.query(CurvaHistoricaSnapshot.total_vendas_referencia).filter(
                    CurvaHistoricaSnapshot.evento_grupo == rg.nome,
                    CurvaHistoricaSnapshot.ano_referencia == prev_ano
                ).first()
                pattern_weights.append(weight_row[0] if weight_row and weight_row[0] else 1)

        if len(patterns_found) >= 2:
            avg_pattern = _average_patterns(patterns_found, weights=pattern_weights)
            logger.info(f"[CurvaResolve] '{evento_grupo}' using regional average ({estado}): {len(patterns_found)} patterns")
            return avg_pattern, {
                "tipo_curva": "regional",
                "fonte_curva": estado,
                "ano_referencia": prev_ano
            }

    logger.info(f"[CurvaResolve] '{evento_grupo}' no fallback found, using linear")
    return None, {
        "tipo_curva": "linear",
        "fonte_curva": None,
        "ano_referencia": None
    }


def _average_patterns(patterns: list, weights: Optional[list] = None) -> dict:
    """Average multiple hist_pattern dicts into one, optionally weighted."""
    all_dms = set()
    for p in patterns:
        all_dms.update(p.keys())

    if weights and len(weights) == len(patterns) and sum(weights) > 0:
        total_weight = sum(weights)
        avg = {}
        for dm in all_dms:
            weighted_sum = 0.0
            for i, p in enumerate(patterns):
                if dm in p:
                    weighted_sum += p[dm] * weights[i]
                else:
                    val = _interpolate_hist_pattern(p, dm)
                    weighted_sum += val * weights[i]
            avg[dm] = weighted_sum / total_weight
    else:
        avg = {}
        for dm in all_dms:
            values = []
            for p in patterns:
                if dm in p:
                    values.append(p[dm])
                else:
                    val = _interpolate_hist_pattern(p, dm)
                    values.append(val)
            avg[dm] = sum(values) / len(values)

    if 0 not in avg:
        avg[0] = 1.0

    return avg


_FORCE_REFRESH_COOLDOWN_SECONDS = int(os.getenv("FORCE_REFRESH_COOLDOWN_SECONDS", "300"))
_force_refresh_last_ts: dict = {}
_force_refresh_lock = _threading.Lock()


def fetch_real_daily_sales_for_projetos(db: Session, projetos: list, days_history: Optional[int] = None, sales_goal: int = 1000, ano: Optional[int] = None, evento_grupo: Optional[str] = None, data_evento: Optional[date] = None, preloaded_hist_pattern: object = "NOT_SET", data_evento_real: Optional[date] = None, force_magento_refresh: bool = False) -> list:
    from ...services.snapshot_service import get_snapshot_vendas
    import time as _frt_time

    # Proteção contra cliques repetidos em "Atualizar" do mesmo grupo
    # (cooldown 5min, env FORCE_REFRESH_COOLDOWN_SECONDS).
    # O lock garante que, mesmo com 2+ requests simultâneos para o mesmo grupo,
    # apenas o PRIMEIRO grava timestamp e prossegue com force_magento_refresh=True;
    # os concorrentes leem o timestamp recém-gravado e são rebaixados para
    # force_magento_refresh=False (caem no caminho normal de cache/snapshot).
    # Isso corta o fan-out típico do force_refresh (cpev1 + count + revenue +
    # fallback + supplementary = 7-10 queries pesadas no Magento) que estava
    # saturando o servidor externo em rajadas de cliques.
    if force_magento_refresh and evento_grupo:
        _now_ts = _frt_time.time()
        _key_ano = ano if ano is not None else today_brazil().year
        _key = f"{evento_grupo}|{_key_ano}"
        with _force_refresh_lock:
            _last = _force_refresh_last_ts.get(_key)
            if _last is not None and (_now_ts - _last) < _FORCE_REFRESH_COOLDOWN_SECONDS:
                force_magento_refresh = False
                _demoted_age = int(_now_ts - _last)
                logger.info(
                    f"[force_magento_refresh] DEMOTED p/ grupo='{evento_grupo}' ano={ano} — "
                    f"cooldown {_demoted_age}s < {_FORCE_REFRESH_COOLDOWN_SECONDS}s. Usando cache/snapshot."
                )
            else:
                _force_refresh_last_ts[_key] = _now_ts

    today = today_brazil()
    if ano is None:
        ano = today.year
    
    all_skus = []
    for projeto in projetos:
        if hasattr(projeto, 'codigo') and projeto.codigo:
            all_skus.append(str(projeto.codigo).upper().strip())
    
    if not all_skus:
        return []
    
    ativo_ids = []
    magento_ids = []
    
    all_active_mappings = _wq_sku_mappings_by_skus(db, all_skus)
    if all_active_mappings is None:
        all_active_mappings = db.query(SkuMapping).filter(
            SkuMapping.sku.in_(all_skus),
            SkuMapping.ativo == True
        ).all()
    
    year_mappings = [m for m in all_active_mappings if m.ano == ano]
    if not year_mappings and all_active_mappings:
        available_years = sorted(set(m.ano for m in all_active_mappings if m.ano), reverse=True)
        if available_years:
            best_year = available_years[0]
            logger.info(f"No SkuMappings for SKUs {all_skus} in year {ano}, using year {best_year}")
            year_mappings = [m for m in all_active_mappings if m.ano == best_year]
    
    for m in year_mappings:
        if m.id_externo:
            if m.fonte == 'ATIVO':
                ativo_ids.append(str(m.id_externo))
            elif m.fonte == 'MAGENTO':
                magento_ids.append(str(m.id_externo))
    
    if not ativo_ids and not magento_ids:
        logger.warning(f"No SkuMappings found for SKUs {all_skus} in any year")
    
    all_daily = {}
    
    snapshot_used = False
    today_in_snapshot = False
    if evento_grupo and not force_magento_refresh:
        snapshot_data = get_snapshot_vendas(db, evento_grupo, data_fim=today, ano=ano)
        if snapshot_data:
            all_daily.update(snapshot_data)
            snapshot_used = True
            today_in_snapshot = today in snapshot_data
            logger.debug(f"Snapshot loaded for '{evento_grupo}': {len(snapshot_data)} days up to {today} (today_in_snapshot={today_in_snapshot})")
    elif force_magento_refresh:
        logger.info(f"[force_magento_refresh] Bypass snapshot-first p/ grupo='{evento_grupo}' — vai direto às fontes")

    if not snapshot_used:
        if ativo_ids:
            ativo_rows = _fetch_daily_sales_ativo_by_ids(list(set(ativo_ids)))
            for row in ativo_rows:
                d = date.fromisoformat(row['dia']) if isinstance(row['dia'], str) else row['dia']
                all_daily[d] = all_daily.get(d, 0) + row['qtd']
        
        if magento_ids:
            _cort = _get_cortesia_magento_ids(db)
            _mag_cort = set(magento_ids) & _cort if _cort else None
            magento_rows = _fetch_daily_sales_magento_by_ids(list(set(magento_ids)), cortesia_magento_ids=_mag_cort if _mag_cort else None, db=db, ano=ano, force_magento_refresh=force_magento_refresh)
            for row in magento_rows:
                d = date.fromisoformat(row['dia']) if isinstance(row['dia'], str) else row['dia']
                all_daily[d] = all_daily.get(d, 0) + row['qtd']
    else:
        event_already_happened = data_evento_real and data_evento_real < today
        # Trust the snapshot for "today" if the background sync ran recently
        # enough — avoids a live MySQL query on every dashboard render. The
        # batch runs every ~45 min and writes today's row, so within that
        # window the snapshot is the freshest source we have.
        _last_sync = get_last_sync_hoje()
        snapshot_is_fresh = bool(
            today_in_snapshot
            and _last_sync
            and (_time.time() - _last_sync) < TODAY_SNAPSHOT_FRESHNESS_S
        )
        if event_already_happened:
            logger.debug(f"Event '{evento_grupo}' already happened ({data_evento_real}), skipping today's live sales query")
        elif snapshot_is_fresh:
            logger.debug(
                f"Snapshot fresh for '{evento_grupo}' (synced {int(_time.time() - _last_sync)}s ago), "
                f"skipping live query (qty hoje={all_daily.get(today, 0)})"
            )
        elif today_in_snapshot and all_daily.get(today, 0) > 0:
            logger.debug(f"Today's data already in snapshot for '{evento_grupo}' (qty={all_daily.get(today, 0)}), skipping live query")
        else:
            if ativo_ids:
                if ativo_breaker.is_open():
                    logger.warning(f"Ativo circuit aberto — pulando overlay de hoje para '{evento_grupo}'")
                else:
                    try:
                        today_sales = ativo_breaker.call(
                            _fetch_today_sales_ativo_by_ids, list(set(ativo_ids))
                        )
                        for d, qty in today_sales.items():
                            all_daily[d] = all_daily.get(d, 0) + qty
                    except CircuitOpenError:
                        pass
                    except Exception as e:
                        logger.warning(f"Failed to fetch today's Ativo sales: {e}")
            if magento_ids:
                if magento_breaker.is_open():
                    logger.warning(f"Magento circuit aberto — pulando overlay de hoje para '{evento_grupo}'")
                else:
                    try:
                        _cort = _get_cortesia_magento_ids(db)
                        _mag_cort = set(magento_ids) & _cort if _cort else None
                        today_sales = magento_breaker.call(
                            _fetch_today_sales_magento_by_ids,
                            list(set(magento_ids)),
                            cortesia_magento_ids=_mag_cort if _mag_cort else None,
                        )
                        for d, qty in today_sales.items():
                            all_daily[d] = all_daily.get(d, 0) + qty
                    except CircuitOpenError:
                        pass
                    except Exception as e:
                        logger.warning(f"Failed to fetch today's Magento sales: {e}")
    
    if not all_daily:
        if days_history:
            start_date = today - timedelta(days=days_history)
        else:
            start_date = today - timedelta(days=60)
        end_date = today
    else:
        earliest = min(all_daily.keys())
        latest_sale = max(all_daily.keys())
        if (today - latest_sale).days > 30:
            end_date = latest_sale
        else:
            end_date = today
        if days_history:
            start_date = max(earliest, end_date - timedelta(days=days_history))
        else:
            start_date = earliest

    # Cap end_date at the real event date if the event has already passed
    if data_evento_real and data_evento_real < today:
        end_date = min(end_date, data_evento_real)
    
    all_dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
    total_days = len(all_dates)

    hist_pattern = None
    if preloaded_hist_pattern != "NOT_SET":
        hist_pattern = preloaded_hist_pattern
    elif evento_grupo and data_evento:
        try:
            hist_pattern, _ = _resolve_hist_pattern(db, evento_grupo, ano)
        except Exception as e:
            logger.warning(f"Error fetching historical pattern for '{evento_grupo}': {e}")
    
    hist_known_dms = None
    hist_max_known = None
    hist_min_known = None
    if hist_pattern:
        hist_known_dms = sorted(hist_pattern.keys(), reverse=True)
        hist_max_known = hist_known_dms[0]
        hist_min_known = hist_known_dms[-1]

    cumulative_sales = 0
    cumulative_expected = 0
    result = []
    for d in all_dates:
        sales = all_daily.get(d, 0)
        cumulative_sales += sales

        if hist_pattern and data_evento and hist_known_dms:
            dm = (data_evento - d).days

            if dm in hist_pattern:
                pct = hist_pattern[dm]
            elif dm > hist_max_known:
                # Beyond the historical range: linearly extrapolate from 0% at D-90
                # to hist_pattern[hist_max_known] at D-hist_max_known so the expected
                # curve is populated even when the current campaign started earlier
                # than the reference year's campaign.
                anchor_pct = hist_pattern[hist_max_known]
                linear_ref = 90
                if dm >= linear_ref or linear_ref == hist_max_known:
                    pct = 0.0
                else:
                    pct = anchor_pct * (linear_ref - dm) / (linear_ref - hist_max_known)
                    pct = max(0.0, pct)
            elif dm <= hist_min_known:
                pct = hist_pattern[hist_min_known]
            else:
                pct = 0.0
                for i in range(len(hist_known_dms) - 1):
                    if hist_known_dms[i] >= dm >= hist_known_dms[i + 1]:
                        upper_dm = hist_known_dms[i]
                        lower_dm = hist_known_dms[i + 1]
                        ratio = (upper_dm - dm) / (upper_dm - lower_dm) if upper_dm != lower_dm else 0
                        pct = hist_pattern[upper_dm] + ratio * (hist_pattern[lower_dm] - hist_pattern[upper_dm])
                        break

            cumulative_expected = pct * sales_goal
            expected = cumulative_expected - (result[-1]['cumulativeExpected'] if result else 0)
            expected = max(0, expected)
        else:
            expected = sales_goal / total_days if total_days > 0 else 0
            cumulative_expected += expected

        dm = (data_evento - d).days if data_evento else None
        cum_exp_rounded = round(cumulative_expected, 1)
        dif = cumulative_sales - cum_exp_rounded
        ating_acum = round((cumulative_sales - cum_exp_rounded) / cum_exp_rounded * 100, 1) if cum_exp_rounded > 0 else 0.0
        expected_rounded = round(expected, 1)
        ating_diario = round((sales - expected_rounded) / expected_rounded * 100, 1) if expected_rounded > 0 else 0.0

        curva_pct = None
        if hist_pattern and data_evento and hist_known_dms:
            lookup_dm = (data_evento - d).days
            if lookup_dm in hist_pattern:
                curva_pct = round(hist_pattern[lookup_dm] * 100, 1)
            elif lookup_dm > hist_max_known:
                anchor_pct2 = hist_pattern[hist_max_known]
                linear_ref2 = 90
                if lookup_dm >= linear_ref2 or linear_ref2 == hist_max_known:
                    curva_pct = 0.0
                else:
                    extrapolated = anchor_pct2 * (linear_ref2 - lookup_dm) / (linear_ref2 - hist_max_known)
                    curva_pct = round(max(0.0, extrapolated) * 100, 1)
            elif lookup_dm <= hist_min_known:
                curva_pct = round(hist_pattern[hist_min_known] * 100, 1)
            else:
                for i in range(len(hist_known_dms) - 1):
                    if hist_known_dms[i] >= lookup_dm >= hist_known_dms[i + 1]:
                        upper_dm = hist_known_dms[i]
                        lower_dm = hist_known_dms[i + 1]
                        ratio = (upper_dm - lookup_dm) / (upper_dm - lower_dm) if upper_dm != lower_dm else 0
                        curva_pct = round((hist_pattern[upper_dm] + ratio * (hist_pattern[lower_dm] - hist_pattern[upper_dm])) * 100, 1)
                        break

        result.append({
            "date": d.isoformat(),
            "sales": sales,
            "expected": expected_rounded,
            "cumulativeSales": cumulative_sales,
            "cumulativeExpected": cum_exp_rounded,
            "dMinus": dm,
            "curvaAnoAnterior": curva_pct,
            "dif": round(dif, 1),
            "atingimentoAcumulado": ating_acum,
            "atingimentoDiario": ating_diario
        })
    
    result = normalize_daily_sales_outliers(result)

    return result


def normalize_daily_sales_outliers(daily_sales_list: list, window: int = 7, threshold: float = 2.0, spread: int = 3) -> list:
    import statistics

    n = len(daily_sales_list)
    if n < window:
        for item in daily_sales_list:
            item["normalizedSales"] = item["sales"]
            item["localMedian"] = None
            item["outlierLimit"] = None
            item["isOutlier"] = False
            item["excessRemoved"] = 0
            item["excessReceived"] = 0
        cum = 0
        for item in daily_sales_list:
            cum += item["normalizedSales"]
            item["cumulativeNormalized"] = cum
        return daily_sales_list

    raw_sales = [item["sales"] for item in daily_sales_list]
    normalized = list(raw_sales)

    non_zero = [s for s in raw_sales if s > 0]
    global_median = statistics.median(non_zero) if non_zero else 0
    min_threshold = max(global_median * 0.5, 5)

    local_medians = [None] * n
    outlier_limits = [None] * n
    is_outlier = [False] * n
    excess_removed = [0.0] * n
    excess_received = [0.0] * n

    for i in range(n):
        half = window // 2
        start = max(0, i - half)
        end = min(n, i + half + 1)
        local_window = raw_sales[start:end]
        if len(local_window) < 3:
            continue
        median_val = statistics.median(local_window)
        limit = max(median_val * threshold, min_threshold)
        local_medians[i] = round(median_val, 1)
        outlier_limits[i] = round(limit, 1)
        if raw_sales[i] > limit:
            excess = raw_sales[i] - limit
            normalized[i] = limit
            is_outlier[i] = True
            excess_removed[i] = excess
            spread_start = max(0, i - spread)
            spread_end = min(n, i + spread + 1)
            neighbors = [j for j in range(spread_start, spread_end) if j != i]
            if not neighbors:
                continue
            neighbor_sales = [max(raw_sales[j], 1) for j in neighbors]
            total_weight = sum(neighbor_sales)
            for idx, j in enumerate(neighbors):
                proportion = neighbor_sales[idx] / total_weight
                share = excess * proportion
                normalized[j] += share
                excess_received[j] += share

    cum = 0
    for i, item in enumerate(daily_sales_list):
        item["normalizedSales"] = round(normalized[i], 1)
        cum += normalized[i]
        item["cumulativeNormalized"] = round(cum, 1)
        item["localMedian"] = local_medians[i]
        item["outlierLimit"] = outlier_limits[i]
        item["isOutlier"] = is_outlier[i]
        item["excessRemoved"] = round(excess_removed[i], 1)
        item["excessReceived"] = round(excess_received[i], 1)

    return daily_sales_list


def get_kit_basico_cost(db: Session, projeto_id: int) -> float:
    """
    Busca o custo total do Kit Básico para um projeto.
    Soma os valores unitários de todos os itens do kit com nome 'Básico'.
    Retorna 50.0 como fallback se não encontrar.
    """
    try:
        cadastro = db.query(CadastroEvento).filter(
            CadastroEvento.projeto_id == projeto_id
        ).first()
        
        if not cadastro:
            return 50.0
        
        kit_basico = db.query(CadastroKitProduto).filter(
            CadastroKitProduto.cadastro_id == cadastro.id,
            CadastroKitProduto.kit.ilike('%básico%')
        ).first()
        
        if not kit_basico:
            kit_basico = db.query(CadastroKitProduto).filter(
                CadastroKitProduto.cadastro_id == cadastro.id,
                CadastroKitProduto.kit.ilike('%basico%')
            ).first()
        
        if not kit_basico:
            return 50.0
        
        itens = db.query(CadastroKitProdutoItem).filter(
            CadastroKitProdutoItem.kit_produto_id == kit_basico.id
        ).all()
        
        if not itens:
            return 50.0
        
        total = sum(float(item.valor_unitario or 0) for item in itens)
        return total if total > 0 else 50.0
        
    except Exception as e:
        logger.error(f"Erro ao buscar custo do Kit Básico para projeto {projeto_id}: {e}")
        return 50.0

def get_kit_basico_costs_batch(db: Session, projeto_ids: List[int]) -> dict:
    """
    Busca o custo do Kit Básico para vários projetos de uma vez.
    Retorna dict {projeto_id: custo}.
    """
    costs = {}
    
    try:
        cadastros = db.query(CadastroEvento).filter(
            CadastroEvento.projeto_id.in_(projeto_ids)
        ).all()
        
        cadastro_map = {c.projeto_id: c.id for c in cadastros}
        
        if not cadastro_map:
            return {pid: 50.0 for pid in projeto_ids}
        
        kits = db.query(CadastroKitProduto).filter(
            CadastroKitProduto.cadastro_id.in_(list(cadastro_map.values())),
            (CadastroKitProduto.kit.ilike('%básico%') | CadastroKitProduto.kit.ilike('%basico%'))
        ).all()
        
        kit_map = {}
        for kit in kits:
            for pid, cid in cadastro_map.items():
                if kit.cadastro_id == cid:
                    kit_map[pid] = kit.id
                    break
        
        if kit_map:
            itens = db.query(CadastroKitProdutoItem).filter(
                CadastroKitProdutoItem.kit_produto_id.in_(list(kit_map.values()))
            ).all()
            
            item_costs = {}
            for item in itens:
                if item.kit_produto_id not in item_costs:
                    item_costs[item.kit_produto_id] = 0
                item_costs[item.kit_produto_id] += float(item.valor_unitario or 0)
            
            for pid, kit_id in kit_map.items():
                costs[pid] = item_costs.get(kit_id, 50.0)
                if costs[pid] == 0:
                    costs[pid] = 50.0
        
        for pid in projeto_ids:
            if pid not in costs:
                costs[pid] = 50.0
                
    except Exception as e:
        logger.error(f"Erro ao buscar custos de Kit Básico em batch: {e}")
        costs = {pid: 50.0 for pid in projeto_ids}
    
    return costs


def _build_kit_cost_batch_data(db: Session, all_projeto_ids: List[int], ano: Optional[int] = None) -> dict:
    """
    Pré-computa dados de custo de kit por bundle para todos os projetos em um único batch.

    Retorna um dict com:
      - 'bundle_custo'    : {bundle_entity_id: custo_kit}  — apenas bundles com custo_kit no KitConfig
      - 'bundle_qty'      : {bundle_entity_id: qty}        — contagem Magento por bundle
      - 'proj_to_bundles' : {projeto_id: set(bundle_entity_ids)} — mapeamento projeto → bundles
      - 'basico_costs'    : {projeto_id: custo}             — custo do Kit Básico (fallback)

    Usado para calcular margemRealizadaKitsTotal = receita - Σ(custo_kit × qty_kit) no list endpoint,
    de forma que o Dashboard mostre a mesma margem que o Dash ISC (que usa get_margem_por_kit).
    """
    from ...models.kit_config import KitConfig

    result = {
        "bundle_custo": {},
        "bundle_qty": {},
        "proj_to_bundles": {},
        "basico_costs": get_kit_basico_costs_batch(db, all_projeto_ids),
    }

    if not all_projeto_ids:
        return result

    try:
        projetos = db.query(DimProjeto).filter(DimProjeto.id.in_(all_projeto_ids)).all()
        proj_by_id = {p.id: p for p in projetos}

        proj_to_mev: dict = {}
        all_mev_ids: set = set()

        for pid in all_projeto_ids:
            proj = proj_by_id.get(pid)
            if not proj or not proj.codigo:
                continue
            sku = proj.codigo.upper().strip()
            q = db.query(SkuMapping).filter(
                SkuMapping.sku == sku,
                SkuMapping.fonte == 'MAGENTO',
                SkuMapping.ativo == True,
            )
            if ano:
                q = q.filter(SkuMapping.ano == ano)
            mev_ids = set()
            for sm in q.all():
                if sm.id_externo:
                    try:
                        mev_ids.add(int(sm.id_externo))
                    except (TypeError, ValueError):
                        pass
            if mev_ids:
                proj_to_mev[pid] = mev_ids
                all_mev_ids.update(mev_ids)

        if not all_mev_ids:
            return result

        kc_records = db.query(KitConfig).filter(
            KitConfig.id_evento.in_(list(all_mev_ids)),
            KitConfig.tipo_kit.isnot(None),
            KitConfig.custo_kit.isnot(None),
            KitConfig.ignorado == False,
        ).all()

        bundle_custo: dict = {}
        mev_to_bundles: dict = {}
        seen_bids: set = set()
        for kc in kc_records:
            if kc.bundle_entity_id in seen_bids:
                continue
            seen_bids.add(kc.bundle_entity_id)
            bundle_custo[kc.bundle_entity_id] = float(kc.custo_kit)
            mev_to_bundles.setdefault(kc.id_evento, set()).add(kc.bundle_entity_id)

        proj_to_bundles: dict = {}
        for pid, mev_ids in proj_to_mev.items():
            bids: set = set()
            for mev_id in mev_ids:
                bids.update(mev_to_bundles.get(mev_id, set()))
            if bids:
                proj_to_bundles[pid] = bids

        result["bundle_custo"] = bundle_custo
        result["proj_to_bundles"] = proj_to_bundles

        if not bundle_custo or db_module.engine_magento is None:
            return result

        all_bundle_ids = list(bundle_custo.keys())
        # OTIMIZAÇÃO (broad fix): lidera com sales_order_item.product_id IN (índice).
        _sql_cnt = (
            "SELECT /*+ MAX_EXECUTION_TIME(20000) */ STRAIGHT_JOIN\n"
            "    soi_parent.product_id              AS bundle_entity_id,\n"
            "    COUNT(DISTINCT soi_parent.item_id) AS qtd\n"
            "FROM sales_order_item soi_parent\n"
            "INNER JOIN sales_order so\n"
            "       ON so.entity_id = soi_parent.order_id\n"
            "WHERE\n"
            "    soi_parent.product_type = 'bundle'\n"
            "AND soi_parent.product_id   IN :bundle_ids\n"
            "AND so.created_at >= DATE_SUB(CURDATE(), INTERVAL 15 MONTH)\n"
            "AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link',\n"
            "                   'reembolso_parcial', 'closed', 'retirado')\n"
            "AND so.state != 'canceled'\n"
            "AND so.base_grand_total > 0\n"
            "AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)\n"
            "AND so.created_at < CURDATE() + INTERVAL 1 DAY\n"
            "AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')\n"
            "AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')\n"
            "AND so.increment_id NOT REGEXP '-[0-9]'\n"
            "GROUP BY soi_parent.product_id"
        )
        def _kit_cost_count_work(conn):
            return conn.execute(
                text(_sql_cnt).bindparams(bindparam("bundle_ids", expanding=True)),
                {"bundle_ids": all_bundle_ids},
            ).fetchall()
        try:
            rows = magento_run(_kit_cost_count_work, label="kit_cost_count", profile="background")
            bundle_qty: dict = {int(r[0]): int(r[1] or 0) for r in rows}
            result["bundle_qty"] = bundle_qty
            logger.info(
                f"[kit_cost_batch] Magento count: {len(all_bundle_ids)} bundles → {len(bundle_qty)} resultados"
            )
        except Exception as e:
            logger.warning(f"[kit_cost_batch] Falha na query Magento de contagem: {e}")

    except Exception as e:
        logger.error(f"Erro em _build_kit_cost_batch_data: {e}")

    return result


def _get_group_kit_cost_sum(
    proj_ids: List[int],
    batch: dict,
    current_sales: int,
) -> Optional[float]:
    """
    Calcula Σ(custo_kit × qty_kit) para um grupo de projetos usando dados do batch.
    Retorna None se não há dados de KitConfig com custo.

    Para bundles sem dados Magento ainda, usa custo × 0 (sem contribuição).
    Para vendas não mapeadas a nenhum bundle com custo, aplica o custo básico como fallback.
    """
    bundle_custo = batch.get("bundle_custo", {})
    bundle_qty = batch.get("bundle_qty", {})
    proj_to_bundles = batch.get("proj_to_bundles", {})
    basico_costs = batch.get("basico_costs", {})

    seen_bids: set = set()
    total_kit_cost = 0.0
    qty_mapped = 0
    has_any_bundle = False

    for pid in proj_ids:
        bids = proj_to_bundles.get(pid, set())
        for bid in bids:
            if bid in seen_bids:
                continue
            seen_bids.add(bid)
            has_any_bundle = True
            custo = bundle_custo.get(bid, 0.0)
            qty = bundle_qty.get(bid, 0)
            total_kit_cost += custo * qty
            qty_mapped += qty

    if not has_any_bundle:
        return None

    qty_remaining = max(0, current_sales - qty_mapped)
    if qty_remaining > 0:
        basico_avg = 0.0
        n = 0
        for pid in proj_ids:
            bc = basico_costs.get(pid)
            if bc is not None and bc > 0:
                basico_avg += bc
                n += 1
        if n > 0:
            basico_avg /= n
        total_kit_cost += basico_avg * qty_remaining

    return total_kit_cost


def get_kit_breakdown_for_projetos(db: Session, projeto_ids: List[int], ano: Optional[int] = None) -> dict:
    """
    Returns {projeto_id: [{tipoKit: str, custoKit: float|None}]} for ALL kit types
    registered in CadastroKitProduto for each projeto.
    Cost resolution: kit_config.custo_kit override (matched by tipo_kit == kit name) first,
    then sum of CadastroKitProdutoItem values.
    """
    from ...models.kit_config import KitConfig

    if not projeto_ids:
        return {}

    try:
        result: dict = {pid: [] for pid in projeto_ids}

        # Build KitConfig override map: tipo_kit (name) -> custo_kit
        # We fetch all kit configs that have custo_kit set and tipo_kit set
        override_map: dict = {}
        all_overrides = db.query(KitConfig).filter(
            KitConfig.tipo_kit.isnot(None),
            KitConfig.custo_kit.isnot(None),
        ).all()
        for ov in all_overrides:
            if ov.tipo_kit and ov.tipo_kit not in override_map:
                override_map[ov.tipo_kit] = float(ov.custo_kit)

        for pid in projeto_ids:
            cad = db.query(CadastroEvento).filter(CadastroEvento.projeto_id == pid).first()
            if not cad:
                continue

            kit_configs_db = db.query(CadastroKitProduto).filter(
                CadastroKitProduto.cadastro_id == cad.id
            ).all()
            if not kit_configs_db:
                continue

            kit_ids = [kc.id for kc in kit_configs_db]
            all_items = db.query(CadastroKitProdutoItem).filter(
                CadastroKitProdutoItem.kit_produto_id.in_(kit_ids)
            ).all()
            items_by_kit: dict = {}
            for item in all_items:
                items_by_kit.setdefault(item.kit_produto_id, []).append(item)

            for kc in kit_configs_db:
                kit_name = (kc.kit or '').strip()
                if not kit_name:
                    continue
                # Cost override from KitConfig takes priority
                if kit_name in override_map:
                    custo: float | None = override_map[kit_name]
                else:
                    cost_sum = sum(float(i.valor_unitario or 0) for i in items_by_kit.get(kc.id, []))
                    custo = round(cost_sum, 2) if cost_sum > 0 else None

                result[pid].append({
                    "tipoKit": kit_name,
                    "custoKit": round(custo, 2) if custo is not None else None,
                })

        return result

    except Exception as e:
        logger.error(f"Erro ao buscar kit breakdown para projetos: {e}")
        return {}


def _calc_margin_fields(budget_ticket: float, kit_cost: float, sales_goal: int,
                        avg_ticket: float, current_sales: int, current_receita: float) -> dict:
    has_budget = budget_ticket > 0 and kit_cost > 0
    has_sales = current_sales > 0 and avg_ticket > 0

    margem_orcada_unit = round(budget_ticket - kit_cost, 2) if has_budget else 0.0
    margem_orcada_total = round(margem_orcada_unit * sales_goal, 2) if has_budget else 0.0
    # Margem bruta orçada % = (ticket_orcado - custo_kit) / ticket_orcado
    margem_orcada_pct = round((margem_orcada_unit / budget_ticket) * 100, 1) if has_budget else 0.0

    margem_realizada_unit = round(avg_ticket - kit_cost, 2) if has_sales else 0.0
    margem_realizada_total = round(current_receita - (kit_cost * current_sales), 2) if has_sales else 0.0
    # Margem bruta realizada % = (ticket_medio - custo_kit) / ticket_medio
    margem_realizada_pct = round((margem_realizada_unit / avg_ticket) * 100, 1) if has_sales else 0.0

    # Taxa de realização da margem = quanto do total de margem orçada foi capturado até agora
    # Fórmula: margem_realizada_R$ / margem_orcada_R$ * 100
    # Indica o progresso financeiro real vs. o plano (ex: 45% = capturou 45% da margem total planejada)
    margem_realizacao_rate = 0.0
    if margem_orcada_total > 0 and has_sales:
        margem_realizacao_rate = round((margem_realizada_total / margem_orcada_total) * 100, 1)

    receita_orcada_total = round(budget_ticket * sales_goal, 2) if has_budget else 0.0

    return {
        "kitCostPerUnit": round(kit_cost, 2),
        "receitaOrcadaTotal": receita_orcada_total,
        "currentReceita": round(current_receita, 2) if has_sales else 0.0,
        "margemOrcadaUnit": margem_orcada_unit,
        "margemOrcadaTotal": margem_orcada_total,
        "margemOrcadaPct": margem_orcada_pct,
        "margemRealizadaUnit": margem_realizada_unit,
        "margemRealizadaTotal": margem_realizada_total,
        "margemRealizadaPct": margem_realizada_pct,
        "margemRealizacaoRate": margem_realizacao_rate,
    }


# Cache em memória para resultados de receita Magento por bundle.
# A revenue query (com join de filhos por nome) é lenta para eventos de alto volume.
# O dado de receita muda raramente dentro de uma sessão — TTL de 4h é suficiente.
_margem_rev_cache: dict = {}  # frozenset(bundle_ids) → (rev_by_bid: dict, timestamp: float)
_MARGEM_REV_TTL_SECONDS = 14400  # 4 horas

# Cache de falhas da revenue query: evita re-tentar o Magento repetidamente quando
# a query já falhou recentemente (ex: timeout). O cooldown é adaptativo:
# falhas isoladas têm cooldown curto (60s); falhas repetidas crescem até 30 min.
# Estrutura: frozenset(bundle_ids) → (timestamp_ultima_falha, n_falhas_consecutivas)
_margem_rev_failure_cache: dict = {}
# Tabela de cooldowns adaptativos (segundos) por número de falhas consecutivas.
# 1ª falha: 60s (transitório provável). 2ª: 5 min. 3ª+: 15 min. 5ª+: 30 min (cap).
_MARGEM_REV_FAILURE_COOLDOWNS = [60, 300, 900, 900, 1800]

# Cache para resultados do count_query (qtd de inscrições por bundle_entity_id).
# Mesmo TTL de 4h que o _margem_rev_cache — garante que uma contagem bem-sucedida
# sobreviva a timeouts posteriores do Magento (kit total não cai para 0 no fallback).
_margem_cnt_cache: dict = {}   # frozenset(bundle_ids) → ({bid: qtd}, monotonic_ts)
_MARGEM_CNT_TTL_SECONDS = 14400  # 4 horas

# Cooldown GLOBAL de Magento para margem: quando qualquer revenue_query falha,
# todos os eventos entram em cooldown por _MARGEM_GLOBAL_COOLDOWN_S segundos.
# Evita que múltiplos eventos simultâneos tentem o Magento instável em paralelo,
# cada um bloqueando um thread por 90s × 2 tentativas antes de desistir.
# Após o cooldown, apenas um evento retenta; se ele falhar, o cooldown se renova.
_margem_magento_global_failure_ts: Optional[float] = None
_margem_magento_global_failure_count: int = 0
_MARGEM_GLOBAL_COOLDOWN_S = 300  # 5 minutos de cooldown global após qualquer falha


# ---------------------------------------------------------------------------
# Singleflight para as 4 queries pesadas do modal de Margem por Tipo de Kit.
# As 4 (count primária, revenue primária, fallback count, fallback receita)
# rodam contra sales_order/sales_order_item (~milhões de linhas, 2 anos de
# histórico, join triplo, regex no increment_id). Os caches TTL pré-existentes
# (_margem_rev_cache, _margem_cnt_cache, 4h cada) já cuidam de freshness; o
# que faltava era dedup de CONCORRÊNCIA: N usuários abrindo o mesmo modal
# logo após cache miss = N queries paralelas idênticas no Magento.
#
# Este wrapper colapsa essas chamadas em 1 execução compartilhada: o "leader"
# executa work_fn; "followers" esperam o resultado dele. Não introduz cache
# próprio (cuidado para não duplicar com os TTLs existentes), apenas dedup
# de concorrência. Resultado/exceção propagam APENAS aos participantes do
# voo corrente (estado por-flight em referência local, nunca global stale).
#
# Lógica preservada: work_fn é o mesmo código de antes (mesma query, mesmos
# bindings, mesmo retry, mesmo cache TTL no caller). Singleflight é
# transparente — se não há concorrência, a chamada se comporta exatamente
# como `work_fn()` direto.
# ---------------------------------------------------------------------------
_MARGEM_SF_LOCK = _threading.Lock()
_MARGEM_SF_FLIGHTS: dict = {}   # key -> {"event": Event, "result": Any, "exc": BaseException|None}

# ---------------------------------------------------------------------------
# Cooldown para force_refresh do endpoint de Margem por Kit.
# Quando o usuário abre/reabre o modal de Margem repetidamente, cada clique
# com force_refresh=True dispara count+revenue (15-90s cada) no Magento.
# O cooldown rebaixa force_refresh para False dentro da janela (default 10min),
# fazendo o caminho normal de cache/snapshot servir o resultado anterior.
# Chave: (tuple sorted projeto_ids, ano normalizado, incluir_cortesias).
# Resultado entregue é idêntico (mesmo cache); só evita re-execução cara.
# ---------------------------------------------------------------------------
_MARGEM_FORCE_REFRESH_COOLDOWN_SECONDS = int(os.getenv("MARGEM_FORCE_REFRESH_COOLDOWN_SECONDS", "600"))
_margem_force_refresh_last_ts: dict = {}
_margem_force_refresh_lock = _threading.Lock()

# ---------------------------------------------------------------------------
# Cache TTL para vendas-kit-detalhe (breakdown por kit/canal/modalidade).
# A query é STRAIGHT_JOIN + agregações + CASEs aninhados, custa 5-30s no
# Magento e os dados raramente mudam minuto-a-minuto. TTL curto (5min default)
# preserva frescor sem martelar o Magento em reaberturas do modal.
# Chave: (frozenset(magento_event_ids), ano, incluir_cortesias).
# ---------------------------------------------------------------------------
_VENDAS_KIT_DETALHE_TTL_SECONDS = int(os.getenv("VENDAS_KIT_DETALHE_TTL_SECONDS", "300"))
_vendas_kit_detalhe_cache: dict = {}   # key -> (rows_list, mono_ts)
_vendas_kit_detalhe_lock = _threading.Lock()

# Cap defensivo: evita crescimento ilimitado dos dicts de cooldown/cache em
# memória. Quando o tamanho ultrapassar o cap, remove as entradas mais antigas
# (sem refazer trabalho — só esquece registros de cooldown vencidos).
_MARGEM_FORCE_REFRESH_MAX_ENTRIES = int(os.getenv("MARGEM_FORCE_REFRESH_MAX_ENTRIES", "500"))
_VENDAS_KIT_DETALHE_MAX_ENTRIES = int(os.getenv("VENDAS_KIT_DETALHE_MAX_ENTRIES", "500"))


def _prune_oldest_inplace(d: dict, max_entries: int, ts_index: int = 0) -> None:
    """Remove entradas mais antigas quando o dict ultrapassa o cap.
    ts_index: posição do timestamp dentro do valor (0 se valor é float ts,
    1 se valor é (data, ts) como no cache de vendas-kit-detalhe).
    Caller deve segurar o lock apropriado.
    """
    if len(d) <= max_entries:
        return
    overflow = len(d) - max_entries
    if ts_index == 0:
        sorted_keys = sorted(d.keys(), key=lambda k: d[k])
    else:
        sorted_keys = sorted(d.keys(), key=lambda k: d[k][ts_index])
    for k in sorted_keys[:overflow + max(1, max_entries // 10)]:
        d.pop(k, None)


def _margem_singleflight(key, work_fn, label: str):
    """Singleflight wrapper genérico (sem TTL próprio) para as 4 queries de Margem.

    `key` deve ser hashable e identificar unicamente o trabalho (ex.: tuple
    contendo kind + frozenset(bundle_ids) + flag de cortesia).
    `work_fn` é callable sem args; pode retornar qualquer shape (tuple, list).
    Exceção do leader é re-raised em todos os followers daquele voo.
    Follower que sofre timeout (120s) NÃO vira leader nem lê estado global;
    executa direto com log de warning, e remove o flight órfão para que o
    próximo caller possa se eleger normalmente.
    """
    with _MARGEM_SF_LOCK:
        flight = _MARGEM_SF_FLIGHTS.get(key)
        if flight is not None:
            leader = False
        else:
            flight = {"event": _threading.Event(), "result": None, "exc": None}
            _MARGEM_SF_FLIGHTS[key] = flight
            leader = True

    if not leader:
        flight["event"].wait(timeout=120.0)
        if flight["event"].is_set():
            # Lê APENAS o resultado deste voo (referência local), nunca estado global stale.
            if flight["exc"] is not None:
                raise flight["exc"]
            return flight["result"]
        logger.warning(
            f"[Margem] singleflight follower timeout (120s) on {label}; "
            "leader não publicou — executando query direta sem dedup"
        )
        # Limpeza defensiva: libera flight órfão (compare-by-identity).
        with _MARGEM_SF_LOCK:
            if _MARGEM_SF_FLIGHTS.get(key) is flight:
                _MARGEM_SF_FLIGHTS.pop(key, None)

    result = None
    exc_caught = None
    try:
        result = work_fn()
    except BaseException as e:
        exc_caught = e
    finally:
        if leader:
            with _MARGEM_SF_LOCK:
                flight["result"] = result
                flight["exc"] = exc_caught
                # Identity-safe pop: se um follower já fez cleanup por timeout
                # (120s) e outro caller criou um flight NOVO para o mesmo key,
                # não podemos remover o flight do sucessor. Só removemos se
                # o slot ainda referencia o nosso voo.
                if _MARGEM_SF_FLIGHTS.get(key) is flight:
                    _MARGEM_SF_FLIGHTS.pop(key, None)
            flight["event"].set()
    if exc_caught is not None:
        raise exc_caught
    return result


def _margem_rev_cooldown_for(n_failures: int) -> int:
    if n_failures <= 0:
        return 0
    idx = min(n_failures - 1, len(_MARGEM_REV_FAILURE_COOLDOWNS) - 1)
    return _MARGEM_REV_FAILURE_COOLDOWNS[idx]


def _execute_magento_with_retry(query, params, label: str, max_attempts: int = 2, backoff_s: float = 1.5):
    """Executa uma query no engine_magento com retry — wrapper legado.

    Mantido por compatibilidade com chamadores que esperam ``(rows, elapsed)``.
    Internamente delega para :func:`magento_run` (helper centralizado em
    ``app.core.db_retry``), que já traz política unificada de retry,
    backoff exponencial e classificação de erros transitórios.
    """
    import time as __time
    profile = "background" if max_attempts >= 3 else "request"

    def _work(conn):
        _t0 = __time.monotonic()
        _rows = conn.execute(query, params).fetchall()
        return _rows, __time.monotonic() - _t0

    return magento_run(_work, label=f"margem:{label}", profile=profile)


def _margem_por_kit_is_degraded(rows: Optional[list]) -> bool:
    """Detecta se a tabela margemPorKit está degradada por dados parciais do Magento.

    Retorna True quando alguma linha não-CONSOLIDADO tem qtd > 0 mas
    receita = 0. Esse cenário ocorre quando a revenue_query do Magento
    "responde" (sem exceção) mas devolve 0 para um ou mais bundles —
    o que faz `margem = receita - custo*qtd` virar negativa e exibe número
    errado para o usuário. Usado como salvaguarda antes de sobrescrever o
    EventoDetailSnapshot persistido.
    """
    if not rows:
        return False
    for r in rows:
        if not isinstance(r, dict):
            continue
        if r.get('tipoKit') == 'CONSOLIDADO':
            continue
        try:
            _qtd_d = int(r.get('qtd') or 0)
            _rec_d = float(r.get('receitaLiquida') or 0)
        except (TypeError, ValueError):
            continue
        if _qtd_d > 0 and _rec_d <= 0:
            return True
    return False


def _consolidate_margem_avisos(avisos: Optional[list]) -> list:
    """Colapsa os avisos de margem em NO MÁXIMO uma mensagem clara.

    Até 3 banners simultâneos (AVISO de instabilidade + INFO de idade do
    snapshot + mensagem de leitura parcial sem prefixo) descreviam o MESMO
    estado: "a leitura ao vivo não veio completa; o que está na tela é o
    último dado confiável". Prioridade:

    1. Mensagem de leitura parcial/correção bloqueada (sem prefixo) → vira UM
       AVISO âmbar, incorporando a idade do snapshot quando conhecida.
    2. AVISO(s) → mantém o primeiro, anexando a idade do snapshot se um INFO
       a trazia.
    3. Só INFO(s) → mantém o primeiro.

    Preserva a semântica do frontend: AVISO → badge "Sincronizando" + botão
    "Atualizar dados"; INFO → badge "Snapshot".

    ATENÇÃO: mensagens SEM prefixo são reservadas aos dois estados canônicos
    (leitura parcial / atualização em andamento) e são colapsadas na mensagem
    genérica correspondente. Qualquer NOVO aviso de margem deve usar prefixo
    "INFO:" ou "AVISO:" para não perder o texto aqui.
    """
    if not avisos:
        return []
    _clean = [a for a in avisos if isinstance(a, str) and a.strip()]
    if not _clean:
        return []
    infos = [a for a in _clean if a.startswith("INFO:")]
    ambers = [a for a in _clean if a.startswith("AVISO:")]
    reds = [a for a in _clean if not a.startswith(("INFO:", "AVISO:"))]

    idade_txt = None
    for a in infos:
        m = _re.search(r"até\s+([\d.,]+\s*(?:min|h|dia\(s\)))\s+atrás", a)
        if m:
            idade_txt = m.group(1).strip()
            break

    if reds:
        if any("em andamento" in a for a in reds):
            return [
                "AVISO: Outra atualização está em andamento — exibindo os últimos "
                "dados confiáveis. Tente novamente em instantes."
            ]
        _idade = f" (dados de {idade_txt} atrás)" if idade_txt else ""
        return [
            "AVISO: A atualização ao vivo veio incompleta — mantendo os últimos "
            f"dados confiáveis{_idade}. Tente atualizar novamente em alguns instantes."
        ]
    if ambers:
        principal = ambers[0].rstrip()
        if idade_txt and idade_txt not in principal:
            principal = f"{principal.rstrip('.')}. Últimos dados confiáveis: {idade_txt} atrás."
        return [principal]
    return [infos[0]]


def _load_prev_margem_rows(db: Session, evento_id, ano) -> Optional[list]:
    """Última margemPorKit ÍNTEGRA persistida no EventoDetailSnapshot.

    Usada quando um force-refresh volta parcial: exibir a tabela parcial
    (contagem ao vivo incompleta misturada com receita de snapshot) subestima
    a Margem Realizada. Nesses casos restauramos a última tabela consistente,
    coerente com o piso do card preservado pelo guard de currentSales.
    """
    try:
        from ...models.evento_detail_snapshot import EventoDetailSnapshot as _EDS_prev
        row = db.query(_EDS_prev).filter(
            _EDS_prev.evento_id == evento_id,
            _EDS_prev.ano == ano,
        ).first()
        if row and isinstance(row.payload, dict):
            evt = row.payload.get("evento")
            if isinstance(evt, dict):
                rows = evt.get("margemPorKit")
                if rows and not _margem_por_kit_is_degraded(rows):
                    return rows
    except Exception as e:
        logger.debug(f"[Margem] prev margemPorKit '{evento_id}/{ano}': {e}")
    return None


def _build_consistency_warning(total_isc: Optional[int], margem_por_kit: Optional[list]) -> Optional[dict]:
    """
    Compara total de inscrições do card ISC com a soma da tabela Margem por Tipo de Kit.
    Retorna um dict de aviso quando a diferença excede a tolerância (2% ou 20 inscrições).
    """
    try:
        if not margem_por_kit or not total_isc or total_isc <= 0:
            return None
        total_margem = sum(int(row.get("qtd", 0) or 0) for row in margem_por_kit)
        if total_margem <= 0:
            return None
        diff = total_isc - total_margem
        abs_diff = abs(diff)
        diff_pct = (abs_diff / total_isc) * 100 if total_isc else 0.0
        tolerance_abs = max(20, int(total_isc * 0.02))
        if abs_diff <= tolerance_abs:
            return None
        return {
            "totalIsc": int(total_isc),
            "totalMargem": int(total_margem),
            "diff": int(diff),
            "diffAbs": int(abs_diff),
            "diffPct": round(diff_pct, 2),
            "tolerance": int(tolerance_abs),
        }
    except Exception as _e:
        logger.warning(f"[Consistency] falha ao calcular aviso: {_e}")
        return None


def _bundle_ids_for_projetos(db: Session, projeto_ids: list, ano: Optional[int] = None) -> list:
    """Resolve os bundle_entity_ids (KitConfig) ligados aos projetos via SKU →
    evento Magento. Espelha a mesma resolução que `get_margem_por_kit` usa
    internamente. Usado pela correção autoritativa de inscritos para escopar o
    sync de margem por bundle a um único evento (ignorando freeze).
    """
    from ...models.kit_config import KitConfig
    if not projeto_ids:
        return []
    proj_rows = db.query(DimProjeto.id, DimProjeto.codigo).filter(
        DimProjeto.id.in_(projeto_ids)
    ).all()
    magento_event_ids: set = set()
    for _pid, _codigo in proj_rows:
        if not _codigo:
            continue
        _sku = _codigo.upper().strip()
        _q = db.query(SkuMapping).filter(
            SkuMapping.sku == _sku,
            SkuMapping.fonte == 'MAGENTO',
            SkuMapping.ativo == True,  # noqa: E712
        )
        if ano:
            _q = _q.filter(SkuMapping.ano == ano)
        for _sm in _q.all():
            if _sm.id_externo:
                try:
                    magento_event_ids.add(int(_sm.id_externo))
                except (ValueError, TypeError):
                    continue
    if not magento_event_ids:
        return []
    _rows = db.query(KitConfig.bundle_entity_id).filter(
        KitConfig.id_evento.in_(list(magento_event_ids)),
        KitConfig.tipo_kit.isnot(None),
        KitConfig.ignorado == False,  # noqa: E712
        KitConfig.bundle_entity_id.isnot(None),
    ).distinct().all()
    return [r[0] for r in _rows if r[0] is not None]


def get_margem_por_kit(
    db: Session,
    projeto_ids: list,
    ano: Optional[int] = None,
    card_total_qty: Optional[int] = None,
    card_total_receita: Optional[float] = None,
    card_kit_cost_avg: Optional[float] = None,
    avisos_out: Optional[list] = None,
    force_refresh: bool = False,
    incluir_cortesias: bool = False,
    meta_out: Optional[dict] = None,
) -> list:
    """Quebra de margem por tipo de kit via vendas Magento bundle.

    `meta_out` (opcional): quando passado, recebe a procedência da contagem e da
    receita (`count_source` / `revenue_source`) em cada ramo do pipeline de
    cache/snapshot/live. Usado pela correção autoritativa de inscritos para
    distinguir uma leitura ao vivo VERIFICADAMENTE completa ("live"/"live") de
    uma servida por cache/snapshot/parcial — só a primeira autoriza baixar o
    valor de um evento concluído.
    """
    from ...models.kit_config import KitConfig

    if meta_out is not None:
        meta_out.setdefault("count_source", "none")
        meta_out.setdefault("revenue_source", "none")

    if not projeto_ids:
        return []

    # Cooldown de force_refresh por (projeto_ids, ano, cortesias). Quando o
    # usuário clica "Atualizar" repetidamente no modal de Margem, só o primeiro
    # clique dentro da janela passa força bruta no Magento; demais são
    # rebaixados a leitura normal de cache/snapshot (mesmo resultado).
    _frc_key = None
    _frc_stamp_set_by_this_request = False
    _frc_my_stamp = None
    if force_refresh and _MARGEM_FORCE_REFRESH_COOLDOWN_SECONDS > 0:
        _frc_now = _time.time()
        _frc_ano = ano if ano is not None else today_brazil().year
        _frc_key = (tuple(sorted(projeto_ids)), _frc_ano, bool(incluir_cortesias))
        with _margem_force_refresh_lock:
            _frc_last = _margem_force_refresh_last_ts.get(_frc_key)
            if _frc_last is not None and (_frc_now - _frc_last) < _MARGEM_FORCE_REFRESH_COOLDOWN_SECONDS:
                _frc_age = int(_frc_now - _frc_last)
                logger.info(
                    f"[Margem] force_refresh DEMOTED — cooldown {_frc_age}s "
                    f"< {_MARGEM_FORCE_REFRESH_COOLDOWN_SECONDS}s key={_frc_key}"
                )
                force_refresh = False
            else:
                _margem_force_refresh_last_ts[_frc_key] = _frc_now
                _prune_oldest_inplace(_margem_force_refresh_last_ts, _MARGEM_FORCE_REFRESH_MAX_ENTRIES, ts_index=0)
                _frc_stamp_set_by_this_request = True
                _frc_my_stamp = _frc_now
                logger.info(f"[Margem] force_refresh ACCEPTED — cooldown reset key={_frc_key}")

    try:
        # 1. Cadastro do Evento → Kits & Produtos serve APENAS como fonte de custo
        # por nome (auto-preenchimento). O nome dos kits exibidos e o custo final
        # vêm do KitConfig (mapeamento). Aqui só montamos um dicionário
        # {nome_kit -> custo_itens} para servir de fallback quando o KitConfig
        # não tiver custo_kit preenchido.
        kit_map: dict = {}
        cadastro_cost_by_name: dict = {}

        for pid in projeto_ids:
            cadastro = db.query(CadastroEvento).filter(CadastroEvento.projeto_id == pid).first()
            if not cadastro:
                continue

            kit_configs_db = db.query(CadastroKitProduto).filter(
                CadastroKitProduto.cadastro_id == cadastro.id
            ).all()
            if not kit_configs_db:
                continue

            kit_ids = [kc.id for kc in kit_configs_db]
            all_items = db.query(CadastroKitProdutoItem).filter(
                CadastroKitProdutoItem.kit_produto_id.in_(kit_ids)
            ).all()
            items_by_kit: dict = {}
            for item in all_items:
                items_by_kit.setdefault(item.kit_produto_id, []).append(item)

            for kc in kit_configs_db:
                kit_name = (kc.kit or "").strip()
                if not kit_name:
                    continue
                cost = sum(float(i.valor_unitario or 0) for i in items_by_kit.get(kc.id, []))
                # Se o mesmo nome aparece em múltiplos projetos, preserva o primeiro custo > 0.
                if kit_name not in cadastro_cost_by_name or (cost > 0 and cadastro_cost_by_name[kit_name] == 0):
                    cadastro_cost_by_name[kit_name] = cost

        # 2. SKU mappings filtrados por ano para evitar contaminação entre edições
        proj_by_id = {
            pid: db.query(DimProjeto).filter(DimProjeto.id == pid).first()
            for pid in projeto_ids
        }

        # Detecta evento finalizado para pular a porta de 25h do snapshot
        # (snapshot é autoridade absoluta para eventos finalizados — evita
        # chamada Magento desnecessária). Critério ALINHADO com o write-side
        # (snapshot_service._load_active_event_magento_ids):
        #   - frozen requer TODOS os projetos com data_evento conhecida E
        #     TODAS expiradas (data_evento < hoje - freeze_days).
        #   - Se ALGUM projeto tem data_evento NULL → NÃO é frozen
        #     (conservador, idem write-side: NULL = ativo).
        # Sem esse alinhamento, um kit com 1 projeto NULL + 1 antigo seria
        # tratado como frozen na leitura (snapshot stale) enquanto o write
        # continua sincronizando — divergência que poderia mascarar dados
        # mais novos.
        try:
            from ...services.snapshot_service import _freeze_after_days as _fad
            _freeze_days_kit = _fad()
        except Exception:
            _freeze_days_kit = 30
        _today_kit = date.today()
        _cutoff_kit = _today_kit - timedelta(days=_freeze_days_kit)
        _projs_kit = [p for p in proj_by_id.values() if p is not None]
        _has_null_date = any(p.data_evento is None for p in _projs_kit)
        _datas_kit = [p.data_evento for p in _projs_kit if p.data_evento is not None]
        _event_frozen = (
            bool(_datas_kit)
            and not _has_null_date
            and all(d < _cutoff_kit for d in _datas_kit)
        )
        # Opção B: a leitura (carregamento da tela/modal) SEMPRE serve do snapshot
        # PostgreSQL, independentemente da idade. A query pesada do Magento (receita
        # por bundle, ~90s) roda apenas no job batch noturno (sincronizar_margem_bundle_rev_batch),
        # nunca no caminho de request. Isso elimina a espera/timeout que o usuário sentia
        # ao abrir as telas. O snapshot é mantido atualizado pelo batch; quando ele não
        # existe (bootstrap) ou em force_refresh (botão Reconsolidar), o caminho live ainda
        # é usado. _event_frozen mantido por clareza histórica (já resultava em None).
        _snapshot_max_age_h = None

        def _get_sku_maps(pid, fonte):
            proj = proj_by_id.get(pid)
            if not proj or not proj.codigo:
                return []
            sku = proj.codigo.upper().strip()
            q = db.query(SkuMapping).filter(
                SkuMapping.sku == sku,
                SkuMapping.fonte == fonte,
                SkuMapping.ativo == True,
            )
            if ano:
                q = q.filter(SkuMapping.ano == ano)
            return q.all()

        # 3. Magento: deduplicação de event IDs e bundle IDs entre todos os projetos
        seen_magento_events: set = set()
        seen_bundle_ids: set = set()
        global_bundle_tipo_map: dict = {}  # bundle_entity_id -> tipo_kit
        custo_kit_override: dict = {}  # tipo_kit -> custo manual (kit_config.custo_kit)

        for pid in projeto_ids:
            for sm in _get_sku_maps(pid, 'MAGENTO'):
                if not sm.id_externo:
                    continue
                try:
                    magento_event_int = int(sm.id_externo)
                except (ValueError, TypeError):
                    continue
                if magento_event_int in seen_magento_events:
                    continue
                seen_magento_events.add(magento_event_int)

                bundles = db.query(KitConfig).filter(
                    KitConfig.id_evento == magento_event_int,
                    KitConfig.tipo_kit.isnot(None),
                    KitConfig.ignorado == False,
                ).all()
                for b in bundles:
                    if b.tipo_kit and b.bundle_entity_id not in seen_bundle_ids:
                        seen_bundle_ids.add(b.bundle_entity_id)
                        global_bundle_tipo_map[b.bundle_entity_id] = b.tipo_kit
                        if b.custo_kit is not None:
                            custo_kit_override[b.tipo_kit] = float(b.custo_kit)

        # Seed kit_map com TODOS os tipo_kit do mapeamento (KitConfig), mesmo sem
        # vendas. Assim o card lista exatamente os kits que o admin configurou.
        # O custo vem do KitConfig.custo_kit; se nulo, cai no custo-por-nome do
        # cadastro do evento (soma dos itens). Se nenhuma fonte tem valor, custo=0.
        for _tipo_kit in set(global_bundle_tipo_map.values()):
            if not _tipo_kit or _tipo_kit in kit_map:
                continue
            _seed_cost = 0.0
            _seed_has_cost = False
            if _tipo_kit in custo_kit_override:
                _seed_cost = custo_kit_override[_tipo_kit]
                _seed_has_cost = True
            elif _tipo_kit in cadastro_cost_by_name:
                _seed_cost = cadastro_cost_by_name[_tipo_kit]
                _seed_has_cost = _seed_cost > 0
            kit_map[_tipo_kit] = {
                "custo": _seed_cost,
                "ativo_categoria": None,
                "qtd": 0,
                "receita": 0.0,
                "has_cost": _seed_has_cost,
            }

        import datetime as _dt
        _ano = ano if ano else _dt.datetime.now().year

        # Fetch ticket_atual (special_price) per tipo_kit from Magento
        tipo_kit_ticket_atual: dict = {}
        if global_bundle_tipo_map and db_module.engine_magento is not None:
            from ..routes.kit_config import _fetch_magento_kits_cached
            _bid_set = set(global_bundle_tipo_map.keys())
            _kcs_sp = db.query(KitConfig).filter(
                KitConfig.bundle_entity_id.in_(list(_bid_set))
            ).all()
            _kc_mult_by_bid = {k.bundle_entity_id: (k.multiplicador or 1) for k in _kcs_sp}
            try:
                _mq_rows, _mq_cols = _fetch_magento_kits_cached(label="margem:ticket_atual_sp")
                _sp_by_bid: dict = {}
                for _r in _mq_rows:
                    _d = dict(zip(_mq_cols, _r))
                    _bid_v = _d.get("bundle_entity_id")
                    if _bid_v is None:
                        continue
                    _bid_i = int(_bid_v)
                    if _bid_i not in _bid_set or _bid_i in _sp_by_bid:
                        continue
                    _sp_v = float(_d["special_price"]) if _d.get("special_price") is not None else None
                    if _sp_v is None:
                        _sp_v = float(_d["price"]) if _d.get("price") is not None else None
                    if _sp_v is not None:
                        _sp_by_bid[_bid_i] = _sp_v
                for _bid_k, _tipo_k in global_bundle_tipo_map.items():
                    _sp_k = _sp_by_bid.get(_bid_k)
                    _mc_k = _kc_mult_by_bid.get(_bid_k, 1)
                    if _sp_k is not None:
                        tipo_kit_ticket_atual[_tipo_k] = round(_sp_k * _mc_k, 2)
            except Exception as _e_sp:
                logger.warning(f"Erro ao buscar special_price por tipo de kit: {_e_sp}")

        _skip_cortesia_filter = bool(incluir_cortesias)

        if global_bundle_tipo_map and db_module.engine_magento is not None:
            bundle_ids = list(global_bundle_tipo_map.keys())

            # Coleta os id_evento Magento para este grupo de projetos.
            # A query de contagem filtra via JOIN a catalog_product_entity_varchar
            # (attribute_id=321 = id_evento do bundle) para garantir que apenas
            # bundles vinculados ao evento correto sejam contados.
            # Critérios "somente Site" (alinhados com a query de receita e com
            # as funções de venda diária do ISC):
            #   - Sem janela de created_at (o JOIN cpev1 já escopa por evento)
            #   - Exclui GRUPOS/B2B (discount_description / coupon_code)
            #   - Exclui cortesias salvo quando o evento inclui cortesias
            #     (gateado por :skip_cortesia_filter)
            # Assim qtd e receita cobrem a MESMA população, e o total exibido
            # no detalhe não infla com cortesia/grupos.
            _id_eventos_cnt: list = [
                sm.id_externo
                for pid in projeto_ids
                for sm in _get_sku_maps(pid, 'MAGENTO')
                if sm.id_externo
            ]

            if _id_eventos_cnt:
                # Mantém bundle_ids IN como restrição de escopo (desempenho +
                # evita retornar bundles do evento fora do KitConfig).
                # O JOIN cpev1 valida que cada bundle pertence ao evento correto,
                # sem janela de created_at, mas com os filtros "somente Site"
                # (exclui GRUPOS/B2B e cortesias) iguais aos da query de receita.
                _sql_count = (
                    "SELECT /*+ MAX_EXECUTION_TIME(20000) */ STRAIGHT_JOIN\n"
                    "    soi_parent.product_id                  AS bundle_entity_id,\n"
                    "    COUNT(DISTINCT soi_parent.item_id)     AS qtd\n"
                    "FROM sales_order_item soi_parent\n"
                    "INNER JOIN sales_order so\n"
                    "       ON so.entity_id = soi_parent.order_id\n"
                    "INNER JOIN (\n"
                    "    SELECT cpev.entity_id\n"
                    "    FROM catalog_product_entity_varchar cpev\n"
                    "    INNER JOIN catalog_product_entity cpe\n"
                    "           ON cpe.entity_id = cpev.entity_id AND cpe.type_id = 'bundle'\n"
                    "    WHERE cpev.attribute_id = 321\n"
                    "      AND cpev.store_id     = 0\n"
                    "      AND cpev.value        IN :id_eventos\n"
                    ") AS cpev1 ON cpev1.entity_id = soi_parent.product_id\n"
                    "WHERE\n"
                    "    soi_parent.product_type = 'bundle'\n"
                    "AND soi_parent.product_id   IN :bundle_ids\n"
                    "AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')\n"
                    "AND so.state NOT IN ('canceled')\n"
                    "AND so.increment_id NOT REGEXP '-[0-9]'\n"
                    "AND (:skip_cortesia_filter OR so.base_grand_total > 0)\n"
                    "AND (:skip_cortesia_filter OR NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50))\n"
                    "AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')\n"
                    "AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')\n"
                    "GROUP BY soi_parent.product_id"
                )
                magento_count_query = text(_sql_count).bindparams(
                    bindparam("id_eventos", expanding=True),
                    bindparam("bundle_ids", expanding=True),
                ).bindparams(id_eventos=_id_eventos_cnt, skip_cortesia_filter=_skip_cortesia_filter)
            else:
                # Fallback: evento sem id_externo mapeado — usa bundle_ids com
                # janela clássica (comportamento legado)
                _sql_count = (
                    "SELECT /*+ MAX_EXECUTION_TIME(20000) */ STRAIGHT_JOIN\n"
                    "    soi_parent.product_id                  AS bundle_entity_id,\n"
                    "    COUNT(DISTINCT soi_parent.item_id)     AS qtd\n"
                    "FROM sales_order_item soi_parent\n"
                    "INNER JOIN sales_order so\n"
                    "       ON so.entity_id = soi_parent.order_id\n"
                    "WHERE\n"
                    "    soi_parent.product_type = 'bundle'\n"
                    "AND soi_parent.product_id   IN :bundle_ids\n"
                    "AND so.created_at >= DATE_SUB(CURDATE(), INTERVAL 15 MONTH)\n"
                    "AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')\n"
                    "AND so.state NOT IN ('canceled')\n"
                    "AND so.increment_id NOT REGEXP '-[0-9]'\n"
                    "AND (:skip_cortesia_filter OR so.base_grand_total > 0)\n"
                    "AND (:skip_cortesia_filter OR NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50))\n"
                    "AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')\n"
                    "AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')\n"
                    "GROUP BY soi_parent.product_id"
                )
                magento_count_query = text(_sql_count).bindparams(
                    bindparam("bundle_ids", expanding=True),
                    skip_cortesia_filter=_skip_cortesia_filter,
                )

            # Query 2: receita — mesmo padrão de partida (sales_order com índice created_at)
            # + join filho para valor da distância/modalidade.
            # Timeout 90s: eventos de alto volume precisam de ~50-55s em pico de carga.
            # Resultado armazenado em cache em memória por 4h (_margem_rev_cache).
            # A segunda chamada (mesmos bundle_ids) é instantânea.
            # OTIMIZAÇÃO (broad fix): lidera com sales_order_item.product_id IN.
            _sql_bundle = (
                "SELECT /*+ MAX_EXECUTION_TIME(90000) */ STRAIGHT_JOIN\n"
                "    soi_parent.product_id                                                              AS bundle_entity_id,\n"
                "    ROUND(SUM(soi_child.price - soi_child.discount_amount), 2)                        AS receita_liquida\n"
                "FROM sales_order_item soi_parent\n"
                "INNER JOIN sales_order so\n"
                "       ON so.entity_id = soi_parent.order_id\n"
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
                "    soi_parent.product_type = 'bundle'\n"
                "AND soi_parent.product_id   IN :bundle_ids\n"
                "AND so.created_at >= DATE_SUB(CURDATE(), INTERVAL 15 MONTH)\n"
                "AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')\n"
                "AND so.state != 'canceled'\n"
                "AND (:skip_cortesia_filter OR so.base_grand_total > 0)\n"
                "AND (:skip_cortesia_filter OR NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50))\n"
                "AND so.created_at < CURDATE() + INTERVAL 1 DAY\n"
                "AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')\n"
                "AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')\n"
                "AND so.increment_id NOT REGEXP '-[0-9]'\n"
                "GROUP BY soi_parent.product_id"
            )
            magento_bundle_query = text(_sql_bundle).bindparams(
                bindparam("bundle_ids", expanding=True),
                skip_cortesia_filter=_skip_cortesia_filter,
            )

            # Nota: NÃO reimporta `time as _time` aqui — já está no nível de módulo (linha 3).
            # Re-importar localmente causa Python a tratar `_time` como variável LOCAL em toda
            # a função get_margem_por_kit, gerando UnboundLocalError quando linhas anteriores
            # (ex.: 2821, no caminho force_refresh=True do Reconsolidar) referenciam `_time`
            # antes de chegar neste import condicional.

            def _log_margem_magento_failed(e_exc, label="primary"):
                _aviso = "AVISO: Conexão com Magento instável — buscando dados do snapshot mais recente."
                if avisos_out is not None and _aviso not in avisos_out:
                    avisos_out.append(_aviso)
                try:
                    from app.services.health_alert_service import log_and_alert as _la
                    from ...models.dimensoes import DimProjeto as _DP
                    _pid = projeto_ids[0] if projeto_ids else None
                    _nome = None
                    if _pid:
                        try:
                            _proj = db.query(_DP).filter(_DP.id == _pid).first()
                            _nome = _proj.evento if _proj else None
                        except Exception:
                            pass
                    _evento_label = _nome or f"projeto_id={_pid}"
                    _la(
                        event_type="MARGEM_MAGENTO_FAILED",
                        severity="HIGH",
                        message=f"Falha na query Magento ({label}) — Margem por Kit: {_evento_label}: {type(e_exc).__name__}",
                        detail=str(e_exc)[:1000],
                    )
                except Exception as _ha_err:
                    logger.warning(f"[HealthAlert] Falha ao registrar MARGEM_MAGENTO_FAILED: {_ha_err}")

            # Executa count e receita como blocos independentes: se a receita falhar,
            # a contagem já calculada é preservada (evita perder qtd por timeout na receita).
            qtd_by_bid: dict = {}
            rev_by_bid: dict = {}

            # --- Query 1: Contagem de inscrições por bundle ---
            # Estratégia em camadas, mesma filosofia da revenue_query:
            #   1) cache em memória 4h (_margem_cnt_cache) — instantâneo
            #   2) snapshot Postgres recente (até 25h) — pré-computado às 4h
            #   3) Magento ao vivo (com retry curto)
            #   4) backfill por bundle (snapshot preenche bundles ausentes da resposta LIVE)
            #   5) fallback final: snapshot stale (qualquer idade) se LIVE falhou
            # Isso elimina o flicker do currentSales causado por respostas parciais
            # do Magento — a contagem nunca cai por causa de queda de conexão.
            def _load_snapshot_qtd(max_age_h: Optional[float] = None):
                """Lê qtd_inscricoes do snapshot. Retorna ({bid: qtd}, idade_horas)."""
                try:
                    from ...models.vendas_snapshot import MargemBundleRevSnapshot as _MBR_q
                    from datetime import timezone as _tz_q
                    _rows_q = db.query(_MBR_q).filter(
                        _MBR_q.bundle_entity_id.in_(bundle_ids)
                    ).all()
                    if not _rows_q:
                        return None, None
                    _agora = _time.time()
                    _oldest = min(
                        r.calculado_em.replace(tzinfo=_tz_q.utc).timestamp()
                        if r.calculado_em.tzinfo is None
                        else r.calculado_em.timestamp()
                        for r in _rows_q
                    )
                    _age_h = (_agora - _oldest) / 3600
                    if max_age_h is not None and _age_h > max_age_h:
                        return None, _age_h
                    return {r.bundle_entity_id: int(r.qtd_inscricoes or 0) for r in _rows_q}, _age_h
                except Exception as _err_q:
                    logger.warning(f"[Margem] Erro ao ler qtd do snapshot: {_err_q}")
                    return None, None

            _cnt_cache_key = (frozenset(bundle_ids), incluir_cortesias)
            _cnt_now_mono = _time.monotonic()
            if force_refresh:
                _margem_cnt_cache.pop(_cnt_cache_key, None)
            _cnt_cached = _margem_cnt_cache.get(_cnt_cache_key)
            if _cnt_cached and (_cnt_now_mono - _cnt_cached[1]) < _MARGEM_CNT_TTL_SECONDS:
                qtd_by_bid = dict(_cnt_cached[0])
                if meta_out is not None:
                    meta_out["count_source"] = "cache"
                logger.info(f"[Margem] count_query cache HIT: {len(bundle_ids)} bundles → {len(qtd_by_bid)} entradas (TTL restante: {int(_MARGEM_CNT_TTL_SECONDS - (_cnt_now_mono - _cnt_cached[1]))}s)")
            else:
                _cnt_snap_loaded = False
                if not force_refresh:
                    _cnt_snap_data, _cnt_snap_age_h = _load_snapshot_qtd(max_age_h=_snapshot_max_age_h)
                    # Aceita snapshot fresco (< max_age_h) mesmo que todos os valores
                    # sejam 0. A filtragem por max_age_h já garante que snapshots
                    # antigos/legados nunca chegam aqui — a checagem extra de "any > 0"
                    # era desnecessária e prejudicial: forçava uma query ao vivo no
                    # Magento (47s+, sujeita a timeout) para eventos sem vendas ou
                    # cujo batch não teve tempo de gravar a contagem. Em evento
                    # finalizado, snapshot é autoridade absoluta (max_age_h = None).
                    if _cnt_snap_data is not None:
                        qtd_by_bid = dict(_cnt_snap_data)
                        if meta_out is not None:
                            meta_out["count_source"] = "snapshot"
                        _margem_cnt_cache[_cnt_cache_key] = (dict(qtd_by_bid), _cnt_now_mono)
                        _cnt_snap_loaded = True
                        _frozen_tag = " [evento finalizado]" if _event_frozen else ""
                        logger.info(
                            f"[Margem] count_query SNAPSHOT HIT (PostgreSQL): {len(bundle_ids)} bundles → "
                            f"{len(qtd_by_bid)} entradas (idade {_cnt_snap_age_h:.1f}h){_frozen_tag}"
                        )

                if not _cnt_snap_loaded:
                    _cnt_live_failed = False
                    try:
                        def _cnt_work_sf():
                            return _execute_magento_with_retry(
                                magento_count_query, {"bundle_ids": bundle_ids}, label="count_query"
                            )
                        _cnt_sf_key = ("margem-count", frozenset(bundle_ids), bool(_skip_cortesia_filter))
                        _rows_cnt, _elapsed_cnt = _margem_singleflight(
                            _cnt_sf_key, _cnt_work_sf, "count_query"
                        )
                        for row in _rows_cnt:
                            qtd_by_bid[int(row[0])] = int(row[1] or 0)
                        logger.info(f"[Margem] count_query: {len(bundle_ids)} bundles → {len(qtd_by_bid)} linhas em {_elapsed_cnt:.2f}s")
                        if meta_out is not None:
                            meta_out["count_source"] = "live"
                        _margem_cnt_cache[_cnt_cache_key] = (dict(qtd_by_bid), _cnt_now_mono)
                    except Exception as e:
                        logger.error(f"Erro ao buscar vendas Magento por bundle para margem: {e}")
                        _log_margem_magento_failed(e, "count")
                        _cnt_live_failed = True
                        if _cnt_cached:
                            qtd_by_bid = dict(_cnt_cached[0])
                            if meta_out is not None:
                                meta_out["count_source"] = "cache_expired"
                            logger.warning(f"[Margem] count_query falhou — usando cache expirado: {len(qtd_by_bid)} entradas")

                    # Backfill por bundle: se o LIVE respondeu mas faltou bundle
                    # que sabidamente tem qtd > 0 no snapshot, preenche do snapshot.
                    # Mesma lógica do backfill de receita — protege contra resposta parcial.
                    # NOTA: backfill é PULADO quando force_refresh=True — neste caso o
                    # usuário quer o resultado ao vivo sem interferência do snapshot
                    # (que pode conter valores inflados/desatualizados).
                    if not _cnt_live_failed and not force_refresh:
                        _bf_snap_data, _bf_snap_age_h = _load_snapshot_qtd(max_age_h=None)
                        if _bf_snap_data:
                            _bf_filled = 0
                            for _bid_bf in bundle_ids:
                                _live_v = int(qtd_by_bid.get(_bid_bf, 0) or 0)
                                _snap_v = int(_bf_snap_data.get(_bid_bf, 0) or 0)
                                # Snapshot é piso: se LIVE entregou menos do que o
                                # snapshot conhece, restaura o número mais alto.
                                if _snap_v > _live_v:
                                    qtd_by_bid[_bid_bf] = _snap_v
                                    _bf_filled += 1
                            if _bf_filled > 0:
                                _margem_cnt_cache[_cnt_cache_key] = (dict(qtd_by_bid), _cnt_now_mono)
                                _bf_age_msg = (
                                    f" (idade {_bf_snap_age_h:.1f}h)"
                                    if _bf_snap_age_h is not None else ""
                                )
                                logger.info(
                                    f"[Margem] count_query BACKFILL PARCIAL: "
                                    f"{_bf_filled} bundles abaixo do snapshot restaurados"
                                    f"{_bf_age_msg}"
                                )

                    # Fallback final: LIVE falhou e cache em memória vazio → tenta snapshot stale
                    if _cnt_live_failed and not qtd_by_bid:
                        _stale_q, _stale_q_age_h = _load_snapshot_qtd(max_age_h=None)
                        if _stale_q:
                            qtd_by_bid = dict(_stale_q)
                            if meta_out is not None:
                                meta_out["count_source"] = "stale"
                            logger.info(
                                f"[Margem] count_query STALE SNAPSHOT FALLBACK: "
                                f"{len(bundle_ids)} bundles → {len(qtd_by_bid)} entradas (idade {_stale_q_age_h:.1f}h)"
                            )

            # --- Query 2: Receita por bundle (join com itens-filho) ---
            # A join com soi_child por nome (LIKE) é lenta para eventos de alto volume
            # porque parent_item_id pode não ter índice no Magento 2.
            # Usamos cache em memória com TTL de 4h para evitar re-executar a cada request.
            _rev_cache_key = (frozenset(bundle_ids), incluir_cortesias)
            _now_mono = _time.monotonic()
            if force_refresh:
                _margem_rev_cache.pop(_rev_cache_key, None)
                _margem_rev_failure_cache.pop(_rev_cache_key, None)
            _cached = _margem_rev_cache.get(_rev_cache_key)
            _failure_entry = _margem_rev_failure_cache.get(_rev_cache_key)
            # Compatibilidade: aceita tanto entrada nova (ts, n) quanto antiga (ts).
            if isinstance(_failure_entry, tuple):
                _last_failure_ts, _failure_count = _failure_entry
            elif _failure_entry is not None:
                _last_failure_ts, _failure_count = _failure_entry, 1
            else:
                _last_failure_ts, _failure_count = None, 0

            def _load_snapshot_revenue(max_age_h: Optional[float] = None):
                """Tenta carregar receita do snapshot Postgres. Retorna (dict|None, idade_horas|None)."""
                try:
                    from ...models.vendas_snapshot import MargemBundleRevSnapshot as _MBR
                    from datetime import timezone as _tz
                    _snap_rows = db.query(_MBR).filter(
                        _MBR.bundle_entity_id.in_(bundle_ids)
                    ).all()
                    if not _snap_rows:
                        return None, None
                    _agora_utc = _time.time()
                    _oldest = min(
                        r.calculado_em.replace(tzinfo=_tz.utc).timestamp()
                        if r.calculado_em.tzinfo is None
                        else r.calculado_em.timestamp()
                        for r in _snap_rows
                    )
                    _age_h = (_agora_utc - _oldest) / 3600
                    if max_age_h is not None and _age_h > max_age_h:
                        return None, _age_h
                    return {r.bundle_entity_id: float(r.receita_liquida) for r in _snap_rows}, _age_h
                except Exception as _snap_err:
                    logger.warning(f"[Margem] Erro ao ler margem_bundle_rev_snapshot: {_snap_err}")
                    return None, None

            def _format_snapshot_warning(age_h: Optional[float]) -> str:
                if age_h is None:
                    return "INFO: Receita calculada com base no último snapshot disponível."
                if age_h < 1:
                    _txt_idade = f"{int(age_h * 60)} min"
                elif age_h < 48:
                    _txt_idade = f"{age_h:.1f} h"
                else:
                    _txt_idade = f"{int(age_h / 24)} dia(s)"
                return (
                    f"INFO: Receita atualizada até {_txt_idade} atrás — valores de inscrições e receita são confiáveis; "
                    f"vendas das últimas {_txt_idade} serão incluídas na próxima atualização."
                )

            if _cached and (_now_mono - _cached[1]) < _MARGEM_REV_TTL_SECONDS:
                rev_by_bid = dict(_cached[0])
                if meta_out is not None:
                    meta_out["revenue_source"] = "cache"
                logger.info(f"[Margem] revenue_query cache HIT: {len(bundle_ids)} bundles → {len(rev_by_bid)} entradas (TTL restante: {int(_MARGEM_REV_TTL_SECONDS - (_now_mono - _cached[1]))}s)")
            else:
                # --- Tentar snapshot PostgreSQL recente antes do Magento ao vivo ---
                _snap_loaded = False
                if not force_refresh:
                    _snap_data, _snap_age_h = _load_snapshot_revenue(max_age_h=_snapshot_max_age_h)
                    if _snap_data is not None:
                        rev_by_bid = _snap_data
                        if meta_out is not None:
                            meta_out["revenue_source"] = "snapshot"
                        _margem_rev_cache[_rev_cache_key] = (dict(rev_by_bid), _now_mono)
                        _margem_rev_failure_cache.pop(_rev_cache_key, None)
                        _snap_loaded = True
                        _frozen_tag = " [evento finalizado]" if _event_frozen else ""
                        logger.info(f"[Margem] revenue_query SNAPSHOT HIT (PostgreSQL): {len(bundle_ids)} bundles → {len(rev_by_bid)} entradas (idade {_snap_age_h:.1f}h){_frozen_tag}")

                if not _snap_loaded:
                    global _margem_magento_global_failure_ts, _margem_magento_global_failure_count
                    _cooldown_s = _margem_rev_cooldown_for(_failure_count)
                    _in_cooldown = bool(_last_failure_ts and (_now_mono - _last_failure_ts) < _cooldown_s)

                    # Verifica também o cooldown GLOBAL (compartilhado entre todos os eventos).
                    # Se qualquer evento falhou recentemente, todos aguardam sem tentar o Magento.
                    _global_in_cooldown = bool(
                        _margem_magento_global_failure_ts is not None
                        and (_now_mono - _margem_magento_global_failure_ts) < _MARGEM_GLOBAL_COOLDOWN_S
                    )
                    if _global_in_cooldown and not _in_cooldown:
                        _global_restante = int(_MARGEM_GLOBAL_COOLDOWN_S - (_now_mono - _margem_magento_global_failure_ts))
                        logger.info(
                            f"[Margem] revenue_query SKIPPED (cooldown GLOBAL ativo, "
                            f"{_global_restante}s restantes, falhas={_margem_magento_global_failure_count}): "
                            f"{len(bundle_ids)} bundles"
                        )
                        _in_cooldown = True

                    _live_failed = False
                    if _in_cooldown:
                        if not _global_in_cooldown:
                            _cooldown_restante = int(_cooldown_s - (_now_mono - _last_failure_ts))
                            logger.info(
                                f"[Margem] revenue_query SKIPPED (cooldown pós-falha #{_failure_count} ativo, "
                                f"{_cooldown_restante}s restantes): {len(bundle_ids)} bundles"
                            )
                        _live_failed = True
                    else:
                        try:
                            def _rev_work_sf():
                                return _execute_magento_with_retry(
                                    magento_bundle_query, {"bundle_ids": bundle_ids}, label="revenue_query"
                                )
                            _rev_sf_key = ("margem-rev", frozenset(bundle_ids), bool(_skip_cortesia_filter))
                            _rows_rev, _elapsed = _margem_singleflight(
                                _rev_sf_key, _rev_work_sf, "revenue_query"
                            )
                            for row in _rows_rev:
                                rev_by_bid[int(row[0])] = float(row[1] or 0)
                            logger.info(f"[Margem] revenue_query LIVE: {len(bundle_ids)} bundles → {len(rev_by_bid)} linhas em {_elapsed:.2f}s")
                            if meta_out is not None:
                                meta_out["revenue_source"] = "live"
                            _margem_rev_cache[_rev_cache_key] = (dict(rev_by_bid), _time.monotonic())
                            _margem_rev_failure_cache.pop(_rev_cache_key, None)
                            # Sucesso: limpa cooldown global
                            _margem_magento_global_failure_ts = None
                            _margem_magento_global_failure_count = 0
                        except Exception as e:
                            logger.error(f"Erro ao buscar receita Magento por bundle para margem: {e}")
                            _new_count = _failure_count + 1
                            _margem_rev_failure_cache[_rev_cache_key] = (_time.monotonic(), _new_count)
                            _next_cd = _margem_rev_cooldown_for(_new_count)
                            logger.info(f"[Margem] revenue_query: registrada falha #{_new_count}; próximo cooldown {_next_cd}s")
                            # Atualiza cooldown global — todos os eventos aguardarão juntos
                            _margem_magento_global_failure_ts = _time.monotonic()
                            _margem_magento_global_failure_count += 1
                            logger.info(
                                f"[Margem] cooldown GLOBAL ativado por {_MARGEM_GLOBAL_COOLDOWN_S}s "
                                f"(falha global #{_margem_magento_global_failure_count})"
                            )
                            _log_margem_magento_failed(e, "revenue")
                            _live_failed = True

                    # Backfill por bundle: quando a revenue_query LIVE "respondeu"
                    # mas devolveu 0 (ou nada) para bundles que têm qtd > 0, o
                    # Magento entregou dados parciais sem lançar exceção. Sem
                    # esta correção o cálculo `margem = receita - custo * qtd`
                    # fica negativo e o usuário vê número errado.
                    # Preenchemos esses bundles a partir do snapshot persistido
                    # (qualquer idade) e sinalizamos que o número exibido é
                    # do último snapshot conhecido.
                    if not _live_failed and qtd_by_bid:
                        _missing_bids_bf = [
                            _bid_bf for _bid_bf in bundle_ids
                            if qtd_by_bid.get(_bid_bf, 0) > 0
                            and float(rev_by_bid.get(_bid_bf, 0) or 0) <= 0
                        ]
                        if _missing_bids_bf:
                            try:
                                from ...models.vendas_snapshot import MargemBundleRevSnapshot as _MBR_bf
                                from datetime import timezone as _tz_bf
                                _bf_rows = db.query(_MBR_bf).filter(
                                    _MBR_bf.bundle_entity_id.in_(_missing_bids_bf)
                                ).all()
                                _bf_filled = 0
                                _bf_oldest_ts = None
                                for _r_bf in _bf_rows:
                                    _v_bf = float(_r_bf.receita_liquida or 0)
                                    if _v_bf <= 0:
                                        continue
                                    rev_by_bid[int(_r_bf.bundle_entity_id)] = _v_bf
                                    _bf_filled += 1
                                    _ts_bf = (
                                        _r_bf.calculado_em.replace(tzinfo=_tz_bf.utc).timestamp()
                                        if _r_bf.calculado_em.tzinfo is None
                                        else _r_bf.calculado_em.timestamp()
                                    )
                                    if _bf_oldest_ts is None or _ts_bf < _bf_oldest_ts:
                                        _bf_oldest_ts = _ts_bf
                                if _bf_filled > 0:
                                    if meta_out is not None:
                                        meta_out["revenue_source"] = "partial"
                                    _margem_rev_cache[_rev_cache_key] = (
                                        dict(rev_by_bid), _time.monotonic()
                                    )
                                    _bf_age_h = None
                                    if _bf_oldest_ts is not None:
                                        _bf_age_h = (_time.time() - _bf_oldest_ts) / 3600
                                    _aviso_bf = _format_snapshot_warning(_bf_age_h)
                                    if avisos_out is not None:
                                        _generic_aviso = "Dados do Magento indisponíveis — totais de inscrições e receita podem estar incompletos."
                                        if _generic_aviso in avisos_out:
                                            avisos_out.remove(_generic_aviso)
                                        if _aviso_bf not in avisos_out:
                                            avisos_out.append(_aviso_bf)
                                    _bf_age_msg = (
                                        f" (idade {_bf_age_h:.1f}h)"
                                        if _bf_age_h is not None else ""
                                    )
                                    logger.info(
                                        f"[Margem] revenue_query BACKFILL PARCIAL: "
                                        f"{_bf_filled}/{len(_missing_bids_bf)} bundles "
                                        f"sem receita LIVE preenchidos do snapshot"
                                        f"{_bf_age_msg}"
                                    )
                            except Exception as _bf_err:
                                logger.warning(
                                    f"[Margem] backfill de receita parcial falhou: {_bf_err}"
                                )

                    # Fallback final: se a tentativa ao vivo falhou (ou está em cooldown),
                    # serve o snapshot de qualquer idade em vez de mostrar receita zerada.
                    # Melhor mostrar dados ligeiramente atrasados do que esconder tudo.
                    if _live_failed and not rev_by_bid:
                        _stale_data, _stale_age_h = _load_snapshot_revenue(max_age_h=None)
                        if _stale_data is not None:
                            rev_by_bid = _stale_data
                            if meta_out is not None:
                                meta_out["revenue_source"] = "stale"
                            # NÃO grava no cache de TTL: queremos voltar a tentar ao vivo
                            # assim que o cooldown expirar.
                            _aviso_stale = _format_snapshot_warning(_stale_age_h)
                            if avisos_out is not None:
                                _generic_aviso = "Dados do Magento indisponíveis — totais de inscrições e receita podem estar incompletos."
                                if _generic_aviso in avisos_out:
                                    avisos_out.remove(_generic_aviso)
                                if _aviso_stale not in avisos_out:
                                    avisos_out.append(_aviso_stale)
                            logger.info(
                                f"[Margem] revenue_query STALE SNAPSHOT FALLBACK: "
                                f"{len(bundle_ids)} bundles → {len(rev_by_bid)} entradas (idade {_stale_age_h:.1f}h)"
                            )
                        else:
                            _aviso_cooldown = "AVISO: Sem snapshot disponível — valores de receita podem estar incompletos até a próxima sincronização."
                            if avisos_out is not None and _aviso_cooldown not in avisos_out:
                                avisos_out.append(_aviso_cooldown)

            # Consolida: usa qtd da query 1 + receita da query 2 (independentes)
            all_bids = set(qtd_by_bid.keys()) | set(rev_by_bid.keys())
            for bid in all_bids:
                qtd = qtd_by_bid.get(bid, 0)
                receita = rev_by_bid.get(bid, 0.0)
                tipo_kit = global_bundle_tipo_map.get(bid)
                if not tipo_kit:
                    continue
                if tipo_kit not in kit_map:
                    kit_map[tipo_kit] = {
                        "custo": 0.0,
                        "ativo_categoria": None,
                        "qtd": 0,
                        "receita": 0.0,
                        "has_cost": False,
                    }
                kit_map[tipo_kit]["qtd"] += qtd
                kit_map[tipo_kit]["receita"] += receita

        # Override custo pelo custo manual do kit_config quando definido.
        # Se o tipo não existe no kit_map (sem Cadastro e sem vendas), cria entrada
        # zerada para que o custo apareça na tabela mesmo sem inscrições.
        for tipo, custo_override in custo_kit_override.items():
            if tipo in kit_map:
                kit_map[tipo]["custo"] = custo_override
                kit_map[tipo]["has_cost"] = True
            else:
                kit_map[tipo] = {
                    "custo": custo_override,
                    "ativo_categoria": None,
                    "qtd": 0,
                    "receita": 0.0,
                    "has_cost": True,
                }

        # KitConfig.ativo_categoria is the authoritative (admin-controlled) mapping source.
        # It overrides any CadastroKitProduto.ativo_categoria that may have been set above.
        for bid, tipo_k in global_bundle_tipo_map.items():
            if tipo_k and tipo_k in kit_map:
                _kc_rec = db.query(KitConfig).filter(
                    KitConfig.bundle_entity_id == bid,
                    KitConfig.ativo_categoria.isnot(None),
                ).first()
                if _kc_rec and _kc_rec.ativo_categoria:
                    kit_map[tipo_k]["ativo_categoria"] = _kc_rec.ativo_categoria

        # 3.5 Fallback: quando algum kit ainda tem qtd=0 (tipo_kit não mapeado no KitConfig),
        # consolida vendas Magento agrupadas por nome do bundle e faz matching por nome
        # contra as chaves do kit_map (ex: "Kit Básico" está contido em "Kit Básico Bravus Race - Speed I")
        kits_sem_venda = [k for k, v in kit_map.items() if v["qtd"] == 0]
        if kits_sem_venda and seen_magento_events and db_module.engine_magento is not None:
            # Nota: NÃO reimporta `time as _time` (já está no módulo). Ver comentário no bloco
            # primary acima — re-import local quebra escopo em toda a função.

            try:
                _log_margem_magento_failed  # noqa: F821
            except NameError:
                def _log_margem_magento_failed(e_exc, label=""):
                    _aviso = "AVISO: Conexão com Magento instável — buscando dados do snapshot mais recente."
                    if avisos_out is not None and _aviso not in avisos_out:
                        avisos_out.append(_aviso)
            ev_ids_fb = list(seen_magento_events)

            # Estratégia do fallback: pré-busca os product_ids via cpev1 (tabela pequena,
            # bem indexada por attribute_id+store_id+value) e depois reutiliza as mesmas
            # queries eficientes do bloco primário — evita subconsulta correlacionada lenta.
            fb_bundle_ids: list = []
            try:
                _cpev1_q = text("""
SELECT /*+ MAX_EXECUTION_TIME(10000) */ DISTINCT entity_id
FROM   catalog_product_entity_varchar
WHERE  attribute_id = 321
AND    store_id     = 0
AND    value        IN :ev_ids_fb
""").bindparams(bindparam("ev_ids_fb", expanding=True))
                def _fb_pid_work(conn):
                    return conn.execute(_cpev1_q, {"ev_ids_fb": ev_ids_fb}).fetchall()
                _pid_rows = magento_run(_fb_pid_work, label="margem:fallback-cpev1", profile="background")
                fb_bundle_ids = [int(r[0]) for r in _pid_rows]
                logger.info(f"[Margem] fallback cpev1 prefetch: {len(ev_ids_fb)} ev_ids → {len(fb_bundle_ids)} bundle_ids")

                # Exclui bundles que o usuário deflagou explicitamente no KitConfig
                # (linha existe com tipo_kit=NULL). Sem este filtro, o matching por
                # substring abaixo agrega bundles como "Kit Básico - 21k", "Kit Básico
                # - 42k" e "Kit Básico - 5k" em uma única linha "Kit Básico", mesmo
                # depois do usuário remover a flag.
                if fb_bundle_ids:
                    _deflagged_bids = {
                        r[0] for r in db.query(KitConfig.bundle_entity_id).filter(
                            KitConfig.bundle_entity_id.in_(fb_bundle_ids),
                            KitConfig.tipo_kit.is_(None),
                        ).all()
                    }
                    if _deflagged_bids:
                        _before = len(fb_bundle_ids)
                        fb_bundle_ids = [bid for bid in fb_bundle_ids if bid not in _deflagged_bids]
                        logger.info(f"[Margem] fallback: excluídos {_before - len(fb_bundle_ids)} bundles deflagados (tipo_kit=NULL no KitConfig)")
            except Exception as _cpev1_err:
                logger.warning(f"[Margem] fallback cpev1 prefetch falhou: {_cpev1_err}")

            if fb_bundle_ids:
                # Reutiliza o mesmo padrão das queries primárias, agrupando por nome do bundle
                # OTIMIZAÇÃO (broad fix): lidera com sales_order_item.product_id IN.
                fb_count_q = text(
                    "SELECT /*+ MAX_EXECUTION_TIME(55000) */ STRAIGHT_JOIN\n"
                    "    soi_parent.name                        AS bundle_name,\n"
                    "    COUNT(DISTINCT soi_parent.item_id)     AS qtd\n"
                    "FROM sales_order_item soi_parent\n"
                    "INNER JOIN sales_order so\n"
                    "       ON so.entity_id = soi_parent.order_id\n"
                    "WHERE\n"
                    "    soi_parent.product_type = 'bundle'\n"
                    "AND soi_parent.product_id   IN :fb_bundle_ids\n"
                    "AND so.created_at >= DATE_SUB(CURDATE(), INTERVAL 15 MONTH)\n"
                    "AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')\n"
                    "AND so.state != 'canceled'\n"
                    "AND (:skip_cortesia_filter OR so.base_grand_total > 0)\n"
                    "AND (:skip_cortesia_filter OR NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50))\n"
                    "AND so.created_at < CURDATE() + INTERVAL 1 DAY\n"
                    "AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')\n"
                    "AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')\n"
                    "AND so.increment_id NOT REGEXP '-[0-9]'\n"
                    "GROUP BY soi_parent.name"
                ).bindparams(
                    bindparam("fb_bundle_ids", expanding=True),
                    skip_cortesia_filter=_skip_cortesia_filter,
                )

                # OTIMIZAÇÃO (broad fix): lidera com sales_order_item.product_id IN.
                fb_rev_q = text(
                    "SELECT /*+ MAX_EXECUTION_TIME(60000) */ STRAIGHT_JOIN\n"
                    "    soi_parent.name                                                                    AS bundle_name,\n"
                    "    ROUND(SUM(soi_child.price - soi_child.discount_amount), 2)                        AS receita_liquida\n"
                    "FROM sales_order_item soi_parent\n"
                    "INNER JOIN sales_order so\n"
                    "       ON so.entity_id = soi_parent.order_id\n"
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
                    "    soi_parent.product_type = 'bundle'\n"
                    "AND soi_parent.product_id   IN :fb_bundle_ids\n"
                    "AND so.created_at >= DATE_SUB(CURDATE(), INTERVAL 15 MONTH)\n"
                    "AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')\n"
                    "AND so.state != 'canceled'\n"
                    "AND (:skip_cortesia_filter OR so.base_grand_total > 0)\n"
                    "AND (:skip_cortesia_filter OR NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50))\n"
                    "AND so.created_at < CURDATE() + INTERVAL 1 DAY\n"
                    "AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')\n"
                    "AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')\n"
                    "AND so.increment_id NOT REGEXP '-[0-9]'\n"
                    "GROUP BY soi_parent.name"
                ).bindparams(
                    bindparam("fb_bundle_ids", expanding=True),
                    skip_cortesia_filter=_skip_cortesia_filter,
                )

                fb_qtd_by_name: dict = {}
                fb_rev_by_name: dict = {}

                # Fallback count — bloco independente
                def _fb_count_work(conn):
                    return conn.execute(fb_count_q, {"fb_bundle_ids": fb_bundle_ids}).fetchall()
                def _fb_count_sf():
                    return magento_run(_fb_count_work, label="margem:fallback-count", profile="background")
                _fb_count_sf_key = ("margem-fb-count", frozenset(fb_bundle_ids), bool(_skip_cortesia_filter))
                try:
                    _t_fb0 = _time.monotonic()
                    for fb_row in _margem_singleflight(_fb_count_sf_key, _fb_count_sf, "margem:fallback-count"):
                        fb_qtd_by_name[(fb_row[0] or "").strip()] = int(fb_row[1] or 0)
                    logger.info(f"[Margem] fallback count_query: {len(fb_bundle_ids)} bundles → {len(fb_qtd_by_name)} em {_time.monotonic()-_t_fb0:.2f}s")
                except Exception as e:
                    logger.error(f"Erro no fallback count Magento para margem: {e}")
                    _log_margem_magento_failed(e, "fallback-count")

                # Fallback receita — bloco independente (com cache em memória)
                _fb_rev_cache_key = (frozenset(fb_bundle_ids), incluir_cortesias)
                _now_mono_fb = _time.monotonic()
                _cached_fb = _margem_rev_cache.get(_fb_rev_cache_key)
                if _cached_fb and (_now_mono_fb - _cached_fb[1]) < _MARGEM_REV_TTL_SECONDS:
                    fb_rev_by_name = dict(_cached_fb[0])
                    logger.info(f"[Margem] fallback revenue_query cache HIT: {len(fb_bundle_ids)} bundles → {len(fb_rev_by_name)} entradas")
                else:
                    # Respeita cooldown global — se Magento está instável para outros eventos,
                    # não tenta o fallback-revenue (que usa a mesma query lenta)
                    _fb_global_in_cd = bool(
                        _margem_magento_global_failure_ts is not None
                        and (_now_mono_fb - _margem_magento_global_failure_ts) < _MARGEM_GLOBAL_COOLDOWN_S
                    )
                    if _fb_global_in_cd:
                        _fb_cd_restante = int(_MARGEM_GLOBAL_COOLDOWN_S - (_now_mono_fb - _margem_magento_global_failure_ts))
                        logger.info(
                            f"[Margem] fallback revenue_query SKIPPED (cooldown GLOBAL ativo, "
                            f"{_fb_cd_restante}s restantes): {len(fb_bundle_ids)} bundles"
                        )
                    else:
                        def _fb_rev_work(conn):
                            return conn.execute(fb_rev_q, {"fb_bundle_ids": fb_bundle_ids}).fetchall()
                        def _fb_rev_sf():
                            return magento_run(_fb_rev_work, label="margem:fallback-revenue", profile="background")
                        _fb_rev_sf_key = ("margem-fb-rev", frozenset(fb_bundle_ids), bool(_skip_cortesia_filter))
                        try:
                            _t_fb1 = _time.monotonic()
                            for fb_row in _margem_singleflight(_fb_rev_sf_key, _fb_rev_sf, "margem:fallback-revenue"):
                                fb_rev_by_name[(fb_row[0] or "").strip()] = float(fb_row[1] or 0)
                            _elapsed_fb = _time.monotonic() - _t_fb1
                            logger.info(f"[Margem] fallback revenue_query: {len(fb_bundle_ids)} bundles → {len(fb_rev_by_name)} em {_elapsed_fb:.2f}s")
                            _margem_rev_cache[_fb_rev_cache_key] = (dict(fb_rev_by_name), _time.monotonic())
                        except Exception as e:
                            logger.error(f"Erro no fallback receita Magento para margem: {e}")
                            _margem_magento_global_failure_ts = _now_mono_fb
                            _margem_magento_global_failure_count += 1
                            logger.info(
                                f"[Margem] cooldown GLOBAL ativado por fallback-revenue: "
                                f"{_MARGEM_GLOBAL_COOLDOWN_S}s (falha global #{_margem_magento_global_failure_count})"
                            )
                            _log_margem_magento_failed(e, "fallback-revenue")

                # Combina e aplica apenas onde qtd ainda é 0
                all_fb_names = set(fb_qtd_by_name.keys()) | set(fb_rev_by_name.keys())
                fb_by_name: dict = {
                    bname: {
                        "qtd": fb_qtd_by_name.get(bname, 0),
                        "receita": fb_rev_by_name.get(bname, 0.0),
                    }
                    for bname in all_fb_names
                }
                # Para cada bundle, escolhe APENAS o kit mais específico (substring mais longa)
                # entre todos os kits do kit_map. Sem isso, um bundle como "Kit Básico - 21k"
                # acaba contado tanto no kit "Kit Básico - 21k" quanto no kit genérico "Kit Básico".
                _all_kit_names_lower = [(str(kn), str(kn).lower()) for kn in kit_map.keys()]
                _bundle_to_kit: dict = {}
                for bname in fb_by_name.keys():
                    bname_lower = str(bname).lower()
                    _best_kn = None
                    _best_len = -1
                    for _kn_orig, _kn_lower in _all_kit_names_lower:
                        if _kn_lower and _kn_lower in bname_lower and len(_kn_lower) > _best_len:
                            _best_kn = _kn_orig
                            _best_len = len(_kn_lower)
                    if _best_kn is not None:
                        _bundle_to_kit[bname] = _best_kn
                for kit_name in kits_sem_venda:
                    total_qtd = 0
                    total_rec = 0.0
                    for bname, bdata in fb_by_name.items():
                        if _bundle_to_kit.get(bname) == kit_name:
                            total_qtd += bdata["qtd"]
                            total_rec += bdata["receita"]
                    if total_qtd > 0 and kit_name in kit_map:
                        kit_map[kit_name]["qtd"]     = total_qtd
                        kit_map[kit_name]["receita"] = total_rec

        # 4.5 Suplementar: bundles no Magento (via atributo cpev1) que NÃO estão no KitConfig
        # têm inscrições contadas pelo card principal mas ignoradas pelo bloco primário.
        # O fallback acima só atualiza kits_sem_venda (qtd=0), então inscrições de bundles extras
        # cujos tipos de kit já têm dados são perdidas. Este bloco as recupera e acumula.
        if seen_magento_events and global_bundle_tipo_map and db_module.engine_magento is not None:
            _kc_bid_set = set(global_bundle_tipo_map.keys())
            # Bundles deflagados explicitamente pelo usuário (linha existe no
            # KitConfig com tipo_kit=NULL) também devem ser excluídos do bloco
            # suplementar, caso contrário o matching por substring abaixo
            # reagregaria as inscrições no kit que o usuário queria desclassificar.
            _deflagged_bid_set = {
                r[0] for r in db.query(KitConfig.bundle_entity_id).filter(
                    KitConfig.tipo_kit.is_(None)
                ).all()
            }
            _supp_extra_bids: list = []
            try:
                _cpev1_supp = text("""
SELECT /*+ MAX_EXECUTION_TIME(10000) */ DISTINCT entity_id
FROM   catalog_product_entity_varchar
WHERE  attribute_id = 321
AND    store_id     = 0
AND    value        IN :ev_ids
""").bindparams(bindparam("ev_ids", expanding=True))
                def _supp_pid_work(conn):
                    return conn.execute(_cpev1_supp, {"ev_ids": list(seen_magento_events)}).fetchall()
                _supp_pid_rows = magento_run(_supp_pid_work, label="margem:supplementary-cpev1", profile="background")
                _supp_extra_bids = [
                    int(r[0]) for r in _supp_pid_rows
                    if int(r[0]) not in _kc_bid_set and int(r[0]) not in _deflagged_bid_set
                ]
                if _supp_extra_bids:
                    logger.info(f"[Margem] supplementary: {len(seen_magento_events)} ev_ids → {len(_supp_extra_bids)} bundles extras fora do KitConfig")
            except Exception as _e_supp0:
                logger.warning(f"[Margem] supplementary cpev1 prefetch falhou: {_e_supp0}")

            if _supp_extra_bids:
                import time as _time_supp
                # OTIMIZAÇÃO (broad fix): lidera com sales_order_item.product_id IN.
                _supp_cnt_q = text(
                    "SELECT /*+ MAX_EXECUTION_TIME(30000) */ STRAIGHT_JOIN\n"
                    "    soi_parent.name                        AS bundle_name,\n"
                    "    COUNT(DISTINCT soi_parent.item_id)     AS qtd\n"
                    "FROM sales_order_item soi_parent\n"
                    "INNER JOIN sales_order so\n"
                    "       ON so.entity_id = soi_parent.order_id\n"
                    "WHERE\n"
                    "    soi_parent.product_type = 'bundle'\n"
                    "AND soi_parent.product_id   IN :supp_bids\n"
                    "AND so.created_at >= DATE_SUB(CURDATE(), INTERVAL 15 MONTH)\n"
                    "AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')\n"
                    "AND so.state != 'canceled'\n"
                    "AND (:skip_cortesia_filter OR so.base_grand_total > 0)\n"
                    "AND (:skip_cortesia_filter OR NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50))\n"
                    "AND so.created_at < CURDATE() + INTERVAL 1 DAY\n"
                    "AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')\n"
                    "AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')\n"
                    "AND so.increment_id NOT REGEXP '-[0-9]'\n"
                    "GROUP BY soi_parent.name"
                ).bindparams(
                    bindparam("supp_bids", expanding=True),
                    skip_cortesia_filter=_skip_cortesia_filter,
                )

                # OTIMIZAÇÃO (broad fix): lidera com sales_order_item.product_id IN.
                _supp_rev_q = text(
                    "SELECT /*+ MAX_EXECUTION_TIME(90000) */ STRAIGHT_JOIN\n"
                    "    soi_parent.name                                                                    AS bundle_name,\n"
                    "    ROUND(SUM(soi_child.price - soi_child.discount_amount), 2)                        AS receita_liquida\n"
                    "FROM sales_order_item soi_parent\n"
                    "INNER JOIN sales_order so\n"
                    "       ON so.entity_id = soi_parent.order_id\n"
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
                    "    soi_parent.product_type = 'bundle'\n"
                    "AND soi_parent.product_id   IN :supp_bids\n"
                    "AND so.created_at >= DATE_SUB(CURDATE(), INTERVAL 15 MONTH)\n"
                    "AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')\n"
                    "AND so.state != 'canceled'\n"
                    "AND (:skip_cortesia_filter OR so.base_grand_total > 0)\n"
                    "AND (:skip_cortesia_filter OR NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50))\n"
                    "AND so.created_at < CURDATE() + INTERVAL 1 DAY\n"
                    "AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')\n"
                    "AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')\n"
                    "AND so.increment_id NOT REGEXP '-[0-9]'\n"
                    "GROUP BY soi_parent.name"
                ).bindparams(
                    bindparam("supp_bids", expanding=True),
                    skip_cortesia_filter=_skip_cortesia_filter,
                )

                _supp_qtd_by_name: dict = {}
                _supp_rev_by_name: dict = {}

                def _supp_cnt_work(conn):
                    return conn.execute(_supp_cnt_q, {"supp_bids": _supp_extra_bids}).fetchall()
                try:
                    _supp_t0 = _time_supp.monotonic()
                    for _sr in magento_run(_supp_cnt_work, label="margem:supplementary-count", profile="once"):
                        _supp_qtd_by_name[(_sr[0] or "").strip()] = int(_sr[1] or 0)
                    logger.info(f"[Margem] supplementary count: {len(_supp_extra_bids)} bundles extras → {sum(_supp_qtd_by_name.values())} inscrições em {_time_supp.monotonic()-_supp_t0:.2f}s")
                except Exception as _e_supp1:
                    logger.warning(f"[Margem] supplementary count query falhou: {_e_supp1}")

                _supp_rev_cache_key = (frozenset(_supp_extra_bids), incluir_cortesias)
                _cached_supp = _margem_rev_cache.get(_supp_rev_cache_key)
                if _cached_supp and (_time_supp.monotonic() - _cached_supp[1]) < _MARGEM_REV_TTL_SECONDS:
                    _supp_rev_by_name = dict(_cached_supp[0])
                else:
                    def _supp_rev_work(conn):
                        return conn.execute(_supp_rev_q, {"supp_bids": _supp_extra_bids}).fetchall()
                    try:
                        _supp_t1 = _time_supp.monotonic()
                        for _sr2 in magento_run(_supp_rev_work, label="margem:supplementary-revenue", profile="once"):
                            _supp_rev_by_name[(_sr2[0] or "").strip()] = float(_sr2[1] or 0)
                        _margem_rev_cache[_supp_rev_cache_key] = (dict(_supp_rev_by_name), _time_supp.monotonic())
                        logger.info(f"[Margem] supplementary revenue: {len(_supp_extra_bids)} bundles extras → {len(_supp_rev_by_name)} em {_time_supp.monotonic()-_supp_t1:.2f}s")
                    except Exception as _e_supp2:
                        logger.warning(f"[Margem] supplementary revenue query falhou: {_e_supp2}")

                # Ordena pelos nomes de kit MAIS LONGOS primeiro, garantindo que
                # bundles como "Kit Básico - 21k Floripa" sejam atribuídos ao kit
                # específico "Kit Básico - 21k" e não ao kit genérico "Kit Básico".
                _kit_names_sorted_supp = sorted(kit_map.keys(), key=lambda k: -len(str(k)))
                for _sname, _sqtd in _supp_qtd_by_name.items():
                    if _sqtd <= 0:
                        continue
                    _sname_lower = str(_sname).lower()
                    _srec = _supp_rev_by_name.get(_sname, 0.0)
                    _matched = False
                    for _kit_nm in _kit_names_sorted_supp:
                        if str(_kit_nm).lower() in _sname_lower:
                            kit_map[_kit_nm]["qtd"]     += _sqtd
                            kit_map[_kit_nm]["receita"] += _srec
                            logger.info(f"[Margem] supplementary: +{_sqtd} inscrições de '{_sname}' → kit '{_kit_nm}'")
                            _matched = True
                            break
                    if not _matched:
                        logger.debug(f"[Margem] supplementary: bundle '{_sname}' sem correspondência no kit_map")

        # 5. Ativo: query por ds_categoria para os event IDs mapeados como fonte=ATIVO
        #    Todos os kits verificam o Ativo; a contribuição é somada ao Magento (ou zerado se não há match).
        ativo_event_ids: list = []
        for pid in projeto_ids:
            for sm in _get_sku_maps(pid, 'ATIVO'):
                if sm.id_externo:
                    try:
                        ativo_event_ids.append(int(sm.id_externo))
                    except (ValueError, TypeError):
                        pass

        if ativo_event_ids and db_module.engine_ssh is not None:
            try:
                _ativo_ids_unique = list(set(ativo_event_ids))
                # Build exact reverse lookup: ds_categoria_lower -> kit_name
                # Priority: (1) KitConfig.ativo_categoria (admin-set), (2) exact kit name match.
                _cat_to_kit: dict = {}
                for _kn, _kd in kit_map.items():
                    _ac = (_kd.get("ativo_categoria") or "").strip()
                    if _ac:
                        # ativo_categoria explicitly configured — supports comma-separated values
                        for _ac_part in _ac.split(","):
                            _ac_part = _ac_part.strip()
                            if _ac_part:
                                _cat_to_kit[_ac_part.lower()] = _kn
                    else:
                        # No explicit mapping: exact case-insensitive kit name fallback
                        _cat_to_kit.setdefault(str(_kn).lower(), _kn)

                _ativo_query = text("""
SELECT
    sub.id_evento,
    sub.ds_categoria,
    SUM(sub.qtd)            AS qtd,
    SUM(sub.receita_liquida) AS receita_liquida
FROM (
    SELECT
        b.id_evento,
        h.ds_categoria,
        CASE
            WHEN a.nr_preco = 0                    THEN 'Cortesia'
            WHEN h.ds_categoria LIKE '%%Grup%%'    THEN 'Grupos/B2B'
            WHEN h.ds_categoria LIKE '%%ortesia%%' THEN 'Cortesia'
            ELSE                                        'Site'
        END                                            AS canal,
        COUNT(DISTINCT a.id_pedido_evento)             AS qtd,
        SUM(GREATEST(a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0), 0)) AS receita_liquida
    FROM sa_evento AS b
    INNER JOIN sa_pedido_evento AS a
        ON a.id_evento = b.id_evento
    INNER JOIN sa_pedido AS c
        ON c.id_pedido = a.id_pedido
        AND c.id_pedido_status IN (2)
        AND c.nr_total > 0
    LEFT JOIN sa_modalidade_categoria AS h
        ON h.id_categoria = a.id_categoria
    LEFT JOIN (
        SELECT e.id_cupom_desconto_item, f.en_cupom_classificacao
        FROM sa_cupom_desconto_item AS e
        INNER JOIN sa_cupom_desconto AS f
            ON f.id_cupom_desconto = e.id_cupom_desconto
    ) AS cupom
        ON cupom.id_cupom_desconto_item = a.id_cupom_individual
    WHERE
        b.id_evento IN :ativo_ids
        AND (b.id_campanha_salesforce IS NULL
             OR b.id_campanha_salesforce NOT LIKE '701d0000000%%')
        AND c.nr_total > 0
        AND (
            cupom.en_cupom_classificacao IS NULL
            OR cupom.en_cupom_classificacao NOT IN (
                'Funcionário',
                'Cortesia Faturada',
                'Grupos',
                'Coligados'
            )
        )
    GROUP BY
        b.id_evento,
        h.ds_categoria,
        CASE 
            WHEN a.nr_preco = 0               THEN 'Cortesia'
            WHEN h.ds_categoria LIKE '%%Grup%%' THEN 'Grupos/B2B'
            ELSE                                   'Site'
        END
) AS sub
WHERE sub.canal = 'Site'
GROUP BY sub.id_evento, sub.ds_categoria
""").bindparams(bindparam("ativo_ids", expanding=True))
                with db_module.engine_ssh.connect() as _conn_ativo:
                    _ativo_result = _conn_ativo.execute(_ativo_query, {"ativo_ids": _ativo_ids_unique})
                    _ativo_rows = _ativo_result.fetchall()

                for _ar in _ativo_rows:
                    # Unpack: id_evento, ds_categoria, qtd, receita_liquida
                    _a_evento = _ar[0]
                    _a_ds_cat = (_ar[1] or "").strip()
                    _a_qtd = int(_ar[2] or 0)
                    _a_rec = float(_ar[3] or 0)
                    if _a_qtd <= 0:
                        continue
                    # Match ds_categoria to kit name — exact case-insensitive only
                    _matched_kit = _cat_to_kit.get(_a_ds_cat.lower())
                    if not _matched_kit:
                        logger.debug(f"Ativo ds_categoria '{_a_ds_cat}' sem correspondência no kit_map")
                        continue
                    if _matched_kit not in kit_map:
                        kit_map[_matched_kit] = {
                            "custo": 0.0,
                            "ativo_categoria": _a_ds_cat,
                            "qtd": 0,
                            "receita": 0.0,
                            "has_cost": False,
                        }
                    kit_map[_matched_kit]["qtd"] += _a_qtd
                    kit_map[_matched_kit]["receita"] += _a_rec
            except Exception as _e_ativo:
                logger.warning(f"Erro ao buscar dados Ativo por categoria para margem: {_e_ativo}")
                _aviso_ativo = "AVISO: Conexão com Ativo instável — inscrições podem estar incompletas até a próxima sincronização."
                if avisos_out is not None and _aviso_ativo not in avisos_out:
                    avisos_out.append(_aviso_ativo)
                try:
                    from app.services.health_alert_service import log_and_alert as _log_alert_ativo
                    _first_pid_ativo = projeto_ids[0] if projeto_ids else None
                    _log_alert_ativo(
                        event_type="MARGEM_ATIVO_FAILED",
                        severity="HIGH",
                        message=f"Falha ao buscar dados Ativo na Margem por Kit (projeto_id={_first_pid_ativo}): {type(_e_ativo).__name__}",
                        detail=str(_e_ativo)[:1000],
                    )
                except Exception as _ha_err_ativo:
                    logger.warning(f"[HealthAlert] Falha ao registrar MARGEM_ATIVO_FAILED: {_ha_err_ativo}")

        # 6. Build result list — inclui kits sem vendas (qtd=0) para visibilidade de custo
        if not kit_map:
            return []

        result_list = []
        total_qtd = 0
        total_receita = 0.0
        total_margem = 0.0

        for kit_name in sorted(kit_map.keys()):
            kdata = kit_map[kit_name]
            qtd = kdata["qtd"]
            receita = kdata["receita"]
            custo = kdata["custo"]
            has_cost = kdata.get("has_cost", True)
            ticket_medio = round(receita / qtd, 2) if qtd > 0 else 0.0
            margem_unit = round(ticket_medio - custo, 2) if qtd > 0 else None
            margem_total = round(receita - (custo * qtd), 2)

            result_list.append({
                "tipoKit": kit_name,
                "qtd": qtd,
                "receitaLiquida": round(receita, 2),
                "ticketMedio": ticket_medio,
                "ticketAtual": tipo_kit_ticket_atual.get(kit_name),
                "custoKit": round(custo, 2) if has_cost else None,
                "margemUnit": margem_unit,
                "margemTotal": margem_total,
            })

            total_qtd += qtd
            total_receita += receita
            total_margem += margem_total

        if result_list:
            # Linha consolidada usa os totais do card principal quando disponíveis,
            # garantindo consistência matemática com os valores exibidos na análise de margem.
            if card_total_qty is not None and card_total_receita is not None:
                c_qtd = card_total_qty
                c_receita = round(card_total_receita, 2)
                c_ticket = round(c_receita / c_qtd, 2) if c_qtd > 0 else 0.0
                c_custo_avg = card_kit_cost_avg or 0.0
                c_margem = round(c_receita - c_custo_avg * c_qtd, 2)
            else:
                c_qtd = total_qtd
                c_receita = round(total_receita, 2)
                c_ticket = round(c_receita / c_qtd, 2) if c_qtd > 0 else 0.0
                c_margem = round(total_margem, 2)
            result_list.append({
                "tipoKit": "CONSOLIDADO",
                "qtd": c_qtd,
                "receitaLiquida": c_receita,
                "ticketMedio": c_ticket,
                "ticketAtual": None,
                "custoKit": None,
                "margemUnit": None,
                "margemTotal": c_margem,
            })

        return result_list

    except Exception as e:
        logger.exception(f"Erro ao calcular margem por kit: {e}")
        # Falha não pode bloquear retry: limpa o stamp de cooldown SE este
        # request foi quem o setou. Sem o guard, um request demoted (que
        # encontrou cooldown ativo) que falhe depois limparia o stamp de outro
        # request que está válido — abrindo brecha para re-execução prematura.
        if _frc_stamp_set_by_this_request and _frc_key is not None:
            # Compare-and-delete: só remove se o stamp ainda é o nosso. Evita
            # apagar um stamp mais novo gravado por outro request após o nosso
            # ter expirado e este só agora falhado.
            with _margem_force_refresh_lock:
                _curr = _margem_force_refresh_last_ts.get(_frc_key)
                if _curr == _frc_my_stamp:
                    _margem_force_refresh_last_ts.pop(_frc_key, None)
        return []


def get_detalhe_vendas_por_kit(
    db: Session,
    projeto_ids: list,
    ano: Optional[int] = None,
    incluir_cortesias: bool = False,
) -> Optional[list]:
    """Breakdown detalhado de vendas Magento por kit/canal/modalidade/distância.
    Returns [] when query succeeds but no data; returns None when query fails (timeout/error).
    """
    if not projeto_ids or db_module.engine_magento is None:
        return []

    import datetime as _dt
    _ano = ano if ano else _dt.datetime.now().year

    # Coleta event IDs do Magento via SkuMapping
    proj_by_id = {
        pid: db.query(DimProjeto).filter(DimProjeto.id == pid).first()
        for pid in projeto_ids
    }
    seen_evt: set = set()
    magento_event_ids: list = []
    for pid in projeto_ids:
        proj = proj_by_id.get(pid)
        if not proj or not proj.codigo:
            continue
        sku = proj.codigo.upper().strip()
        q = db.query(SkuMapping).filter(
            SkuMapping.sku == sku,
            SkuMapping.fonte == 'MAGENTO',
            SkuMapping.ativo == True,
        )
        if ano:
            q = q.filter(SkuMapping.ano == ano)
        for sm in q.all():
            if not sm.id_externo:
                continue
            try:
                eid = int(sm.id_externo)
            except (ValueError, TypeError):
                continue
            if eid not in seen_evt:
                seen_evt.add(eid)
                magento_event_ids.append(eid)

    if not magento_event_ids:
        return []

    # Cache TTL curto: dentro da janela, devolve resultado idêntico sem tocar Magento.
    _vkd_cache_key = (frozenset(magento_event_ids), _ano, bool(incluir_cortesias))
    if _VENDAS_KIT_DETALHE_TTL_SECONDS > 0:
        _vkd_now = _time.monotonic()
        with _vendas_kit_detalhe_lock:
            _vkd_entry = _vendas_kit_detalhe_cache.get(_vkd_cache_key)
        if _vkd_entry and (_vkd_now - _vkd_entry[1]) < _VENDAS_KIT_DETALHE_TTL_SECONDS:
            logger.info(
                f"[vendas-kit-detalhe] cache HIT: {len(magento_event_ids)} event_ids → "
                f"{len(_vkd_entry[0])} linhas (TTL restante: "
                f"{int(_VENDAS_KIT_DETALHE_TTL_SECONDS - (_vkd_now - _vkd_entry[1]))}s)"
            )
            return list(_vkd_entry[0])

    _cort_ids = _get_cortesia_magento_ids(db) if incluir_cortesias else None
    detalhe_query = text(build_query_isc_magento_detalhe(magento_event_ids, _ano, cortesia_magento_ids=_cort_ids))

    def _detalhe_work(conn):
        return conn.execute(detalhe_query).fetchall()
    try:
        result_rows = magento_run(_detalhe_work, label="vendas-kit-detalhe", profile="request")
        rows = []
        for row in result_rows:
            rows.append({
                "kit":            row[2],
                "tipoCategoria":  row[3],
                "distancia":      row[4],
                "canal":          row[5],
                "loteAtual":      row[6],
                "price":          float(row[7]) if row[7] is not None else None,
                "specialPrice":   float(row[8]) if row[8] is not None else None,
                "inscritos":      int(row[9] or 0),
                "receitaBruta":   round(float(row[10] or 0), 2),
                "receitaLiquida": round(float(row[11] or 0), 2),
                "ticketMedio":    round(float(row[12]), 2) if row[12] else None,
            })
        _vkd_result = rows if rows else []
        if _VENDAS_KIT_DETALHE_TTL_SECONDS > 0:
            with _vendas_kit_detalhe_lock:
                _vendas_kit_detalhe_cache[_vkd_cache_key] = (list(_vkd_result), _time.monotonic())
                _prune_oldest_inplace(_vendas_kit_detalhe_cache, _VENDAS_KIT_DETALHE_MAX_ENTRIES, ts_index=1)
        return _vkd_result
    except Exception as e:
        logger.error(f"Erro ao buscar detalhe de vendas por kit: {e}")
        return None


def build_query_isc_magento_detalhe(magento_event_ids: list, ano: int, cortesia_magento_ids: Optional[set] = None) -> str:
    """Returns SQL for detailed Magento sales by kit/canal/modalidade (V6).

    Returns rows grouped by: id_evento, evento, kit, tipo_categoria, distancia, canal, lote_atual, price, special_price.
    Columns (by index): 0=id_evento, 1=evento, 2=kit, 3=tipoCategoria, 4=distancia, 5=canal,
                        6=loteAtual, 7=price, 8=specialPrice, 9=inscritos,
                        10=receitaBruta, 11=receitaLiquida, 12=ticketMedio.
    """
    ids_str = ", ".join(str(int(i)) for i in magento_event_ids)
    # Versão com aspas para comparação contra colunas VARCHAR (ex.: v.value na
    # derivada 'agg'): IN numérico contra varchar força cast por linha = full scan.
    ids_quoted = ", ".join(f"'{int(i)}'" for i in magento_event_ids)
    cort_ids = cortesia_magento_ids or set()
    has_cortesia = bool(cort_ids & set(str(i) for i in magento_event_ids))
    if has_cortesia:
        cort_child_price = ""
    else:
        cort_child_price = "AND soi_child.price          > 0"
    return f"""
SELECT /*+ MAX_EXECUTION_TIME(300000) */
    cpev1.value                                                                         AS id_evento,
    cpev2.value                                                                         AS evento,
    soi_parent.name                                                                     AS kit,
    eaov_tipo.value                                                                     AS tipo_categoria,
    COALESCE(soi_child.name, 'Outras modalidades')                                      AS distancia,
    CASE
        WHEN so.base_grand_total = 0                                    THEN 'Cortesia'
        WHEN soi_child.price - soi_child.discount_amount = 0           THEN 'Cortesia'
        WHEN so.discount_description LIKE '%%GRUPOS%%'                  THEN 'Grupos/B2B'
        WHEN so.coupon_code LIKE 'GRUP%%'                               THEN 'Grupos/B2B'
        ELSE                                                                 'Site'
    END                                                                                 AS canal,
    lote_atual.lot_name                                                                 AS lote_atual,
    soi_prices.price                                                                    AS price,
    soi_prices.special_price                                                            AS special_price,
    COUNT(DISTINCT soi_parent.item_id)                                                  AS inscritos,
    SUM(CASE
        WHEN so.base_grand_total = 0                                    THEN 0
        ELSE soi_child.price
    END)                                                                                AS receita_bruta,
    SUM(CASE
        WHEN so.base_grand_total = 0                                    THEN 0
        ELSE soi_child.price - soi_child.discount_amount
           - COALESCE(
                 (ABS(so.discount_amount) - COALESCE(agg.desc_itens, 0))
                     / NULLIF(agg.qtd_bundles, 0)
               , 0)
    END)                                                                                AS receita_liquida,
    SUM(CASE
        WHEN so.base_grand_total = 0                                    THEN 0
        ELSE soi_child.price - soi_child.discount_amount
           - COALESCE(
                 (ABS(so.discount_amount) - COALESCE(agg.desc_itens, 0))
                     / NULLIF(agg.qtd_bundles, 0)
               , 0)
    END) / NULLIF(COUNT(DISTINCT CASE
        WHEN so.base_grand_total = 0                                    THEN NULL
        ELSE soi_parent.item_id
    END), 0)                                                                            AS ticket_medio

FROM sales_order so

JOIN sales_order_item soi_parent
       ON soi_parent.order_id     = so.entity_id
      AND soi_parent.product_type = 'bundle'

LEFT JOIN sales_order_item soi_child
       ON soi_child.parent_item_id = soi_parent.item_id
      AND soi_child.product_type   = 'simple'
      {cort_child_price}
      AND (
            soi_child.name LIKE '%%Distância%%'
         OR soi_child.name LIKE '%%Distancia%%'
         OR soi_child.name LIKE '%%Distâncias%%'
         OR soi_child.name LIKE '%%Modalidade%%'
         OR soi_child.name REGEXP '-[0-9]+[Kk]m$'
         OR soi_child.name REGEXP '^[0-9]+[Kk]m?$'
         OR soi_child.name LIKE 'Kit Participação%%'
         OR soi_child.name LIKE 'Olímpico%%'
         OR soi_child.name LIKE 'Yoga%%'
      )

JOIN (
    SELECT cpev.entity_id, cpev.value
    FROM catalog_product_entity_varchar cpev
    JOIN catalog_product_entity cpe
          ON cpe.entity_id = cpev.entity_id
         AND cpe.type_id   = 'bundle'
    WHERE cpev.attribute_id = 321
      AND cpev.store_id     = 0
) AS cpev1 ON cpev1.entity_id = soi_parent.product_id

LEFT JOIN (
    SELECT entity_id, MIN(value) AS value
    FROM catalog_product_entity_varchar
    WHERE attribute_id = 73
      AND store_id     = 0
    GROUP BY entity_id
) AS cpev2 ON cpev2.entity_id = cpev1.value

LEFT JOIN (
    -- Agregados por pedido para o rateio do desconto de CARRINHO
    -- (mesma fórmula do Detalhe de Eventos — _RECEITA_LIQUIDA_SUM):
    --   qtd_bundles → denominador do rateio
    --   desc_itens  → descontos já lançados nos itens (não-bundle)
    -- Escopo limitado aos pedidos que contêm bundles dos eventos solicitados
    -- (filtro DENTRO da derivada — evita full scan em sales_order_item).
    SELECT
        i.order_id,
        SUM(CASE WHEN i.product_type =  'bundle' THEN 1 ELSE 0 END)                 AS qtd_bundles,
        SUM(CASE WHEN i.product_type <> 'bundle' THEN i.discount_amount ELSE 0 END) AS desc_itens
    FROM sales_order_item i
    JOIN (
        -- pedidos-alvo: têm pelo menos um bundle dos eventos solicitados
        SELECT DISTINCT bo.order_id
        FROM catalog_product_entity_varchar v
        JOIN sales_order_item bo
               ON bo.product_id   = v.entity_id
              AND bo.product_type = 'bundle'
        WHERE v.attribute_id = 321
          AND v.store_id     = 0
          AND v.value IN ({ids_quoted})
    ) AS tgt ON tgt.order_id = i.order_id
    GROUP BY i.order_id
) AS agg ON agg.order_id = soi_parent.order_id

JOIN (
    SELECT entity_id, MIN(value) AS value
    FROM catalog_product_entity_datetime
    WHERE attribute_id = 195
    GROUP BY entity_id
) AS cped ON cped.entity_id = cpev1.value

LEFT JOIN (
    SELECT attribute_id
    FROM eav_attribute
    WHERE attribute_code = 'tipo_categoria'
      AND entity_type_id = (
            SELECT entity_type_id FROM eav_entity_type
            WHERE entity_type_code = 'catalog_product'
      )
) AS attr_tipo ON 1 = 1
LEFT JOIN catalog_product_entity_int cpei_tipo
       ON cpei_tipo.entity_id    = soi_parent.product_id
      AND cpei_tipo.attribute_id = attr_tipo.attribute_id
LEFT JOIN eav_attribute_option_value eaov_tipo
       ON eaov_tipo.option_id = cpei_tipo.value

LEFT JOIN (
    SELECT lp.entity_id, lp.lot_name
    FROM catalog_product_entity_event_lot_price lp
    JOIN (
        SELECT entity_id, MAX(record_id) AS max_record_id
        FROM catalog_product_entity_event_lot_price
        GROUP BY entity_id
    ) lp_max
          ON lp_max.entity_id     = lp.entity_id
         AND lp_max.max_record_id = lp.record_id
) AS lote_atual ON lote_atual.entity_id = cpev1.value

LEFT JOIN (
    SELECT
        cpeos.parent_product_id,
        (
            MAX(CASE
                WHEN cpev_s.value LIKE '%%Distancia%%'
                  OR cpev_s.value LIKE '%%Distância%%'
                  OR cpev_s.value LIKE '%%Modalidade%%'
                THEN cpep.value ELSE NULL
            END)
            + COALESCE(MAX(CASE
                WHEN cpep.value > 0
                 AND cpev_s.value NOT LIKE '%%Distancia%%'
                 AND cpev_s.value NOT LIKE '%%Distância%%'
                 AND cpev_s.value NOT LIKE '%%Modalidade%%'
                 AND cpev_s.value NOT LIKE '%%Personaliz%%'
                 AND cpev_s.value NOT LIKE '%%Aceite%%'
                 AND cpev_s.value NOT LIKE '%%aceito%%'
                 AND cpev_s.value NOT LIKE '%%Treinão%%'
                 AND cpev_s.value NOT LIKE '%%Horário%%'
                 AND cpev_s.value NOT LIKE '%%Bateria%%'
                 AND cpev_s.value NOT LIKE '%%Doar%%'
                 AND cpev_s.value NOT LIKE '%%Tênis%%'
                 AND cpev_s.value NOT LIKE '%%Tenis%%'
                 AND cpev_s.value NOT LIKE '%%Bike%%'
                 AND cpev_s.value NOT LIKE '%%Biciclet%%'
                 AND cpev_s.value NOT LIKE '%%Festival%%'
                 AND cpev_s.value NOT LIKE '%%Bag%%'
                 AND cpev_s.value NOT LIKE '%%Inscrição%%'
                 AND cpev_s.value NOT LIKE '%%Declaro%%'
                 AND cpev_s.value NOT LIKE '%%Pochete%%'
                 AND cpev_s.value NOT LIKE '%%Tarifa%%'
                 AND cpev_s.value NOT LIKE '%%Skate%%'
                 AND cpev_s.value NOT LIKE '%%Obstáculo%%'
                 AND cpev_s.value NOT LIKE '%%Bravinhos%%'
                 AND cpev_s.value NOT LIKE '%%teste%%'
                 AND cpev_s.value NOT LIKE '%%Porta%%'
                 AND cpev_s.value NOT LIKE '%%Luva%%'
                 AND cpev_s.value NOT LIKE '%%Toalha%%'
                 AND cpev_s.value NOT LIKE '%%Corrida +%%'
                THEN cpep.value ELSE NULL
            END), 0)
        ) * COALESCE(mult.multiplicador, 1)             AS price,
        (
            MAX(CASE
                WHEN cpev_s.value LIKE '%%Distancia%%'
                  OR cpev_s.value LIKE '%%Distância%%'
                  OR cpev_s.value LIKE '%%Modalidade%%'
                THEN pi.final_price ELSE NULL
            END)
            + COALESCE(MAX(CASE
                WHEN pi.final_price > 0
                 AND cpev_s.value NOT LIKE '%%Distancia%%'
                 AND cpev_s.value NOT LIKE '%%Distância%%'
                 AND cpev_s.value NOT LIKE '%%Modalidade%%'
                 AND cpev_s.value NOT LIKE '%%Personaliz%%'
                 AND cpev_s.value NOT LIKE '%%Aceite%%'
                 AND cpev_s.value NOT LIKE '%%aceito%%'
                 AND cpev_s.value NOT LIKE '%%Treinão%%'
                 AND cpev_s.value NOT LIKE '%%Horário%%'
                 AND cpev_s.value NOT LIKE '%%Bateria%%'
                 AND cpev_s.value NOT LIKE '%%Doar%%'
                 AND cpev_s.value NOT LIKE '%%Tênis%%'
                 AND cpev_s.value NOT LIKE '%%Tenis%%'
                 AND cpev_s.value NOT LIKE '%%Bike%%'
                 AND cpev_s.value NOT LIKE '%%Biciclet%%'
                 AND cpev_s.value NOT LIKE '%%Festival%%'
                 AND cpev_s.value NOT LIKE '%%Bag%%'
                 AND cpev_s.value NOT LIKE '%%Inscrição%%'
                 AND cpev_s.value NOT LIKE '%%Declaro%%'
                 AND cpev_s.value NOT LIKE '%%Pochete%%'
                 AND cpev_s.value NOT LIKE '%%Tarifa%%'
                 AND cpev_s.value NOT LIKE '%%Skate%%'
                 AND cpev_s.value NOT LIKE '%%Obstáculo%%'
                 AND cpev_s.value NOT LIKE '%%Bravinhos%%'
                 AND cpev_s.value NOT LIKE '%%teste%%'
                 AND cpev_s.value NOT LIKE '%%Porta%%'
                 AND cpev_s.value NOT LIKE '%%Luva%%'
                 AND cpev_s.value NOT LIKE '%%Toalha%%'
                 AND cpev_s.value NOT LIKE '%%Corrida +%%'
                THEN pi.final_price ELSE NULL
            END), 0)
        ) * COALESCE(mult.multiplicador, 1)             AS special_price

    FROM catalog_product_bundle_selection cpeos
    JOIN catalog_product_bundle_option cpeo
          ON cpeo.option_id = cpeos.option_id
    LEFT JOIN catalog_product_entity_varchar cpev_s
          ON cpev_s.entity_id    = cpeos.product_id
         AND cpev_s.attribute_id = 73
         AND cpev_s.store_id     = 0
    LEFT JOIN catalog_product_entity_decimal cpep
          ON cpep.entity_id    = cpeos.product_id
         AND cpep.attribute_id = 77
    LEFT JOIN catalog_product_index_price pi
          ON pi.entity_id         = cpeos.product_id
         AND pi.website_id        = 1
         AND pi.customer_group_id = 0
    LEFT JOIN (
        SELECT
            cpe.entity_id,
            CASE cpei.value
                WHEN 1606 THEN 2 WHEN 1607 THEN 3 WHEN 1608 THEN 4
                WHEN 1609 THEN 2 WHEN 1700 THEN 2 WHEN 1701 THEN 4
                ELSE 1
            END                                         AS multiplicador
        FROM catalog_product_entity cpe
        JOIN catalog_product_entity_int cpei
              ON cpei.entity_id    = cpe.entity_id
             AND cpei.attribute_id = (
                    SELECT attribute_id FROM eav_attribute
                    WHERE attribute_code = 'tipo_categoria'
                      AND entity_type_id = (
                            SELECT entity_type_id FROM eav_entity_type
                            WHERE entity_type_code = 'catalog_product'
                      )
             )
        WHERE cpe.type_id = 'bundle'
    ) AS mult ON mult.entity_id = cpeo.parent_id
    GROUP BY cpeos.parent_product_id
) AS soi_prices ON soi_prices.parent_product_id = soi_parent.product_id

WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
  AND so.state NOT IN ('canceled')
  AND so.increment_id   NOT REGEXP '-[0-9]'
  AND cpev1.value IN ({ids_str})
  AND cped.value >= MAKEDATE({ano}, 1)
  AND cped.value <  MAKEDATE({ano + 1}, 1)

GROUP BY
    cpev1.value,
    cpev2.value,
    soi_parent.name,
    eaov_tipo.value,
    COALESCE(soi_child.name, 'Outras modalidades'),
    CASE
        WHEN so.base_grand_total = 0                                    THEN 'Cortesia'
        WHEN soi_child.price - soi_child.discount_amount = 0           THEN 'Cortesia'
        WHEN so.discount_description LIKE '%%GRUPOS%%'                  THEN 'Grupos/B2B'
        WHEN so.coupon_code LIKE 'GRUP%%'                               THEN 'Grupos/B2B'
        ELSE                                                                 'Site'
    END,
    lote_atual.lot_name,
    soi_prices.price,
    soi_prices.special_price

ORDER BY
    cpev1.value,
    canal,
    inscritos DESC
"""


def build_query_isc_ativo_detalhe(ativo_event_ids: list, ano: int) -> str:
    """Returns SQL for detailed Ativo sales by modalidade/categoria/canal (CORAÇÃO EVENTO).

    Returns rows grouped by: id_evento, ds_evento, distancia, kit (categoria), canal.
    Columns: id_evento, evento, distancia, kit, canal, inscritos, receitaBruta, receitaLiquida, ticketMedio.
    """
    ids_str = ", ".join(str(int(i)) for i in ativo_event_ids)
    return f"""
SELECT /*+ MAX_EXECUTION_TIME(60000) */
    b.id_evento                                                                     AS id_evento,
    b.ds_evento                                                                     AS evento,
    m.nm_modalidade                                                                 AS distancia,
    h.ds_categoria                                                                  AS kit,
    CASE
        WHEN a.nr_preco = 0                                                                             THEN 'Cortesia'
        WHEN cupom.en_cupom_classificacao = 'Grupos'                                                    THEN 'Grupos/B2B'
        WHEN h.ds_categoria LIKE '%%Grup%%'                                                             THEN 'Grupos/B2B'
        ELSE                                                                                                  'Site'
    END                                                                             AS canal,
    COUNT(DISTINCT a.id_pedido_evento)                                              AS inscritos,
    SUM(a.nr_preco)                                                                 AS receita_bruta,
    SUM(GREATEST(a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0), 0)) AS receita_liquida,
    SUM(GREATEST(a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0), 0))
        / NULLIF(COUNT(DISTINCT a.id_pedido_evento), 0)                             AS ticket_medio
FROM sa_evento AS b
INNER JOIN sa_pedido_evento AS a ON a.id_evento = b.id_evento
INNER JOIN sa_pedido AS c
    ON c.id_pedido = a.id_pedido
   AND c.id_pedido_status IN (2)
LEFT JOIN sa_modalidade_categoria AS h ON h.id_categoria = a.id_categoria
-- Modalidade pela CATEGORIA (h.id_modalidade): ds_modalidade fica vazia em muitos
-- eventos; nm_modalidade é a fonte confiável (query canônica do analista).
LEFT JOIN sa_evento_modalidade AS m ON m.id_modalidade = h.id_modalidade
LEFT JOIN (
    SELECT e.id_cupom_desconto_item, f.en_cupom_classificacao
    FROM sa_cupom_desconto_item AS e
    INNER JOIN sa_cupom_desconto AS f ON f.id_cupom_desconto = e.id_cupom_desconto
) AS cupom ON cupom.id_cupom_desconto_item = a.id_cupom_individual
WHERE b.id_evento IN ({ids_str})
  AND (b.id_campanha_salesforce IS NULL OR b.id_campanha_salesforce NOT LIKE '701d0000000%%')
GROUP BY
    b.id_evento,
    b.ds_evento,
    m.id_modalidade,
    m.nm_modalidade,
    h.id_categoria,
    h.ds_categoria,
    CASE
        WHEN a.nr_preco = 0                                                                             THEN 'Cortesia'
        WHEN cupom.en_cupom_classificacao = 'Grupos'                                                    THEN 'Grupos/B2B'
        WHEN h.ds_categoria LIKE '%%Grup%%'                                                             THEN 'Grupos/B2B'
        ELSE                                                                                                  'Site'
    END
ORDER BY b.id_evento, canal, inscritos DESC
"""


def get_detalhe_vendas_ativo(
    db: Session,
    projeto_ids: list,
    ano: Optional[int] = None,
) -> list:
    """Breakdown detalhado de vendas Ativo por modalidade/categoria/canal (CORAÇÃO EVENTO)."""
    if not projeto_ids or db_module.engine_ssh is None:
        return []

    import datetime as _dt
    _ano = ano if ano else _dt.datetime.now().year

    seen_evt: set = set()
    ativo_event_ids: list = []
    for pid in projeto_ids:
        proj = db.query(DimProjeto).filter(DimProjeto.id == pid).first()
        if not proj or not proj.codigo:
            continue
        sku = proj.codigo.upper().strip()
        q = db.query(SkuMapping).filter(
            SkuMapping.sku == sku,
            SkuMapping.fonte == 'ATIVO',
            SkuMapping.ativo == True,
        )
        if ano:
            q = q.filter(SkuMapping.ano == ano)
        for sm in q.all():
            if not sm.id_externo:
                continue
            try:
                eid = int(sm.id_externo)
            except (ValueError, TypeError):
                continue
            if eid not in seen_evt:
                seen_evt.add(eid)
                ativo_event_ids.append(eid)

    if not ativo_event_ids:
        return []

    try:
        sql = text(build_query_isc_ativo_detalhe(ativo_event_ids, _ano))
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(sql)
            rows = []
            for row in result.fetchall():
                rows.append({
                    "kit":            row[3],
                    "tipoCategoria":  None,
                    "distancia":      row[2],
                    "canal":          row[4],
                    "loteAtual":      None,
                    "price":          None,
                    "specialPrice":   None,
                    "inscritos":      int(row[5] or 0),
                    "receitaBruta":   round(float(row[6] or 0), 2),
                    "receitaLiquida": round(float(row[7] or 0), 2),
                    "ticketMedio":    round(float(row[8]), 2) if row[8] else None,
                    "banco":          "Ativo",
                })
            return rows if rows else []
    except Exception as e:
        logger.error(f"Erro ao buscar detalhe de vendas Ativo: {e}")
        return []


_isc_cache = {}
_isc_cache_timestamp = None

from ...core.cache import isc_cache as _smart_isc_cache, event_detail_cache, daily_sales_cache, curva_cache, medias_cache, eventos_list_cache, CURRENT_YEAR_TTL, get_last_sync_hoje, try_acquire_sync_hoje, release_sync_hoje, is_sync_hoje_running, get_sync_hoje_running_by, try_acquire_user_sync, release_user_sync, is_user_sync_running, get_user_sync_info
from ...core.resilience import CircuitBreaker, CircuitOpenError, CoalescingCache

# Circuit breakers protect the upstream MySQL pools from being hammered when
# they are already saturated. After 3 failures within 2 min, the breaker opens
# and rejects calls for 60s — letting the upstream DB recover instead of
# piling on more requests that will only timeout and exhaust connections.
magento_breaker = CircuitBreaker("magento", failure_threshold=3, cooldown_s=60.0, window_s=120.0)
ativo_breaker = CircuitBreaker("ativo", failure_threshold=3, cooldown_s=60.0, window_s=120.0)

# Single-flight TTL cache for "Atualizar Hoje". When many users click the same
# event's button within a short window, only the first executes the actual
# Magento/Ativo fetch; the rest wait and get the cached result. This caps the
# upstream load no matter how many concurrent users we have.
_atualizar_hoje_cache = CoalescingCache(ttl_s=20.0, name="atualizar_hoje")

# Cooldown por evento: 30 min após SUCESSO de "Atualizar Hoje".
# Tupla: (timestamp_float, user_email, user_nome)
# Só é gravado após status == "ok". Falha/parcial não bloqueia nova tentativa.
_atualizar_hoje_cooldown: dict = {}
_ATUALIZAR_HOJE_COOLDOWN_S = 1800  # 30 minutos

# Lock global de sync manual gerenciado em cache.py (try_acquire_user_sync / release_user_sync).

# Trust the persisted snapshot for "today" if the background batch ran within
# this many seconds. Slightly larger than the batch interval so we always
# have one batch's worth of overlap. Avoids redundant live MySQL queries on
# every dashboard list render.
TODAY_SNAPSHOT_FRESHNESS_S = 3000  # ~50 min (batch runs every ~45 min)

# Global set to track cache keys currently being refreshed in a SWR background thread.
# Prevents multiple concurrent threads for the same event when the recompute takes >16s
# and several requests arrive before the first thread finishes.
_swr_recompute_in_progress: set = set()

# Concurrent computation guard: prevents cache stampede when multiple requests hit
# the same uncached event simultaneously. Only one thread computes; others wait.
import threading as _threading_module
_event_computing_events: dict = {}   # cache_key -> threading.Event (set when done)
_event_computing_lock = _threading_module.Lock()

# Bump this when ISC calculation logic changes so old permanent cache entries
# are automatically detected as stale and recomputed in background (SWR pattern).
_DETAIL_CACHE_VERSION = "27"  # v27: contagem correta de inscrições — todas as origens (cortesias + grupos/B2B + site), sem filtro canal

def build_query_isc_ativo(excluded_ids: Optional[list] = None) -> str:
    excl_clause = ""
    if excluded_ids:
        ids_str = ", ".join(str(int(i)) for i in excluded_ids)
        excl_clause = f"        AND b.id_evento NOT IN ({ids_str})\n"
    return f"""
SELECT
    base.id_evento                                                           AS "ID Evento",
    base.ds_evento                                                           AS "Evento",
    base.qtd_site                                                            AS "Qtd Site",
    base.inscricao_liquida                                                   AS "Inscrição Líquida Site",
    base.inscricao_liquida / NULLIF(base.qtd_site, 0)                       AS "Ticket Médio Site",
    ROUND(base.qtd_30d / 30.0, 2)                                           AS "Média Diária 30d",
    ROUND(base.qtd_14d / 14.0, 2)                                           AS "Média Diária 14d",
    ROUND(base.qtd_7d  /  7.0, 2)                                           AS "Média Diária 7d"
FROM (
    SELECT
        b.id_evento,
        b.ds_evento,
        b.dt_evento,
        COUNT(DISTINCT a.id_pedido_evento)                                   AS qtd_site,

        SUM(CASE
            WHEN c.dt_pedido >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            THEN 1 ELSE 0
        END)                                                                 AS qtd_30d,

        SUM(CASE
            WHEN c.dt_pedido >= DATE_SUB(CURDATE(), INTERVAL 14 DAY)
            THEN 1 ELSE 0
        END)                                                                 AS qtd_14d,

        SUM(CASE
            WHEN c.dt_pedido >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
            THEN 1 ELSE 0
        END)                                                                 AS qtd_7d,

        SUM(IF(a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0) < 0, 0,
               a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0)))
                                                                             AS inscricao_liquida

    FROM sa_evento AS b

    INNER JOIN sa_pedido_evento AS a
        ON a.id_evento = b.id_evento

    INNER JOIN sa_pedido AS c
        ON c.id_pedido = a.id_pedido
       AND c.id_pedido_status IN (2)

    LEFT JOIN sa_modalidade_categoria AS h
        ON h.id_categoria = a.id_categoria

    LEFT JOIN (
        SELECT e.id_cupom_desconto_item, f.en_cupom_classificacao
        FROM sa_cupom_desconto_item AS e
        INNER JOIN sa_cupom_desconto AS f
            ON f.id_cupom_desconto = e.id_cupom_desconto
    ) AS cupom ON cupom.id_cupom_desconto_item = a.id_cupom_individual

    WHERE
        b.dt_evento >= MAKEDATE(YEAR(CURDATE()) - 1, 1)
        AND b.dt_evento <  MAKEDATE(YEAR(CURDATE()) + 1, 1)
{excl_clause}
        AND (b.id_campanha_salesforce IS NULL
             OR b.id_campanha_salesforce NOT LIKE '701d0000000%%')

    GROUP BY
        b.id_evento,
        b.ds_evento,
        b.dt_evento
) AS base
ORDER BY base.id_evento;
"""


def build_query_isc_magento(excluded_ids: Optional[list] = None, cortesia_magento_ids: Optional[set] = None) -> str:
    excl_clause = ""
    if excluded_ids:
        ids_str = ", ".join(str(i) for i in excluded_ids)
        excl_clause = f"AND cpev1.value NOT IN ({ids_str})\n"
    return f"""
SELECT /*+ MAX_EXECUTION_TIME(300000) */
    cpev1.value                                                              AS "ID Evento",
    cpev2.value                                                              AS "Evento",

    COUNT(DISTINCT soi_parent.item_id)                                       AS "Qtd Site",

    ROUND(SUM(CASE WHEN so.base_grand_total = 0 THEN 0
                   ELSE soi_child.price - soi_child.discount_amount END), 2) AS "Inscrição Líquida",

    ROUND(SUM(CASE WHEN so.base_grand_total = 0 THEN 0
                   ELSE soi_child.price - soi_child.discount_amount END)
          / NULLIF(COUNT(DISTINCT CASE WHEN so.base_grand_total = 0 THEN NULL
                                       ELSE soi_parent.item_id END), 0), 2) AS "Ticket Médio",

    ROUND(COUNT(DISTINCT CASE
        WHEN so.created_at >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        THEN soi_parent.item_id END) / 30.0, 2)                             AS "Média Diária 30d",

    ROUND(COUNT(DISTINCT CASE
        WHEN so.created_at >= DATE_SUB(CURDATE(), INTERVAL 14 DAY)
        THEN soi_parent.item_id END) / 14.0, 2)                             AS "Média Diária 14d",

    ROUND(COUNT(DISTINCT CASE
        WHEN so.created_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
        THEN soi_parent.item_id END) / 7.0, 2)                              AS "Média Diária 7d"

FROM sales_order so
INNER JOIN sales_order_item soi_parent
       ON soi_parent.order_id     = so.entity_id
      AND soi_parent.product_type = 'bundle'
INNER JOIN sales_order_item soi_child
       ON soi_child.parent_item_id = soi_parent.item_id
      AND soi_child.product_type   = 'simple'
      AND (
            soi_child.name LIKE '%%Distância%%'
         OR soi_child.name LIKE '%%Distancia%%'
         OR soi_child.name LIKE '%%Distâncias%%'
         OR soi_child.name LIKE '%%Modalidade%%'
         OR soi_child.name REGEXP '-[0-9]+[Kk]m$'
         OR soi_child.name REGEXP '^[0-9]+[Kk]m?$'
         OR soi_child.name LIKE 'Kit Participação%%'
         OR soi_child.name LIKE 'Olímpico%%'
         OR soi_child.name LIKE 'Yoga%%'
      )
INNER JOIN (
    SELECT entity_id, value
    FROM catalog_product_entity_varchar
    WHERE attribute_id = 321 AND store_id = 0
) AS cpev1 ON cpev1.entity_id = soi_parent.product_id
INNER JOIN (
    SELECT entity_id, MIN(value) AS value
    FROM catalog_product_entity_datetime
    WHERE attribute_id = 195
    GROUP BY entity_id
) AS cped ON cped.entity_id = cpev1.value
LEFT JOIN (
    SELECT entity_id, value
    FROM catalog_product_entity_varchar
    WHERE attribute_id = 73 AND store_id = 0
) AS cpev2 ON cpev2.entity_id = cpev1.value
WHERE
    so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
AND so.state != 'canceled'
AND so.created_at < CURDATE() + INTERVAL 1 DAY
AND so.increment_id NOT REGEXP '-[0-9]'
AND cped.value BETWEEN MAKEDATE(YEAR(CURDATE()) - 1, 1) AND MAKEDATE(YEAR(CURDATE()) + 1, 1) - INTERVAL 1 DAY
{excl_clause}
GROUP BY
    cpev1.value,
    cpev2.value

ORDER BY
    cpev1.value;
"""


def _parse_isc_row(row) -> dict:
    return {
        "id_evento": str(row[0]) if row[0] else None,
        "evento": str(row[1]) if row[1] else None,
        "qtd_site": int(row[2]) if row[2] else 0,
        "inscricao_liquida": float(row[3]) if row[3] else 0.0,
        "ticket_medio": float(row[4]) if row[4] else 0.0,
        "media_30d": float(row[5]) if row[5] else 0.0,
        "media_14d": float(row[6]) if row[6] else 0.0,
        "media_7d": float(row[7]) if row[7] else 0.0,
        "dias_ate_evento": 0,
        "fator_aceleracao": 0.0,
        "projecao_linear": 0.0,
        "projecao_ajustada": 0.0,
        "tendencia": "Sem histórico comparativo",
    }


def _fetch_with_retry(engine, query_builder, source_name, max_retries=1):
    import time as _time
    if engine is None:
        return {"error": f"Conexão {source_name} não configurada"}
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            start = _time.time()
            query = query_builder()
            with engine.connect() as conn:
                result = conn.execute(text(query))
                rows = result.fetchall()
            elapsed = round(_time.time() - start, 2)
            logger.info(f"ISC {source_name}: {len(rows)} registros em {elapsed}s (tentativa {attempt + 1})")
            return [_parse_isc_row(row) for row in rows]
        except Exception as e:
            last_error = e
            elapsed = round(_time.time() - start, 2)
            logger.warning(f"ISC {source_name} falhou em {elapsed}s (tentativa {attempt + 1}/{max_retries + 1}): {type(e).__name__}: {e}")
            if attempt < max_retries:
                _time.sleep(2 * (attempt + 1))
    logger.error(f"ISC {source_name} falhou após {max_retries + 1} tentativas: {last_error}")
    return {"error": f"Timeout ou erro de conexão ({type(last_error).__name__})"}


def fetch_isc_data_ativo():
    return _fetch_with_retry(db_module.engine_ssh, build_query_isc_ativo, "Ativo")


def fetch_isc_data_magento(cortesia_magento_ids: Optional[set] = None):
    return _fetch_with_retry(db_module.engine_magento, lambda: build_query_isc_magento(cortesia_magento_ids=cortesia_magento_ids), "Magento")


_isc_warnings = []


def fetch_isc_pricing_data(db: Optional[Session] = None, force_refresh: bool = False) -> dict:
    """
    Reads ISC totals and rolling averages from vendas_diaria_snapshot (PostgreSQL).
    No MySQL queries in the read path — data comes from the background auto-sync.
    """
    global _isc_cache, _isc_cache_timestamp, _isc_warnings
    import time

    current_year = datetime.now().year
    smart_cache_key = f"{current_year}_isc"

    if not force_refresh:
        # stale_ok=False: once TTL (5 min) expires, force a fresh PostgreSQL read.
        # This is safe because get_isc_totals_from_snapshot is <5ms — no need for stale data.
        cached = _smart_isc_cache.get(smart_cache_key, stale_ok=False)
        if cached is not None:
            cache_info = _smart_isc_cache.get_info(smart_cache_key)
            logger.info(f"ISC cache HIT: key={smart_cache_key}, age={cache_info.get('age_seconds', '?')}s")
            return cached
        else:
            logger.info(f"ISC cache MISS: key={smart_cache_key}")
    else:
        logger.info(f"ISC cache BYPASS (force_refresh): key={smart_cache_key}")

    current_time = time.time()
    warnings = []

    # ---------------------------------------------------------------------------
    # STEP 1: Build grupo→SKU map and classify events by regime.
    #   consolidated_grupos: set of grupo names where regime == "consolidated"
    #   _isc_grupo_latest:    {grupo: latest event date (for dias_ate_evento)}
    #   consolidated_grupo_skus: {grupo: [normalized SKU strings]} (todas as anos, achatado)
    #   consolidated_grupo_skus_por_ano: {grupo: {ano: [normalized SKU strings]}}
    #     — SKUs SEMPRE particionados por ano; nunca misturar SKUs de anos
    #     diferentes numa mesma lista, senão o total de um ano vaza pra dentro
    #     da linha do outro ano (ver STEP 3).
    # ---------------------------------------------------------------------------
    consolidated_grupos: set = set()
    consolidated_grupo_skus: dict = {}          # {grupo: [sku_norm, ...]} (flat, compat)
    consolidated_grupo_skus_por_ano: dict = {}  # {grupo: {ano: [sku_norm, ...]}}
    _isc_grupo_latest: dict = {}           # {grupo: latest event date}
    _isc_grupo_ano_latest: dict = {}       # {(grupo, ano): latest event date daquele ano}

    _isc_grupos_ano_seguinte: set = set()  # grupos com mapping ativo já para current_year+1
    if db:
        try:
            from ...models.dimensoes import SkuMapping as _ISC_SM
            # Inclui o ano seguinte: um evento pode ter o carrinho aberto
            # antecipadamente (mapping já cadastrado para current_year+1) antes
            # mesmo de current_year terminar — sem isso o grupo nunca entra em
            # consolidated_grupo_skus e fica invisível no Dash ISC.
            _isc_grupo_rows = db.query(
                _ISC_SM.evento_grupo, _ISC_SM.sku, _ISC_SM.data_evento, _ISC_SM.ano,
            ).filter(
                _ISC_SM.evento_grupo != None,
                _ISC_SM.ativo == True,
                _ISC_SM.ano.in_([current_year, current_year + 1]),
            ).all()

            for _isc_row in _isc_grupo_rows:
                _gn = _isc_row.evento_grupo
                if not _gn:
                    continue
                _row_ano = _isc_row.ano
                if _row_ano == current_year + 1:
                    _isc_grupos_ano_seguinte.add(_gn)
                if _isc_row.data_evento:
                    if (
                        _gn not in _isc_grupo_latest
                        or _isc_row.data_evento > _isc_grupo_latest[_gn]
                    ):
                        _isc_grupo_latest[_gn] = _isc_row.data_evento
                    _ay_key = (_gn, _row_ano)
                    if (
                        _ay_key not in _isc_grupo_ano_latest
                        or _isc_row.data_evento > _isc_grupo_ano_latest[_ay_key]
                    ):
                        _isc_grupo_ano_latest[_ay_key] = _isc_row.data_evento
                if _gn not in consolidated_grupo_skus:
                    consolidated_grupo_skus[_gn] = []
                _ano_map = consolidated_grupo_skus_por_ano.setdefault(_gn, {})
                _ano_skus = _ano_map.setdefault(_row_ano, [])
                if _isc_row.sku:
                    _sn = normalize_sku(_isc_row.sku)
                    if _sn:
                        if _sn not in consolidated_grupo_skus[_gn]:
                            consolidated_grupo_skus[_gn].append(_sn)
                        if _sn not in _ano_skus:
                            _ano_skus.append(_sn)

            # Resolve missing event dates from dim_projeto using fuzzy-match
            # so regime classification works without manual date entry in SKU mappings.
            # Janela inclui o ano seguinte pelo mesmo motivo acima — mappings novos
            # frequentemente ainda não têm data_evento preenchida na própria linha.
            _grupos_sem_data = set(consolidated_grupo_skus.keys()) - set(_isc_grupo_latest.keys())
            if _grupos_sem_data:
                try:
                    _dp_all = _wq_all_dim_projetos(db)
                    _dp_yr = [p for p in _dp_all if p.data_evento and p.data_evento.year in (current_year, current_year + 1)]
                    for _gn_nd in _grupos_sem_data:
                        _norm_gn = _normalize_name_for_match(_gn_nd)
                        _best_sc, _best_dt = 0.0, None
                        for _p in _dp_yr:
                            _pn = _normalize_name_for_match(_p.evento or "")
                            _gw = set(_norm_gn.split())
                            _pw = set(_pn.split())
                            if not _gw or not _pw:
                                continue
                            _sc = len(_gw & _pw) / max(len(_gw), len(_pw))
                            if _sc > _best_sc:
                                _best_sc = _sc
                                _best_dt = _p.data_evento
                        if _best_dt and _best_sc >= 0.5:
                            _isc_grupo_latest[_gn_nd] = _best_dt
                except Exception as _date_err:
                    logger.warning(f"[ISC] failed to resolve dates from dim_projeto: {_date_err}")

            # Classify by regime
            _live_count = 0
            for _gn, _evt_date in _isc_grupo_latest.items():
                _rc = _evt_date - timedelta(days=2)
                _raw_dm = (_rc - today_brazil()).days
                _regime = get_event_regime(_raw_dm)
                # Grupos com mapping já ativo para o ano seguinte nunca são
                # "consolidated": a data resolvida acima pode ser a do ano
                # corrente (já encerrado) quando a linha do ano seguinte ainda
                # não tem data_evento própria nem correspondência em
                # dim_projeto — sem esta exceção o grupo ficaria congelado no
                # regime antigo mesmo já vendendo a próxima edição.
                if _regime == "consolidated" and _gn not in _isc_grupos_ano_seguinte:
                    consolidated_grupos.add(_gn)
                else:
                    _live_count += 1

            logger.info(
                f"[ISC] Regime: {len(consolidated_grupos)} consolidated, "
                f"{_live_count} live/hybrid (total: {len(consolidated_grupo_skus)} grupos)"
            )
        except Exception as _cls_err:
            logger.warning(f"[ISC] Regime classification failed: {_cls_err}")
            # SSL drops or other connection failures leave the session in an
            # invalid transaction state. Rollback here so STEP 2 can reuse the
            # same session without getting "Can't reconnect until invalid
            # transaction is rolled back".
            if db:
                try:
                    db.rollback()
                except Exception:
                    pass

    # ---------------------------------------------------------------------------
    # STEP 2: Read ALL grupo metrics from PostgreSQL snapshot table (<5ms).
    # This replaces the previous MySQL Ativo + Magento queries entirely.
    # If a grupo has no snapshot rows, it gets zeros with a warning — the
    # background auto-sync will populate it within the next 30-min cycle.
    # ---------------------------------------------------------------------------
    # {ano: {grupo: metrics}} — SEMPRE ano a ano, nunca combinado. Um grupo com
    # edições simultâneas em dois anos (carrinho do ano seguinte aberto antes
    # do encerramento do corrente) precisa manter os totais de cada ano
    # isolados; combinar aqui faz o total de um ano vazar pra dentro da linha
    # do outro ano (era exatamente esse o bug: a edição do ano seguinte
    # "herdava" o total do ano corrente inteiro, ou vice-versa).
    snapshot_by_ano: dict = {current_year: {}, current_year + 1: {}}
    if db:
        try:
            from ...services.snapshot_service import get_isc_totals_from_snapshot
            for _ano_snap in (current_year, current_year + 1):
                snapshot_by_ano[_ano_snap] = get_isc_totals_from_snapshot(db, _ano_snap)
            # Coverage check: warn about active grupos not yet in snapshot so ops team can
            # trigger a manual sync or verify SkuMapping completeness.
            mapped_grupos = set(consolidated_grupo_skus_por_ano.keys())
            covered_grupos: set = set()
            for _sy in snapshot_by_ano.values():
                covered_grupos |= set(_sy.keys())
            uncovered = mapped_grupos - covered_grupos
            if uncovered:
                logger.warning(
                    f"[ISC] {len(uncovered)}/{len(mapped_grupos)} grupos sem dados no snapshot "
                    f"(auto-sync não rodou ou sem vendas em {current_year}/{current_year + 1}): {sorted(uncovered)}"
                )
            logger.info(
                f"[ISC] PostgreSQL snapshot: {len(covered_grupos)} grupos com dados, "
                f"{len(mapped_grupos) - len(uncovered)}/{len(mapped_grupos)} mapeados cobertos"
            )
        except Exception as e:
            logger.error(f"[ISC] Erro ao ler snapshot PostgreSQL: {e}")
            # Ensure session is clean for subsequent callers even after failure
            try:
                db.rollback()
            except Exception:
                pass
            warnings.append("⚠️ Erro ao ler dados do PostgreSQL. Dashboard pode exibir valores desatualizados.")

    # ---------------------------------------------------------------------------
    # STEP 3: Build all_data keyed by normalized SKU (same format as before).
    # Live/hybrid grupos get full metrics + projection math.
    # Consolidated grupos get snapshot totals with _regime='consolidated'.
    # ---------------------------------------------------------------------------
    all_data: dict = {}
    consolidated_totals: dict = {}   # {grupo: snap_metrics} — kept in output for callers

    def _isc_zero_snap() -> dict:
        return {
            "qtd_site": 0, "receita_liquida_site": 0.0, "inscricao_liquida": 0.0,
            "ticket_medio": 0.0, "media_7d": 0.0, "media_14d": 0.0, "media_30d": 0.0,
        }

    for _gn, _skus_por_ano in consolidated_grupo_skus_por_ano.items():
        is_consolidated = _gn in consolidated_grupos

        if is_consolidated:
            # Grupos consolidados são excluídos de _isc_grupos_ano_seguinte acima,
            # ou seja, por construção NUNCA têm mapping ativo no ano seguinte —
            # basta o snapshot de current_year. Achata os SKUs (raro ter mais de
            # um) só pra manter o convênio "primeiro SKU carrega o total".
            snap = snapshot_by_ano.get(current_year, {}).get(_gn) or _isc_zero_snap()
            _flat_skus: list = []
            for _ano_k in sorted(_skus_por_ano.keys()):
                for _sn in _skus_por_ano[_ano_k]:
                    if _sn not in _flat_skus:
                        _flat_skus.append(_sn)
            for _i, _sn in enumerate(_flat_skus):
                if not _sn:
                    continue
                all_data[_sn] = {
                    'qtd_site':            snap['qtd_site'] if _i == 0 else 0,
                    'inscricao_liquida':   snap['inscricao_liquida'] if _i == 0 else 0.0,
                    'media_30d': 0.0, 'media_14d': 0.0, 'media_7d': 0.0,
                    'dias_ate_evento': 0,
                    'evento_name':         _gn,
                    'ticket_medio':        snap.get('ticket_medio', 0.0) if _i == 0 else 0.0,
                    'fator_aceleracao':    0.0,
                    'projecao_linear':     snap['qtd_site'] if _i == 0 else 0,
                    'projecao_ajustada':   snap['qtd_site'] if _i == 0 else 0,
                    'projecao_final':      snap['qtd_site'] if _i == 0 else 0,
                    'tendencia':           'Consolidado',
                    'receita_liquida_site': snap['receita_liquida_site'] if _i == 0 else 0.0,
                    '_regime':             'consolidated',
                }
                if _i == 0:
                    consolidated_totals[_gn] = snap
        else:
            # Live/híbrido: cada ano-edição do grupo usa SOMENTE o snapshot
            # daquele mesmo ano — nunca o de outro ano. É essa mistura que
            # fazia a edição do ano seguinte "roubar" o total do ano corrente
            # (ou vice-versa) quando as duas tinham mapping ativo ao mesmo tempo.
            for _ano_k in sorted(_skus_por_ano.keys()):
                _skus = _skus_por_ano[_ano_k]
                snap = snapshot_by_ano.get(_ano_k, {}).get(_gn)
                if not snap:
                    logger.warning(
                        f"[ISC] Grupo '{_gn}' (ano {_ano_k}) sem dados no snapshot — "
                        f"auto-sync ainda não rodou ou grupo sem vendas nesse ano"
                    )
                    snap = _isc_zero_snap()

                _evt_date = _isc_grupo_ano_latest.get((_gn, _ano_k)) or _isc_grupo_latest.get(_gn)
                dias_ate_evento = (_evt_date - today_brazil()).days if _evt_date else 0

                for _i, _sn in enumerate(_skus):
                    if not _sn:
                        continue
                    if _i == 0:
                        all_data[_sn] = {
                            'qtd_site':            snap['qtd_site'],
                            'inscricao_liquida':   snap['inscricao_liquida'],
                            'media_30d':           snap['media_30d'],
                            'media_14d':           snap['media_14d'],
                            'media_7d':            snap['media_7d'],
                            'dias_ate_evento':     dias_ate_evento,
                            'evento_name':         _gn,
                            'ticket_medio':        0.0,
                            'fator_aceleracao':    0.0,
                            'projecao_linear':     0.0,
                            'projecao_ajustada':   0.0,
                            'projecao_final':      0.0,
                            'tendencia':           'Sem histórico comparativo',
                            'receita_liquida_site': snap['receita_liquida_site'],
                        }
                    else:
                        all_data[_sn] = {
                            'qtd_site': 0, 'inscricao_liquida': 0.0,
                            'media_30d': 0.0, 'media_14d': 0.0, 'media_7d': 0.0,
                            'dias_ate_evento': 0, 'evento_name': _gn,
                            'ticket_medio': 0.0, 'fator_aceleracao': 0.0,
                            'projecao_linear': 0.0, 'projecao_ajustada': 0.0,
                            'projecao_final': 0.0, 'tendencia': 'Sem histórico comparativo',
                            'receita_liquida_site': 0.0,
                        }

    # STEP 4: Compute projection metrics for live/hybrid events (same math as before).
    for sku, data in all_data.items():
        if data.get('_regime') == 'consolidated':
            continue
        qtd_site  = data['qtd_site']
        dias      = max(data['dias_ate_evento'], 0)
        media_14d = data['media_14d']
        media_7d  = data['media_7d']

        qtd_7d          = media_7d  * 7.0
        qtd_7d_anterior = media_14d * 14.0 - qtd_7d

        data['ticket_medio']        = round(data['inscricao_liquida'] / qtd_site, 2) if qtd_site > 0 else 0.0
        data['receita_liquida_site'] = data['inscricao_liquida']

        data['fator_aceleracao'] = round(qtd_7d / qtd_7d_anterior, 2) if qtd_7d_anterior > 0 else 0.0
        data['projecao_linear']  = round(qtd_site + media_14d * dias, 0)

        fator_clamped           = min(max(data['fator_aceleracao'] if data['fator_aceleracao'] > 0 else 1.0, 0.3), 2.5)
        data['projecao_ajustada'] = round(qtd_site + media_14d * fator_clamped * dias, 0)
        data['projecao_final']    = data['projecao_linear']

        if qtd_7d_anterior <= 0:
            data['tendencia'] = 'Sem histórico comparativo'
        elif data['fator_aceleracao'] >= 1.15:
            data['tendencia'] = 'Acelerando'
        elif data['fator_aceleracao'] >= 0.85:
            data['tendencia'] = 'Estável'
        else:
            data['tendencia'] = 'Desacelerando'

    # STEP 4b: Override consolidated totals with kit-aligned currentSales from
    # EventoDetailSnapshot. For completed events the detail view aligns currentSales
    # with the kit table total (which includes Magento data even when live queries
    # fail). Without this override the list view shows the raw snapshot value
    # (Ativo-only when Magento was down during the last sync) while the detail
    # view shows the higher, correct kit-aligned value — causing a visible mismatch.
    if db and consolidated_totals:
        try:
            from ...models.evento_detail_snapshot import EventoDetailSnapshot as _EDS
            _evento_ids = [f"grp_{g}" for g in consolidated_totals.keys()]
            _detail_rows = db.query(_EDS).filter(
                _EDS.evento_id.in_(_evento_ids),
                _EDS.ano == current_year,
                _EDS.is_completed == True,  # noqa: E712
            ).all()
            for _dr in _detail_rows:
                _grp_n = _dr.evento_id[4:]  # strip "grp_"
                _pl = _dr.payload if isinstance(_dr.payload, dict) else {}
                _evt_d = _pl.get("evento") if isinstance(_pl, dict) else None
                if not isinstance(_evt_d, dict):
                    continue
                _cs = _evt_d.get("currentSales", 0)
                if not _cs or int(_cs) <= 0:
                    continue
                _cs = int(_cs)
                _snap_qty = consolidated_totals.get(_grp_n, {}).get("qtd_site", 0)
                if _cs > _snap_qty:
                    logger.info(
                        f"[ISC] Overriding consolidated qtd_site '{_grp_n}': "
                        f"{_snap_qty} → {_cs} (from EventoDetailSnapshot)"
                    )
                    consolidated_totals[_grp_n] = {
                        **consolidated_totals.get(_grp_n, {}),
                        "qtd_site": _cs,
                    }
                    # Also update the primary SKU entry in all_data so the ISC
                    # cache stays consistent with consolidated_totals.
                    _grp_skus = consolidated_grupo_skus.get(_grp_n, [])
                    if _grp_skus:
                        _primary_sku = _grp_skus[0]
                        if _primary_sku in all_data:
                            all_data[_primary_sku]["qtd_site"] = _cs
                            all_data[_primary_sku]["projecao_linear"] = _cs
                            all_data[_primary_sku]["projecao_ajustada"] = _cs
                            all_data[_primary_sku]["projecao_final"] = _cs
        except Exception as _ov_e:
            logger.warning(f"[ISC] Falha ao ler EventoDetailSnapshot para override consolidados: {_ov_e}")

    all_data['_consolidated_totals'] = consolidated_totals

    if not warnings:
        logger.info(
            f"[ISC] PostgreSQL read OK: {len(all_data) - 1} SKUs "
            f"({len(consolidated_grupos)} consolidated, {len(consolidated_grupo_skus_por_ano)} grupos mapeados)"
        )

    _isc_cache = all_data
    _isc_cache_timestamp = current_time
    _isc_warnings = warnings
    _smart_isc_cache.set(smart_cache_key, all_data)
    return all_data


def get_isc_warnings() -> list:
    return _isc_warnings


_sales_cache = {}
_cache_timestamp = None

def fetch_consolidated_sales_by_skus(skus: List[str], ano: int, apenas_site: bool = False, db: Optional[Session] = None) -> dict:
    """
    Busca vendas consolidadas (Ativo + Magento) para uma lista de SKUs.
    Usa cache para evitar queries repetidas.
    Retorna dict com SKU normalizado como chave.
    
    Args:
        skus: Lista de SKUs para buscar
        ano: Ano do evento
        apenas_site: Se True, retorna apenas vendas do canal Site (excluindo Grupos e Cortesia).
                     Se False (default), retorna vendas totais (Site + Grupos + Cortesia).
        db: Sessão do banco para buscar mapeamentos de SKU (opcional mas recomendado).
    """
    global _sales_cache, _cache_timestamp
    from .inscricoes_consolidado import fetch_ativo_data, fetch_magento_data, get_sku_mappings_from_db, enrich_with_mappings
    import time
    
    sales_by_sku = {}
    
    if not skus:
        return sales_by_sku
    
    import copy
    
    skus_normalized = [normalize_sku(s) for s in skus]
    enriched = db is not None
    cache_key = f"{ano}_{'site' if apenas_site else 'total'}_{'enriched' if enriched else 'raw'}"
    
    current_time = time.time()
    cache_valid = _cache_timestamp and (current_time - _cache_timestamp) < 300
    
    if cache_valid and cache_key in _sales_cache:
        cached_data = _sales_cache[cache_key]
        for sku in skus_normalized:
            if sku in cached_data:
                sales_by_sku[sku] = cached_data[sku].copy()
        return sales_by_sku
    
    mappings = None
    if db:
        try:
            mappings = get_sku_mappings_from_db(db, ano)
        except Exception as e:
            logger.warning(f"Erro ao buscar mapeamentos SKU: {e}")
    
    all_sales = {}
    
    try:
        dados_ativo, error = fetch_ativo_data(ano)
        if dados_ativo:
            if mappings:
                dados_ativo = copy.deepcopy(dados_ativo)
                dados_ativo = enrich_with_mappings(dados_ativo, mappings, "ativo", ano)
            for row in dados_ativo:
                sku = normalize_sku(row.get('sku', '') or '')
                if sku:
                    if apenas_site:
                        qtd = int(row.get('qtd_site', 0) or 0)
                        valor = float(row.get('inscricao_liquida_site', 0) or 0)
                    else:
                        qtd = int(row.get('qtd_vendida', 0) or 0)
                        valor = float(row.get('inscricao_liquida', 0) or 0)
                    if sku in all_sales:
                        all_sales[sku]['qtd_ativo'] += qtd
                        all_sales[sku]['valor_ativo'] += valor
                    else:
                        all_sales[sku] = {
                            'qtd_ativo': qtd,
                            'valor_ativo': valor,
                            'qtd_magento': 0,
                            'valor_magento': 0
                        }
        else:
            logger.warning(f"Sem dados Ativo: {error}")
    except Exception as e:
        logger.error(f"Erro ao buscar dados Ativo: {e}")
    
    try:
        dados_magento, error = fetch_magento_data(ano)
        if dados_magento:
            if mappings:
                dados_magento = copy.deepcopy(dados_magento)
                dados_magento = enrich_with_mappings(dados_magento, mappings, "magento", ano)
            for row in dados_magento:
                sku = normalize_sku(row.get('sku', '') or '')
                if sku:
                    if apenas_site:
                        qtd = int(row.get('qtd_site', 0) or 0)
                        valor = float(row.get('inscricao_liquida_site', 0) or 0)
                    else:
                        qtd = int(row.get('qtd_vendida', 0) or 0)
                        valor = float(row.get('inscricao_liquida', 0) or 0)
                    if sku in all_sales:
                        all_sales[sku]['qtd_magento'] += qtd
                        all_sales[sku]['valor_magento'] += valor
                    else:
                        all_sales[sku] = {
                            'qtd_ativo': 0,
                            'valor_ativo': 0,
                            'qtd_magento': qtd,
                            'valor_magento': valor
                        }
        else:
            logger.warning(f"Sem dados Magento: {error}")
    except Exception as e:
        logger.error(f"Erro ao buscar dados Magento: {e}")
    
    _sales_cache[cache_key] = all_sales
    _cache_timestamp = current_time
    
    for sku in skus_normalized:
        if sku in all_sales:
            sales_by_sku[sku] = all_sales[sku].copy()
    
    return sales_by_sku


def _build_sku_to_grupo_map(db: Session, ano: int) -> dict:
    """
    Constrói mapeamento: SKU normalizado -> evento_grupo
    para o ano solicitado.
    """
    mappings = db.query(SkuMapping).filter(
        SkuMapping.ano == ano,
        SkuMapping.ativo == True,
        SkuMapping.evento_grupo.isnot(None),
        SkuMapping.evento_grupo != ''
    ).all()
    
    sku_to_grupo = {}
    for m in mappings:
        sku_norm = normalize_sku(m.sku)
        if sku_norm:
            sku_to_grupo[sku_norm] = m.evento_grupo
    return sku_to_grupo


def _aggregate_grupo_sales(sales_data: dict, sku_to_grupo: dict) -> dict:
    """
    Agrega vendas de múltiplos SKUs que pertencem ao mesmo evento_grupo.
    Retorna: {evento_grupo: {qtd_ativo, valor_ativo, qtd_magento, valor_magento}}
    """
    grupo_sales = {}
    for sku, sales in sales_data.items():
        grupo = sku_to_grupo.get(sku)
        if grupo is None:
            continue
        if grupo not in grupo_sales:
            grupo_sales[grupo] = {'qtd_ativo': 0, 'valor_ativo': 0.0, 'qtd_magento': 0, 'valor_magento': 0.0}
        grupo_sales[grupo]['qtd_ativo'] += sales.get('qtd_ativo', 0)
        grupo_sales[grupo]['valor_ativo'] += sales.get('valor_ativo', 0.0)
        grupo_sales[grupo]['qtd_magento'] += sales.get('qtd_magento', 0)
        grupo_sales[grupo]['valor_magento'] += sales.get('valor_magento', 0.0)
    return grupo_sales


@router.get("/playbook")
def get_playbook(current_user: Usuario = Depends(require_permission("marketing_dashboard", "pode_visualizar"))):
    """Retorna o playbook completo com todas as 9 entradas (3 estágios × 3 estados ISC)."""
    stages = [
        {"key": "analitico", "label": "D-90 → D-50", "sublabel": "Analítico", "description": "Fase de análise antecipada. Ações de percepção de valor e construção de demanda."},
        {"key": "estrategico", "label": "D-50 → D-32", "sublabel": "Estratégico", "description": "Fase de decisão estratégica. Janela para ajustes de preço ou promoções privadas."},
        {"key": "operacional", "label": "D-32 → D-0", "sublabel": "Operacional", "description": "Fase de execução final. Foco em conversão, escassez e fechamento de volume."},
    ]
    isc_states = [
        {"key": "forte", "label": "ISC Forte", "threshold": ">1,12", "color": "green"},
        {"key": "estavel", "label": "ISC Estável", "threshold": "0,90–1,12", "color": "yellow"},
        {"key": "fraco", "label": "ISC Fraco", "threshold": "<0,90", "color": "red"},
    ]
    entries = []
    for stage in stages:
        for isc in isc_states:
            entry = _PLAYBOOK.get((stage["key"], isc["key"]), {})
            entries.append({**entry, "stageInfo": stage, "iscInfo": isc})
    return {"stages": stages, "iscStates": isc_states, "entries": entries}

def _refresh_d_minus_in_cached_eventos(cached: dict, cache_key: str) -> dict:
    """
    O cache da lista de eventos pode ter sido gerado em um dia anterior
    (TTL ~22h, stale até 48h) ou ter sido populado a partir do snapshot
    persistido (cuja `dMinusInscricoes` foi gravada quando o snapshot foi
    calculado, dias atrás). Para que o D- exibido sempre reflita o dia
    de hoje (Brasil), recalculamos `dMinus` e `dMinusInscricoes` de cada
    evento diretamente a partir de `evt["date"]` (data do evento) — sem
    depender do timestamp do cache, que pode estar fresco mesmo quando os
    valores embutidos estão antigos.

    Preservamos `dias_encerramento` deduzindo-o da diferença original
    (`dMinus - dMinusInscricoes`), assim cada evento mantém sua própria
    janela de encerramento de inscrições.

    Não mexemos em isActive/iscStatus/etc — esses são reciclados no próximo
    refresh do cache; queremos apenas evitar mostrar D- desatualizado nas
    telas (Dash ISC, Nori, etc.).
    """
    if not isinstance(cached, dict):
        return cached
    eventos = cached.get("eventos")
    if not isinstance(eventos, list) or not eventos:
        return cached
    today = today_brazil()
    new_eventos = []
    changed = False
    for ev in eventos:
        if not isinstance(ev, dict):
            new_eventos.append(ev)
            continue
        ev_date_raw = ev.get("date")
        if not isinstance(ev_date_raw, str) or not ev_date_raw:
            new_eventos.append(ev)
            continue
        try:
            ev_date = date.fromisoformat(ev_date_raw[:10])
        except Exception:
            new_eventos.append(ev)
            continue
        d_ins = ev.get("dMinusInscricoes")
        d_evt = ev.get("dMinus")
        # Deduz dias_encerramento a partir dos valores armazenados (são
        # consistentes entre si mesmo quando defasados em relação a hoje).
        if isinstance(d_ins, int) and isinstance(d_evt, int) and d_evt >= d_ins:
            dias_enc = d_evt - d_ins
        else:
            dias_enc = 2
        new_d_evt_raw = (ev_date - today).days
        new_d_ins_raw = new_d_evt_raw - dias_enc
        new_d_evt = max(0, new_d_evt_raw)
        new_d_ins = max(0, new_d_ins_raw)
        if new_d_ins != d_ins or new_d_evt != d_evt:
            ev = {**ev, "dMinusInscricoes": new_d_ins, "dMinus": new_d_evt}
            changed = True
        # Atualiza isActive com base no delta cru: D-0 (fecha hoje) = ativo
        new_is_active = new_d_ins_raw >= 0
        if ev.get("isActive") != new_is_active:
            ev = {**ev, "isActive": new_is_active}
            changed = True
        new_eventos.append(ev)
    if not changed:
        return cached
    return {**cached, "eventos": new_eventos}


_CUTOFF_VALUES = [65, 50, 45, 35, 30, 15, 7]
_CUTOFF_ESTAGIO = {65: "analitico", 50: "analitico", 45: "estrategico", 35: "estrategico", 30: "operacional", 15: "operacional", 7: "final"}
_CUTOFF_ESTAGIO_LABEL = {65: "Analítico", 50: "Analítico", 45: "Estratégico", 35: "Estratégico", 30: "Operacional", 15: "Operacional", 7: "Final"}

def _match_cutoff_with_weekend(d_minus: int) -> int | None:
    if d_minus in _CUTOFF_VALUES:
        return d_minus
    today = today_brazil()
    weekday = today.weekday()
    if weekday == 4:
        if (d_minus - 1) in _CUTOFF_VALUES:
            return d_minus - 1
        if (d_minus - 2) in _CUTOFF_VALUES:
            return d_minus - 2
    return None

@router.get("/cutoff-alerts")
def get_cutoff_alerts(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing_dashboard", "pode_visualizar")),
):
    """Retorna eventos cujo D-Inscrição está exatamente em um ponto de corte estratégico.
    Na sexta-feira, antecipa pontos de corte que cairiam no sábado ou domingo."""
    ano = datetime.now().year
    cache_key = f"{ano}_active_all_"
    used_cache_key = cache_key
    cached, _ = eventos_list_cache.get_or_revalidate(cache_key, refresh_fn=None)
    if cached is None:
        cache_key2 = f"{ano}_all_all_"
        cached, _ = eventos_list_cache.get_or_revalidate(cache_key2, refresh_fn=None)
        if cached is not None:
            used_cache_key = cache_key2
    # Cache miss (e.g., right after a dash refresh invalidated it): compute the
    # eventos list inline so the Nori cutoff alerts don't temporarily disappear.
    if cached is None:
        try:
            cached = get_marketing_events(
                ano=ano, status=None, categoria=None, busca=None,
                force_refresh=False, db=db, current_user=current_user, response=None,
            )
        except Exception as _e_recompute:
            logger.warning(f"[CutoffAlerts] fallback recompute falhou: {_e_recompute}")
            cached = None
    # Detecta estado "preparing" para o frontend pollar até a lista real chegar.
    data_status = "ready"
    if not cached:
        data_status = "preparing"
    elif isinstance(cached, dict) and cached.get("status") == "preparing":
        data_status = "preparing"
    # Aplica o mesmo recálculo diário de D- usado pela lista de eventos para que
    # os alertas reflitam o dia de hoje mesmo que o cache tenha sido gerado ontem.
    if cached:
        cached = _refresh_d_minus_in_cached_eventos(cached, used_cache_key)
    eventos = cached.get("eventos", []) if cached else []
    alerts = []
    for ev in eventos:
        d = ev.get("dMinusInscricoes") if isinstance(ev, dict) else getattr(ev, "dMinusInscricoes", None)
        matched_cutoff = _match_cutoff_with_weekend(d) if d is not None else None
        if matched_cutoff is not None:
            ev_id = ev.get("id") if isinstance(ev, dict) else getattr(ev, "id", None)
            ev_name = ev.get("name") if isinstance(ev, dict) else getattr(ev, "name", None)
            ev_cat = ev.get("category") if isinstance(ev, dict) else getattr(ev, "category", None)
            ev_isc = ev.get("isc") if isinstance(ev, dict) else getattr(ev, "isc", None)
            ev_isc_status = ev.get("iscStatus") if isinstance(ev, dict) else getattr(ev, "iscStatus", None)
            antecipado = matched_cutoff != d
            alerts.append({
                "id": ev_id,
                "name": ev_name,
                "category": ev_cat,
                "dMinusInscricoes": d,
                "ponto_corte": f"D-{matched_cutoff}",
                "estagio": _CUTOFF_ESTAGIO.get(matched_cutoff, ""),
                "estagio_label": _CUTOFF_ESTAGIO_LABEL.get(matched_cutoff, ""),
                "isc": round(ev_isc, 2) if ev_isc is not None else None,
                "iscStatus": ev_isc_status,
                "antecipado": antecipado,
            })
    alerts.sort(key=lambda x: x["dMinusInscricoes"])

    # Enriquecer alerts com flag de ação registrada consultando acoes_comerciais via SkuMapping
    if alerts:
        from ...models.dimensoes import AcaoComercial
        from .inscricoes_consolidado import normalize_sku as _norm_sku
        cutoff_pcs = [f"D-{v}" for v in _CUTOFF_VALUES]

        # Buscar ações para os ponto_corte conhecidos com o codigo do projeto
        acoes_rows = (
            db.query(AcaoComercial.ponto_corte, DimProjeto.id, DimProjeto.codigo)
            .join(DimProjeto, AcaoComercial.projeto_id == DimProjeto.id)
            .filter(AcaoComercial.ponto_corte.in_(cutoff_pcs))
            .all()
        )

        if acoes_rows:
            # Coletar codigos brutos para filtrar SkuMapping via SQL
            raw_codigos = {str(r.codigo) for r in acoes_rows if r.codigo}
            sm_rows = (
                db.query(SkuMapping.sku, SkuMapping.evento_grupo)
                .filter(SkuMapping.sku.in_(raw_codigos), SkuMapping.evento_grupo != None)
                .all()
            )
            # Chave normalizada -> grupo (mesmo padrão usado no eventos list)
            sku_to_grupo = {_norm_sku(r.sku): r.evento_grupo for r in sm_rows}

            # Construir set de chaves {ev_id|ponto_corte}
            action_keys: set = set()
            for a in acoes_rows:
                pc = a.ponto_corte
                sku_n = _norm_sku(str(a.codigo)) if a.codigo else None
                grupo = sku_to_grupo.get(sku_n) if sku_n else None
                if grupo:
                    action_keys.add(f"grp_{grupo}|{pc}")
                else:
                    action_keys.add(f"{a.id}|{pc}")

            for alert in alerts:
                key = f"{alert['id']}|{alert['ponto_corte']}"
                alert["acao_definida"] = key in action_keys
        else:
            for alert in alerts:
                alert["acao_definida"] = False

    return {"alerts": alerts, "total": len(alerts), "status": data_status}


@router.get("/eventos", response_model=MarketingEventsResponse)
def get_marketing_events(
    ano: int = Query(default=None, description="Ano dos eventos"),
    status: Optional[str] = Query(None, description="Filtrar por status: active, closed, all"),
    categoria: Optional[str] = Query(None, description="Filtrar por categoria/modalidade"),
    busca: Optional[str] = Query(None, description="Buscar por nome do evento"),
    force_refresh: bool = Query(default=False, description="Forçar atualização dos dados ignorando cache"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing_dashboard", "pode_visualizar")),
    response: Response = None
):
    """
    Retorna eventos para o Dashboard ISC com dados consolidados de vendas
    dos bancos Ativo e Magento.
    Agrupa projetos por EventoGrupo quando disponível.
    """
    if ano is None:
        ano = datetime.now().year

    cache_key = f"{ano}_{status or 'all'}_{categoria or 'all'}_{busca or ''}"

    # Caminho de usuário: nunca recomputa síncrono. force_refresh=True de um
    # usuário é tratado como "serve cache + bg refresh" — mesma semântica SWR.
    # Apenas chamadas internas (current_user=None) executam o caminho lento.
    _is_internal_call = current_user is None
    _user_force_refresh = force_refresh and not _is_internal_call

    def _swr_refresh():
        from ...core.database import SessionLocal
        _db = SessionLocal()
        try:
            get_marketing_events(
                ano=ano, status=status, categoria=categoria, busca=busca,
                force_refresh=True, db=_db, current_user=None,
            )
        finally:
            _db.close()

    def _kick_bg_refresh():
        """Dispara refresh em background, deduplicado por cache_key."""
        _bg_key = f"eventos_list:{cache_key}"
        if _bg_key in _swr_recompute_in_progress:
            return
        _swr_recompute_in_progress.add(_bg_key)
        def _runner():
            try:
                _swr_refresh()
            except Exception as _e:
                logger.warning(f"[EventosList] bg refresh '{cache_key}' falhou: {_e}")
            finally:
                _swr_recompute_in_progress.discard(_bg_key)
        try:
            import threading as _list_threading
            _list_threading.Thread(target=_runner, daemon=True).start()
        except Exception:
            _swr_recompute_in_progress.discard(_bg_key)

    _USE_SNAPSHOT_FIRST_LIST = os.getenv(
        "USE_SNAPSHOT_FIRST_LIST", "true"
    ).lower() not in ("0", "false", "no")

    if not _is_internal_call:
        # Usuário: sempre tenta cache primeiro.
        cached, is_stale = eventos_list_cache.get_or_revalidate(
            cache_key,
            refresh_fn=_swr_refresh if not _user_force_refresh else None,
        )
        if _user_force_refresh:
            _kick_bg_refresh()
        # "Empty" só é suspeito quando NÃO há filtros (busca/categoria/status):
        # uma busca que legitimamente não casa com nenhum evento deve retornar
        # eventos=[] de forma estável e não ser tratada como cache envenenado.
        _is_base_query = (
            not busca
            and (not categoria or categoria == "all")
            and (not status or status == "all")
        )
        # Detecta cache "envenenado" por build parcial: cache existe porém
        # com eventos vazios na consulta base. Trata como cache miss e cai no
        # fallback de snapshot, para que a lista nunca apareça vazia se
        # houver dados persistidos no banco.
        _cached_eventos_empty = (
            _is_base_query
            and isinstance(cached, dict)
            and not (cached.get("eventos") or [])
            and cached.get("status") != "preparing"
        )
        def _serve_cached(_c):
            from app.core.cache import get_last_full_refresh as _glf_eventos
            _lfr_ev = _glf_eventos()
            _c = dict(_c)
            if _lfr_ev:
                _c["ultima_atualizacao"] = datetime.fromtimestamp(
                    _lfr_ev, tz=ZoneInfo('America/Sao_Paulo')
                ).isoformat()
            # Avisos refletem o estado atual da conexão — não devem ser servidos
            # do cache, senão um erro transitório no momento do build congela o
            # banner "Dados Parciais" indefinidamente, mesmo após recuperação.
            _c["avisos"] = list(get_isc_warnings())
            _c = _refresh_d_minus_in_cached_eventos(_c, cache_key)
            if response is not None:
                response.headers["X-Data-Stale"] = "true" if (is_stale or _user_force_refresh) else "false"
            return _c

        if cached is not None and not _cached_eventos_empty:
            return _serve_cached(cached)
        if _cached_eventos_empty:
            # Cache base com eventos=[] pode ser: (a) envenenado por build
            # parcial — neste caso o snapshot persistente terá eventos e
            # devemos invalidar/substituir; ou (b) ambiente legitimamente
            # vazio — neste caso o snapshot também volta vazio/None e
            # devemos servir o cache atual mesmo, em vez de entrar em loop
            # de "preparing". Decidimos com base no que o snapshot diz.
            _snap_probe = None
            if _USE_SNAPSHOT_FIRST_LIST:
                try:
                    from ...services.event_detail_snapshot_service import (
                        aggregate_eventos_list_from_snapshots as _agg_list_p,
                    )
                    _snap_probe = _agg_list_p(db, ano, status, categoria, busca)
                except Exception as _agg_pe:
                    logger.warning(f"[EventosList] snapshot probe falhou: {_agg_pe}")
                    _snap_probe = None
            if _snap_probe is not None and (_snap_probe.get("eventos") or []):
                logger.warning(
                    f"[EventosList] cache envenenado (eventos=[]) detectado "
                    f"(cache_key={cache_key}) — substituindo pelo snapshot persistido "
                    f"com {len(_snap_probe.get('eventos') or [])} eventos"
                )
                try:
                    eventos_list_cache.invalidate(cache_key)
                except Exception:
                    try:
                        eventos_list_cache.invalidate()
                    except Exception:
                        pass
                eventos_list_cache.set(cache_key, _snap_probe)
                _kick_bg_refresh()
                if response is not None:
                    response.headers["X-Data-Stale"] = "true"
                    response.headers["X-Data-Source"] = "snapshot-aggregate"
                _snap_probe = dict(_snap_probe)
                _snap_probe["avisos"] = list(get_isc_warnings())
                return _refresh_d_minus_in_cached_eventos(_snap_probe, cache_key)
            # Snapshot probe == None pode significar: (1) nenhuma linha de
            # snapshot para o ano (ambiente legitimamente vazio), (2) cobertura
            # abaixo do threshold (rows existem mas não suficientes), ou (3)
            # erro de leitura. Só confirmamos "empty legítimo" quando uma
            # contagem direta no EventoDetailSnapshot confirmar zero linhas.
            _snap_rows_for_year = -1
            try:
                from ...models.evento_detail_snapshot import EventoDetailSnapshot
                _snap_rows_for_year = (
                    db.query(EventoDetailSnapshot)
                    .filter(EventoDetailSnapshot.ano == ano)
                    .count()
                )
            except Exception as _cnt_e:
                logger.warning(f"[EventosList] count EventoDetailSnapshot falhou: {_cnt_e}")
                _snap_rows_for_year = -1
            # Segunda checagem de legitimidade: além de 0 snapshots, exigir
            # 0 eventos canônicos cadastrados no ano. Sem isso, um ambiente
            # com CadastroEvento mas sem snapshots construídos seria
            # classificado erroneamente como "empty legítimo" e os eventos
            # ficariam invisíveis até manual refresh.
            _canonical_count_for_year = -1
            try:
                from ...models.cadastro_evento import CadastroEvento as _CadEvt
                from sqlalchemy import or_ as _or
                # data_evento é nullable e o cadastro pode ter apenas
                # ano_evento. Confirmamos "vazio canônico" exigindo ambas
                # condições negativas: nenhum match nem por ano_evento nem
                # pelo intervalo indexavel de data_evento.
                _year_start = date(int(ano), 1, 1)
                _year_end = date(int(ano) + 1, 1, 1)
                _canonical_count_for_year = (
                    db.query(_CadEvt)
                    .filter(
                        _or(
                            _CadEvt.ano_evento == ano,
                            (
                                (_CadEvt.data_evento >= _year_start)
                                & (_CadEvt.data_evento < _year_end)
                            ),
                        )
                    )
                    .count()
                )
            except Exception as _cce:
                logger.warning(f"[EventosList] count CadastroEvento falhou: {_cce}")
                _canonical_count_for_year = -1
            if _snap_rows_for_year == 0 and _canonical_count_for_year == 0:
                logger.info(
                    f"[EventosList] cache eventos=[] confirmado por 0 snapshots e "
                    f"0 cadastros no ano (cache_key={cache_key}) — servindo cache "
                    f"como resultado legítimo"
                )
                # Refresh dedupado de auto-cura, caso novos cadastros entrem.
                _kick_bg_refresh()
                return _serve_cached(cached)
            # Snapshots existem mas probe não retornou (cobertura baixa ou erro).
            # NÃO confirma empty — agenda refresh e cai no caminho de
            # "preparing" abaixo, evitando cimentar o cache envenenado.
            logger.warning(
                f"[EventosList] cache eventos=[] suspeito (cache_key={cache_key}, "
                f"snapshot_rows_ano={_snap_rows_for_year}) — não confirmado por probe, "
                f"agendando refresh e retornando preparing"
            )
            try:
                eventos_list_cache.invalidate(cache_key)
            except Exception:
                try:
                    eventos_list_cache.invalidate()
                except Exception:
                    pass
            _kick_bg_refresh()
        # Sem cache em memória (ou cache vazio descartado acima): tenta agregar
        # dos snapshots persistentes (mesmo motivo do detalhe — abrir
        # instantâneo após restart). Se a cobertura for boa, retorna
        # imediatamente e dispara um refresh em bg para promover ao caminho
        # lento (margem por kit, etc.).
        if _USE_SNAPSHOT_FIRST_LIST:
            try:
                from ...services.event_detail_snapshot_service import (
                    aggregate_eventos_list_from_snapshots as _agg_list,
                )
                _snap_list = _agg_list(db, ano, status, categoria, busca)
            except Exception as _agg_e:
                logger.warning(f"[EventosList] snapshot aggregate falhou: {_agg_e}")
                _snap_list = None
            # Mesma guarda do caminho lento, restrita à consulta base: só
            # bloqueamos a promoção de snapshots vazios quando NÃO há filtros.
            # Para buscas/categorias filtradas, um aggregate vazio pode ser
            # legítimo ("nenhum evento casa") e deve ser servido normalmente.
            _snap_has_eventos = bool(_snap_list and (_snap_list.get("eventos") or []))
            if _snap_list is not None and (_snap_has_eventos or not _is_base_query):
                eventos_list_cache.set(cache_key, _snap_list)
                _kick_bg_refresh()
                if response is not None:
                    response.headers["X-Data-Stale"] = "true"
                    response.headers["X-Data-Source"] = "snapshot-aggregate"
                # Avisos atualizados também aqui, pelo mesmo motivo do
                # caminho de cache-hit acima.
                _snap_list = dict(_snap_list)
                _snap_list["avisos"] = list(get_isc_warnings())
                return _refresh_d_minus_in_cached_eventos(_snap_list, cache_key)
            # Cobertura de snapshots insuficiente (ex: snapshot de um evento foi
            # apagado pelo kit_config e o rebuild ainda está em andamento). Antes
            # de cair em "preparing" com lista vazia, tenta servir um stale do
            # eventos_list_cache — ele não é invalidado pelo kit_config e pode
            # conter a lista completa do último build bem-sucedido.
            if _snap_list is None:
                _stale_fallback = eventos_list_cache.get(cache_key, stale_ok=True)
                if _stale_fallback and (_stale_fallback.get("eventos") or []):
                    _kick_bg_refresh()
                    if response is not None:
                        response.headers["X-Data-Stale"] = "true"
                        response.headers["X-Data-Source"] = "stale-fallback"
                    logger.info(
                        f"[EventosList] cobertura snapshot baixa — servindo stale cache "
                        f"({len(_stale_fallback.get('eventos') or [])} eventos) enquanto rebuild ocorre"
                    )
                    _stale_fallback = dict(_stale_fallback)
                    _stale_fallback["avisos"] = list(get_isc_warnings())
                    return _refresh_d_minus_in_cached_eventos(_stale_fallback, cache_key)
        # Sem cache e sem cobertura de snapshot: dispara refresh em background
        # (deduplicado) e retorna preparing. O frontend faz polling.
        _kick_bg_refresh()
        if response is not None:
            response.headers["X-Data-Preparing"] = "true"
            response.headers["X-Data-Stale"] = "true"
        return {
            "status": "preparing",
            "eventos": [],
            "resumo": {
                "totalActiveEvents": 0,
                "eventsGreen": 0,
                "eventsYellow": 0,
                "eventsRed": 0,
            },
            "categorias": [],
            "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(),
            "avisos": ["Estamos preparando os eventos. Em alguns segundos a lista aparece aqui."],
        }
    # Caminho interno (warmup/SWR): executa o caminho completo abaixo.

    # Coleta IDs de snapshots já existentes para este ano — usados adiante para
    # "bootstrap" de grupos sem snapshot (sem abrir queries individuais no loop).
    _existing_snapshot_ids: set[str] = set()
    if _is_internal_call and not status and not categoria and not busca:
        try:
            from ...services.event_detail_snapshot_service import EventoDetailSnapshot as _EDS
            _snap_id_rows = db.query(_EDS.evento_id).filter(_EDS.ano == ano).all()
            _existing_snapshot_ids = {r[0] for r in _snap_id_rows}
        except Exception:
            pass

    isc_cfg = _get_isc_settings(db)
    
    cadastro_query = db.query(CadastroEvento)
    if categoria and categoria != 'all':
        cadastro_query = cadastro_query.filter(CadastroEvento.modalidade == categoria)
    if busca:
        cadastro_query = cadastro_query.filter(CadastroEvento.nome.ilike(f'%{busca}%'))
    cadastros = cadastro_query.all()
    
    cadastro_by_projeto_id = {}
    for cad in cadastros:
        if cad.projeto_id:
            cadastro_by_projeto_id[cad.projeto_id] = cad
    
    projeto_ids = [cad.projeto_id for cad in cadastros if cad.projeto_id]
    projetos = db.query(DimProjeto).filter(DimProjeto.id.in_(projeto_ids)).all() if projeto_ids else []
    
    from ...core.cache import is_full_refresh_in_progress as _is_refreshing
    isc_force = force_refresh and not _is_refreshing()
    isc_data = fetch_isc_pricing_data(db=db, force_refresh=isc_force)
    
    sku_to_grupo = _build_sku_to_grupo_map(db, ano)
    
    grupo_names_set = set(sku_to_grupo.values())
    grupo_details = {}
    if grupo_names_set:
        grupo_list = db.query(EventoGrupoModel).filter(
            EventoGrupoModel.nome.in_(list(grupo_names_set)),
            EventoGrupoModel.ativo == True
        ).all()
        for g in grupo_list:
            grupo_details[g.nome] = g
    
    grupo_projetos = {}
    standalone_projetos = []
    
    for projeto in projetos:
        projeto_codigo = str(projeto.codigo) if projeto.codigo else None
        if not projeto_codigo:
            continue
        
        sku_norm = normalize_sku(projeto_codigo)
        grupo_nome = sku_to_grupo.get(sku_norm)
        
        if grupo_nome and grupo_nome in grupo_details:
            if grupo_nome not in grupo_projetos:
                grupo_projetos[grupo_nome] = []
            grupo_projetos[grupo_nome].append(projeto)
        else:
            standalone_projetos.append(projeto)
    
    eventos = []
    categorias_set: set[str] = set()
    events_green = 0
    events_yellow = 0
    events_red = 0
    active_count = 0
    
    all_projeto_ids = []
    for proj_list in grupo_projetos.values():
        all_projeto_ids.extend([p.id for p in proj_list])
    all_projeto_ids.extend([p.id for p in standalone_projetos])
    
    active_actions_map = get_active_actions_for_projects(db, all_projeto_ids)
    kit_costs_batch = get_kit_basico_costs_batch(db, all_projeto_ids) if all_projeto_ids else {}
    _kit_batch_data = _build_kit_cost_batch_data(db, all_projeto_ids, ano) if all_projeto_ids else {}
    ticket_atual_map = _get_ticket_atual_map(db)

    all_grupo_names_for_hist = set(grupo_projetos.keys())
    for projeto in standalone_projetos:
        sku_n = normalize_sku(str(projeto.codigo)) if projeto.codigo else None
        if sku_n:
            eg = sku_to_grupo.get(sku_n)
            if eg:
                all_grupo_names_for_hist.add(eg)
    hist_patterns_prefetch, curva_info_prefetch = _prefetch_all_historical_patterns(db, list(all_grupo_names_for_hist), ano)

    # Fix P1: batch UMA query de snapshot agregado pra TODOS os grupos antes
    # do loop, eliminando N+1 quando _consolidated_totals dá miss. Grupos não
    # consolidados simplesmente não retornam linhas — sem custo extra.
    # Flag `_snapshot_batch_failed` separa "prefetch deu exceção" (precisa
    # fallback per-grupo) de "prefetch ok porém vazio" (resultado válido,
    # vai direto pro fallback live sem refazer N queries).
    _snapshot_batch_failed = False
    _snapshot_batch_metrics: dict = {}
    try:
        from ...services.snapshot_service import get_snapshot_metrics_for_grupos_batch as _snap_batch
        _snapshot_batch_metrics = _snap_batch(db, list(grupo_projetos.keys()), ano=ano)
    except Exception as _snap_err:
        logger.warning(f"[ISC] prefetch batch snapshot falhou, fallback per-grupo: {_snap_err}")
        _snapshot_batch_failed = True

    for grupo_nome, proj_list in grupo_projetos.items():
        grupo = grupo_details[grupo_nome]
        
        total_capacity = 0
        for p in proj_list:
            cad = cadastro_by_projeto_id.get(p.id)
            if cad:
                total_capacity += get_meta_from_cadastro(cad)
            else:
                total_capacity += get_meta_orcada(db, p.id)
        
        latest_date = None
        rep_projeto = proj_list[0]
        rep_cadastro = cadastro_by_projeto_id.get(rep_projeto.id)
        
        for p in proj_list:
            if p.data_evento:
                if latest_date is None or p.data_evento > latest_date:
                    latest_date = p.data_evento
                    rep_projeto = p
                    rep_cadastro = cadastro_by_projeto_id.get(p.id)
        
        projeto_data_evento = latest_date or rep_projeto.data_evento
        dias_enc = get_dias_encerramento(db, projeto_id=rep_projeto.id, cadastro=rep_cadastro) if rep_projeto else 2
        d_minus_inscricoes = calculate_d_minus(projeto_data_evento, dias_encerramento=dias_enc) if projeto_data_evento else 0
        d_minus = calculate_d_minus(projeto_data_evento, dias_encerramento=0) if projeto_data_evento else 0
        # is_active usa delta cru (sem max(0,…)) para incluir eventos com D-0
        # (inscrições fechando hoje). calculate_d_minus clamp a 0, então D-0
        # e D-negativo retornam 0 — precisamos da comparação de data direta.
        is_active = bool(
            projeto_data_evento and
            (projeto_data_evento - timedelta(days=dias_enc)) >= today_brazil()
        )
        grupo_regime = get_data_regime(projeto_data_evento, dias_enc) if projeto_data_evento else "live"
        
        if status == 'active' and not is_active:
            continue
        if status == 'closed' and is_active:
            continue
        
        current_sales = 0
        current_receita = 0.0
        grupo_m7d = 0.0
        grupo_m14d = 0.0
        grupo_m30d = 0.0

        if grupo_regime == "consolidated":
            _ct = isc_data.get('_consolidated_totals', {}).get(grupo_nome)
            if _ct is not None:
                current_sales = _ct['qtd_site']
                current_receita = _ct['receita_liquida_site']
            else:
                # Fix P1: lê do batch prefetched; só cai no per-grupo quando
                # o prefetch deu EXCEÇÃO (flag explícita). Prefetch ok porém
                # vazio para o grupo é resultado válido → vai direto pro
                # fallback live abaixo sem refazer N queries.
                snap = _snapshot_batch_metrics.get(grupo_nome)
                if snap is None and _snapshot_batch_failed:
                    snap = _get_snapshot_metrics_for_grupo(db, grupo_nome, ano=ano)
                if snap is not None:
                    current_sales = snap['qtd_site']
                    current_receita = snap['receita_liquida_site']
                else:
                    seen_grupo_norms_c = set()
                    for p in proj_list:
                        p_sku = normalize_sku(str(p.codigo)) if p.codigo else None
                        if p_sku and p_sku not in seen_grupo_norms_c and p_sku in isc_data:
                            seen_grupo_norms_c.add(p_sku)
                            current_sales += isc_data[p_sku].get('qtd_site', 0)
                            current_receita += isc_data[p_sku].get('receita_liquida_site', 0.0)
        else:
            seen_grupo_norms = set()
            for p in proj_list:
                p_sku = normalize_sku(str(p.codigo)) if p.codigo else None
                if p_sku and p_sku not in seen_grupo_norms and p_sku in isc_data:
                    seen_grupo_norms.add(p_sku)
                    current_sales += isc_data[p_sku].get('qtd_site', 0)
                    current_receita += isc_data[p_sku].get('receita_liquida_site', 0.0)
                    grupo_m7d += isc_data[p_sku].get('media_7d', 0.0)
                    grupo_m14d += isc_data[p_sku].get('media_14d', 0.0)
                    grupo_m30d += isc_data[p_sku].get('media_30d', 0.0)

        sales_goal = total_capacity
        avg_ticket = round(current_receita / current_sales, 2) if current_sales > 0 else 0.0

        budget_ticket_total_receita = 0.0
        budget_ticket_total_qtd = 0
        for p in proj_list:
            cad_bt = cadastro_by_projeto_id.get(p.id)
            if cad_bt and cad_bt.atletas_site_tkt_medio and cad_bt.atletas_site_pago:
                budget_ticket_total_receita += float(cad_bt.atletas_site_tkt_medio) * int(cad_bt.atletas_site_pago)
                budget_ticket_total_qtd += int(cad_bt.atletas_site_pago)
        budget_ticket = round(budget_ticket_total_receita / budget_ticket_total_qtd, 2) if budget_ticket_total_qtd > 0 else 0.0

        grupo_hist_pattern = hist_patterns_prefetch.get(grupo_nome)
        grupo_curva_info = curva_info_prefetch.get(grupo_nome, {"tipo_curva": "linear", "fonte_curva": None, "ano_referencia": None})
        grupo_reg_close = (projeto_data_evento - timedelta(days=dias_enc)) if projeto_data_evento else None

        isc_components = calculate_isc_components(
            current_sales, sales_goal, d_minus_inscricoes,
            media_7d=grupo_m7d,
            media_14d=grupo_m14d,
            media_30d=grupo_m30d,
            hist_pattern=grupo_hist_pattern,
            registration_close_date=grupo_reg_close,
            curva_info=grupo_curva_info,
            use_normalized_curve=isc_cfg.get("useNormalizedCurveForISC", False)
        )
        isc = calculate_isc(isc_components, isc_cfg["ia730Weight"], isc_cfg["curvaDWeight"], isc_cfg["rolling14dWeight"])
        isc_status = get_isc_status(isc, isc_cfg["greenThreshold"], isc_cfg["yellowThreshold"])
        suggested_action = get_suggested_action(isc, d_minus_inscricoes, isc_cfg["greenThreshold"], isc_cfg["yellowThreshold"], isc_cfg["promotionDeadline"])
        
        if is_active:
            active_count += 1
            if isc_status == 'accelerating':
                events_green += 1
            elif isc_status == 'stable':
                events_yellow += 1
            else:
                events_red += 1
        
        grupo_modalidade = str(rep_cadastro.modalidade) if rep_cadastro and rep_cadastro.modalidade else (str(rep_projeto.modalidade) if rep_projeto.modalidade else None)
        if grupo_modalidade:
            categorias_set.add(grupo_modalidade)
        
        grupo_location = str(rep_cadastro.localizacao_evento) if rep_cadastro and rep_cadastro.localizacao_evento else (str(rep_projeto.cidade) if rep_projeto.cidade else None)
        
        skus_list = [str(p.codigo) for p in proj_list if p.codigo]
        
        grupo_active_action = None
        for p in proj_list:
            if p.id in active_actions_map:
                grupo_active_action = active_actions_map[p.id]
                break
        
        grupo_kit_weighted_num = 0.0
        grupo_kit_weighted_den = 0
        for p in proj_list:
            p_cad = cadastro_by_projeto_id.get(p.id)
            p_cap = get_meta_from_cadastro(p_cad) if p_cad else get_meta_orcada(db, p.id)
            p_kc = kit_costs_batch.get(p.id, 50.0)
            grupo_kit_weighted_num += p_kc * p_cap
            grupo_kit_weighted_den += p_cap
        grupo_kit_cost_avg = (grupo_kit_weighted_num / grupo_kit_weighted_den) if grupo_kit_weighted_den > 0 else 50.0
        grupo_margin = _calc_margin_fields(budget_ticket, grupo_kit_cost_avg, sales_goal,
                                            avg_ticket, current_sales, current_receita)

        _grupo_proj_ids = [p.id for p in proj_list]
        _grupo_kit_cost_sum = _get_group_kit_cost_sum(_grupo_proj_ids, _kit_batch_data, current_sales)
        _grupo_margem_kits_total = round(current_receita - _grupo_kit_cost_sum, 2) if (
            _grupo_kit_cost_sum is not None and current_receita > 0
        ) else None
        
        grupo_ticket_atual = _get_ticket_atual_for_event(ticket_atual_map, _grupo_proj_ids)
        grupo_ticket_kit_nome = _get_ticket_atual_kit_nome_for_event(ticket_atual_map, _grupo_proj_ids)
        
        evento = MarketingEvent(
            id=f"grp_{grupo_nome}",
            name=grupo.nome,
            date=projeto_data_evento.isoformat() if projeto_data_evento else "",
            location=grupo_location or "Não definido",
            category=grupo_modalidade or "Corrida",
            totalCapacity=sales_goal,
            currentSales=current_sales,
            salesGoal=sales_goal,
            averageTicket=round(avg_ticket, 2),
            budgetTicket=budget_ticket,
            dMinus=d_minus,
            dMinusInscricoes=d_minus_inscricoes,
            isc=isc,
            iscComponents=isc_components,
            iscStatus=isc_status,
            suggestedAction=suggested_action,
            activeAction=grupo_active_action,
            isActive=is_active,
            sku=",".join(skus_list),
            ticketAtual=grupo_ticket_atual,
            ticketKitNome=grupo_ticket_kit_nome,
            dataRegime=grupo_regime,
            incluirCortesias=bool(getattr(grupo, 'incluir_cortesias', False)),
            margemRealizadaKitsTotal=_grupo_margem_kits_total,
            **grupo_margin
        )
        eventos.append(evento)

        # Bootstrap: salva snapshot para grupos sem registro persistido,
        # garantindo que apareçam no aggregate após restarts do servidor.
        if _is_internal_call and evento.id not in _existing_snapshot_ids:
            try:
                from ...services.event_detail_snapshot_service import save_persisted_detail as _spd
                _spd(
                    db, evento.id, ano,
                    {"evento": evento.model_dump(mode="json")},
                    data_evento=projeto_data_evento,
                    is_completed=not is_active,
                )
                _existing_snapshot_ids.add(evento.id)
                logger.info(f"[EventosList] snapshot bootstrap salvo para {evento.id} ano={ano}")
            except Exception as _snap_e:
                logger.debug(f"[EventosList] snapshot bootstrap falhou para {evento.id}: {_snap_e}")

    for projeto in standalone_projetos:
        projeto_codigo = str(projeto.codigo) if projeto.codigo else None
        if not projeto_codigo:
            continue
        
        cad = cadastro_by_projeto_id.get(projeto.id)
        sku = projeto_codigo
        projeto_data_evento = projeto.data_evento
        dias_enc = get_dias_encerramento(db, projeto_id=projeto.id, cadastro=cad)
        d_minus_inscricoes = calculate_d_minus(projeto_data_evento, dias_encerramento=dias_enc) if projeto_data_evento else 0
        d_minus = calculate_d_minus(projeto_data_evento, dias_encerramento=0) if projeto_data_evento else 0
        is_active = bool(
            projeto_data_evento and
            (projeto_data_evento - timedelta(days=dias_enc)) >= today_brazil()
        )
        standalone_regime = get_data_regime(projeto_data_evento, dias_enc) if projeto_data_evento else "live"
        
        if status == 'active' and not is_active:
            continue
        if status == 'closed' and is_active:
            continue
        
        sku_norm = normalize_sku(sku)
        standalone_eg = sku_to_grupo.get(normalize_sku(sku))

        if standalone_regime == "consolidated":
            snap_eg = standalone_eg or sku_norm
            snap = _get_snapshot_metrics_for_grupo(db, snap_eg, ano=ano)
            if snap is not None:
                current_sales = snap['qtd_site']
                current_receita = snap['receita_liquida_site']
                standalone_m7d = 0.0
                standalone_m14d = 0.0
                standalone_m30d = 0.0
            else:
                sales_info = isc_data.get(sku_norm, {})
                current_sales = sales_info.get('qtd_site', 0)
                current_receita = sales_info.get('receita_liquida_site', 0.0)
                standalone_m7d = 0.0
                standalone_m14d = 0.0
                standalone_m30d = 0.0
        else:
            sales_info = isc_data.get(sku_norm, {})
            current_sales = sales_info.get('qtd_site', 0)
            current_receita = sales_info.get('receita_liquida_site', 0.0)
            standalone_m7d = sales_info.get('media_7d', 0.0)
            standalone_m14d = sales_info.get('media_14d', 0.0)
            standalone_m30d = sales_info.get('media_30d', 0.0)
        
        sales_goal = get_meta_from_cadastro(cad) if cad else get_meta_orcada(db, projeto.id)
        avg_ticket = round(current_receita / current_sales, 2) if current_sales > 0 else 0.0
        standalone_budget_ticket = round(float(cad.atletas_site_tkt_medio), 2) if cad and cad.atletas_site_tkt_medio and cad.atletas_site_pago and cad.atletas_site_pago > 0 else 0.0
        
        standalone_hist = hist_patterns_prefetch.get(standalone_eg) if standalone_eg else None
        standalone_curva_info = curva_info_prefetch.get(standalone_eg, {"tipo_curva": "linear", "fonte_curva": None, "ano_referencia": None}) if standalone_eg else {"tipo_curva": "linear", "fonte_curva": None, "ano_referencia": None}
        standalone_reg_close = (projeto_data_evento - timedelta(days=dias_enc)) if projeto_data_evento else None

        isc_components = calculate_isc_components(
            current_sales, sales_goal, d_minus_inscricoes,
            media_7d=standalone_m7d,
            media_14d=standalone_m14d,
            media_30d=standalone_m30d,
            hist_pattern=standalone_hist,
            registration_close_date=standalone_reg_close,
            curva_info=standalone_curva_info,
            use_normalized_curve=isc_cfg.get("useNormalizedCurveForISC", False)
        )
        isc = calculate_isc(isc_components, isc_cfg["ia730Weight"], isc_cfg["curvaDWeight"], isc_cfg["rolling14dWeight"])
        isc_status = get_isc_status(isc, isc_cfg["greenThreshold"], isc_cfg["yellowThreshold"])
        suggested_action = get_suggested_action(isc, d_minus_inscricoes, isc_cfg["greenThreshold"], isc_cfg["yellowThreshold"], isc_cfg["promotionDeadline"])
        
        if is_active:
            active_count += 1
            if isc_status == 'accelerating':
                events_green += 1
            elif isc_status == 'stable':
                events_yellow += 1
            else:
                events_red += 1
        
        evento_modalidade = str(cad.modalidade) if cad and cad.modalidade else (str(projeto.modalidade) if projeto.modalidade else None)
        if evento_modalidade:
            categorias_set.add(evento_modalidade)
        
        evento_location = str(cad.localizacao_evento) if cad and cad.localizacao_evento else (str(projeto.cidade) if projeto.cidade else None)
        evento_nome = str(cad.nome) if cad and cad.nome else (str(projeto.evento) if projeto.evento else "Evento sem nome")
        
        standalone_active_action = active_actions_map.get(projeto.id)
        
        standalone_kit_cost = kit_costs_batch.get(projeto.id, 50.0)
        standalone_margin = _calc_margin_fields(standalone_budget_ticket, standalone_kit_cost, sales_goal,
                                                 avg_ticket, current_sales, current_receita)

        _sa_kit_cost_sum = _get_group_kit_cost_sum([projeto.id], _kit_batch_data, current_sales)
        _sa_margem_kits_total = round(current_receita - _sa_kit_cost_sum, 2) if (
            _sa_kit_cost_sum is not None and current_receita > 0
        ) else None
        
        standalone_ticket_atual = _get_ticket_atual_for_event(ticket_atual_map, projeto.id)
        standalone_ticket_kit_nome = _get_ticket_atual_kit_nome_for_event(ticket_atual_map, projeto.id)
        
        evento = MarketingEvent(
            id=str(projeto.id),
            name=evento_nome,
            date=projeto_data_evento.isoformat() if projeto_data_evento else "",
            location=evento_location or "Não definido",
            category=evento_modalidade or "Corrida",
            totalCapacity=sales_goal,
            currentSales=current_sales,
            salesGoal=sales_goal,
            averageTicket=round(avg_ticket, 2),
            budgetTicket=standalone_budget_ticket,
            dMinus=d_minus,
            dMinusInscricoes=d_minus_inscricoes,
            isc=isc,
            iscComponents=isc_components,
            iscStatus=isc_status,
            suggestedAction=suggested_action,
            activeAction=standalone_active_action,
            isActive=is_active,
            sku=sku,
            ticketAtual=standalone_ticket_atual,
            ticketKitNome=standalone_ticket_kit_nome,
            dataRegime=standalone_regime,
            incluirCortesias=bool(getattr(projeto, 'incluir_cortesias', False)),
            margemRealizadaKitsTotal=_sa_margem_kits_total,
            **standalone_margin
        )
        eventos.append(evento)

        # Bootstrap: salva snapshot para standalone sem registro persistido.
        if _is_internal_call and evento.id not in _existing_snapshot_ids:
            try:
                from ...services.event_detail_snapshot_service import save_persisted_detail as _spd
                _spd(
                    db, evento.id, ano,
                    {"evento": evento.model_dump(mode="json")},
                    data_evento=projeto_data_evento,
                    is_completed=not is_active,
                )
                _existing_snapshot_ids.add(evento.id)
                logger.info(f"[EventosList] snapshot bootstrap salvo para standalone {evento.id} ano={ano}")
            except Exception as _snap_e:
                logger.debug(f"[EventosList] snapshot bootstrap falhou para standalone {evento.id}: {_snap_e}")

    eventos.sort(key=lambda e: (not e.isActive, e.dMinus))
    
    resumo = DashboardSummary(
        totalActiveEvents=active_count,
        eventsGreen=events_green,
        eventsYellow=events_yellow,
        eventsRed=events_red
    )
    
    from app.core.cache import get_last_full_refresh as _eventos_get_lfr
    _eventos_lfr = _eventos_get_lfr()
    _eventos_ts = (
        datetime.fromtimestamp(_eventos_lfr, tz=ZoneInfo('America/Sao_Paulo')).isoformat()
        if _eventos_lfr
        else datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat()
    )
    result = MarketingEventsResponse(
        status="success",
        eventos=eventos,
        resumo=resumo,
        categorias=sorted(list(categorias_set)),
        ultima_atualizacao=_eventos_ts,
        avisos=get_isc_warnings()
    )
    # Guarda: nunca persistir um cache vazio NA CONSULTA BASE. Builds parciais
    # (falha transitória do PostgreSQL/Magento) podem produzir `eventos=[]`
    # mesmo havendo dados gravados; cachear esse resultado faria a lista
    # "sumir" para todos os usuários até a próxima reconstrução. Para
    # consultas filtradas (busca/categoria/status), eventos=[] pode ser
    # legítimo e é cacheado normalmente.
    _is_base_query_w = (
        not busca
        and (not categoria or categoria == "all")
        and (not status or status == "all")
    )
    # Só preservamos cache anterior (skip do set) quando há evidência de que o
    # "vazio" é anômalo: existe um cache prévio com eventos para a MESMA
    # cache_key. Sem essa evidência, um ambiente legitimamente vazio (ano sem
    # eventos, env nova) ficaria preso em "preparing" para sempre.
    _skip_empty_cache_write = False
    if not eventos and _is_base_query_w:
        try:
            _prior = eventos_list_cache.get(cache_key, stale_ok=True)
            if isinstance(_prior, dict) and (_prior.get("eventos") or []):
                _skip_empty_cache_write = True
        except Exception:
            _skip_empty_cache_write = False
    if not _skip_empty_cache_write:
        eventos_list_cache.set(cache_key, result.model_dump(mode="json"))
    else:
        logger.warning(
            f"[EventosList] resultado vazio NÃO cacheado (cache_key={cache_key}, "
            f"avisos={len(get_isc_warnings())}) — preservando cache anterior não-vazio"
        )
    if response is not None:
        response.headers["X-Data-Stale"] = "false" if eventos else "true"
    return result


@router.get("/resumo")
def get_marketing_summary(
    ano: int = Query(default=None, description="Ano dos eventos"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing_dashboard", "pode_visualizar"))
):
    """
    Retorna apenas o resumo do Dashboard ISC (contagem por zona).
    """
    response = get_marketing_events(ano=ano, db=db, current_user=current_user)
    return {
        "status": "success",
        "resumo": response.resumo,
        "ultima_atualizacao": response.ultima_atualizacao
    }


@router.get("/eventos/{evento_id}/medias-vendas")
def get_sales_averages(
    evento_id: str,
    periodo: int = Query(default=30, description="Período em dias para calcular médias (7, 14, 30, 60, 90)"),
    ano: int = Query(default=None, description="Ano do evento"),
    force_refresh: bool = Query(default=False, description="Forçar atualização dos dados ignorando cache"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing_dashboard", "pode_visualizar")),
    response: Response = None
):
    from datetime import timedelta
    
    today = today_brazil()
    if ano is None:
        if evento_id.startswith('grp_'):
            ano = _resolve_default_ano_for_grupo(db, evento_id.replace('grp_', ''), today.year)
        else:
            ano = today.year
    
    medias_cache_key = f"{ano}_{evento_id}_{periodo}_medias"
    if not force_refresh:
        def _swr_medias_refresh():
            from ...core.database import SessionLocal
            _db = SessionLocal()
            try:
                get_sales_averages(evento_id=evento_id, periodo=periodo, ano=ano, force_refresh=True, db=_db, current_user=None)
            finally:
                _db.close()

        cached_medias, is_stale = medias_cache.get_or_revalidate(medias_cache_key, refresh_fn=_swr_medias_refresh)
        if cached_medias is not None:
            if response is not None:
                response.headers["X-Data-Stale"] = "true" if is_stale else "false"
            return cached_medias
    
    is_consolidated = evento_id.startswith('grp_')
    
    all_skus = []
    
    if is_consolidated:
        grupo_nome = evento_id.replace('grp_', '')
        mappings = _wq_sku_mappings_by_grupo_single_year(db, grupo_nome, ano)
        if not mappings:
            mappings = _wq_sku_mappings_by_grupo(db, grupo_nome, [ano])
            if not mappings:
                from app.core.cache import get_warmup_sku_mappings_by_grupo
                if _is_warmup_thread():
                    all_grupo_mappings = get_warmup_sku_mappings_by_grupo(grupo_nome, list(range(2020, ano+1)))
                else:
                    all_grupo_mappings = db.query(SkuMapping).filter(
                        SkuMapping.evento_grupo == grupo_nome,
                        SkuMapping.ativo == True
                    ).all()
                if all_grupo_mappings:
                    best_year = max(m.ano for m in all_grupo_mappings if m.ano)
                    mappings = [m for m in all_grupo_mappings if m.ano == best_year]
        all_skus = list(set(m.sku.upper().strip() for m in mappings if m.sku))
    else:
        try:
            projeto_id = int(evento_id)
            projeto = _wq_dim_projeto_by_id(db, projeto_id)
            if projeto and projeto.codigo:
                all_skus = [str(projeto.codigo).upper().strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail="ID do evento inválido")
    
    if not all_skus:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    
    ativo_ids = []
    magento_ids = []
    
    all_active_mappings = _wq_sku_mappings_by_skus(db, all_skus)
    if all_active_mappings is None:
        all_active_mappings = db.query(SkuMapping).filter(
            SkuMapping.sku.in_(all_skus),
            SkuMapping.ativo == True
        ).all()
    
    year_mappings = [m for m in all_active_mappings if m.ano == ano]
    if not year_mappings and all_active_mappings:
        available_years = sorted(set(m.ano for m in all_active_mappings if m.ano), reverse=True)
        if available_years:
            year_mappings = [m for m in all_active_mappings if m.ano == available_years[0]]
    
    for m in year_mappings:
        if m.id_externo:
            if m.fonte == 'ATIVO':
                ativo_ids.append(str(m.id_externo))
            elif m.fonte == 'MAGENTO':
                magento_ids.append(str(m.id_externo))
    
    all_raw_sales = {}

    # For consolidated groups, prefer VendasDiariaSnapshot (same strategy as
    # fetch_real_daily_sales_for_projetos).  This makes medias-vendas resilient
    # to Ativo/Magento timeouts: when the live sources are unavailable the
    # snapshot — which is refreshed every ~45 min by the background sync — is
    # used as the primary source, preventing the averages from showing zeros.
    snapshot_used_medias = False
    if is_consolidated and grupo_nome:
        from ...services.snapshot_service import get_snapshot_vendas as _gsv_medias
        _snap = _gsv_medias(db, grupo_nome, ano=ano)
        if _snap:
            all_raw_sales.update(_snap)
            snapshot_used_medias = True
            logger.debug(f"[medias-vendas] snapshot loaded for '{grupo_nome}': {len(_snap)} days")

    if not snapshot_used_medias:
        if ativo_ids:
            ativo_rows = _fetch_daily_sales_ativo_by_ids(list(set(ativo_ids)))
            for row in ativo_rows:
                d = date.fromisoformat(row['dia']) if isinstance(row['dia'], str) else row['dia']
                all_raw_sales[d] = all_raw_sales.get(d, 0) + row['qtd']

        if magento_ids:
            _cort_avg = _get_cortesia_magento_ids(db)
            _mag_cort_avg = set(magento_ids) & _cort_avg if _cort_avg else None
            magento_rows = _fetch_daily_sales_magento_by_ids(list(set(magento_ids)), cortesia_magento_ids=_mag_cort_avg if _mag_cort_avg else None, db=db, ano=ano)
            for row in magento_rows:
                d = date.fromisoformat(row['dia']) if isinstance(row['dia'], str) else row['dia']
                all_raw_sales[d] = all_raw_sales.get(d, 0) + row['qtd']

    # As médias e janelas de vendas devem terminar em ONTEM (último dia
    # fechado), nunca em "hoje". Incluir o dia corrente — que é sempre parcial
    # (o dia ainda não acabou e o snapshot só tem as vendas até o último sync) —
    # arrasta as médias para baixo, com efeito tanto maior quanto menor a
    # janela (7d > 14d > 30d). Isso causava a divergência observada contra o
    # controle externo "até ontem". Alinhado também com o card "Inscrições
    # acumuladas até ontem" e com o fallback de médias do frontend, que já
    # filtram `< hoje`.
    yesterday = today - timedelta(days=1)
    if all_raw_sales:
        latest_sale = max(all_raw_sales.keys())
        if (today - latest_sale).days > 30:
            ref_date = latest_sale
        else:
            ref_date = yesterday
    else:
        ref_date = yesterday
    
    start_date = ref_date - timedelta(days=periodo)
    all_daily_sales = {d: v for d, v in all_raw_sales.items() if d > start_date and d <= ref_date}
    
    sorted_dates = sorted(all_daily_sales.keys())
    daily_data = [{"date": d.isoformat(), "sales": all_daily_sales[d]} for d in sorted_dates]
    
    total_sales = sum(all_daily_sales.values())
    media_geral = round(total_sales / periodo, 1) if periodo > 0 else 0
    
    sub_periods_map = {
        7:  [7],
        14: [7, 14],
        30: [7, 14, 30],
        60: [7, 30, 60],
        90: [7, 30, 90],
    }
    sub_periods = sub_periods_map.get(periodo, [7, 14, 30])
    
    medias_list = []
    for p in sub_periods:
        cutoff = ref_date - timedelta(days=p)
        sales_in_period = sum(v for d, v in all_daily_sales.items() if d > cutoff)
        medias_list.append({
            "periodo": p,
            "label": f"{p}d",
            "media": round(sales_in_period / p, 1),
            "total": sales_in_period,
            "dias": p,
        })
    
    tendencia_data = []
    if len(sorted_dates) >= 7:
        window = 7
        for i in range(window - 1, len(sorted_dates)):
            window_dates = sorted_dates[max(0, i - window + 1):i + 1]
            window_sales = sum(all_daily_sales[d] for d in window_dates)
            media_movel = round(window_sales / len(window_dates), 1)
            tendencia_data.append({
                "date": sorted_dates[i].isoformat(),
                "media_movel_7d": media_movel,
                "vendas": all_daily_sales[sorted_dates[i]]
            })
    
    medias_result = {
        "status": "success",
        "periodo_dias": periodo,
        "media_geral": media_geral,
        "total_vendas": total_sales,
        "dias_com_dados": len(sorted_dates),
        "medias": medias_list,
        "vendas_diarias": daily_data,
        "tendencia": tendencia_data
    }
    medias_cache.set(medias_cache_key, medias_result)
    return medias_result


@router.get("/eventos/{evento_id}/curva-snapshot")
def get_curva_snapshot(
    evento_id: str,
    ano: int = Query(default=None, description="Ano do evento"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing_dashboard", "pode_visualizar"))
):
    """
    Retorna os dados da curva histórica snapshot (ano anterior) para um evento,
    incluindo as quantidades de meta calculadas a partir do percentual e da meta atual.
    """
    from ...services.snapshot_service import get_curva_historica_snapshot

    is_grouped = evento_id.startswith("grp_")

    if ano is None:
        if is_grouped:
            ano = _resolve_default_ano_for_grupo(db, evento_id.replace("grp_", ""), datetime.now().year)
        else:
            ano = datetime.now().year

    projetos_for_meta = []
    grupo_id_resolved: Optional[int] = None
    if is_grouped:
        grupo_nome = evento_id.replace("grp_", "")
        grupo = db.query(EventoGrupoModel).filter(EventoGrupoModel.nome == grupo_nome).first()
        if not grupo:
            raise HTTPException(status_code=404, detail="Grupo de evento não encontrado")
        grupo_id_resolved = grupo.id
        mappings = _wq_sku_mappings_by_grupo_single_year(db, grupo_nome, ano)
        proj_skus = list(set(m.sku for m in mappings))
        projetos_q = _wq_dim_projetos_by_codigos(db, proj_skus)
        sales_goal = get_meta_orcada_projetos(db, projetos_q)
        evento_grupo = grupo_nome
        projetos_for_meta = list(projetos_q or [])
    else:
        projeto = _wq_dim_projeto_by_id(db, int(evento_id))
        if not projeto:
            raise HTTPException(status_code=404, detail="Evento não encontrado")
        sales_goal = get_meta_orcada(db, projeto.id)
        evento_grupo = None
        sku = str(projeto.codigo) if projeto.codigo else None
        if sku:
            standalone_mappings = _wq_sku_mappings_by_sku(db, sku)
            for sm in standalone_mappings:
                if sm.evento_grupo and sm.evento_grupo.strip():
                    evento_grupo = sm.evento_grupo
                    break
        projetos_for_meta = [projeto]

    if not evento_grupo:
        raise HTTPException(status_code=404, detail="Evento sem grupo configurado")

    # Resolve grupo_id para qualquer caminho (inclusive standalone) — usado
    # pelo frontend para chamar PUT /admin/evento-grupos/{id}/curva-override
    # sem precisar fazer lookup por nome (que pode falhar com acentos/case).
    if grupo_id_resolved is None:
        try:
            grupo_obj = db.query(EventoGrupoModel.id).filter(
                EventoGrupoModel.nome == evento_grupo
            ).first()
            if grupo_obj:
                grupo_id_resolved = grupo_obj[0]
        except Exception:
            grupo_id_resolved = None

    # Override configurado neste grupo (se houver). Serve para avisar a UI
    # quando a curva escolhida pelo usuário NÃO pôde ser aplicada (alvo ainda
    # não encerrou no modo vigente, saturação, poucos dados) e o sistema caiu
    # silenciosamente na cadeia de fallback automática.
    _override_target = None
    _override_modo = None
    try:
        _ov_row = db.query(
            EventoGrupoModel.curva_override,
            EventoGrupoModel.curva_override_modo,
        ).filter(EventoGrupoModel.nome == evento_grupo).first()
        if _ov_row and _ov_row[0]:
            _override_target = _ov_row[0]
            _override_modo = _ov_row[1] or "historico"
    except Exception:
        pass

    def _override_aplicado_for(final_tipo: Optional[str]) -> Optional[bool]:
        """None quando não há override; senão True só se a curva em uso veio
        do override (tipo manual/manual_vigente)."""
        if not _override_target:
            return None
        return final_tipo in ("manual", "manual_vigente")

    # Descobre estado e data do evento para alimentar o fallback regional
    # e a fabricação linear (último recurso).
    _estado = None
    _data_evento = None
    _rep_projeto = None
    for _p in projetos_for_meta:
        if getattr(_p, "data_evento", None):
            if not _data_evento or _p.data_evento > _data_evento:
                _data_evento = _p.data_evento
                _rep_projeto = _p
    if _rep_projeto and getattr(_rep_projeto, "estado", None):
        _estado = str(_rep_projeto.estado)
    _dias_enc = 2
    try:
        if _rep_projeto:
            _dias_enc = get_dias_encerramento(db, projeto_id=_rep_projeto.id)
    except Exception:
        pass

    # Usa a cadeia completa de fallback (override → próprio → circuito+cidade →
    # circuito → regional → linear) em vez de ler o snapshot direto. Sem isso,
    # eventos como Vitória — cujo histórico próprio é degenerado (5 inscrições)
    # E cujo override (Outono Vitória) está saturado em pct=1.0 — caíam num
    # padrão onde pct_dia=0 em todos os dias, gerando meta_dia=0 na tabela.
    prev_ano = ano - 1
    pattern, curva_info = _resolve_hist_pattern(db, evento_grupo, ano, estado=_estado)
    ano_ref = (curva_info or {}).get("ano_referencia") or prev_ano

    # Mesmo após o fallback, o padrão pode vir saturado em ~100% num D- alto.
    # Usa o helper canônico de snapshot_service para manter UMA regra de
    # saturação em todo o sistema (consolidação, blends de fallback e leitura).
    from ...services.snapshot_service import is_curve_saturated as _pattern_is_saturated

    if _pattern_is_saturated(pattern):
        logger.info(
            f"[CurvaSnapshot] '{evento_grupo}' padrão resolvido está saturado "
            f"(tipo={(curva_info or {}).get('tipo_curva')}, fonte={(curva_info or {}).get('fonte_curva')}) "
            f"— descartando e caindo em fabricação linear"
        )
        pattern = None

    # Fabricação linear como último recurso: distribui a meta uniformemente
    # da abertura de inscrições (estimada) até D=0. Garante que a coluna
    # "Meta Dia" nunca fique zerada quando há sales_goal e data de evento.
    fabricated_linear = False
    if not pattern and _data_evento:
        today_lin = today_brazil()
        days_to_event = max((_data_evento - today_lin).days, 0)
        # Janela total: dias até o evento + 90 dias de histórico observável.
        d_open = max(days_to_event + 90, 60)
        # A meta deve estar 100% atingida no fechamento das inscrições
        # (data_evento - dias_enc), não em D=0. Sem isso, a meta_dia
        # continua incremental nos dias em que já não há venda possível.
        d_close = max(int(_dias_enc or 0), 0)
        span = max(d_open - d_close, 1)
        pattern = {}
        for dm in range(0, d_open + 1):
            if dm <= d_close:
                pattern[dm] = 1.0
            else:
                pattern[dm] = max(0.0, 1.0 - ((dm - d_close) / span))
        pattern[0] = 1.0
        curva_info = {"tipo_curva": "linear", "fonte_curva": None, "ano_referencia": None}
        ano_ref = None
        fabricated_linear = True
        logger.info(
            f"[CurvaSnapshot] '{evento_grupo}' sem padrão histórico utilizável — "
            f"fabricando curva linear sobre {d_open} dias "
            f"(data_evento={_data_evento}, dias_enc={d_close})"
        )

    if not pattern:
        return {
            "status": "success",
            "evento_grupo": evento_grupo,
            "grupo_id": grupo_id_resolved,
            "ano_referencia": prev_ano,
            "sales_goal": sales_goal,
            "override_target": _override_target,
            "override_modo": _override_modo,
            "override_aplicado": _override_aplicado_for(None),
            "data": [],
            "message": f"Sem dados de curva histórica para {prev_ano} e sem data de evento para projeção linear"
        }

    sorted_dms = sorted(pattern.keys(), reverse=True)
    rows = []
    prev_pct = 0.0
    for i, dm in enumerate(sorted_dms):
        pct_acum = pattern[dm]
        pct_dia = pct_acum - prev_pct
        meta_acumulado = round(pct_acum * sales_goal)
        meta_dia = round(pct_dia * sales_goal)
        rows.append({
            "d_minus": dm,
            "percentual_acumulado": round(pct_acum * 100, 2),
            "percentual_dia": round(pct_dia * 100, 2),
            "meta_acumulado": meta_acumulado,
            "meta_dia": meta_dia,
        })
        prev_pct = pct_acum

    return {
        "status": "success",
        "evento_grupo": evento_grupo,
        "grupo_id": grupo_id_resolved,
        "ano_referencia": ano_ref,
        "sales_goal": sales_goal,
        "tipo_curva": (curva_info or {}).get("tipo_curva"),
        "fonte_curva": (curva_info or {}).get("fonte_curva"),
        "fabricated_linear": fabricated_linear,
        "override_target": _override_target,
        "override_modo": _override_modo,
        "override_aplicado": _override_aplicado_for((curva_info or {}).get("tipo_curva")),
        "data": rows
    }


_diagnostico_curvas_cache: dict = {}
_DIAGNOSTICO_CURVAS_TTL_S = 300  # 5 min


def _resolve_hist_pattern_readonly(db: Session, evento_grupo: str, ano: int,
                                    estado: Optional[str],
                                    grupo_obj: Optional['EventoGrupoModel'],
                                    snap_index: dict, sat_cache: dict) -> dict:
    """Versão read-only de _resolve_hist_pattern: SÓ lê snapshots já gravados
    em CurvaHistoricaSnapshot (PostgreSQL). NUNCA toca em Magento/Ativo.

    snap_index: dict pre-carregado {(grupo, ano): {'pattern': dict, 'total': int}}
    sat_cache: dict {(grupo, ano): bool} — cache de saturação por grupo/ano

    Replica a cadeia: override → próprio → circuito+cidade → circuito (média) →
    regional (média ≥2) → linear. Para cada padrão considerado, exige snapshot
    persistido — se faltar, pula (e o diagnóstico informa snapshot_ausente)."""
    from ...services.snapshot_service import is_curve_saturated
    prev_ano = ano - 1
    MIN_REF_SALES = 50
    SATURATION_PCT = 0.95

    def _saturated(grupo: str, ar: int) -> bool:
        key = (grupo, ar)
        if key in sat_cache:
            return sat_cache[key]
        entry = snap_index.get(key)
        if not entry or not entry.get("pattern"):
            sat_cache[key] = False
            return False
        try:
            res = is_curve_saturated(entry["pattern"])
        except Exception:
            res = False
        sat_cache[key] = res
        return res

    def _is_degenerate_snapshot(grupo: str, ar: int) -> bool:
        entry = snap_index.get((grupo, ar))
        if not entry:
            return True  # sem snapshot conta como inválido pro readonly
        ref_total = entry.get("total", 0)
        pattern = entry.get("pattern")
        if ref_total > 0 and ref_total < MIN_REF_SALES:
            return True
        if pattern:
            try:
                max_dm = max(pattern.keys())
                if max_dm >= 30 and pattern[max_dm] >= SATURATION_PCT:
                    return True
            except (ValueError, KeyError):
                pass
        return False

    # 1. Override manual
    if grupo_obj and grupo_obj.curva_override:
        target = grupo_obj.curva_override
        override_modo = (getattr(grupo_obj, "curva_override_modo", None) or "historico")
        # Modo "vigente": a curva é montada ao vivo a partir de
        # vendas_diaria_snapshot (não há CurvaHistoricaSnapshot). Para o
        # diagnóstico read-only só reportamos o rótulo apontando para o ano
        # corrente; a validade real é checada no caminho normal.
        if override_modo == "vigente":
            return {"tipo_curva": "manual_vigente", "fonte_curva": target,
                    "ano_referencia": ano, "fabricated_linear": False,
                    "saturated_descartado": False}
        # tenta prev_ano e, se faltar, mais recente disponível pra esse grupo
        candidate_anos = [prev_ano]
        for (g, ar) in snap_index.keys():
            if g == target and ar not in candidate_anos:
                candidate_anos.append(ar)
        candidate_anos.sort(reverse=True)
        for ar in candidate_anos:
            if (target, ar) in snap_index and not _is_degenerate_snapshot(target, ar):
                return {"tipo_curva": "manual", "fonte_curva": target,
                        "ano_referencia": ar, "fabricated_linear": False,
                        "saturated_descartado": False}
        # override existe mas não tem snapshot válido — segue cadeia
        return {"tipo_curva": "manual", "fonte_curva": target,
                "ano_referencia": None, "fabricated_linear": True,
                "saturated_descartado": True,
                "obs": "override aponta para grupo sem snapshot válido — fallback ativo"}

    # 2. Próprio — mas honra a coluna `origem`: um snapshot gravado sob o nome
    # do próprio evento pode ser uma curva derivada (média regional/circuito)
    # pré-computada pelo job de consolidação, não histórico próprio real.
    DERIVED_ORIGENS = {"regional", "circuito", "circuito_similar", "manual", "derivado"}
    DERIVED_FONTE_FALLBACK = {
        "regional": "Média Regional",
        "circuito": "Similar (Circuito)",
        "circuito_similar": "Média do Circuito",
        "derivado": "Derivada",
    }
    if (evento_grupo, prev_ano) in snap_index:
        if not _is_degenerate_snapshot(evento_grupo, prev_ano):
            own_entry = snap_index.get((evento_grupo, prev_ano), {})
            own_origem = own_entry.get("origem")
            if own_origem and own_origem in DERIVED_ORIGENS:
                return {"tipo_curva": own_origem,
                        "fonte_curva": own_entry.get("fonte_origem") or DERIVED_FONTE_FALLBACK.get(own_origem),
                        "ano_referencia": prev_ano, "fabricated_linear": False,
                        "saturated_descartado": False}
            return {"tipo_curva": "historico", "fonte_curva": evento_grupo,
                    "ano_referencia": prev_ano, "fabricated_linear": False,
                    "saturated_descartado": False}

    circuito = grupo_obj.circuito if grupo_obj else None
    cidade = grupo_obj.cidade_normalizada if grupo_obj else None

    # 3. Circuito + cidade (primeiro sibling não-saturado)
    if circuito and cidade:
        siblings = db.query(EventoGrupoModel.nome).filter(
            EventoGrupoModel.circuito == circuito,
            EventoGrupoModel.cidade_normalizada == cidade,
            EventoGrupoModel.nome != evento_grupo,
            EventoGrupoModel.ativo == True
        ).all()
        for (sib_nome,) in siblings:
            if (sib_nome, prev_ano) in snap_index and not _saturated(sib_nome, prev_ano):
                return {"tipo_curva": "circuito", "fonte_curva": sib_nome,
                        "ano_referencia": prev_ano, "fabricated_linear": False,
                        "saturated_descartado": False}

    # 4. Circuito (média)
    if circuito:
        siblings = db.query(EventoGrupoModel.nome).filter(
            EventoGrupoModel.circuito == circuito,
            EventoGrupoModel.nome != evento_grupo,
            EventoGrupoModel.ativo == True
        ).all()
        usados = [s for (s,) in siblings
                  if (s, prev_ano) in snap_index and not _saturated(s, prev_ano)]
        if usados:
            label = f"Média {circuito}" if len(usados) > 1 else usados[0]
            return {"tipo_curva": "circuito_similar", "fonte_curva": label,
                    "ano_referencia": prev_ano, "fabricated_linear": False,
                    "saturated_descartado": False}

    # 5. Regional (precisa ≥2)
    if estado:
        regional = db.query(EventoGrupoModel.nome).join(
            SkuMapping, SkuMapping.evento_grupo == EventoGrupoModel.nome
        ).join(
            DimProjeto, DimProjeto.codigo == SkuMapping.sku
        ).filter(
            DimProjeto.estado == estado,
            EventoGrupoModel.nome != evento_grupo,
            EventoGrupoModel.ativo == True
        ).distinct().all()
        usados = [s for (s,) in regional
                  if (s, prev_ano) in snap_index and not _saturated(s, prev_ano)]
        if len(usados) >= 2:
            return {"tipo_curva": "regional", "fonte_curva": estado,
                    "ano_referencia": prev_ano, "fabricated_linear": False,
                    "saturated_descartado": False}

    return {"tipo_curva": "linear", "fonte_curva": None,
            "ano_referencia": None, "fabricated_linear": True,
            "saturated_descartado": False}


@router.get("/diagnostico-curvas")
def get_diagnostico_curvas(
    ano: int = Query(default=None, description="Ano de referência (default: atual)"),
    force_refresh: bool = Query(default=False, description="Ignora cache e recalcula"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin())
):
    """Diagnóstico read-only: lista, para todos os grupos ativos, qual fonte
    de curva D-% será escolhida (override/próprio/circuito+cidade/circuito/
    regional/linear). Lê APENAS snapshots persistidos — não dispara Magento."""
    from ...models.vendas_snapshot import CurvaHistoricaSnapshot
    import time as _t

    if ano is None:
        ano = datetime.now().year

    cache_key = f"diagcurvas:{ano}"
    if not force_refresh:
        cached = _diagnostico_curvas_cache.get(cache_key)
        if cached and (_t.time() - cached["ts"]) < _DIAGNOSTICO_CURVAS_TTL_S:
            return cached["payload"]

    prev_ano = ano - 1
    # Pre-carrega TODOS os snapshots em uma só query (evita N+1)
    snap_rows = db.query(
        CurvaHistoricaSnapshot.evento_grupo,
        CurvaHistoricaSnapshot.ano_referencia,
        CurvaHistoricaSnapshot.d_minus,
        CurvaHistoricaSnapshot.percentual_acumulado,
        CurvaHistoricaSnapshot.total_vendas_referencia,
        CurvaHistoricaSnapshot.origem,
        CurvaHistoricaSnapshot.fonte_origem,
    ).all()
    snap_index: dict = {}
    for eg, ar, dm, pct, tot, origem, fonte_origem in snap_rows:
        key = (eg, ar)
        entry = snap_index.setdefault(key, {"pattern": {}, "total": 0, "origem": None, "fonte_origem": None})
        entry["pattern"][int(dm)] = float(pct or 0)
        if tot and tot > entry["total"]:
            entry["total"] = int(tot)
        if origem and not entry["origem"]:
            entry["origem"] = origem
        if fonte_origem and not entry["fonte_origem"]:
            entry["fonte_origem"] = fonte_origem
    sat_cache: dict = {}

    grupos = db.query(EventoGrupoModel).filter(
        EventoGrupoModel.ativo == True
    ).order_by(EventoGrupoModel.nome).all()

    eventos = []
    for grupo in grupos:
        try:
            mappings = _wq_sku_mappings_by_grupo_single_year(db, grupo.nome, ano)
            proj_skus = list({m.sku for m in mappings if m.sku})
            data_evento = None
            estado = None
            sales_goal = 0
            if proj_skus:
                projetos = _wq_dim_projetos_by_codigos(db, proj_skus) or []
                rep = None
                for p in projetos:
                    if getattr(p, "data_evento", None):
                        if not data_evento or p.data_evento > data_evento:
                            data_evento = p.data_evento
                            rep = p
                if rep and getattr(rep, "estado", None):
                    estado = str(rep.estado)
                try:
                    sales_goal = get_meta_orcada_projetos(db, projetos)
                except Exception:
                    sales_goal = 0

            curva_info = _resolve_hist_pattern_readonly(
                db, grupo.nome, ano, estado=estado,
                grupo_obj=grupo, snap_index=snap_index, sat_cache=sat_cache
            )
            tipo = curva_info.get("tipo_curva")
            fonte = curva_info.get("fonte_curva")
            ano_ref = curva_info.get("ano_referencia")
            fabricated_linear = bool(curva_info.get("fabricated_linear"))
            saturated = bool(curva_info.get("saturated_descartado"))

            eventos.append({
                "grupo_id": grupo.id,
                "evento_grupo": grupo.nome,
                "circuito": grupo.circuito,
                "cidade": grupo.cidade_normalizada,
                "estado": estado,
                "data_evento": data_evento.isoformat() if data_evento else None,
                "tipo_curva": tipo,
                "fonte_curva": fonte,
                "ano_referencia": ano_ref,
                "tem_override": bool(grupo.curva_override),
                "override_target": grupo.curva_override,
                "fabricated_linear": fabricated_linear,
                "saturated_descartado": saturated,
                "sales_goal": int(sales_goal or 0),
                "tem_mapeamento": bool(proj_skus),
                "obs": curva_info.get("obs"),
            })
        except Exception as e:
            logger.warning(f"[DiagnosticoCurvas] erro em '{grupo.nome}': {e}")
            eventos.append({
                "grupo_id": grupo.id,
                "evento_grupo": grupo.nome,
                "circuito": grupo.circuito,
                "cidade": grupo.cidade_normalizada,
                "erro": str(e),
            })

    payload = {"ano": ano, "total": len(eventos), "eventos": eventos}
    _diagnostico_curvas_cache[cache_key] = {"ts": _t.time(), "payload": payload}
    return payload


@router.get("/eventos/{evento_id}/simulacao")
def get_event_simulation(
    evento_id: str,
    ano: int = Query(default=None, description="Ano do evento"),
    force_refresh: bool = Query(default=False, description="Forçar atualização"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing_dashboard", "pode_visualizar"))
):
    from datetime import timedelta
    today = today_brazil()
    if ano is None:
        ano = today.year

    is_consolidated = evento_id.startswith('grp_')

    all_skus = []
    projetos = []
    if is_consolidated:
        grupo_nome = evento_id.replace('grp_', '')
        mappings = db.query(SkuMapping).filter(
            SkuMapping.evento_grupo == grupo_nome,
            SkuMapping.ano == ano,
            SkuMapping.ativo == True
        ).all()
        if not mappings:
            mappings = db.query(SkuMapping).filter(
                SkuMapping.evento_grupo == grupo_nome,
                SkuMapping.ativo == True
            ).all()
            if mappings:
                best_year = max(m.ano for m in mappings if m.ano)
                mappings = [m for m in mappings if m.ano == best_year]
        all_skus = list(set(m.sku.upper().strip() for m in mappings if m.sku))
        projetos = db.query(DimProjeto).filter(DimProjeto.codigo.in_(all_skus)).all() if all_skus else []
    else:
        try:
            projeto_id_int = int(evento_id)
            projeto = db.query(DimProjeto).filter(DimProjeto.id == projeto_id_int).first()
            if projeto:
                projetos = [projeto]
                if projeto.codigo:
                    all_skus = [str(projeto.codigo).upper().strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail="ID do evento inválido")

    if not all_skus:
        raise HTTPException(status_code=404, detail="Evento não encontrado")

    data_evento = None
    for p in projetos:
        if p.data_evento:
            if data_evento is None or p.data_evento > data_evento:
                data_evento = p.data_evento

    # Use D-Inscrição (registration close date) — same reference used by Dashboard and ISC.
    # get_dias_encerramento reads dias_encerramento_inscricao from CadastroEvento (default 2).
    dias_enc_sim = get_dias_encerramento(db, projeto_id=projetos[0].id) if projetos else 2
    dias_ate_evento = calculate_d_minus(data_evento, dias_encerramento=dias_enc_sim) if data_evento else 0

    # Fix P1: eliminar N+1 — antes get_meta_orcada_projetos chamava 1 query
    # por projeto (cache mitiga só após 1ª request), e logo abaixo havia OUTRO
    # loop com 1 query CadastroEvento por projeto. Agora UMA query com IN(...)
    # alimenta AMBOS os cálculos (meta_orcada + ticket_medio_orcado), com
    # mesma regra de desempate. CadastroEvento.projeto_id não tem UNIQUE
    # constraint (FK nullable), então garantimos determinismo com
    # order_by(id) + setdefault: a primeira linha (menor id) vence,
    # reproduzindo o comportamento típico de `.first()` sem order_by.
    _projeto_ids_sim = [p.id for p in projetos]
    _cads_sim = (
        db.query(CadastroEvento)
        .filter(CadastroEvento.projeto_id.in_(_projeto_ids_sim))
        .order_by(CadastroEvento.id.asc())
        .all()
        if _projeto_ids_sim else []
    )
    _cad_by_proj_sim: dict = {}
    for _c in _cads_sim:
        _cad_by_proj_sim.setdefault(_c.projeto_id, _c)

    # meta_orcada agora vem da mesma fonte; get_meta_from_cadastro retorna
    # int(cad.atletas_site_pago) quando > 0, igual ao caminho antigo.
    meta_orcada = 0
    for p in projetos:
        cad = _cad_by_proj_sim.get(p.id)
        if cad:
            meta_orcada += get_meta_from_cadastro(cad)

    budget_ticket_total_receita = 0.0
    budget_ticket_total_qtd = 0
    for p in projetos:
        cad = _cad_by_proj_sim.get(p.id)
        if cad and cad.atletas_site_tkt_medio and cad.atletas_site_pago and cad.atletas_site_pago > 0:
            budget_ticket_total_receita += float(cad.atletas_site_tkt_medio) * int(cad.atletas_site_pago)
            budget_ticket_total_qtd += int(cad.atletas_site_pago)
    ticket_medio_orcado = round(budget_ticket_total_receita / budget_ticket_total_qtd, 2) if budget_ticket_total_qtd > 0 else 0.0

    all_active_mappings = db.query(SkuMapping).filter(
        SkuMapping.sku.in_(all_skus),
        SkuMapping.ativo == True
    ).all()
    year_mappings = [m for m in all_active_mappings if m.ano == ano]
    if not year_mappings and all_active_mappings:
        available_years = sorted(set(m.ano for m in all_active_mappings if m.ano), reverse=True)
        if available_years:
            year_mappings = [m for m in all_active_mappings if m.ano == available_years[0]]

    ativo_ids = []
    magento_ids = []
    for m in year_mappings:
        if m.id_externo:
            if m.fonte == 'ATIVO':
                ativo_ids.append(str(m.id_externo))
            elif m.fonte == 'MAGENTO':
                magento_ids.append(str(m.id_externo))

    # Determine evento_grupo for snapshot lookup (same source used by Dashboard)
    evento_grupo_sim = None
    if is_consolidated:
        evento_grupo_sim = grupo_nome
    else:
        # Try to get evento_grupo from the mappings
        for m in year_mappings:
            if m.evento_grupo:
                evento_grupo_sim = m.evento_grupo
                break

    all_raw_sales = {}
    all_raw_receita = {}

    # Priority 1: use the snapshot table (same source as Dashboard)
    snapshot_used_sim = False
    if evento_grupo_sim:
        from ...services.snapshot_service import get_snapshot_vendas_com_receita
        snap_rows = get_snapshot_vendas_com_receita(db, evento_grupo_sim, ano=ano)
        if snap_rows:
            snapshot_used_sim = True
            for row in snap_rows:
                d = date.fromisoformat(row['dia']) if isinstance(row['dia'], str) else row['dia']
                all_raw_sales[d] = all_raw_sales.get(d, 0) + row['qtd']
                all_raw_receita[d] = all_raw_receita.get(d, 0) + row.get('receita', 0)

    # If snapshot was used, also fetch today's live data if today is not already covered.
    # We estimate today's revenue using the snapshot ticket_medio so that total_receita
    # stays proportional to total_vendas (same ratio used by the Dashboard event detail).
    if snapshot_used_sim:
        event_already_happened = data_evento and data_evento < today
        today_in_snap = today in all_raw_sales
        if not event_already_happened and not today_in_snap:
            # Compute snapshot ticket_medio to estimate today's revenue
            snap_qty_total = sum(all_raw_sales.values())
            snap_receita_total = sum(all_raw_receita.values())
            snap_ticket_medio = (snap_receita_total / snap_qty_total) if snap_qty_total > 0 else 0.0

            today_live_qty = 0
            if ativo_ids:
                if ativo_breaker.is_open():
                    logger.warning("[Simulacao] Ativo circuit aberto — pulando overlay de hoje")
                else:
                    try:
                        today_sales = ativo_breaker.call(
                            _fetch_today_sales_ativo_by_ids, list(set(ativo_ids))
                        )
                        for d, qty in today_sales.items():
                            all_raw_sales[d] = all_raw_sales.get(d, 0) + qty
                            today_live_qty += qty
                    except CircuitOpenError:
                        pass
                    except Exception as e:
                        logger.warning(f"[Simulacao] Failed to fetch today's Ativo sales: {e}")
            if magento_ids:
                if magento_breaker.is_open():
                    logger.warning("[Simulacao] Magento circuit aberto — pulando overlay de hoje")
                else:
                    try:
                        _cort = _get_cortesia_magento_ids(db)
                        _mag_cort = set(magento_ids) & _cort if _cort else None
                        today_sales = magento_breaker.call(
                            _fetch_today_sales_magento_by_ids,
                            list(set(magento_ids)),
                            cortesia_magento_ids=_mag_cort if _mag_cort else None,
                        )
                        for d, qty in today_sales.items():
                            all_raw_sales[d] = all_raw_sales.get(d, 0) + qty
                            today_live_qty += qty
                    except CircuitOpenError:
                        pass
                    except Exception as e:
                        logger.warning(f"[Simulacao] Failed to fetch today's Magento sales: {e}")

            # Estimate today's revenue using the snapshot ticket_medio so the ticket
            # and margem remain consistent with the Dashboard (no artificial dilution)
            if today_live_qty > 0 and snap_ticket_medio > 0:
                all_raw_receita[today] = all_raw_receita.get(today, 0.0) + today_live_qty * snap_ticket_medio

    # Priority 2 (fallback): query external sources directly when no snapshot exists
    if not snapshot_used_sim:
        if ativo_ids:
            ativo_rows = _fetch_daily_sales_ativo_by_ids(list(set(ativo_ids)))
            for row in ativo_rows:
                d = date.fromisoformat(row['dia']) if isinstance(row['dia'], str) else row['dia']
                all_raw_sales[d] = all_raw_sales.get(d, 0) + row['qtd']
                all_raw_receita[d] = all_raw_receita.get(d, 0) + row.get('receita', 0)

    if not snapshot_used_sim and magento_ids:
        _cort = _get_cortesia_magento_ids(db)
        _mag_cort = set(magento_ids) & _cort if _cort else None
        magento_rows = _fetch_daily_sales_magento_by_ids(list(set(magento_ids)), cortesia_magento_ids=_mag_cort if _mag_cort else None, db=db, ano=ano)
        for row in magento_rows:
            d = date.fromisoformat(row['dia']) if isinstance(row['dia'], str) else row['dia']
            all_raw_sales[d] = all_raw_sales.get(d, 0) + row['qtd']
            all_raw_receita[d] = all_raw_receita.get(d, 0) + row.get('receita', 0)

    total_vendas = sum(all_raw_sales.values())
    total_receita = round(sum(all_raw_receita.values()), 2)

    # ── Align with Dashboard event detail: use ISC cache as the authoritative source
    # for current totals on live/hybrid events (same logic as get_marketing_event_by_id).
    # For consolidated events (dias_ate_evento <= 0) snapshot is already authoritative.
    if evento_grupo_sim and dias_ate_evento > 0:
        try:
            _isc_sim = fetch_isc_pricing_data(db=db)
            _isc_receita_sim = 0.0
            _isc_qtd_sim = 0
            _seen_norms_sim: set = set()
            for _sku_sim in all_skus:
                _norm_sim = normalize_sku(_sku_sim)
                if _norm_sim in _seen_norms_sim:
                    continue
                _seen_norms_sim.add(_norm_sim)
                _info_sim = _isc_sim.get(_norm_sim, {})
                _isc_receita_sim += _info_sim.get('receita_liquida_site', 0.0)
                _isc_qtd_sim += _info_sim.get('qtd_site', 0)
            if _isc_qtd_sim > 0:
                total_receita = round(_isc_receita_sim, 2)
                if _isc_qtd_sim > total_vendas:
                    total_vendas = _isc_qtd_sim
        except Exception as _e_sim:
            logger.warning(f"[Simulacao] ISC alignment failed, using snapshot totals: {_e_sim}")

    ticket_medio_atual = round(total_receita / total_vendas, 2) if total_vendas > 0 else 0.0

    sorted_dates = sorted(all_raw_sales.keys())

    media_7d = 0.0
    media_14d = 0.0
    media_30d = 0.0
    if sorted_dates:
        for window, attr_name in [(7, 'media_7d'), (14, 'media_14d'), (30, 'media_30d')]:
            cutoff = today - timedelta(days=window)
            sales_in = sum(v for d, v in all_raw_sales.items() if d > cutoff and d < today)
            if attr_name == 'media_7d':
                media_7d = round(sales_in / window, 1)
            elif attr_name == 'media_14d':
                media_14d = round(sales_in / window, 1)
            else:
                media_30d = round(sales_in / window, 1)

    primeiro_dia_venda = sorted_dates[0] if sorted_dates else today
    dias_em_venda = (today - primeiro_dia_venda).days + 1
    media_historica = round(total_vendas / dias_em_venda, 1) if dias_em_venda > 0 else 0.0

    receita_7d = sum(v for d, v in all_raw_receita.items() if d > today - timedelta(days=7) and d <= today)
    vendas_7d = sum(v for d, v in all_raw_sales.items() if d > today - timedelta(days=7) and d <= today)
    ticket_7d = round(receita_7d / vendas_7d, 2) if vendas_7d > 0 else ticket_medio_atual

    cenarios = {}
    if dias_ate_evento > 0:
        taxas_base = sorted([media_7d, media_14d, media_30d])
        for nome, taxa in [("pessimista", taxas_base[0] * 0.85), ("realista", taxas_base[1]), ("otimista", taxas_base[2] * 1.15)]:
            proj_vendas = total_vendas + round(taxa * dias_ate_evento)
            proj_receita = total_receita + round(taxa * dias_ate_evento * ticket_7d, 2)
            pct_meta = round(proj_vendas / meta_orcada * 100, 1) if meta_orcada > 0 else 0
            cenarios[nome] = {
                "vendas_projetadas": proj_vendas,
                "receita_projetada": proj_receita,
                "ticket_medio_projetado": round(proj_receita / proj_vendas, 2) if proj_vendas > 0 else 0,
                "ritmo_diario": round(taxa, 1),
                "pct_meta": pct_meta,
                "vendas_restantes": max(0, proj_vendas - total_vendas),
            }
    else:
        cenarios = {
            "pessimista": {"vendas_projetadas": total_vendas, "receita_projetada": total_receita, "ticket_medio_projetado": ticket_medio_atual, "ritmo_diario": 0, "pct_meta": round(total_vendas / meta_orcada * 100, 1) if meta_orcada > 0 else 0, "vendas_restantes": 0},
            "realista": {"vendas_projetadas": total_vendas, "receita_projetada": total_receita, "ticket_medio_projetado": ticket_medio_atual, "ritmo_diario": 0, "pct_meta": round(total_vendas / meta_orcada * 100, 1) if meta_orcada > 0 else 0, "vendas_restantes": 0},
            "otimista": {"vendas_projetadas": total_vendas, "receita_projetada": total_receita, "ticket_medio_projetado": ticket_medio_atual, "ritmo_diario": 0, "pct_meta": round(total_vendas / meta_orcada * 100, 1) if meta_orcada > 0 else 0, "vendas_restantes": 0},
        }

    vendas_por_dia = []
    if sorted_dates and dias_ate_evento > 0:
        for d in sorted_dates:
            vendas_por_dia.append({"date": d.isoformat(), "vendas": all_raw_sales[d], "receita": round(all_raw_receita.get(d, 0), 2)})

    ritmo_necessario = round((meta_orcada - total_vendas) / dias_ate_evento, 1) if dias_ate_evento > 0 and meta_orcada > 0 else 0
    receita_orcada = round(meta_orcada * ticket_medio_orcado, 2) if ticket_medio_orcado > 0 else 0
    gap_vendas = max(0, meta_orcada - total_vendas)
    gap_receita = round(max(0, receita_orcada - total_receita), 2)

    # Custo de kit e margem
    projeto_ids_list = [p.id for p in projetos]
    kit_costs = get_kit_basico_costs_batch(db, projeto_ids_list)
    custo_kit = round(sum(kit_costs.values()) / len(kit_costs), 2) if kit_costs else 50.0

    margem_unit_atual = round(ticket_medio_atual - custo_kit, 2) if ticket_medio_atual > 0 else 0.0
    margem_total_atual = round(total_receita - custo_kit * total_vendas, 2) if total_vendas > 0 else 0.0
    margem_pct_atual = round((margem_unit_atual / ticket_medio_atual) * 100, 1) if ticket_medio_atual > 0 else 0.0

    margem_orcada_unit = round(ticket_medio_orcado - custo_kit, 2) if ticket_medio_orcado > 0 else 0.0
    margem_orcada_total = round(margem_orcada_unit * meta_orcada, 2) if meta_orcada > 0 and ticket_medio_orcado > 0 else 0.0

    # Enrich cenários with margin data
    for nome in cenarios:
        c = cenarios[nome]
        pv = c["vendas_projetadas"]
        pr = c["receita_projetada"]
        c["margem_projetada_unit"] = round(ticket_7d - custo_kit, 2)
        c["margem_projetada_total"] = round(pr - custo_kit * pv, 2) if pv > 0 else 0.0
        c["margem_projetada_pct"] = round(((ticket_7d - custo_kit) / ticket_7d) * 100, 1) if ticket_7d > 0 else 0.0

    return {
        "status": "success",
        "evento": {
            "data_evento": data_evento.isoformat() if data_evento else None,
            "dias_ate_evento": dias_ate_evento,
            "meta_orcada": meta_orcada,
            "ticket_medio_orcado": ticket_medio_orcado,
            "receita_orcada": receita_orcada,
            "custo_kit": custo_kit,
            "margem_orcada_unit": margem_orcada_unit,
            "margem_orcada_total": margem_orcada_total,
        },
        "atual": {
            "total_vendas": total_vendas,
            "total_receita": total_receita,
            "ticket_medio": ticket_medio_atual,
            "ticket_medio_7d": ticket_7d,
            "pct_meta": round(total_vendas / meta_orcada * 100, 1) if meta_orcada > 0 else 0,
            "media_7d": media_7d,
            "media_14d": media_14d,
            "media_30d": media_30d,
            "media_historica": media_historica,
            "dias_em_venda": dias_em_venda,
            "ritmo_necessario": ritmo_necessario,
            "gap_vendas": gap_vendas,
            "custo_kit": custo_kit,
            "margem_unit": margem_unit_atual,
            "margem_total": margem_total_atual,
            "margem_pct": margem_pct_atual,
            "gap_receita": gap_receita,
        },
        "cenarios": cenarios,
        "vendas_diarias": vendas_por_dia,
    }


@router.get("/check-duplicate-action/{projeto_id}")
def check_duplicate_action_endpoint(
    projeto_id: int,
    tipo: str = Query(..., description="Tipo da ação"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing_dashboard", "pode_visualizar"))
):
    """Verifica se já existe uma ação duplicada do mesmo tipo nos últimos 7 dias"""
    duplicate = check_duplicate_action(db, projeto_id, tipo)
    return {
        "status": "success",
        "has_duplicate": duplicate is not None,
        "existing_action": duplicate
    }


def _fetch_monthly_sales_ativo(ano_atual: int, ano_anterior: int) -> list:
    if db_module.engine_ssh is None:
        return []
    try:
        query = """
SELECT /*+ MAX_EXECUTION_TIME(90000) */
    YEAR(c.dt_pedido) AS ano,
    MONTH(c.dt_pedido) AS mes,
    COUNT(CASE WHEN (f.en_cupom_classificacao IS NULL
              OR f.en_cupom_classificacao NOT IN ('Funcionário', 'Cortesia Faturada', 'Grupos', 'Coligados'))
        AND (h.ds_categoria IS NULL OR (h.ds_categoria NOT LIKE '%%GRUPOS%%' AND h.ds_categoria NOT LIKE '%%ortesia%%'))
        AND c.nr_total > 0 THEN 1 END) AS qtd,
    SUM(CASE WHEN (f.en_cupom_classificacao IS NULL
              OR f.en_cupom_classificacao NOT IN ('Funcionário', 'Cortesia Faturada', 'Grupos', 'Coligados'))
        AND (h.ds_categoria IS NULL OR (h.ds_categoria NOT LIKE '%%GRUPOS%%' AND h.ds_categoria NOT LIKE '%%ortesia%%'))
        AND c.nr_total > 0 THEN 
        GREATEST(a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0), 0)
    ELSE 0 END) AS receita
FROM sa_pedido_evento AS a
INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
INNER JOIN sa_pedido AS c ON c.id_pedido = a.id_pedido
LEFT JOIN sa_modalidade_categoria AS h ON a.id_categoria = h.id_categoria
LEFT JOIN sa_cupom_desconto_item AS e ON e.id_cupom_desconto_item = a.id_cupom_individual
LEFT JOIN sa_cupom_desconto AS f ON f.id_cupom_desconto = e.id_cupom_desconto
WHERE 
    c.id_pedido_status IN (2)
    AND (b.id_campanha_salesforce IS NULL OR b.id_campanha_salesforce NOT LIKE '701d0000000%%')
    AND YEAR(c.dt_pedido) IN (:ano_atual, :ano_anterior)
GROUP BY YEAR(c.dt_pedido), MONTH(c.dt_pedido)
ORDER BY ano, mes
"""
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(text(query), {"ano_atual": ano_atual, "ano_anterior": ano_anterior})
            return [{"ano": int(r[0]), "mes": int(r[1]), "qtd": int(r[2] or 0), "receita": float(r[3] or 0)} for r in result.fetchall()]
    except Exception as e:
        logger.error(f"Erro monthly sales Ativo: {e}")
        return []


def _fetch_monthly_sales_magento(ano_atual: int, ano_anterior: int) -> list:
    if db_module.engine_magento is None:
        return []
    try:
        query = """
SELECT /*+ MAX_EXECUTION_TIME(90000) */
    YEAR(so.created_at) AS ano,
    MONTH(so.created_at) AS mes,
    COUNT(CASE WHEN (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%') 
        AND so.base_grand_total > 0 THEN 1 END) AS qtd,
    SUM(CASE WHEN (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%') THEN
        (soi.price - CASE WHEN soi.price = 0 THEN 0
            WHEN soi.name LIKE '%%plus%%' THEN 69.00
            WHEN soi.name LIKE '%%super%%' THEN 269.00
            WHEN soi.name LIKE '%%vip%%' THEN 199.99
            ELSE 0 END
        + COALESCE(so.base_discount_invoiced, 0) * (soi.price / NULLIF(so.base_subtotal, 1))
        - CASE WHEN cg.customer_group_id = 4 THEN 0
            WHEN cg.customer_group_id IN (0, 1, 2, 3, 5, 7) AND COALESCE(soi_persona.persona_price, 0) = 14.90 THEN 14.90
            ELSE 0 END)
    ELSE 0 END) AS receita
FROM sales_order AS so
LEFT JOIN sales_order_item AS soi ON soi.order_id = so.entity_id
LEFT JOIN customer_group AS cg ON cg.customer_group_id = so.customer_group_id
LEFT JOIN (
    SELECT parent_item_id, MAX(price) AS persona_price
    FROM sales_order_item
    WHERE name LIKE '%%persona%%'
    GROUP BY parent_item_id
) soi_persona ON soi_persona.parent_item_id = soi.item_id
WHERE
    YEAR(so.created_at) IN (:ano_atual, :ano_anterior)
    AND so.increment_id NOT LIKE "%%-1%%"
    AND so.increment_id NOT LIKE "%%-2%%"
    AND so.increment_id NOT LIKE "%%-3%%"
    AND so.increment_id NOT LIKE "%%-4%%"
    AND so.increment_id NOT LIKE "%%-5%%"
    AND so.increment_id NOT LIKE "%%-6%%"
    AND so.increment_id NOT LIKE "%%-7%%"
    AND so.increment_id NOT LIKE "%%-8%%"
    AND so.increment_id NOT LIKE "%%-9%%"
    AND so.increment_id NOT LIKE "%%-10%%"
    AND so.increment_id NOT LIKE "%%-11%%"
    AND so.increment_id NOT LIKE "%%-12%%"
    AND so.increment_id NOT LIKE "%%-13%%"
    AND so.increment_id NOT LIKE "%%-14%%"
    AND so.increment_id NOT LIKE "%%-15%%"
    AND so.increment_id NOT LIKE "%%-16%%"
    AND so.status IN ('Processing', 'Complete', 'approved')
    AND soi.product_type = 'Bundle'
GROUP BY YEAR(so.created_at), MONTH(so.created_at)
ORDER BY ano, mes
"""
        def _curva_monthly_work(conn):
            return conn.execute(text(query), {"ano_atual": ano_atual, "ano_anterior": ano_anterior}).fetchall()
        rows = magento_run(_curva_monthly_work, label="curva:monthly-sales", profile="background")
        return [{"ano": int(r[0]), "mes": int(r[1]), "qtd": int(r[2] or 0), "receita": float(r[3] or 0)} for r in rows]
    except Exception as e:
        logger.error(f"Erro monthly sales Magento: {e}")
        return []


_curva_cache = {}
_curva_cache_timestamp = None


@router.get("/curva-comparativa")
def get_curva_comparativa(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing_comparativo", "pode_visualizar"))
):
    global _curva_cache, _curva_cache_timestamp
    import time

    current_time = time.time()
    cache_valid = _curva_cache_timestamp and (current_time - _curva_cache_timestamp) < 300

    if cache_valid and _curva_cache:
        return _curva_cache

    ano_atual = datetime.now().year
    ano_anterior = ano_atual - 1

    meses_labels = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

    future_ativo = _rolling_avg_executor.submit(_fetch_monthly_sales_ativo, ano_atual, ano_anterior)
    future_magento = _rolling_avg_executor.submit(_fetch_monthly_sales_magento, ano_atual, ano_anterior)

    try:
        dados_ativo = future_ativo.result(timeout=60)
    except Exception as e:
        logger.error(f"Curva comparativa Ativo timeout: {e}")
        dados_ativo = []

    try:
        dados_magento = future_magento.result(timeout=60)
    except Exception as e:
        logger.error(f"Curva comparativa Magento timeout: {e}")
        dados_magento = []

    monthly = {}
    for m in range(1, 13):
        monthly[m] = {
            "mes": meses_labels[m - 1],
            f"vendas_{ano_atual}": 0,
            f"vendas_{ano_anterior}": 0,
            f"receita_{ano_atual}": 0.0,
            f"receita_{ano_anterior}": 0.0,
        }

    for row in dados_ativo + dados_magento:
        m = row["mes"]
        a = row["ano"]
        if 1 <= m <= 12:
            if a == ano_atual:
                monthly[m][f"vendas_{ano_atual}"] += row["qtd"]
                monthly[m][f"receita_{ano_atual}"] += row["receita"]
            elif a == ano_anterior:
                monthly[m][f"vendas_{ano_anterior}"] += row["qtd"]
                monthly[m][f"receita_{ano_anterior}"] += row["receita"]

    data = []
    acum_atual = 0
    acum_anterior = 0
    acum_receita_atual = 0.0
    acum_receita_anterior = 0.0
    for m in range(1, 13):
        entry = monthly[m]
        acum_atual += entry[f"vendas_{ano_atual}"]
        acum_anterior += entry[f"vendas_{ano_anterior}"]
        acum_receita_atual += entry[f"receita_{ano_atual}"]
        acum_receita_anterior += entry[f"receita_{ano_anterior}"]
        entry[f"receita_{ano_atual}"] = round(entry[f"receita_{ano_atual}"], 2)
        entry[f"receita_{ano_anterior}"] = round(entry[f"receita_{ano_anterior}"], 2)
        entry[f"acumulado_{ano_atual}"] = acum_atual
        entry[f"acumulado_{ano_anterior}"] = acum_anterior
        entry[f"acumulado_receita_{ano_atual}"] = round(acum_receita_atual, 2)
        entry[f"acumulado_receita_{ano_anterior}"] = round(acum_receita_anterior, 2)
        data.append(entry)

    result = {
        "status": "success",
        "ano_atual": ano_atual,
        "ano_anterior": ano_anterior,
        "data": data,
        "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat()
    }

    _curva_cache = result
    _curva_cache_timestamp = current_time
    return result


def _sanitize_skus(skus: list) -> list:
    import re
    return [re.sub(r"[^a-zA-Z0-9_\-]", "", str(s)) for s in skus if s]


def _fetch_monthly_sales_ativo_by_ids(id_eventos: list) -> list:
    if db_module.engine_ssh is None or not id_eventos:
        return []
    try:
        safe_ids = [int(i) for i in id_eventos if str(i).isdigit()]
        if not safe_ids:
            return []
        query = text("""
SELECT /*+ MAX_EXECUTION_TIME(90000) */
    MONTH(c.dt_pedido) AS mes,
    COUNT(CASE WHEN (f.en_cupom_classificacao IS NULL
              OR f.en_cupom_classificacao NOT IN ('Funcionário', 'Cortesia Faturada', 'Grupos', 'Coligados'))
        AND (h.ds_categoria IS NULL OR (h.ds_categoria NOT LIKE '%%GRUPOS%%' AND h.ds_categoria NOT LIKE '%%ortesia%%'))
        AND c.nr_total > 0 THEN 1 END) AS qtd,
    SUM(CASE WHEN (f.en_cupom_classificacao IS NULL
              OR f.en_cupom_classificacao NOT IN ('Funcionário', 'Cortesia Faturada', 'Grupos', 'Coligados'))
        AND (h.ds_categoria IS NULL OR (h.ds_categoria NOT LIKE '%%GRUPOS%%' AND h.ds_categoria NOT LIKE '%%ortesia%%'))
        AND c.nr_total > 0 THEN 
        GREATEST(a.nr_preco - COALESCE(a.nr_desconto_individual, 0) - COALESCE(h.vl_kit, 0), 0)
    ELSE 0 END) AS receita
FROM sa_pedido_evento AS a
INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
INNER JOIN sa_pedido AS c ON c.id_pedido = a.id_pedido
LEFT JOIN sa_modalidade_categoria AS h ON a.id_categoria = h.id_categoria
LEFT JOIN sa_cupom_desconto_item AS e ON e.id_cupom_desconto_item = a.id_cupom_individual
LEFT JOIN sa_cupom_desconto AS f ON f.id_cupom_desconto = e.id_cupom_desconto
WHERE 
    c.id_pedido_status IN (2)
    AND (b.id_campanha_salesforce IS NULL OR b.id_campanha_salesforce NOT LIKE '701d0000000%%')
    AND b.id_evento IN :id_eventos
GROUP BY MONTH(c.dt_pedido)
ORDER BY mes
""").bindparams(bindparam("id_eventos", expanding=True))
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(query, {"id_eventos": safe_ids})
            return [{"mes": int(r[0]), "qtd": int(r[1] or 0), "receita": float(r[2] or 0)} for r in result.fetchall()]
    except Exception as e:
        logger.error(f"Erro monthly sales Ativo by IDs: {e}")
        return []


def _fetch_monthly_sales_magento_by_ids(magento_event_ids: list, data_floor: Optional[date] = None) -> list:
    if db_module.engine_magento is None or not magento_event_ids:
        return []
    try:
        safe_ids = [int(i) for i in magento_event_ids if str(i).isdigit()]
        if not safe_ids:
            return []
        _floor_clause = "AND so.created_at >= :data_floor" if data_floor else ""
        query = text(f"""
SELECT /*+ MAX_EXECUTION_TIME(90000) */
    MONTH(so.created_at) AS mes,
    COUNT(CASE WHEN so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')
        THEN 1 END) AS qtd,
    SUM(CASE WHEN so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%') THEN
        (soi.price - CASE WHEN soi.price = 0 THEN 0
            WHEN soi.name LIKE '%%plus%%' THEN 69.00
            WHEN soi.name LIKE '%%super%%' THEN 269.00
            WHEN soi.name LIKE '%%vip%%' THEN 199.99
            ELSE 0 END
        + COALESCE(so.base_discount_invoiced, 0) * (soi.price / NULLIF(so.base_subtotal, 1))
        - CASE WHEN cg.customer_group_id = 4 THEN 0
            WHEN cg.customer_group_id IN (0, 1, 2, 3, 5, 7) AND COALESCE(soi_persona.persona_price, 0) = 14.90 THEN 14.90
            ELSE 0 END)
    ELSE 0 END) AS receita
FROM sales_order AS so
INNER JOIN sales_order_item AS soi ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
LEFT JOIN customer_group AS cg ON cg.customer_group_id = so.customer_group_id
LEFT JOIN (
    SELECT parent_item_id, MAX(price) AS persona_price
    FROM sales_order_item
    WHERE name LIKE '%%persona%%'
    GROUP BY parent_item_id
) soi_persona ON soi_persona.parent_item_id = soi.item_id
WHERE
    so.increment_id NOT REGEXP '-[0-9]'
    AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
    AND so.state != 'canceled'
    AND cpev1.value IN :magento_event_ids
    {_floor_clause}
GROUP BY MONTH(so.created_at)
ORDER BY mes
""").bindparams(bindparam("magento_event_ids", expanding=True))
        params = {"magento_event_ids": safe_ids}
        if data_floor:
            params["data_floor"] = data_floor
        def _monthly_by_ids_work(conn):
            return conn.execute(query, params).fetchall()
        rows = magento_run(_monthly_by_ids_work, label="curva:monthly-by-ids", profile="background")
        return [{"mes": int(r[0]), "qtd": int(r[1] or 0), "receita": float(r[2] or 0)} for r in rows]
    except Exception as e:
        logger.error(f"Erro monthly sales Magento by IDs: {e}")
        return []


def _fetch_daily_sales_ativo_by_ids_grouped(id_eventos: list) -> dict:
    if not id_eventos:
        return {}
    if _is_warmup_thread():
        with _warmup_daily_cache_lock:
            ativo_cache = _warmup_daily_cache.get("ativo")
        if ativo_cache is not None:
            safe_ids = [str(int(i)) for i in id_eventos if str(i).isdigit()]
            result = {}
            for eid in safe_ids:
                if eid in ativo_cache:
                    result[eid] = dict(ativo_cache[eid])
            if result:
                return result
    if db_module.engine_ssh is None:
        return {}
    try:
        safe_ids = [str(int(i)) for i in id_eventos if str(i).isdigit()]
        if not safe_ids:
            return {}
        query = text("""
SELECT /*+ MAX_EXECUTION_TIME(90000) */
    b.id_evento,
    DATE(c.dt_pedido)                  AS dia,
    COUNT(DISTINCT a.id_pedido_evento) AS qtd
FROM sa_pedido_evento AS a
INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
INNER JOIN sa_pedido AS c
    ON c.id_pedido = a.id_pedido
   AND c.id_pedido_status IN (2)
LEFT JOIN sa_modalidade_categoria AS h ON h.id_categoria = a.id_categoria
LEFT JOIN (
    SELECT e.id_cupom_desconto_item, f.en_cupom_classificacao
    FROM sa_cupom_desconto_item AS e
    INNER JOIN sa_cupom_desconto AS f ON f.id_cupom_desconto = e.id_cupom_desconto
) AS cupom ON cupom.id_cupom_desconto_item = a.id_cupom_individual
WHERE
    b.id_evento IN :id_eventos
    AND (b.id_campanha_salesforce IS NULL OR b.id_campanha_salesforce NOT LIKE '701d0000000%%')
    AND a.nr_preco > 0
    AND (cupom.en_cupom_classificacao IS NULL OR cupom.en_cupom_classificacao <> 'Grupos')
    AND (h.ds_categoria IS NULL OR h.ds_categoria NOT LIKE '%%Grup%%')
    AND c.dt_pedido < CURDATE() + INTERVAL 1 DAY
GROUP BY b.id_evento, DATE(c.dt_pedido)
ORDER BY b.id_evento, dia
""").bindparams(bindparam("id_eventos", expanding=True))
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(query, {"id_eventos": [int(i) for i in safe_ids]})
            grouped = {}
            for r in result.fetchall():
                eid = str(r[0])
                d_str = str(r[1])
                qtd = int(r[2] or 0)
                if eid not in grouped:
                    grouped[eid] = {}
                d = date.fromisoformat(d_str)
                grouped[eid][d] = grouped[eid].get(d, 0) + qtd
            return grouped
    except Exception as e:
        logger.error(f"Erro daily sales Ativo grouped: {e}")
        return {}


def _fetch_daily_sales_magento_by_ids_grouped(magento_event_ids: list, cortesia_magento_ids: Optional[set] = None, data_floor: Optional[date] = None) -> dict:
    if not magento_event_ids:
        return {}
    cort_ids = cortesia_magento_ids or set()
    if not cort_ids and _is_warmup_thread():
        with _warmup_daily_cache_lock:
            magento_cache = _warmup_daily_cache.get("magento")
        if magento_cache is not None:
            safe_ids = [str(int(i)) for i in magento_event_ids if str(i).isdigit()]
            result = {}
            for lid in safe_ids:
                if lid in magento_cache:
                    result[lid] = dict(magento_cache[lid])
            if result:
                return result
    if db_module.engine_magento is None:
        return {}
    try:
        safe_ids = [int(i) for i in magento_event_ids if str(i).isdigit()]
        if not safe_ids:
            return {}
        _floor_clause = "AND so.created_at >= :data_floor" if data_floor else ""
        query = text(f"""
SELECT /*+ MAX_EXECUTION_TIME(90000) */
    cpev1.value                            AS id_evento,
    DATE(so.created_at)                    AS dia,
    COUNT(DISTINCT soi_parent.item_id)     AS qtd
FROM catalog_product_entity_varchar cpev1
INNER JOIN sales_order_item soi_parent
       ON soi_parent.product_id   = cpev1.entity_id
      AND soi_parent.product_type = 'bundle'
INNER JOIN sales_order so
       ON so.entity_id = soi_parent.order_id
      AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
      AND so.state NOT IN ('canceled')
      AND so.increment_id NOT REGEXP '-[0-9]'
      AND so.base_grand_total > 0
      AND (so.discount_description NOT LIKE '%%GRUPOS%%' OR so.discount_description IS NULL)
      AND (so.coupon_code NOT LIKE 'GRUP%%' OR so.coupon_code IS NULL)
      AND so.created_at < CURDATE() + INTERVAL 1 DAY
      {_floor_clause}
INNER JOIN sales_order_item soi_child
       ON soi_child.parent_item_id = soi_parent.item_id
      AND soi_child.product_type   = 'simple'
      AND soi_child.price > 0
      AND (soi_child.price - soi_child.discount_amount) > 0
      AND (
            soi_child.name LIKE '%%Distância%%'
         OR soi_child.name LIKE '%%Distancia%%'
         OR soi_child.name LIKE '%%Distâncias%%'
         OR soi_child.name LIKE '%%Modalidade%%'
         OR soi_child.name REGEXP '-[0-9]+[Kk]m$'
         OR soi_child.name REGEXP '^[0-9]+[Kk]m?$'
         OR soi_child.name LIKE 'Kit Participação%%'
         OR soi_child.name LIKE 'Olímpico%%'
         OR soi_child.name LIKE 'Yoga%%'
      )
WHERE
    cpev1.attribute_id = 321
    AND cpev1.store_id = 0
    AND cpev1.value IN :magento_event_ids
GROUP BY cpev1.value, DATE(so.created_at)
ORDER BY cpev1.value, dia
""")
        query = query.bindparams(bindparam("magento_event_ids", expanding=True))
        exec_params = {"magento_event_ids": safe_ids}
        if data_floor:
            exec_params["data_floor"] = data_floor
        def _daily_grouped_work(conn):
            return conn.execute(query, exec_params).fetchall()
        rows = magento_run(_daily_grouped_work, label="daily-sales-grouped", profile="background")
        grouped = {}
        for r in rows:
            lid = str(r[0])
            d_str = str(r[1])
            qtd = int(r[2] or 0)
            if lid not in grouped:
                grouped[lid] = {}
            d = date.fromisoformat(d_str)
            grouped[lid][d] = grouped[lid].get(d, 0) + qtd
        return grouped
    except Exception as e:
        logger.error(f"Erro daily sales Magento grouped: {e}")
        return {}


def _fetch_daily_sales_ativo_by_ids(id_eventos: list, raise_on_error: bool = False, data_floor: Optional[date] = None) -> list:
    if not id_eventos:
        return []
    if _is_warmup_thread():
        with _warmup_daily_cache_lock:
            ativo_cache = _warmup_daily_cache.get("ativo")
        if ativo_cache is not None:
            safe_ids = [str(int(i)) for i in id_eventos if str(i).isdigit()]
            combined = {}
            for eid in safe_ids:
                if eid in ativo_cache:
                    for d, qtd in ativo_cache[eid].items():
                        combined[d] = combined.get(d, 0) + qtd
            if combined:
                return [{"dia": d.isoformat() if hasattr(d, 'isoformat') else str(d), "qtd": qtd, "receita": 0} for d, qtd in sorted(combined.items())]
    if db_module.engine_ssh is None:
        if raise_on_error:
            raise RuntimeError("engine_ssh indisponível para Ativo")
        return []
    try:
        safe_ids = [int(i) for i in id_eventos if str(i).isdigit()]
        if not safe_ids:
            return []
        query = text(f"""
SELECT /*+ MAX_EXECUTION_TIME(90000) */
    DATE(c.dt_pedido)                                                          AS dia,
    COUNT(DISTINCT a.id_pedido_evento)                                         AS qtd,
    SUM(IF(a.nr_preco - IF(a.nr_desconto_individual IS NULL, 0, a.nr_desconto_individual)
           - IF(h.vl_kit IS NULL, 0, h.vl_kit) < 0, 0,
           a.nr_preco - IF(a.nr_desconto_individual IS NULL, 0, a.nr_desconto_individual)
           - IF(h.vl_kit IS NULL, 0, h.vl_kit)))                              AS receita
FROM sa_pedido_evento AS a
INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
INNER JOIN sa_pedido AS c
    ON c.id_pedido = a.id_pedido
   AND c.id_pedido_status IN (2)
LEFT JOIN sa_modalidade_categoria AS h ON h.id_categoria = a.id_categoria
LEFT JOIN (
    SELECT e.id_cupom_desconto_item, f.en_cupom_classificacao
    FROM sa_cupom_desconto_item AS e
    INNER JOIN sa_cupom_desconto AS f ON f.id_cupom_desconto = e.id_cupom_desconto
) AS cupom ON cupom.id_cupom_desconto_item = a.id_cupom_individual
WHERE
    b.id_evento IN :id_eventos
    AND (b.id_campanha_salesforce IS NULL OR b.id_campanha_salesforce NOT LIKE '701d0000000%%')
    AND a.nr_preco > 0
    AND (cupom.en_cupom_classificacao IS NULL OR cupom.en_cupom_classificacao <> 'Grupos')
    AND (h.ds_categoria IS NULL OR h.ds_categoria NOT LIKE '%%Grup%%')
    AND c.dt_pedido < CURDATE() + INTERVAL 1 DAY
    {('AND c.dt_pedido >= :data_floor' if data_floor else '')}
GROUP BY DATE(c.dt_pedido)
ORDER BY dia
""").bindparams(bindparam("id_eventos", expanding=True))
        ativo_params = {"id_eventos": safe_ids}
        if data_floor:
            ativo_params["data_floor"] = data_floor
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(query, ativo_params)
            return [{"dia": str(r[0]), "qtd": int(r[1] or 0), "receita": float(r[2] or 0)} for r in result.fetchall()]
    except Exception as e:
        logger.error(f"Erro daily sales Ativo by IDs: {e}")
        if raise_on_error:
            raise
        return []


def _fetch_today_sales_ativo_by_ids(id_eventos: list) -> dict:
    if not id_eventos or db_module.engine_ssh is None:
        return {}
    try:
        safe_ids = [int(i) for i in id_eventos if str(i).isdigit()]
        if not safe_ids:
            return {}
        query = text("""
SELECT /*+ MAX_EXECUTION_TIME(30000) */
    DATE(c.dt_pedido)                  AS dia,
    COUNT(DISTINCT a.id_pedido_evento) AS qtd
FROM sa_pedido_evento AS a
INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
INNER JOIN sa_pedido AS c
    ON c.id_pedido = a.id_pedido
   AND c.id_pedido_status IN (2)
LEFT JOIN sa_modalidade_categoria AS h ON h.id_categoria = a.id_categoria
LEFT JOIN (
    SELECT e.id_cupom_desconto_item, f.en_cupom_classificacao
    FROM sa_cupom_desconto_item AS e
    INNER JOIN sa_cupom_desconto AS f ON f.id_cupom_desconto = e.id_cupom_desconto
) AS cupom ON cupom.id_cupom_desconto_item = a.id_cupom_individual
WHERE
    b.id_evento IN :id_eventos
    AND (b.id_campanha_salesforce IS NULL OR b.id_campanha_salesforce NOT LIKE '701d0000000%%')
    AND a.nr_preco > 0
    AND (cupom.en_cupom_classificacao IS NULL OR cupom.en_cupom_classificacao <> 'Grupos')
    AND (h.ds_categoria IS NULL OR h.ds_categoria NOT LIKE '%%Grup%%')
    AND c.dt_pedido >= CURDATE()
    AND c.dt_pedido <  CURDATE() + INTERVAL 1 DAY
GROUP BY DATE(c.dt_pedido)
""").bindparams(bindparam("id_eventos", expanding=True))
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(query, {"id_eventos": safe_ids})
            rows = result.fetchall()
            daily = {}
            for r in rows:
                d = date.fromisoformat(str(r[0])) if isinstance(r[0], str) else r[0]
                daily[d] = daily.get(d, 0) + int(r[1] or 0)
            return daily
    except Exception as e:
        logger.error(f"Erro today sales Ativo by IDs: {e}")
        return {}


def _fetch_today_sales_magento_by_ids(magento_event_ids: list, cortesia_magento_ids: Optional[set] = None) -> dict:
    if not magento_event_ids or db_module.engine_magento is None:
        return {}
    try:
        safe_ids = [str(int(i)) for i in magento_event_ids if str(i).isdigit()]
        if not safe_ids:
            return {}
        query = text("""
SELECT /*+ MAX_EXECUTION_TIME(30000) */
    DATE(so.created_at)                    AS dia,
    COUNT(DISTINCT soi_parent.item_id)     AS qtd
FROM sales_order so
INNER JOIN sales_order_item soi_parent
       ON soi_parent.order_id     = so.entity_id
      AND soi_parent.product_type = 'bundle'
INNER JOIN sales_order_item soi_child
       ON soi_child.parent_item_id = soi_parent.item_id
      AND soi_child.product_type   = 'simple'
      AND soi_child.price > 0
      AND (soi_child.price - soi_child.discount_amount) > 0
      AND (
            soi_child.name LIKE '%%Distância%%'
         OR soi_child.name LIKE '%%Distancia%%'
         OR soi_child.name LIKE '%%Distâncias%%'
         OR soi_child.name LIKE '%%Modalidade%%'
         OR soi_child.name REGEXP '-[0-9]+[Kk]m$'
         OR soi_child.name REGEXP '^[0-9]+[Kk]m?$'
         OR soi_child.name LIKE 'Kit Participação%%'
         OR soi_child.name LIKE 'Olímpico%%'
         OR soi_child.name LIKE 'Yoga%%'
      )
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id    = soi_parent.product_id
      AND cpev1.attribute_id = 321
      AND cpev1.store_id     = 0
WHERE
    so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
    AND so.state NOT IN ('canceled')
    AND so.base_grand_total > 0
    AND (so.discount_description NOT LIKE '%%GRUPOS%%' OR so.discount_description IS NULL)
    AND (so.coupon_code NOT LIKE 'GRUP%%' OR so.coupon_code IS NULL)
    AND cpev1.value IN :magento_event_ids
    AND so.increment_id NOT REGEXP '-[0-9]'
    AND so.created_at >= CURDATE()
    AND so.created_at <  CURDATE() + INTERVAL 1 DAY
GROUP BY DATE(so.created_at)
""").bindparams(bindparam("magento_event_ids", expanding=True))
        def _today_by_ids_work(conn):
            return conn.execute(query, {"magento_event_ids": safe_ids}).fetchall()
        rows = magento_run(_today_by_ids_work, label="today-sales-by-ids", profile="request")
        daily = {}
        for r in rows:
            d = date.fromisoformat(str(r[0])) if isinstance(r[0], str) else r[0]
            daily[d] = daily.get(d, 0) + int(r[1] or 0)
        return daily
    except Exception as e:
        logger.error(f"Erro today sales Magento by IDs: {e}")
        return {}


def _fetch_today_sales_ativo_grouped(id_eventos: list, raise_on_error: bool = False) -> dict:
    """
    Single-query batch for today's Ativo sales grouped by id_evento.
    Returns {str(id_evento): {"qtd": int, "receita": float}}.
    When ``raise_on_error`` is True, the caller will see exceptions instead of
    a silent empty dict — this lets sync paths preserve previous snapshots
    instead of overwriting today with 0 when Ativo is unavailable.
    """
    if not id_eventos:
        return {}
    if db_module.engine_ssh is None:
        if raise_on_error:
            raise RuntimeError("engine_ssh indisponível para Ativo")
        return {}
    try:
        safe_ids = [int(i) for i in id_eventos if str(i).isdigit()]
        if not safe_ids:
            return {}
        query = text("""
SELECT /*+ MAX_EXECUTION_TIME(20000) */
    b.id_evento,
    COUNT(DISTINCT a.id_pedido_evento)                                         AS qtd,
    SUM(IF(a.nr_preco - IF(a.nr_desconto_individual IS NULL, 0, a.nr_desconto_individual)
           - IF(h.vl_kit IS NULL, 0, h.vl_kit) < 0, 0,
           a.nr_preco - IF(a.nr_desconto_individual IS NULL, 0, a.nr_desconto_individual)
           - IF(h.vl_kit IS NULL, 0, h.vl_kit)))                              AS receita
FROM sa_pedido_evento AS a
INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
INNER JOIN sa_pedido AS c
    ON c.id_pedido = a.id_pedido
   AND c.id_pedido_status IN (2)
LEFT JOIN sa_modalidade_categoria AS h ON h.id_categoria = a.id_categoria
LEFT JOIN (
    SELECT e.id_cupom_desconto_item, f.en_cupom_classificacao
    FROM sa_cupom_desconto_item AS e
    INNER JOIN sa_cupom_desconto AS f ON f.id_cupom_desconto = e.id_cupom_desconto
) AS cupom ON cupom.id_cupom_desconto_item = a.id_cupom_individual
WHERE
    b.id_evento IN :id_eventos
    AND (b.id_campanha_salesforce IS NULL OR b.id_campanha_salesforce NOT LIKE '701d0000000%%')
    AND a.nr_preco > 0
    AND (cupom.en_cupom_classificacao IS NULL OR cupom.en_cupom_classificacao <> 'Grupos')
    AND (h.ds_categoria IS NULL OR h.ds_categoria NOT LIKE '%%Grup%%')
    AND c.dt_pedido >= CURDATE()
    AND c.dt_pedido <  CURDATE() + INTERVAL 1 DAY
GROUP BY b.id_evento
""").bindparams(bindparam("id_eventos", expanding=True))
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(query, {"id_eventos": safe_ids})
            grouped = {}
            for r in result.fetchall():
                grouped[str(r[0])] = {"qtd": int(r[1] or 0), "receita": float(r[2] or 0.0)}
            return grouped
    except Exception as e:
        logger.error(f"Erro today sales Ativo grouped: {e}")
        if raise_on_error:
            raise
        return {}


def _fetch_today_sales_magento_grouped(magento_event_ids: list, cortesia_magento_ids: Optional[set] = None, raise_on_error: bool = False, acquire_timeout: Optional[float] = None, max_exec_ms: int = 12000) -> dict:
    """
    Single-query batch for today's Magento sales grouped by id_evento.
    Returns {str(id_evento): {"qtd": int, "receita": float}}.
    Uses the same revenue formula as _fetch_daily_sales_magento_by_ids
    (kit-type adjustments + persona discount + group filter) for consistency.
    When ``raise_on_error`` is True, the caller will see exceptions instead of
    a silent empty dict — this lets sync paths preserve previous snapshots
    instead of overwriting today with 0 when Magento is unavailable.
    """
    if not magento_event_ids:
        return {}
    if db_module.engine_magento is None:
        if raise_on_error:
            raise RuntimeError("engine_magento indisponível")
        return {}
    try:
        safe_ids = [str(int(i)) for i in magento_event_ids if str(i).isdigit()]
        if not safe_ids:
            return {}
        # Clamp defensivo: evita hint inválido/extremo por erro de chamada futura.
        _exec_ms = max(1000, min(60000, int(max_exec_ms)))
        # STRAIGHT_JOIN força o otimizador a ler as tabelas na ordem do FROM,
        # ou seja, liderar pela `sales_order` JÁ filtrada por created_at >= hoje
        # (um único dia = pouquíssimas linhas). Sem isso, o MySQL às vezes lidera
        # por cpev1 (produtos do evento) e materializa itens de TODAS as edições
        # do evento antes de aplicar o filtro de data — explodindo o tempo de
        # execução e batendo no MAX_EXECUTION_TIME (erro 3024), o que zerava o
        # Magento de "hoje" no "Atualizar Hoje".
        query = text(f"""
SELECT /*+ MAX_EXECUTION_TIME({_exec_ms}) */ STRAIGHT_JOIN
    cpev1.value                            AS id_evento,
    COUNT(DISTINCT soi_parent.item_id)     AS qtd,
    SUM(
        soi_child.price
      - soi_child.discount_amount
      - COALESCE(
            (ABS(so.discount_amount) - COALESCE(agg.desc_itens, 0))
                / NULLIF(agg.qtd_bundles, 0)
          , 0)
    )                                       AS receita
FROM sales_order so
INNER JOIN sales_order_item soi_parent
       ON soi_parent.order_id     = so.entity_id
      AND soi_parent.product_type = 'bundle'
INNER JOIN sales_order_item soi_child
       ON soi_child.parent_item_id = soi_parent.item_id
      AND soi_child.product_type   = 'simple'
      AND soi_child.price > 0
      AND (soi_child.price - soi_child.discount_amount) > 0
      AND (
            soi_child.name LIKE '%%Distância%%'
         OR soi_child.name LIKE '%%Distancia%%'
         OR soi_child.name LIKE '%%Distâncias%%'
         OR soi_child.name LIKE '%%Modalidade%%'
         OR soi_child.name REGEXP '-[0-9]+[Kk]m$'
         OR soi_child.name REGEXP '^[0-9]+[Kk]m?$'
         OR soi_child.name LIKE 'Kit Participação%%'
         OR soi_child.name LIKE 'Olímpico%%'
         OR soi_child.name LIKE 'Yoga%%'
      )
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id    = soi_parent.product_id
      AND cpev1.attribute_id = 321
      AND cpev1.store_id     = 0
LEFT JOIN (
    SELECT
        i.order_id,
        SUM(CASE WHEN i.product_type =  'bundle' THEN 1 ELSE 0 END)                 AS qtd_bundles,
        SUM(CASE WHEN i.product_type <> 'bundle' THEN i.discount_amount ELSE 0 END) AS desc_itens
    FROM sales_order_item i
    JOIN (
        SELECT DISTINCT b.order_id
        FROM catalog_product_entity_varchar v
        JOIN sales_order_item b
               ON b.product_id   = v.entity_id
              AND b.product_type = 'bundle'
        JOIN sales_order o2
               ON o2.entity_id   = b.order_id
              AND o2.created_at >= CURDATE()
              AND o2.created_at <  CURDATE() + INTERVAL 1 DAY
        WHERE v.attribute_id = 321
          AND v.store_id     = 0
          AND v.value IN :magento_event_ids_agg
    ) AS tgt ON tgt.order_id = i.order_id
    GROUP BY i.order_id
) AS agg ON agg.order_id = soi_parent.order_id
WHERE
    so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
    AND so.state NOT IN ('canceled')
    AND so.base_grand_total > 0
    AND (so.discount_description NOT LIKE '%%GRUPOS%%' OR so.discount_description IS NULL)
    AND (so.coupon_code NOT LIKE 'GRUP%%' OR so.coupon_code IS NULL)
    AND cpev1.value IN :magento_event_ids
    AND so.increment_id NOT REGEXP '-[0-9]'
    AND so.created_at >= CURDATE()
    AND so.created_at <  CURDATE() + INTERVAL 1 DAY
GROUP BY cpev1.value
""").bindparams(
            bindparam("magento_event_ids", expanding=True),
            bindparam("magento_event_ids_agg", expanding=True),
        )
        def _today_grouped_work(conn):
            # Enforce session-level execution timeout as a hard backstop in case
            # the optimizer hint MAX_EXECUTION_TIME is ignored (e.g. the query is
            # waiting for a lock rather than actually executing).
            try:
                conn.execute(text(f"SET SESSION MAX_EXECUTION_TIME={_exec_ms}"))
            except Exception:
                pass
            return conn.execute(query, {"magento_event_ids": safe_ids, "magento_event_ids_agg": safe_ids}).fetchall()
        rows = magento_run(_today_grouped_work, label="today-sales-grouped", profile="once", acquire_timeout=acquire_timeout)
        grouped = {}
        for r in rows:
            grouped[str(r[0])] = {"qtd": int(r[1] or 0), "receita": float(r[2] or 0.0)}
        return grouped
    except Exception as e:
        logger.error(f"Erro today sales Magento grouped: {e}")
        if raise_on_error:
            raise
        return {}


# ---------------------------------------------------------------------------
# Singleflight + ultra-short TTL para _fetch_daily_sales_magento_by_ids.
# Motivo: a query 'daily-sales-by-ids' é a mais cara do sistema (full join
# em sales_order/sales_order_item/cpev1 + persona subquery) e era disparada
# de 12+ pontos por request, frequentemente em paralelo com IDs idênticos.
# Este wrapper deduplica chamadas concorrentes (singleflight) e segura o
# resultado por _DS_SF_TTL segundos pra absorver re-chamadas em sequência
# rápida dentro da mesma request HTTP. Não muda lógica: o resultado servido
# é exatamente o que o _impl produziria. Exceções são propagadas com o mesmo
# critério de raise_on_error.
# ---------------------------------------------------------------------------
_DS_SF_LOCK = _threading.Lock()
_DS_SF_INFLIGHT: dict = {}
_DS_SF_RESULTS: dict = {}
_DS_SF_TTL = 5.0
_DS_SF_MAX_ENTRIES = 256


def _ds_sf_key(magento_event_ids, cortesia_magento_ids, data_floor, ano,
               force_magento_refresh, raise_on_error, db_provided, is_warmup):
    return (
        tuple(sorted(str(i) for i in magento_event_ids)),
        tuple(sorted(str(i) for i in (cortesia_magento_ids or []))),
        data_floor.isoformat() if data_floor else None,
        ano,
        bool(force_magento_refresh),
        bool(raise_on_error),
        bool(db_provided),
        bool(is_warmup),
    )


def _ds_sf_prune_locked():
    if len(_DS_SF_RESULTS) <= _DS_SF_MAX_ENTRIES:
        return
    cutoff = _time.time() - (_DS_SF_TTL * 3.0)
    stale = [k for k, v in _DS_SF_RESULTS.items() if v[0] < cutoff]
    for k in stale:
        _DS_SF_RESULTS.pop(k, None)


def _fetch_daily_sales_magento_by_ids(
    magento_event_ids: list,
    cortesia_magento_ids: Optional[set] = None,
    raise_on_error: bool = False,
    data_floor: Optional[date] = None,
    *,
    db: Optional[Session] = None,
    ano: Optional[int] = None,
    force_magento_refresh: bool = False,
) -> list:
    """Wrapper singleflight+TTL. Delega para _impl. Ver bloco acima."""
    if not magento_event_ids:
        return []
    # Inclui is_warmup no key porque _impl tem branch específico para warmup
    # thread (lê de _warmup_daily_cache em vez de Magento), o que produz
    # resultados diferentes (ex.: receita=0). Sem essa dimensão, um warmup
    # leader poderia poluir o cache para uma request normal por 5s.
    try:
        _is_warmup_ctx = _is_warmup_thread()
    except Exception:
        _is_warmup_ctx = False
    key = _ds_sf_key(
        magento_event_ids, cortesia_magento_ids, data_floor, ano,
        force_magento_refresh, raise_on_error, db is not None, _is_warmup_ctx,
    )
    now = _time.time()
    leader = False
    wait_evt = None
    with _DS_SF_LOCK:
        cached = _DS_SF_RESULTS.get(key)
        if cached and (now - cached[0]) < _DS_SF_TTL:
            _, c_res, c_exc = cached
            if c_exc is not None:
                if raise_on_error:
                    raise c_exc
                return c_res if c_res is not None else []
            return c_res if c_res is not None else []
        evt = _DS_SF_INFLIGHT.get(key)
        if evt is not None:
            wait_evt = evt
        else:
            wait_evt = _threading.Event()
            _DS_SF_INFLIGHT[key] = wait_evt
            leader = True
    if not leader:
        # Waiter: aguarda o leader publicar o resultado.
        wait_evt.wait(timeout=60.0)
        with _DS_SF_LOCK:
            cached = _DS_SF_RESULTS.get(key)
        if cached:
            _, c_res, c_exc = cached
            if c_exc is not None:
                if raise_on_error:
                    raise c_exc
                return c_res if c_res is not None else []
            return c_res if c_res is not None else []
        # Fallback raro: leader sumiu sem publicar — segue para computar direto.
        leader = True
    # Leader: executa o impl e publica o resultado.
    result = None
    exc_caught = None
    try:
        result = _fetch_daily_sales_magento_by_ids_impl(
            magento_event_ids,
            cortesia_magento_ids=cortesia_magento_ids,
            raise_on_error=raise_on_error,
            data_floor=data_floor,
            db=db,
            ano=ano,
            force_magento_refresh=force_magento_refresh,
        )
    except BaseException as e:
        exc_caught = e
    finally:
        with _DS_SF_LOCK:
            _DS_SF_RESULTS[key] = (_time.time(), result, exc_caught)
            _DS_SF_INFLIGHT.pop(key, None)
            _ds_sf_prune_locked()
        wait_evt.set()
    if exc_caught is not None:
        raise exc_caught
    return result if result is not None else []


def _fetch_daily_sales_magento_by_ids_impl(
    magento_event_ids: list,
    cortesia_magento_ids: Optional[set] = None,
    raise_on_error: bool = False,
    data_floor: Optional[date] = None,
    *,
    db: Optional[Session] = None,
    ano: Optional[int] = None,
    force_magento_refresh: bool = False,
) -> list:
    """Vendas diárias por IDs Magento.

    Quando ``db`` é fornecido e ``force_magento_refresh=False``: divide os IDs
    em ativos vs. congelados (data_evento + EVENTO_FREEZE_AFTER_DAYS < hoje),
    lê os congelados direto do snapshot PostgreSQL (sem ir ao Magento) e roda
    a query no Magento apenas para os IDs ativos. Os resultados são mesclados
    por data antes do retorno.
    """
    if not magento_event_ids:
        return []
    # --- Roteamento inteligente: snapshot p/ frozen, Magento p/ ativos -------
    _snap_daily: dict = {}
    if db is not None and not force_magento_refresh:
        try:
            from ...services.snapshot_service import (
                partition_magento_ids_by_freeze as _part,
                read_daily_sales_snapshot_by_magento_ids as _snap_read,
            )
            active_ids, frozen_ids = _part(db, magento_event_ids, force_magento_refresh=False)
            if frozen_ids:
                _snap_daily = _snap_read(db, frozen_ids, ano=ano, data_floor=data_floor)
                logger.info(
                    f"[daily-by-ids] {len(frozen_ids)} IDs congelados servidos do snapshot "
                    f"({len(_snap_daily)} dias); {len(active_ids)} IDs ativos ainda vão ao Magento"
                )
            magento_event_ids = active_ids
        except Exception as _e_part:
            logger.warning(f"[daily-by-ids] particionamento freeze falhou (ignorado): {_e_part}")
    if not magento_event_ids:
        if not _snap_daily:
            return []
        return [
            {"dia": d.isoformat() if hasattr(d, 'isoformat') else str(d), "qtd": v[0], "receita": v[1]}
            for d, v in sorted(_snap_daily.items())
        ]
    cort_ids = cortesia_magento_ids or set()
    if not cort_ids and _is_warmup_thread():
        with _warmup_daily_cache_lock:
            magento_cache = _warmup_daily_cache.get("magento")
        if magento_cache is not None:
            safe_ids = [str(int(i)) for i in magento_event_ids if str(i).isdigit()]
            combined = {}
            for lid in safe_ids:
                if lid in magento_cache:
                    for d, qtd in magento_cache[lid].items():
                        combined[d] = combined.get(d, 0) + qtd
            if combined:
                return [{"dia": d.isoformat() if hasattr(d, 'isoformat') else str(d), "qtd": qtd, "receita": 0} for d, qtd in sorted(combined.items())]
    if db_module.engine_magento is None:
        if raise_on_error:
            raise RuntimeError("engine_magento indisponível")
        return []
    try:
        safe_ids = [str(int(i)) for i in magento_event_ids if str(i).isdigit()]
        if not safe_ids:
            return []
        query = text(f"""
SELECT /*+ MAX_EXECUTION_TIME(90000) */
    DATE(so.created_at)                    AS dia,
    COUNT(DISTINCT soi_parent.item_id)     AS qtd,
    SUM(
        soi_child.price
      - soi_child.discount_amount
      - COALESCE(
            (ABS(so.discount_amount) - COALESCE(agg.desc_itens, 0))
                / NULLIF(agg.qtd_bundles, 0)
          , 0)
    )                                       AS receita
FROM catalog_product_entity_varchar cpev1
INNER JOIN sales_order_item soi_parent
       ON soi_parent.product_id   = cpev1.entity_id
      AND soi_parent.product_type = 'bundle'
INNER JOIN sales_order so
       ON so.entity_id = soi_parent.order_id
      AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
      AND so.state NOT IN ('canceled')
      AND so.increment_id NOT REGEXP '-[0-9]'
      AND so.base_grand_total > 0
      AND (so.discount_description NOT LIKE '%%GRUPOS%%' OR so.discount_description IS NULL)
      AND (so.coupon_code NOT LIKE 'GRUP%%' OR so.coupon_code IS NULL)
      AND so.created_at < CURDATE() + INTERVAL 1 DAY
      {('AND so.created_at >= :data_floor' if data_floor else '')}
INNER JOIN sales_order_item soi_child
       ON soi_child.parent_item_id = soi_parent.item_id
      AND soi_child.product_type   = 'simple'
      AND soi_child.price > 0
      AND (soi_child.price - soi_child.discount_amount) > 0
      AND (
            soi_child.name LIKE '%%Distância%%'
         OR soi_child.name LIKE '%%Distancia%%'
         OR soi_child.name LIKE '%%Distâncias%%'
         OR soi_child.name LIKE '%%Modalidade%%'
         OR soi_child.name REGEXP '-[0-9]+[Kk]m$'
         OR soi_child.name REGEXP '^[0-9]+[Kk]m?$'
         OR soi_child.name LIKE 'Kit Participação%%'
         OR soi_child.name LIKE 'Olímpico%%'
         OR soi_child.name LIKE 'Yoga%%'
      )
LEFT JOIN (
    SELECT
        i.order_id,
        SUM(CASE WHEN i.product_type =  'bundle' THEN 1 ELSE 0 END)                 AS qtd_bundles,
        SUM(CASE WHEN i.product_type <> 'bundle' THEN i.discount_amount ELSE 0 END) AS desc_itens
    FROM sales_order_item i
    JOIN (
        SELECT DISTINCT b.order_id
        FROM catalog_product_entity_varchar v
        JOIN sales_order_item b
               ON b.product_id   = v.entity_id
              AND b.product_type = 'bundle'
        JOIN sales_order o2
               ON o2.entity_id  = b.order_id
              AND o2.created_at < CURDATE() + INTERVAL 1 DAY
              {('AND o2.created_at >= :data_floor' if data_floor else '')}
        WHERE v.attribute_id = 321
          AND v.store_id     = 0
          AND v.value IN :magento_event_ids_agg
    ) AS tgt ON tgt.order_id = i.order_id
    GROUP BY i.order_id
) AS agg ON agg.order_id = soi_parent.order_id
WHERE
    cpev1.attribute_id = 321
    AND cpev1.store_id = 0
    AND cpev1.value IN :magento_event_ids
GROUP BY DATE(so.created_at)
ORDER BY dia
""")
        bp = [
            bindparam("magento_event_ids", expanding=True),
            bindparam("magento_event_ids_agg", expanding=True),
        ]
        params = {"magento_event_ids": safe_ids, "magento_event_ids_agg": safe_ids}
        if data_floor:
            params["data_floor"] = data_floor
        query = query.bindparams(*bp)
        def _daily_by_ids_work(conn):
            return conn.execute(query, params).fetchall()
        # "request" profile (2 tentativas) mesmo para background: evita bloquear o
        # tunnel SSH do Magento por até 270s (90s × 3) quando o servidor está lento.
        # Se 2 tentativas de 25s falharem, o snapshot existente é preservado.
        profile = "request"
        rows = magento_run(_daily_by_ids_work, label="daily-sales-by-ids", profile=profile)
        # Mescla snapshot (frozen) + Magento (ativos) por dia.
        merged: dict = {}
        for d, (q_s, r_s) in _snap_daily.items():
            key = d.isoformat() if hasattr(d, 'isoformat') else str(d)
            merged[key] = (q_s, r_s)
        for r in rows:
            key = str(r[0])
            q_m = int(r[1] or 0)
            r_m = float(r[2] or 0)
            prev_q, prev_r = merged.get(key, (0, 0.0))
            merged[key] = (prev_q + q_m, prev_r + r_m)
        return [{"dia": k, "qtd": v[0], "receita": v[1]} for k, v in sorted(merged.items())]
    except Exception as e:
        logger.error(f"Erro daily sales Magento by IDs: {e}")
        if raise_on_error:
            raise
        # Mesmo em falha do Magento, devolve o snapshot se houver dados.
        if _snap_daily:
            return [
                {"dia": d.isoformat() if hasattr(d, 'isoformat') else str(d), "qtd": v[0], "receita": v[1]}
                for d, v in sorted(_snap_daily.items())
            ]
        return []


def _fetch_category_sales_ativo_by_ids(id_eventos: list) -> list:
    if not id_eventos:
        return []
    if _is_warmup_thread():
        with _warmup_daily_cache_lock:
            cat_cache = _warmup_daily_cache.get("cat_ativo")
        if cat_cache is not None:
            safe_ids = [str(int(i)) for i in id_eventos if str(i).isdigit()]
            combined = {}
            for eid in safe_ids:
                if eid in cat_cache:
                    for cat, qtd in cat_cache[eid].items():
                        combined[cat] = combined.get(cat, 0) + qtd
            if combined:
                return [{"categoria": cat, "qtd": qtd} for cat, qtd in sorted(combined.items(), key=lambda x: -x[1])]
    if db_module.engine_ssh is None:
        return []
    try:
        safe_ids = [str(int(i)) for i in id_eventos if str(i).isdigit()]
        if not safe_ids:
            return []
        query = text("""
SELECT /*+ MAX_EXECUTION_TIME(90000) */
    h.ds_categoria AS categoria,
    COUNT(CASE WHEN (f.en_cupom_classificacao IS NULL
              OR f.en_cupom_classificacao NOT IN ('Funcionário', 'Cortesia Faturada', 'Grupos', 'Coligados'))
        AND (h.ds_categoria IS NULL OR (h.ds_categoria NOT LIKE '%%GRUPOS%%' AND h.ds_categoria NOT LIKE '%%ortesia%%'))
        AND c.nr_total > 0 THEN 1 END) AS qtd
FROM sa_pedido_evento AS a
INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
INNER JOIN sa_pedido AS c ON c.id_pedido = a.id_pedido
LEFT JOIN sa_modalidade_categoria AS h ON a.id_categoria = h.id_categoria
LEFT JOIN sa_cupom_desconto_item AS e ON e.id_cupom_desconto_item = a.id_cupom_individual
LEFT JOIN sa_cupom_desconto AS f ON f.id_cupom_desconto = e.id_cupom_desconto
WHERE 
    c.id_pedido_status IN (2)
    AND (b.id_campanha_salesforce IS NULL OR b.id_campanha_salesforce NOT LIKE '701d0000000%%')
    AND b.id_evento IN :id_eventos
GROUP BY h.ds_categoria
ORDER BY qtd DESC
""").bindparams(bindparam("id_eventos", expanding=True))
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(query, {"id_eventos": safe_ids})
            return [{"categoria": str(r[0] or "Sem categoria"), "qtd": int(r[1] or 0)} for r in result.fetchall()]
    except Exception as e:
        logger.error(f"Erro category sales Ativo by IDs: {e}")
        return []


def _fetch_category_sales_ativo_by_ids_grouped(id_eventos: list) -> dict:
    if db_module.engine_ssh is None or not id_eventos:
        return {}
    try:
        safe_ids = [str(int(i)) for i in id_eventos if str(i).isdigit()]
        if not safe_ids:
            return {}
        query = text("""
SELECT /*+ MAX_EXECUTION_TIME(90000) */
    b.id_evento,
    h.ds_categoria AS categoria,
    COUNT(CASE WHEN (f.en_cupom_classificacao IS NULL
              OR f.en_cupom_classificacao NOT IN ('Funcionário', 'Cortesia Faturada', 'Grupos', 'Coligados'))
        AND (h.ds_categoria IS NULL OR (h.ds_categoria NOT LIKE '%%GRUPOS%%' AND h.ds_categoria NOT LIKE '%%ortesia%%'))
        AND c.nr_total > 0 THEN 1 END) AS qtd
FROM sa_pedido_evento AS a
INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento
INNER JOIN sa_pedido AS c ON c.id_pedido = a.id_pedido
LEFT JOIN sa_modalidade_categoria AS h ON a.id_categoria = h.id_categoria
LEFT JOIN sa_cupom_desconto_item AS e ON e.id_cupom_desconto_item = a.id_cupom_individual
LEFT JOIN sa_cupom_desconto AS f ON f.id_cupom_desconto = e.id_cupom_desconto
WHERE 
    c.id_pedido_status IN (2)
    AND (b.id_campanha_salesforce IS NULL OR b.id_campanha_salesforce NOT LIKE '701d0000000%%')
    AND b.id_evento IN :id_eventos
GROUP BY b.id_evento, h.ds_categoria
ORDER BY b.id_evento, qtd DESC
""").bindparams(bindparam("id_eventos", expanding=True))
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(query, {"id_eventos": [int(i) for i in safe_ids]})
            grouped = {}
            for r in result.fetchall():
                eid = str(r[0])
                cat = str(r[1] or "Sem categoria")
                qtd = int(r[2] or 0)
                if eid not in grouped:
                    grouped[eid] = {}
                grouped[eid][cat] = grouped[eid].get(cat, 0) + qtd
            return grouped
    except Exception as e:
        logger.error(f"Erro category sales Ativo grouped: {e}")
        return {}


def _fetch_category_sales_magento_by_ids_grouped(magento_event_ids: list) -> dict:
    if db_module.engine_magento is None or not magento_event_ids:
        return {}
    try:
        safe_ids = [int(i) for i in magento_event_ids if str(i).isdigit()]
        if not safe_ids:
            return {}
        query = text("""
SELECT /*+ MAX_EXECUTION_TIME(90000) */
    cpev1.value AS event_id,
    soi.name AS categoria,
    COUNT(CASE WHEN so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')
        AND soi.price > 0 THEN 1 END) AS qtd
FROM sales_order AS so
INNER JOIN sales_order_item AS soi ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1 ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
LEFT JOIN customer_group AS cg ON cg.customer_group_id = so.customer_group_id
WHERE
    so.increment_id NOT REGEXP '-[0-9]'
    AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
    AND so.state != 'canceled'
    AND cpev1.value IN :magento_event_ids
GROUP BY cpev1.value, soi.name
ORDER BY cpev1.value, qtd DESC
""").bindparams(bindparam("magento_event_ids", expanding=True))
        def _cat_grouped_work(conn):
            return conn.execute(query, {"magento_event_ids": safe_ids}).fetchall()
        rows = magento_run(_cat_grouped_work, label="category-sales-grouped", profile="background")
        grouped = {}
        for r in rows:
            lid = str(r[0])
            cat = str(r[1] or "Sem categoria")
            qtd = int(r[2] or 0)
            if lid not in grouped:
                grouped[lid] = {}
            grouped[lid][cat] = grouped[lid].get(cat, 0) + qtd
        return grouped
    except Exception as e:
        logger.error(f"Erro category sales Magento grouped: {e}")
        return {}


def _fetch_category_sales_magento_by_ids(magento_event_ids: list) -> list:
    if not magento_event_ids:
        return []
    if _is_warmup_thread():
        with _warmup_daily_cache_lock:
            cat_cache = _warmup_daily_cache.get("cat_magento")
        if cat_cache is not None:
            safe_ids = [str(int(i)) for i in magento_event_ids if str(i).isdigit()]
            combined = {}
            for lid in safe_ids:
                if lid in cat_cache:
                    for cat, qtd in cat_cache[lid].items():
                        combined[cat] = combined.get(cat, 0) + qtd
            if combined:
                return [{"categoria": cat, "qtd": qtd} for cat, qtd in sorted(combined.items(), key=lambda x: -x[1])]
    if db_module.engine_magento is None:
        return []
    try:
        safe_ids = [int(i) for i in magento_event_ids if str(i).isdigit()]
        if not safe_ids:
            return []
        query = text("""
SELECT /*+ MAX_EXECUTION_TIME(90000) */
    soi.name AS categoria,
    COUNT(CASE WHEN so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')
        THEN 1 END) AS qtd
FROM sales_order AS so
INNER JOIN sales_order_item AS soi ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
LEFT JOIN customer_group AS cg ON cg.customer_group_id = so.customer_group_id
WHERE
    so.increment_id NOT REGEXP '-[0-9]'
    AND so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
    AND so.state != 'canceled'
    AND cpev1.value IN :magento_event_ids
GROUP BY soi.name
ORDER BY qtd DESC
""").bindparams(bindparam("magento_event_ids", expanding=True))
        def _cat_by_ids_work(conn):
            return conn.execute(query, {"magento_event_ids": safe_ids}).fetchall()
        rows = magento_run(_cat_by_ids_work, label="category-sales-by-ids", profile="background")
        return [{"categoria": str(r[0] or "Sem categoria"), "qtd": int(r[1] or 0)} for r in rows]
    except Exception as e:
        logger.error(f"Erro category sales Magento by IDs: {e}")
        return []


import re as _re
import unicodedata as _unicodedata

def _normalize_name_for_match(name: str) -> str:
    s = _unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    s = _re.sub(r'\d{4}', '', s)
    s = _re.sub(r'\s*-\s*', ' ', s)
    s = _re.sub(r'\s+\d+$', '', s.strip())
    s = _re.sub(r'\s+', ' ', s).strip().lower()
    return s

_hist_pattern_cache: dict = {}
_hist_curva_info_cache: dict = {}
_hist_pattern_cache_lock = _threading.Lock()

def _prefetch_all_historical_patterns(db: Session, grupo_names: list, ano: int) -> tuple:
    from ...models.dimensoes import SkuMapping
    prev_ano = ano - 1
    all_requested_names = list(grupo_names)
    if not grupo_names:
        return {}, {}

    cache_key = f"{ano}_hist_patterns"
    with _hist_pattern_cache_lock:
        cached = _hist_pattern_cache.get(cache_key)
    if cached is not None:
        filtered = {g: cached[g] for g in grupo_names if g in cached}
        uncached = [g for g in grupo_names if g not in cached]
        cached_ci = _hist_curva_info_cache.get(cache_key, {})
        if not uncached:
            curva_info_map = {gn: cached_ci.get(gn, {"tipo_curva": "historico", "fonte_curva": gn, "ano_referencia": prev_ano}) for gn in filtered}
            missing_from_cache = [g for g in all_requested_names if g not in filtered]
            mc_estado_map = {}
            for gn in missing_from_cache:
                estado_row = db.query(DimProjeto.estado).join(
                    SkuMapping, SkuMapping.sku == DimProjeto.codigo
                ).filter(
                    SkuMapping.evento_grupo == gn,
                    DimProjeto.estado.isnot(None)
                ).first()
                if estado_row:
                    mc_estado_map[gn] = estado_row[0]
            for gn in missing_from_cache:
                try:
                    estado = mc_estado_map.get(gn)
                    fb_pattern, fb_info = _resolve_hist_pattern(db, gn, ano, estado=estado)
                    if fb_pattern:
                        filtered[gn] = fb_pattern
                    curva_info_map[gn] = fb_info
                except Exception:
                    curva_info_map[gn] = {"tipo_curva": "linear", "fonte_curva": None, "ano_referencia": None}
            return filtered, curva_info_map
        grupo_names = uncached

    grupo_data_evento = {}
    grupo_mappings_map = {}
    all_prev_ativo_ids = []
    all_prev_magento_ids = []
    grupo_id_map = {}

    for grupo_nome in grupo_names:
        prev_data_evento = _find_data_evento(db, grupo_nome, prev_ano)
        if not prev_data_evento:
            continue
        grupo_data_evento[grupo_nome] = prev_data_evento

        prev_mappings = db.query(SkuMapping).filter(
            SkuMapping.evento_grupo == grupo_nome,
            SkuMapping.ano == prev_ano,
            SkuMapping.ativo == True
        ).all()

        if not prev_mappings:
            prev_skus_from_current = db.query(SkuMapping.sku).filter(
                SkuMapping.evento_grupo == grupo_nome,
                SkuMapping.ano == ano,
                SkuMapping.ativo == True
            ).distinct().all()
            prev_skus = [s[0] for s in prev_skus_from_current]
            if prev_skus:
                prev_mappings = db.query(SkuMapping).filter(
                    SkuMapping.sku.in_(prev_skus),
                    SkuMapping.ano == prev_ano,
                    SkuMapping.ativo == True
                ).all()

        if not prev_mappings:
            continue

        ativo_ids = []
        magento_ids = []
        for m in prev_mappings:
            if m.id_externo:
                ext_id = str(m.id_externo)
                if m.fonte == 'ATIVO':
                    ativo_ids.append(ext_id)
                    all_prev_ativo_ids.append(ext_id)
                    if ext_id not in grupo_id_map:
                        grupo_id_map[ext_id] = []
                    grupo_id_map[ext_id].append(('ATIVO', grupo_nome))
                elif m.fonte == 'MAGENTO':
                    magento_ids.append(ext_id)
                    all_prev_magento_ids.append(ext_id)
                    if ext_id not in grupo_id_map:
                        grupo_id_map[ext_id] = []
                    grupo_id_map[ext_id].append(('MAGENTO', grupo_nome))

        grupo_mappings_map[grupo_nome] = {'ativo': ativo_ids, 'magento': magento_ids}

    ativo_grouped = {}
    if all_prev_ativo_ids:
        try:
            ativo_grouped = _fetch_daily_sales_ativo_by_ids_grouped(list(set(all_prev_ativo_ids)))
        except Exception as e:
            logger.error(f"Batch historical Ativo fetch error: {e}")

    magento_grouped = {}
    if all_prev_magento_ids:
        try:
            _cort_batch = _get_cortesia_magento_ids(db)
            _mag_cort_batch = set(all_prev_magento_ids) & _cort_batch if _cort_batch else None
            magento_grouped = _fetch_daily_sales_magento_by_ids_grouped(list(set(all_prev_magento_ids)), cortesia_magento_ids=_mag_cort_batch if _mag_cort_batch else None)
        except Exception as e:
            logger.error(f"Batch historical Magento fetch error: {e}")

    result = {}
    for grupo_nome in grupo_names:
        if grupo_nome not in grupo_data_evento or grupo_nome not in grupo_mappings_map:
            continue

        prev_data_evento = grupo_data_evento[grupo_nome]
        ids_info = grupo_mappings_map[grupo_nome]

        prev_dias_enc = 2
        try:
            prev_proj = db.query(DimProjeto).filter(
                DimProjeto.data_evento == prev_data_evento
            ).first()
            if prev_proj:
                prev_dias_enc = get_dias_encerramento(db, projeto_id=prev_proj.id)
        except Exception:
            pass
        prev_data_inscricao = prev_data_evento - timedelta(days=prev_dias_enc)

        prev_daily = {}
        for eid in ids_info['ativo']:
            if eid in ativo_grouped:
                for d, qtd in ativo_grouped[eid].items():
                    prev_daily[d] = prev_daily.get(d, 0) + qtd
        for lid in ids_info['magento']:
            if lid in magento_grouped:
                for d, qtd in magento_grouped[lid].items():
                    prev_daily[d] = prev_daily.get(d, 0) + qtd

        if not prev_daily:
            continue

        total_prev_sales = sum(prev_daily.values())
        if total_prev_sales == 0:
            continue

        d_minus_sales = {}
        for sale_date, qty in prev_daily.items():
            dm = (prev_data_inscricao - sale_date).days
            d_minus_sales[dm] = d_minus_sales.get(dm, 0) + qty

        d_minus_sales = {dm: qty for dm, qty in d_minus_sales.items() if dm >= 0}
        if not d_minus_sales:
            continue

        max_dm = max(d_minus_sales.keys())
        min_dm = min(d_minus_sales.keys())

        cumulative = 0
        pattern = {}
        for dm in range(max_dm, min_dm - 1, -1):
            cumulative += d_minus_sales.get(dm, 0)
            pattern[dm] = cumulative / total_prev_sales

        if 0 not in pattern:
            pattern[0] = 1.0
        if min_dm > 0:
            for dm in range(min_dm - 1, -1, -1):
                pattern[dm] = 1.0

        logger.info(f"Batch: Built historical pattern for '{grupo_nome}' from ano={prev_ano}: {len(prev_daily)} sale days, total={total_prev_sales}, D- range [{min_dm}, {max_dm}]")
        result[grupo_nome] = pattern

    curva_info_map = {}
    for gn in list(result.keys()):
        curva_info_map[gn] = {
            "tipo_curva": "historico",
            "fonte_curva": gn,
            "ano_referencia": prev_ano
        }

    missing = [g for g in all_requested_names if g not in result]
    missing_estado_map = {}
    if missing:
        for gn in missing:
            estado_row = db.query(DimProjeto.estado).join(
                SkuMapping, SkuMapping.sku == DimProjeto.codigo
            ).filter(
                SkuMapping.evento_grupo == gn,
                DimProjeto.estado.isnot(None)
            ).first()
            if estado_row:
                missing_estado_map[gn] = estado_row[0]
    for gn in missing:
        try:
            estado = missing_estado_map.get(gn)
            fb_pattern, fb_info = _resolve_hist_pattern(db, gn, ano, estado=estado)
            if fb_pattern:
                result[gn] = fb_pattern
                curva_info_map[gn] = fb_info
            else:
                curva_info_map[gn] = fb_info
        except Exception as e:
            logger.warning(f"Fallback resolution failed for '{gn}': {e}")
            curva_info_map[gn] = {"tipo_curva": "linear", "fonte_curva": None, "ano_referencia": None}

    with _hist_pattern_cache_lock:
        if cache_key not in _hist_pattern_cache:
            _hist_pattern_cache[cache_key] = {}
        _hist_pattern_cache[cache_key].update(result)
        if cache_key not in _hist_curva_info_cache:
            _hist_curva_info_cache[cache_key] = {}
        _hist_curva_info_cache[cache_key].update(curva_info_map)

    if cached is not None:
        result.update(filtered)
        cached_ci = _hist_curva_info_cache.get(cache_key, {})
        for gn in filtered:
            if gn not in curva_info_map:
                curva_info_map[gn] = cached_ci.get(gn, {"tipo_curva": "historico", "fonte_curva": gn, "ano_referencia": prev_ano})

    return result, curva_info_map


_FIND_DATA_EVENTO_UNSET = object()


def _find_data_evento(
    db: Session,
    evento_grupo: str,
    ano: int,
    projetos: Optional[list] = None,
    sku_mapping_date=_FIND_DATA_EVENTO_UNSET,
) -> Optional[date]:
    """Resolve a data do evento para um (grupo, ano).

    Parâmetros opcionais para uso em lote (evita N consultas idênticas quando
    resolvendo muitos grupos de uma vez — ver
    ``_fetch_current_year_realized_patterns_batch``):
      - ``projetos``: lista de DimProjeto já carregada (filtrada para
        ``data_evento is not None``). Quando ausente, é carregada via
        ``_wq_all_dim_projetos``.
      - ``sku_mapping_date``: data já resolvida do sku_mappings para este grupo
        (ou ``None`` quando não há). Quando ausente, é consultada aqui.
    """
    from ...models.dimensoes import SkuMapping
    ano_corrente = today_brazil().year

    if sku_mapping_date is _FIND_DATA_EVENTO_UNSET:
        sku_mapping_date = None
        mapping_with_date = db.query(SkuMapping).filter(
            SkuMapping.evento_grupo == evento_grupo,
            SkuMapping.ano == ano,
            SkuMapping.data_evento.isnot(None),
            SkuMapping.ativo == True
        ).first()
        if mapping_with_date:
            sku_mapping_date = mapping_with_date.data_evento
            if ano < ano_corrente:
                logger.info(f"Found data_evento in sku_mappings for '{evento_grupo}' ano={ano} (ano anterior): {sku_mapping_date}")
                return sku_mapping_date
            else:
                logger.debug(f"sku_mappings has data_evento={sku_mapping_date} for '{evento_grupo}' ano={ano}, but preferring dim_projeto/cadastro for current year")
        elif ano < ano_corrente:
            logger.info(f"No data_evento in sku_mappings for '{evento_grupo}' ano={ano} (ano anterior), falling back to dim_projeto")
    else:
        # Data do sku_mappings pré-resolvida pelo chamador em lote. Replica a
        # mesma decisão de short-circuit do caminho não-batch.
        if sku_mapping_date is not None and ano < ano_corrente:
            return sku_mapping_date

    normalized_grupo = _normalize_name_for_match(evento_grupo)
    if projetos is None:
        projetos = _wq_all_dim_projetos(db)
        projetos = [p for p in projetos if p.data_evento is not None]
    
    best_match = None
    best_score = 0
    
    for p in projetos:
        p_year = p.data_evento.year if p.data_evento else None
        if p_year != ano:
            continue
        normalized_proj = _normalize_name_for_match(p.evento or "")
        
        grupo_words = set(normalized_grupo.split())
        proj_words = set(normalized_proj.split())
        if not grupo_words or not proj_words:
            continue
        common = grupo_words & proj_words
        score = len(common) / max(len(grupo_words), len(proj_words))
        
        if score > best_score:
            best_score = score
            best_match = p
    
    if best_match and best_score >= 0.5:
        logger.info(f"Matched evento_grupo '{evento_grupo}' ano={ano} -> projeto '{best_match.evento}' data_evento={best_match.data_evento} (score={best_score:.2f})")
        return best_match.data_evento
    
    adj_best_match = None
    adj_best_score = 0
    adj_year_diff = None
    for p in projetos:
        p_year = p.data_evento.year
        if p_year == ano:
            continue
        normalized_proj = _normalize_name_for_match(p.evento or "")
        grupo_words = set(normalized_grupo.split())
        proj_words = set(normalized_proj.split())
        if not grupo_words or not proj_words:
            continue
        common = grupo_words & proj_words
        score = len(common) / max(len(grupo_words), len(proj_words))
        year_distance = abs(p_year - ano)
        if score > adj_best_score or (score == adj_best_score and adj_year_diff is not None and year_distance < adj_year_diff):
            adj_best_score = score
            adj_best_match = p
            adj_year_diff = year_distance

    if adj_best_match and adj_best_score >= 0.5:
        try:
            adjusted_date = adj_best_match.data_evento.replace(year=ano)
        except ValueError:
            month = adj_best_match.data_evento.month
            day = 28 if adj_best_match.data_evento.month == 2 else adj_best_match.data_evento.day
            adjusted_date = date(ano, month, day)

        if sku_mapping_date and abs((adjusted_date - sku_mapping_date).days) > 60:
            logger.warning(
                f"Estimated data_evento ({adjusted_date}) for '{evento_grupo}' ano={ano} differs by "
                f"{abs((adjusted_date - sku_mapping_date).days)} days from sku_mappings date ({sku_mapping_date}). "
                f"Using sku_mappings date as it is more reliable."
            )
            return sku_mapping_date

        logger.info(f"Estimated data_evento for '{evento_grupo}' ano={ano} from year {adj_best_match.data_evento.year} event '{adj_best_match.evento}': {adjusted_date}")
        return adjusted_date

    if sku_mapping_date:
        logger.info(f"No dim_projeto match for '{evento_grupo}' ano={ano}, using sku_mappings date: {sku_mapping_date}")
        return sku_mapping_date

    logger.warning(f"Could not match evento_grupo '{evento_grupo}' ano={ano} to any dim_projeto (best_score={best_score:.2f})")
    return None


def _resolve_default_ano_for_grupo(db: Session, grupo_nome: str, fallback: int) -> int:
    """
    Resolve o ano-edição default de um evento agrupado quando o caller não
    informa `ano` explicitamente. Usa a MAIOR edição com SkuMapping ativo do
    grupo — não o ano civil corrente — porque um grupo pode já ter o
    carrinho do ano seguinte aberto (às vezes o ano corrente nem tem mais
    mapping ativo). Eventos não-agrupados já resolvem isso via
    `projeto.data_evento.year` e não precisam deste helper.
    """
    try:
        latest = (
            db.query(func.max(SkuMapping.ano))
            .filter(SkuMapping.evento_grupo == grupo_nome, SkuMapping.ativo == True)
            .scalar()
        )
        if latest:
            return int(latest)
    except Exception as _e:
        logger.warning(f"_resolve_default_ano_for_grupo('{grupo_nome}') falhou, usando fallback {fallback}: {_e}")
    return fallback


_curva_evento_cache = {}
_curva_evento_cache_timestamp = {}


@router.get("/curva-comparativa/{evento_id}")
def get_curva_comparativa_evento(
    evento_id: str,
    ano: int = Query(default=None, description="Ano base para comparacao"),
    force_refresh: bool = Query(default=False, description="Forçar atualização dos dados ignorando cache"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing_comparativo", "pode_visualizar")),
    response: Response = None
):
    import time

    cache_key = f"{evento_id}_{ano}"
    current_time = time.time()
    
    smart_curva_key = f"{ano}_{evento_id}_curva"
    if not force_refresh:
        def _swr_curva_refresh():
            from ...core.database import SessionLocal
            _db = SessionLocal()
            try:
                get_curva_comparativa_evento(evento_id=evento_id, ano=ano, force_refresh=True, db=_db, current_user=None)
            finally:
                _db.close()

        cached_curva, is_stale = curva_cache.get_or_revalidate(smart_curva_key, refresh_fn=_swr_curva_refresh)
        if cached_curva is not None:
            cached_data = cached_curva.get("data", []) if isinstance(cached_curva, dict) else []
            if cached_data:
                if response is not None:
                    response.headers["X-Data-Stale"] = "true" if is_stale else "false"
                return cached_curva
            else:
                logger.warning(f"Discarding empty cached curva for key={smart_curva_key}, will recalculate")
                curva_cache.invalidate(smart_curva_key)

    is_grouped = evento_id.startswith("grp_")

    if is_grouped:
        grupo_nome = evento_id.replace("grp_", "")
        if ano is None:
            ano = datetime.now().year
        ano_anterior = ano - 1

        all_mappings = _wq_sku_mappings_by_grupo(db, grupo_nome, [ano, ano_anterior])
    else:
        projeto = _wq_dim_projeto_by_id(db, int(evento_id))
        if not projeto:
            raise HTTPException(status_code=404, detail="Evento nao encontrado")

        sku = str(projeto.codigo) if projeto.codigo else None
        if not sku:
            return {"status": "success", "ano_atual": datetime.now().year, "ano_anterior": datetime.now().year - 1, "data": [], "evento_nome": str(projeto.evento or "")}

        if ano is None:
            ano = projeto.data_evento.year if projeto.data_evento else datetime.now().year
        ano_anterior = ano - 1

        mapping_list = _wq_sku_mappings_by_sku(db, sku)
        mapping = mapping_list[0] if mapping_list else None

        if mapping and mapping.evento_grupo:
            all_mappings = _wq_sku_mappings_by_grupo(db, mapping.evento_grupo, [ano, ano_anterior])
        else:
            all_mappings = _wq_sku_mappings_by_sku(db, sku)
            if not all_mappings:
                all_mappings = []

    mappings_atual = [m for m in all_mappings if m.ano == ano]
    mappings_anterior = [m for m in all_mappings if m.ano == ano_anterior]

    ids_ativo_atual = list(set([m.id_externo for m in mappings_atual if m.fonte == 'ATIVO']))
    ids_magento_atual = list(set([m.id_externo for m in mappings_atual if m.fonte == 'MAGENTO']))
    ids_ativo_anterior = list(set([m.id_externo for m in mappings_anterior if m.fonte == 'ATIVO']))
    ids_magento_anterior = list(set([m.id_externo for m in mappings_anterior if m.fonte == 'MAGENTO']))

    all_ids = ids_ativo_atual + ids_magento_atual + ids_ativo_anterior + ids_magento_anterior
    if not all_ids:
        return {"status": "success", "ano_atual": ano, "ano_anterior": ano_anterior, "data": [], "evento_nome": ""}

    grupo_nome_for_match = grupo_nome if is_grouped else str(projeto.evento or "")
    data_evento_atual = _find_data_evento(db, grupo_nome_for_match, ano)
    data_evento_anterior = _find_data_evento(db, grupo_nome_for_match, ano_anterior)

    if not data_evento_atual and not data_evento_anterior:
        logger.warning(f"No data_evento found for {grupo_nome_for_match}, falling back to month-based")
        return _curva_comparativa_mensal_fallback(
            ids_ativo_atual, ids_magento_atual, ids_ativo_anterior, ids_magento_anterior,
            ano, ano_anterior, evento_id, is_grouped, projeto if not is_grouped else None
        )

    if data_evento_atual and not data_evento_anterior:
        ref_day_month = (data_evento_atual.month, data_evento_atual.day)
        data_evento_anterior = date(ano_anterior, ref_day_month[0], min(ref_day_month[1], 28))
        logger.info(f"No data_evento for {ano_anterior}, estimated from {ano}: {data_evento_anterior}")
    elif data_evento_anterior and not data_evento_atual:
        ref_day_month = (data_evento_anterior.month, data_evento_anterior.day)
        data_evento_atual = date(ano, ref_day_month[0], min(ref_day_month[1], 28))
        logger.info(f"No data_evento for {ano}, estimated from {ano_anterior}: {data_evento_atual}")

    _cort_curva = _get_cortesia_magento_ids(db)
    _mag_cort_atual = (set(ids_magento_atual) & _cort_curva) if _cort_curva and ids_magento_atual else None
    _mag_cort_anterior = (set(ids_magento_anterior) & _cort_curva) if _cort_curva and ids_magento_anterior else None

    is_warmup = _is_warmup_thread()
    if is_warmup:
        try:
            dados_ativo_atual = _fetch_daily_sales_ativo_by_ids(ids_ativo_atual)
        except Exception as e:
            logger.error(f"Curva comparativa daily Ativo atual error: {e}")
            dados_ativo_atual = []
        try:
            dados_magento_atual = _fetch_daily_sales_magento_by_ids(ids_magento_atual, cortesia_magento_ids=_mag_cort_atual if _mag_cort_atual else None)
        except Exception as e:
            logger.error(f"Curva comparativa daily Magento atual error: {e}")
            dados_magento_atual = []
        try:
            dados_ativo_anterior = _fetch_daily_sales_ativo_by_ids(ids_ativo_anterior)
        except Exception as e:
            logger.error(f"Curva comparativa daily Ativo anterior error: {e}")
            dados_ativo_anterior = []
        try:
            dados_magento_anterior = _fetch_daily_sales_magento_by_ids(ids_magento_anterior, cortesia_magento_ids=_mag_cort_anterior if _mag_cort_anterior else None)
        except Exception as e:
            logger.error(f"Curva comparativa daily Magento anterior error: {e}")
            dados_magento_anterior = []
    else:
        future_ativo_atual = _rolling_avg_executor.submit(_fetch_daily_sales_ativo_by_ids, ids_ativo_atual)
        future_magento_atual = _rolling_avg_executor.submit(_fetch_daily_sales_magento_by_ids, ids_magento_atual, cortesia_magento_ids=_mag_cort_atual if _mag_cort_atual else None)
        future_ativo_anterior = _rolling_avg_executor.submit(_fetch_daily_sales_ativo_by_ids, ids_ativo_anterior)
        future_magento_anterior = _rolling_avg_executor.submit(_fetch_daily_sales_magento_by_ids, ids_magento_anterior, cortesia_magento_ids=_mag_cort_anterior if _mag_cort_anterior else None)

        try:
            dados_ativo_atual = future_ativo_atual.result(timeout=60)
        except Exception as e:
            logger.error(f"Curva comparativa daily Ativo atual timeout: {e}")
            dados_ativo_atual = []
        try:
            dados_magento_atual = future_magento_atual.result(timeout=60)
        except Exception as e:
            logger.error(f"Curva comparativa daily Magento atual timeout: {e}")
            dados_magento_atual = []
        try:
            dados_ativo_anterior = future_ativo_anterior.result(timeout=60)
        except Exception as e:
            logger.error(f"Curva comparativa daily Ativo anterior timeout: {e}")
            dados_ativo_anterior = []
        try:
            dados_magento_anterior = future_magento_anterior.result(timeout=60)
        except Exception as e:
            logger.error(f"Curva comparativa daily Magento anterior timeout: {e}")
            dados_magento_anterior = []

    BUCKET_SIZE = 7

    def _build_daily_map(dados_list: list, data_evento_ref: Optional[date]) -> dict:
        daily = {}
        if not data_evento_ref:
            return daily
        for row in dados_list:
            try:
                dia = date.fromisoformat(row["dia"])
            except (ValueError, KeyError):
                continue
            dias_antes = (data_evento_ref - dia).days
            if dias_antes not in daily:
                daily[dias_antes] = {"qtd": 0, "receita": 0.0}
            daily[dias_antes]["qtd"] += row["qtd"]
            daily[dias_antes]["receita"] += row["receita"]
        return daily

    dias_enc_atual = 2
    if data_evento_atual:
        try:
            proj_atual = db.query(DimProjeto).filter(DimProjeto.data_evento == data_evento_atual).first()
            if proj_atual:
                dias_enc_atual = get_dias_encerramento(db, projeto_id=proj_atual.id)
        except Exception:
            pass
    dias_enc_anterior = 2
    if data_evento_anterior:
        try:
            proj_anterior = db.query(DimProjeto).filter(DimProjeto.data_evento == data_evento_anterior).first()
            if proj_anterior:
                dias_enc_anterior = get_dias_encerramento(db, projeto_id=proj_anterior.id)
        except Exception:
            pass
    data_insc_atual = data_evento_atual - timedelta(days=dias_enc_atual) if data_evento_atual else None
    data_insc_anterior = data_evento_anterior - timedelta(days=dias_enc_anterior) if data_evento_anterior else None

    daily_atual = _build_daily_map(dados_ativo_atual + dados_magento_atual, data_insc_atual)
    daily_anterior = _build_daily_map(dados_ativo_anterior + dados_magento_anterior, data_insc_anterior)

    all_dias = set(daily_atual.keys()) | set(daily_anterior.keys())
    if not all_dias:
        max_dias = 180
        min_dias = 0
    else:
        max_dias = max(all_dias)
        min_dias = min(all_dias)

    def _bucket_key_for(d: int) -> int:
        if d >= 0:
            return (d // BUCKET_SIZE) * BUCKET_SIZE
        return -((abs(d) // BUCKET_SIZE + 1) * BUCKET_SIZE)

    max_bucket = _bucket_key_for(max_dias)
    if max_bucket < max_dias:
        max_bucket += BUCKET_SIZE
    min_bucket = _bucket_key_for(min_dias) if min_dias < 0 else 0

    buckets = {}
    b = min_bucket
    while b <= max_bucket:
        if b < 0:
            label = f"D+{abs(b)}"
        elif b == 0:
            label = "D-0"
        else:
            label = f"D-{b}"
        buckets[b] = {
            "dias_antes": b,
            "label": label,
            f"vendas_{ano}": 0,
            f"vendas_{ano_anterior}": 0,
            f"receita_{ano}": 0.0,
            f"receita_{ano_anterior}": 0.0,
        }
        b += BUCKET_SIZE

    for dias, vals in daily_atual.items():
        bk = _bucket_key_for(dias)
        if bk in buckets:
            buckets[bk][f"vendas_{ano}"] += vals["qtd"]
            buckets[bk][f"receita_{ano}"] += vals["receita"]

    for dias, vals in daily_anterior.items():
        bk = _bucket_key_for(dias)
        if bk in buckets:
            buckets[bk][f"vendas_{ano_anterior}"] += vals["qtd"]
            buckets[bk][f"receita_{ano_anterior}"] += vals["receita"]

    hoje = today_brazil()
    dias_ate_evento_atual = (data_evento_atual - hoje).days if data_evento_atual else 0

    total_vendas_atual = sum(v["qtd"] for v in daily_atual.values())
    total_receita_atual = sum(v["receita"] for v in daily_atual.values())

    dias_com_vendas = sorted([d for d in daily_atual.keys() if daily_atual[d]["qtd"] > 0])
    if dias_com_vendas and dias_ate_evento_atual > 0:
        dias_recentes = [d for d in dias_com_vendas if d >= dias_ate_evento_atual and d <= dias_ate_evento_atual + 30]
        if not dias_recentes:
            dias_recentes = sorted(dias_com_vendas)[:30]
        
        window = min(14, len(dias_recentes))
        if window > 0:
            vendas_window = sum(daily_atual[d]["qtd"] for d in dias_recentes[:window])
            receita_window = sum(daily_atual[d]["receita"] for d in dias_recentes[:window])
            media_diaria_vendas = vendas_window / window
            media_diaria_receita = receita_window / window
        else:
            dias_total = len(dias_com_vendas)
            media_diaria_vendas = total_vendas_atual / max(1, dias_total)
            media_diaria_receita = total_receita_atual / max(1, dias_total)
    else:
        media_diaria_vendas = 0
        media_diaria_receita = 0.0

    sorted_keys = sorted(buckets.keys(), reverse=True)
    data = []
    acum_atual = 0
    acum_anterior = 0
    acum_receita_atual = 0.0
    acum_receita_anterior = 0.0
    for bk in sorted_keys:
        entry = buckets[bk]
        acum_atual += entry[f"vendas_{ano}"]
        acum_anterior += entry[f"vendas_{ano_anterior}"]
        acum_receita_atual += entry[f"receita_{ano}"]
        acum_receita_anterior += entry[f"receita_{ano_anterior}"]
        entry[f"receita_{ano}"] = round(entry[f"receita_{ano}"], 2)
        entry[f"receita_{ano_anterior}"] = round(entry[f"receita_{ano_anterior}"], 2)
        entry[f"acumulado_{ano}"] = acum_atual
        entry[f"acumulado_{ano_anterior}"] = acum_anterior
        entry[f"acumulado_receita_{ano}"] = round(acum_receita_atual, 2)
        entry[f"acumulado_receita_{ano_anterior}"] = round(acum_receita_anterior, 2)
        entry["is_projecao"] = False
        data.append(entry)

    if dias_ate_evento_atual > 0 and media_diaria_vendas > 0 and ano == datetime.now().year:
        last_real_idx = None
        for i, entry in enumerate(data):
            if entry[f"vendas_{ano}"] > 0:
                last_real_idx = i

        if last_real_idx is not None:
            acum_proj_vendas = data[last_real_idx][f"acumulado_{ano}"]
            acum_proj_receita = data[last_real_idx][f"acumulado_receita_{ano}"]

            data[last_real_idx][f"projecao_acumulado_{ano}"] = acum_proj_vendas
            data[last_real_idx][f"projecao_acumulado_receita_{ano}"] = acum_proj_receita

            for i in range(last_real_idx + 1, len(data)):
                proj_vendas_bucket = media_diaria_vendas * BUCKET_SIZE
                proj_receita_bucket = media_diaria_receita * BUCKET_SIZE
                acum_proj_vendas += proj_vendas_bucket
                acum_proj_receita += proj_receita_bucket
                data[i][f"projecao_acumulado_{ano}"] = round(acum_proj_vendas)
                data[i][f"projecao_acumulado_receita_{ano}"] = round(acum_proj_receita, 2)
                data[i]["is_projecao"] = True

    total_vendas_anterior = sum(entry[f"vendas_{ano_anterior}"] for entry in data)
    total_receita_anterior = sum(entry[f"receita_{ano_anterior}"] for entry in data)
    total_vendas_atual = sum(entry[f"vendas_{ano}"] for entry in data)
    total_receita_atual_sum = sum(entry[f"receita_{ano}"] for entry in data)

    for entry in data:
        acum_v = entry.get(f"acumulado_{ano}", 0)
        acum_v_ant = entry.get(f"acumulado_{ano_anterior}", 0)
        acum_r = entry.get(f"acumulado_receita_{ano}", 0)
        acum_r_ant = entry.get(f"acumulado_receita_{ano_anterior}", 0)
        entry[f"pct_meta_vendas_{ano}"] = round((acum_v / total_vendas_anterior * 100), 1) if total_vendas_anterior > 0 else 0
        entry[f"pct_meta_vendas_{ano_anterior}"] = round((acum_v_ant / total_vendas_anterior * 100), 1) if total_vendas_anterior > 0 else 0
        entry[f"pct_meta_receita_{ano}"] = round((acum_r / total_receita_anterior * 100), 1) if total_receita_anterior > 0 else 0
        entry[f"pct_meta_receita_{ano_anterior}"] = round((acum_r_ant / total_receita_anterior * 100), 1) if total_receita_anterior > 0 else 0

        proj_v = entry.get(f"projecao_acumulado_{ano}")
        proj_r = entry.get(f"projecao_acumulado_receita_{ano}")
        if proj_v is not None and total_vendas_anterior > 0:
            entry[f"pct_meta_projecao_vendas_{ano}"] = round((proj_v / total_vendas_anterior * 100), 1)
        if proj_r is not None and total_receita_anterior > 0:
            entry[f"pct_meta_projecao_receita_{ano}"] = round((proj_r / total_receita_anterior * 100), 1)

    ultimo_acum_vendas_atual = 0
    ultimo_acum_receita_atual = 0.0
    for entry in data:
        if not entry.get("is_projecao", False) and entry.get(f"acumulado_{ano}", 0) > 0:
            ultimo_acum_vendas_atual = entry[f"acumulado_{ano}"]
            ultimo_acum_receita_atual = entry[f"acumulado_receita_{ano}"]

    pct_atingido_vendas = round((ultimo_acum_vendas_atual / total_vendas_anterior * 100), 1) if total_vendas_anterior > 0 else 0
    pct_atingido_receita = round((ultimo_acum_receita_atual / total_receita_anterior * 100), 1) if total_receita_anterior > 0 else 0

    ultimo_acum_vendas_anterior_mesmo_d = 0
    ultimo_acum_receita_anterior_mesmo_d = 0.0
    if dias_ate_evento_atual > 0 and daily_anterior:
        for d_ant, vals in daily_anterior.items():
            if d_ant >= dias_ate_evento_atual:
                ultimo_acum_vendas_anterior_mesmo_d += vals["qtd"]
                ultimo_acum_receita_anterior_mesmo_d += vals["receita"]

    pct_anterior_vendas_mesmo_d = round((ultimo_acum_vendas_anterior_mesmo_d / total_vendas_anterior * 100), 1) if total_vendas_anterior > 0 else 0
    pct_anterior_receita_mesmo_d = round((ultimo_acum_receita_anterior_mesmo_d / total_receita_anterior * 100), 1) if total_receita_anterior > 0 else 0

    meta_orcada = 0
    try:
        if is_grouped:
            skus_atual = list(set([m.sku for m in mappings_atual if m.sku]))
            projetos_atual = db.query(DimProjeto).filter(DimProjeto.codigo.in_(skus_atual)).all() if skus_atual else []
        else:
            projetos_atual = [projeto] if projeto else []
        meta_orcada = get_meta_orcada_projetos(db, projetos_atual)
    except Exception as e:
        logger.warning(f"Could not fetch meta_orcada for curva comparativa: {e}")

    ritmo_diario_necessario_vendas = 0.0
    ritmo_diario_necessario_receita = 0.0
    meta_referencia = meta_orcada if meta_orcada > 0 else total_vendas_anterior
    if dias_ate_evento_atual > 0 and meta_referencia > 0:
        faltam_vendas = max(0, meta_referencia - ultimo_acum_vendas_atual)
        ritmo_diario_necessario_vendas = round(faltam_vendas / dias_ate_evento_atual, 1)
    if dias_ate_evento_atual > 0 and total_receita_anterior > 0:
        faltam_receita = max(0, total_receita_anterior - ultimo_acum_receita_atual)
        ritmo_diario_necessario_receita = round(faltam_receita / dias_ate_evento_atual, 2)

    variacao_mesmo_d_vendas = round(((ultimo_acum_vendas_atual - ultimo_acum_vendas_anterior_mesmo_d) / ultimo_acum_vendas_anterior_mesmo_d * 100), 1) if ultimo_acum_vendas_anterior_mesmo_d > 0 else 0
    variacao_mesmo_d_receita = round(((ultimo_acum_receita_atual - ultimo_acum_receita_anterior_mesmo_d) / ultimo_acum_receita_anterior_mesmo_d * 100), 1) if ultimo_acum_receita_anterior_mesmo_d > 0 else 0

    evento_nome = ""
    if is_grouped:
        evento_nome = evento_id.replace("grp_", "")
    else:
        evento_nome = str(projeto.evento or "")

    result = {
        "status": "success",
        "modo": "dias_antes_evento",
        "ano_atual": ano,
        "ano_anterior": ano_anterior,
        "data_evento_atual": str(data_evento_atual) if data_evento_atual else None,
        "data_evento_anterior": str(data_evento_anterior) if data_evento_anterior else None,
        "data": data,
        "evento_nome": evento_nome,
        "media_diaria_vendas": round(media_diaria_vendas, 2),
        "media_diaria_receita": round(media_diaria_receita, 2),
        "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(),
        "meta": {
            "total_vendas_anterior": total_vendas_anterior,
            "total_receita_anterior": round(total_receita_anterior, 2),
            "total_vendas_atual": total_vendas_atual,
            "total_receita_atual": round(total_receita_atual_sum, 2),
            "pct_atingido_vendas": pct_atingido_vendas,
            "pct_atingido_receita": pct_atingido_receita,
            "diff_pp_vendas": round(pct_atingido_vendas - pct_anterior_vendas_mesmo_d, 1),
            "diff_pp_receita": round(pct_atingido_receita - pct_anterior_receita_mesmo_d, 1),
            "pct_anterior_vendas_mesmo_d": pct_anterior_vendas_mesmo_d,
            "pct_anterior_receita_mesmo_d": pct_anterior_receita_mesmo_d,
            "ultimo_acum_vendas_anterior_mesmo_d": ultimo_acum_vendas_anterior_mesmo_d,
            "ultimo_acum_receita_anterior_mesmo_d": round(ultimo_acum_receita_anterior_mesmo_d, 2),
            "meta_orcada": meta_orcada,
            "dias_ate_evento": dias_ate_evento_atual,
            "ritmo_diario_necessario_vendas": ritmo_diario_necessario_vendas,
            "ritmo_diario_necessario_receita": ritmo_diario_necessario_receita,
            "variacao_mesmo_d_vendas": variacao_mesmo_d_vendas,
            "variacao_mesmo_d_receita": variacao_mesmo_d_receita,
        }
    }

    _curva_evento_cache[cache_key] = result
    _curva_evento_cache_timestamp[cache_key] = current_time
    curva_cache.set(smart_curva_key, result)
    return result


@router.get("/eventos/{evento_id}/insights")
def get_evento_insights(
    evento_id: str,
    ano: int = Query(default=None, description="Ano base para comparacao"),
    force_refresh: bool = Query(default=False, description="Forçar atualização dos dados ignorando cache"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing_dashboard", "pode_visualizar")),
    response: Response = None
):
    smart_insights_key = f"{ano}_{evento_id}_insights"
    if not force_refresh:
        def _swr_insights_refresh():
            from ...core.database import SessionLocal
            _db = SessionLocal()
            try:
                get_evento_insights(evento_id=evento_id, ano=ano, force_refresh=True, db=_db, current_user=None)
            finally:
                _db.close()

        cached, is_stale = curva_cache.get_or_revalidate(smart_insights_key, refresh_fn=_swr_insights_refresh)
        if cached is not None:
            if response is not None:
                response.headers["X-Data-Stale"] = "true" if is_stale else "false"
            return cached

    is_grouped = evento_id.startswith("grp_")

    if is_grouped:
        grupo_nome = evento_id.replace("grp_", "")
        if ano is None:
            ano = _resolve_default_ano_for_grupo(db, grupo_nome, datetime.now().year)
        ano_anterior = ano - 1

        all_mappings = _wq_sku_mappings_by_grupo(db, grupo_nome, [ano, ano_anterior])
    else:
        projeto = _wq_dim_projeto_by_id(db, int(evento_id))
        if not projeto:
            raise HTTPException(status_code=404, detail="Evento nao encontrado")

        sku = str(projeto.codigo) if projeto.codigo else None
        if not sku:
            return {"status": "success", "ano_atual": datetime.now().year, "ano_anterior": datetime.now().year - 1, "evento_nome": str(projeto.evento or ""), "indice_aceleracao": [], "pace_diario": [], "projecao_fechamento": {}, "janela_acao": {}, "ticket_medio": [], "mix_categorias": {"atual": [], "anterior": []}, "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat()}

        if ano is None:
            ano = projeto.data_evento.year if projeto.data_evento else datetime.now().year
        ano_anterior = ano - 1

        mapping_list = _wq_sku_mappings_by_sku(db, sku)
        mapping = mapping_list[0] if mapping_list else None

        if mapping and mapping.evento_grupo:
            all_mappings = _wq_sku_mappings_by_grupo(db, mapping.evento_grupo, [ano, ano_anterior])
        else:
            all_mappings = _wq_sku_mappings_by_sku(db, sku)
            if not all_mappings:
                all_mappings = []

    mappings_atual = [m for m in all_mappings if m.ano == ano]
    mappings_anterior = [m for m in all_mappings if m.ano == ano_anterior]

    ids_ativo_atual = list(set([m.id_externo for m in mappings_atual if m.fonte == 'ATIVO']))
    ids_magento_atual = list(set([m.id_externo for m in mappings_atual if m.fonte == 'MAGENTO']))
    ids_ativo_anterior = list(set([m.id_externo for m in mappings_anterior if m.fonte == 'ATIVO']))
    ids_magento_anterior = list(set([m.id_externo for m in mappings_anterior if m.fonte == 'MAGENTO']))

    all_ids = ids_ativo_atual + ids_magento_atual + ids_ativo_anterior + ids_magento_anterior
    if not all_ids:
        return {"status": "success", "ano_atual": ano, "ano_anterior": ano_anterior, "evento_nome": "", "indice_aceleracao": [], "pace_diario": [], "projecao_fechamento": {}, "janela_acao": {}, "ticket_medio": [], "mix_categorias": {"atual": [], "anterior": []}, "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat()}

    grupo_nome_for_match = grupo_nome if is_grouped else str(projeto.evento or "")
    data_evento_atual = _find_data_evento(db, grupo_nome_for_match, ano)
    data_evento_anterior = _find_data_evento(db, grupo_nome_for_match, ano_anterior)

    if data_evento_atual and not data_evento_anterior:
        ref_day_month = (data_evento_atual.month, data_evento_atual.day)
        data_evento_anterior = date(ano_anterior, ref_day_month[0], min(ref_day_month[1], 28))
    elif data_evento_anterior and not data_evento_atual:
        ref_day_month = (data_evento_anterior.month, data_evento_anterior.day)
        data_evento_atual = date(ano, ref_day_month[0], min(ref_day_month[1], 28))

    _cort_insights = _get_cortesia_magento_ids(db)
    _mag_cort_atual_ins = (set(ids_magento_atual) & _cort_insights) if _cort_insights and ids_magento_atual else None
    _mag_cort_anterior_ins = (set(ids_magento_anterior) & _cort_insights) if _cort_insights and ids_magento_anterior else None

    is_warmup = _is_warmup_thread()
    if is_warmup:
        try:
            dados_ativo_atual = _fetch_daily_sales_ativo_by_ids(ids_ativo_atual)
        except Exception as e:
            logger.error(f"Insights daily Ativo atual error: {e}")
            dados_ativo_atual = []
        try:
            dados_magento_atual = _fetch_daily_sales_magento_by_ids(ids_magento_atual, cortesia_magento_ids=_mag_cort_atual_ins if _mag_cort_atual_ins else None)
        except Exception as e:
            logger.error(f"Insights daily Magento atual error: {e}")
            dados_magento_atual = []
        try:
            dados_ativo_anterior = _fetch_daily_sales_ativo_by_ids(ids_ativo_anterior)
        except Exception as e:
            logger.error(f"Insights daily Ativo anterior error: {e}")
            dados_ativo_anterior = []
        try:
            dados_magento_anterior = _fetch_daily_sales_magento_by_ids(ids_magento_anterior, cortesia_magento_ids=_mag_cort_anterior_ins if _mag_cort_anterior_ins else None)
        except Exception as e:
            logger.error(f"Insights daily Magento anterior error: {e}")
            dados_magento_anterior = []
        try:
            cat_ativo_atual = _fetch_category_sales_ativo_by_ids(ids_ativo_atual)
        except Exception:
            cat_ativo_atual = []
        try:
            cat_magento_atual = _fetch_category_sales_magento_by_ids(ids_magento_atual)
        except Exception:
            cat_magento_atual = []
        try:
            cat_ativo_anterior = _fetch_category_sales_ativo_by_ids(ids_ativo_anterior)
        except Exception:
            cat_ativo_anterior = []
        try:
            cat_magento_anterior = _fetch_category_sales_magento_by_ids(ids_magento_anterior)
        except Exception:
            cat_magento_anterior = []
    else:
        future_ativo_atual = _rolling_avg_executor.submit(_fetch_daily_sales_ativo_by_ids, ids_ativo_atual)
        future_magento_atual = _rolling_avg_executor.submit(_fetch_daily_sales_magento_by_ids, ids_magento_atual, cortesia_magento_ids=_mag_cort_atual_ins if _mag_cort_atual_ins else None)
        future_ativo_anterior = _rolling_avg_executor.submit(_fetch_daily_sales_ativo_by_ids, ids_ativo_anterior)
        future_magento_anterior = _rolling_avg_executor.submit(_fetch_daily_sales_magento_by_ids, ids_magento_anterior, cortesia_magento_ids=_mag_cort_anterior_ins if _mag_cort_anterior_ins else None)
        future_cat_ativo_atual = _rolling_avg_executor.submit(_fetch_category_sales_ativo_by_ids, ids_ativo_atual)
        future_cat_magento_atual = _rolling_avg_executor.submit(_fetch_category_sales_magento_by_ids, ids_magento_atual)
        future_cat_ativo_anterior = _rolling_avg_executor.submit(_fetch_category_sales_ativo_by_ids, ids_ativo_anterior)
        future_cat_magento_anterior = _rolling_avg_executor.submit(_fetch_category_sales_magento_by_ids, ids_magento_anterior)

        try:
            dados_ativo_atual = future_ativo_atual.result(timeout=60)
        except Exception as e:
            logger.error(f"Insights daily Ativo atual timeout: {e}")
            dados_ativo_atual = []
        try:
            dados_magento_atual = future_magento_atual.result(timeout=60)
        except Exception as e:
            logger.error(f"Insights daily Magento atual timeout: {e}")
            dados_magento_atual = []
        try:
            dados_ativo_anterior = future_ativo_anterior.result(timeout=60)
        except Exception as e:
            logger.error(f"Insights daily Ativo anterior timeout: {e}")
            dados_ativo_anterior = []
        try:
            dados_magento_anterior = future_magento_anterior.result(timeout=60)
        except Exception as e:
            logger.error(f"Insights daily Magento anterior timeout: {e}")
            dados_magento_anterior = []
        try:
            cat_ativo_atual = future_cat_ativo_atual.result(timeout=60)
        except Exception:
            cat_ativo_atual = []
        try:
            cat_magento_atual = future_cat_magento_atual.result(timeout=60)
        except Exception:
            cat_magento_atual = []
        try:
            cat_ativo_anterior = future_cat_ativo_anterior.result(timeout=60)
        except Exception:
            cat_ativo_anterior = []
        try:
            cat_magento_anterior = future_cat_magento_anterior.result(timeout=60)
        except Exception:
            cat_magento_anterior = []

    BUCKET_SIZE = 7

    def _build_daily_map_insights(dados_list: list, data_evento_ref: Optional[date]) -> dict:
        daily = {}
        if not data_evento_ref:
            return daily
        for row in dados_list:
            try:
                dia = date.fromisoformat(row["dia"])
            except (ValueError, KeyError):
                continue
            dias_antes = (data_evento_ref - dia).days
            if dias_antes not in daily:
                daily[dias_antes] = {"qtd": 0, "receita": 0.0}
            daily[dias_antes]["qtd"] += row["qtd"]
            daily[dias_antes]["receita"] += row["receita"]
        return daily

    dias_enc_atual_ins = 2
    if data_evento_atual:
        try:
            proj_atual_ins = db.query(DimProjeto).filter(DimProjeto.data_evento == data_evento_atual).first()
            if proj_atual_ins:
                dias_enc_atual_ins = get_dias_encerramento(db, projeto_id=proj_atual_ins.id)
        except Exception:
            pass
    dias_enc_anterior_ins = 2
    if data_evento_anterior:
        try:
            proj_anterior_ins = db.query(DimProjeto).filter(DimProjeto.data_evento == data_evento_anterior).first()
            if proj_anterior_ins:
                dias_enc_anterior_ins = get_dias_encerramento(db, projeto_id=proj_anterior_ins.id)
        except Exception:
            pass
    data_insc_atual_ins = data_evento_atual - timedelta(days=dias_enc_atual_ins) if data_evento_atual else None
    data_insc_anterior_ins = data_evento_anterior - timedelta(days=dias_enc_anterior_ins) if data_evento_anterior else None

    daily_atual = _build_daily_map_insights(dados_ativo_atual + dados_magento_atual, data_insc_atual_ins)
    daily_anterior = _build_daily_map_insights(dados_ativo_anterior + dados_magento_anterior, data_insc_anterior_ins)

    all_dias = set(daily_atual.keys()) | set(daily_anterior.keys())
    if not all_dias:
        max_dias = 180
    else:
        max_dias = max(all_dias)

    def _bucket_key(d: int) -> int:
        if d >= 0:
            return (d // BUCKET_SIZE) * BUCKET_SIZE
        return -((abs(d) // BUCKET_SIZE + 1) * BUCKET_SIZE)

    max_bucket = _bucket_key(max_dias)
    if max_bucket < max_dias:
        max_bucket += BUCKET_SIZE

    bucket_keys_set = set()
    b = 0
    while b <= max_bucket:
        bucket_keys_set.add(b)
        b += BUCKET_SIZE

    sorted_bucket_keys = sorted(bucket_keys_set, reverse=True)

    bucket_data_atual = {}
    bucket_data_anterior = {}
    for bk in sorted_bucket_keys:
        bucket_data_atual[bk] = {"qtd": 0, "receita": 0.0}
        bucket_data_anterior[bk] = {"qtd": 0, "receita": 0.0}

    for dias, vals in daily_atual.items():
        bk = _bucket_key(dias)
        if bk in bucket_data_atual:
            bucket_data_atual[bk]["qtd"] += vals["qtd"]
            bucket_data_atual[bk]["receita"] += vals["receita"]

    for dias, vals in daily_anterior.items():
        bk = _bucket_key(dias)
        if bk in bucket_data_anterior:
            bucket_data_anterior[bk]["qtd"] += vals["qtd"]
            bucket_data_anterior[bk]["receita"] += vals["receita"]

    def _calc_rolling_avg(daily_map: dict, d_minus: int, window: int) -> float:
        total = 0
        for d in range(d_minus, d_minus + window):
            if d in daily_map:
                total += daily_map[d]["qtd"]
        return total / window

    hoje = today_brazil()
    dias_ate_evento_atual = (data_evento_atual - hoje).days if data_evento_atual else 0
    d_minus_atual = max(0, dias_ate_evento_atual)

    indice_aceleracao = []
    max_d_daily = max_dias if max_dias > 0 else 180
    for d in range(max_d_daily, -1, -1):
        label = f"D-{d}"

        atual_alcancado = d >= d_minus_atual
        if atual_alcancado:
            ma7_atual = _calc_rolling_avg(daily_atual, d, 7)
            ma30_atual = _calc_rolling_avg(daily_atual, d, 30)
            ia_atual = round(ma7_atual / ma30_atual, 2) if (ma7_atual >= 1 and ma30_atual >= 1) else None
        else:
            ia_atual = None

        ma7_ant = _calc_rolling_avg(daily_anterior, d, 7)
        ma30_ant = _calc_rolling_avg(daily_anterior, d, 30)
        ia_ant = round(ma7_ant / ma30_ant, 2) if (ma7_ant >= 1 and ma30_ant >= 1) else None
        indice_aceleracao.append({"d_minus": d, "label": label, "ia_atual": ia_atual, "ia_anterior": ia_ant})

    pace_diario = []
    for bk in sorted_bucket_keys:
        label = f"D-{bk}" if bk >= 0 else f"D+{abs(bk)}"
        atual_alcancado = bk >= d_minus_atual
        pace_at = round(bucket_data_atual[bk]["qtd"] / BUCKET_SIZE, 2) if (BUCKET_SIZE > 0 and atual_alcancado) else None
        pace_ant = round(bucket_data_anterior[bk]["qtd"] / BUCKET_SIZE, 2) if BUCKET_SIZE > 0 else None
        pace_diario.append({"d_minus": bk, "label": label, "pace_atual": pace_at, "pace_anterior": pace_ant})

    ticket_medio = []
    acum_q_at = 0
    acum_r_at = 0.0
    acum_q_ant = 0
    acum_r_ant = 0.0
    for d in range(max_d_daily, -1, -1):
        label = f"D-{d}"
        atual_alcancado = d >= d_minus_atual
        if d in daily_anterior:
            acum_q_ant += daily_anterior[d]["qtd"]
            acum_r_ant += daily_anterior[d]["receita"]
        if atual_alcancado and d in daily_atual:
            acum_q_at += daily_atual[d]["qtd"]
            acum_r_at += daily_atual[d]["receita"]
        ticket_at = round(acum_r_at / acum_q_at, 2) if (acum_q_at > 0 and atual_alcancado) else None
        ticket_ant = round(acum_r_ant / acum_q_ant, 2) if acum_q_ant > 0 else None
        ticket_medio.append({"d_minus": d, "label": label, "ticket_atual": ticket_at, "ticket_anterior": ticket_ant})

    total_vendas_atual = sum(v["qtd"] for v in daily_atual.values())
    total_receita_atual = sum(v["receita"] for v in daily_atual.values())
    total_vendas_anterior = sum(v["qtd"] for v in daily_anterior.values())
    total_receita_anterior = sum(v["receita"] for v in daily_anterior.values())

    dias_ate_evento = dias_ate_evento_atual

    if dias_ate_evento > 0:
        total_qtd_14 = 0
        total_rec_14 = 0.0
        for dd in range(d_minus_atual, d_minus_atual + 14):
            if dd in daily_atual:
                total_qtd_14 += daily_atual[dd]["qtd"]
                total_rec_14 += daily_atual[dd]["receita"]
        media_diaria_14d = total_qtd_14 / 14
        media_receita_14d = total_rec_14 / 14
    else:
        media_diaria_14d = 0
        media_receita_14d = 0.0

    projecao_inscricoes = round(total_vendas_atual + media_diaria_14d * max(0, dias_ate_evento))
    projecao_receita = round(total_receita_atual + media_receita_14d * max(0, dias_ate_evento), 2)
    pct_vs_anterior = round(projecao_inscricoes / total_vendas_anterior * 100, 1) if total_vendas_anterior > 0 else 0.0

    projecao_fechamento = {
        "projecao_inscricoes": projecao_inscricoes,
        "projecao_receita": projecao_receita,
        "total_anterior": total_vendas_anterior,
        "receita_anterior": round(total_receita_anterior, 2),
        "pct_vs_anterior": pct_vs_anterior,
        "media_diaria_atual": round(media_diaria_14d, 2),
        "dias_restantes": max(0, dias_ate_evento)
    }

    dentro_d40 = 0 < dias_ate_evento <= 40
    meta_total = total_vendas_anterior if total_vendas_anterior > 0 else 1
    pct_atingido = round(total_vendas_atual / meta_total * 100, 1)
    deficit_superavit = total_vendas_atual - meta_total
    pace_necessario = round((meta_total - total_vendas_atual) / max(1, dias_ate_evento), 2) if dias_ate_evento > 0 else 0
    pace_atual_val = round(media_diaria_14d, 2)

    if total_vendas_atual >= meta_total:
        status_janela = "Acima do esperado"
    elif pace_atual_val >= pace_necessario and pace_necessario > 0:
        status_janela = "Em ritmo"
    else:
        status_janela = "Ação necessária"

    janela_acao = {
        "dias_ate_evento": max(0, dias_ate_evento),
        "dentro_d40": dentro_d40,
        "vendas_acumuladas": total_vendas_atual,
        "meta_total": meta_total,
        "pct_atingido": pct_atingido,
        "pace_necessario": pace_necessario,
        "pace_atual": pace_atual_val,
        "status": status_janela,
        "deficit_superavit": deficit_superavit
    }

    def _merge_categories(cat_list_a: list, cat_list_b: list) -> list:
        merged = {}
        for item in cat_list_a + cat_list_b:
            cat = item["categoria"]
            merged[cat] = merged.get(cat, 0) + item["qtd"]
        total = sum(merged.values())
        result = []
        for cat, qtd in sorted(merged.items(), key=lambda x: x[1], reverse=True):
            pct = round(qtd / total * 100, 1) if total > 0 else 0.0
            result.append({"categoria": cat, "qtd": qtd, "pct": pct})
        return result

    mix_atual = _merge_categories(cat_ativo_atual, cat_magento_atual)
    mix_anterior = _merge_categories(cat_ativo_anterior, cat_magento_anterior)

    evento_nome = ""
    if is_grouped:
        evento_nome = evento_id.replace("grp_", "")
    else:
        evento_nome = str(projeto.evento or "")

    result = {
        "status": "success",
        "ano_atual": ano,
        "ano_anterior": ano_anterior,
        "evento_nome": evento_nome,
        "data_evento_atual": str(data_evento_atual) if data_evento_atual else None,
        "data_evento_anterior": str(data_evento_anterior) if data_evento_anterior else None,
        "indice_aceleracao": indice_aceleracao,
        "pace_diario": pace_diario,
        "projecao_fechamento": projecao_fechamento,
        "janela_acao": janela_acao,
        "ticket_medio": ticket_medio,
        "mix_categorias": {
            "atual": mix_atual,
            "anterior": mix_anterior
        },
        "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat()
    }

    curva_cache.set(smart_insights_key, result)
    return result


def _curva_comparativa_mensal_fallback(
    ids_ativo_atual, ids_magento_atual, ids_ativo_anterior, ids_magento_anterior,
    ano, ano_anterior, evento_id, is_grouped, projeto=None
):
    future_ativo_atual = _rolling_avg_executor.submit(_fetch_monthly_sales_ativo_by_ids, ids_ativo_atual)
    future_magento_atual = _rolling_avg_executor.submit(_fetch_monthly_sales_magento_by_ids, ids_magento_atual)
    future_ativo_anterior = _rolling_avg_executor.submit(_fetch_monthly_sales_ativo_by_ids, ids_ativo_anterior)
    future_magento_anterior = _rolling_avg_executor.submit(_fetch_monthly_sales_magento_by_ids, ids_magento_anterior)

    try:
        dados_ativo_atual = future_ativo_atual.result(timeout=60)
    except Exception:
        dados_ativo_atual = []
    try:
        dados_magento_atual = future_magento_atual.result(timeout=60)
    except Exception:
        dados_magento_atual = []
    try:
        dados_ativo_anterior = future_ativo_anterior.result(timeout=60)
    except Exception:
        dados_ativo_anterior = []
    try:
        dados_magento_anterior = future_magento_anterior.result(timeout=60)
    except Exception:
        dados_magento_anterior = []

    meses_labels = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
    monthly = {}
    for m in range(1, 13):
        monthly[m] = {
            "mes": meses_labels[m - 1],
            f"vendas_{ano}": 0,
            f"vendas_{ano_anterior}": 0,
            f"receita_{ano}": 0.0,
            f"receita_{ano_anterior}": 0.0,
        }
    for row in dados_ativo_atual + dados_magento_atual:
        m = row["mes"]
        if 1 <= m <= 12:
            monthly[m][f"vendas_{ano}"] += row["qtd"]
            monthly[m][f"receita_{ano}"] += row["receita"]
    for row in dados_ativo_anterior + dados_magento_anterior:
        m = row["mes"]
        if 1 <= m <= 12:
            monthly[m][f"vendas_{ano_anterior}"] += row["qtd"]
            monthly[m][f"receita_{ano_anterior}"] += row["receita"]
    data = []
    acum_atual = 0
    acum_anterior = 0
    acum_receita_atual = 0.0
    acum_receita_anterior = 0.0
    for m in range(1, 13):
        entry = monthly[m]
        acum_atual += entry[f"vendas_{ano}"]
        acum_anterior += entry[f"vendas_{ano_anterior}"]
        acum_receita_atual += entry[f"receita_{ano}"]
        acum_receita_anterior += entry[f"receita_{ano_anterior}"]
        entry[f"receita_{ano}"] = round(entry[f"receita_{ano}"], 2)
        entry[f"receita_{ano_anterior}"] = round(entry[f"receita_{ano_anterior}"], 2)
        entry[f"acumulado_{ano}"] = acum_atual
        entry[f"acumulado_{ano_anterior}"] = acum_anterior
        entry[f"acumulado_receita_{ano}"] = round(acum_receita_atual, 2)
        entry[f"acumulado_receita_{ano_anterior}"] = round(acum_receita_anterior, 2)
        data.append(entry)
    evento_nome = evento_id.replace("grp_", "") if is_grouped else str(projeto.evento or "")
    return {
        "status": "success",
        "modo": "mensal",
        "ano_atual": ano,
        "ano_anterior": ano_anterior,
        "data": data,
        "evento_nome": evento_nome,
        "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat()
    }


def _fetch_commercial_actions_from_db(db: Session, projeto_ids: list) -> list:
    """Always reads fresh from DB — never cached. Returns formatted commercial actions list."""
    if not projeto_ids:
        return []
    from ...models.dimensoes import AcaoComercial
    tipo_map = {
        'AUMENTO_PRECO': 'price_increase', 'REDUCAO_PRECO': 'price_decrease',
        'PROMOCAO': 'promotion', 'CAMPANHA': 'campaign', 'COMUNICACAO': 'communication',
        'NENHUMA_ACAO': 'communication', 'OUTROS': 'communication',
    }
    acoes = db.query(AcaoComercial).filter(
        AcaoComercial.projeto_id.in_(projeto_ids)
    ).order_by(AcaoComercial.data_acao.desc()).all()
    result = []
    for a in acoes:
        impacto = calculate_action_impact(db, a)
        ip = impacto.get("impacto_percentual")
        impact_str = (f"+{ip}%" if ip and ip > 0 else f"{ip}%") if ip is not None else None
        result.append({
            "id": str(a.id),
            "tipo": a.tipo,
            "type": tipo_map.get(a.tipo, 'communication'),
            "description": a.descricao,
            "date": a.data_acao.isoformat() if a.data_acao else None,
            "impact": impact_str,
            "vendas_antes": impacto.get("vendas_antes"),
            "vendas_depois": impacto.get("vendas_depois"),
            "impacto_percentual": ip,
            "status_impacto": impacto.get("status", "calculado") if ip is not None else "aguardando_dados",
            "ponto_corte": a.ponto_corte,
            "estagio": a.estagio,
            "snapshot_isc": float(a.snapshot_isc) if a.snapshot_isc is not None else None,
            "snapshot_isc_state": a.snapshot_isc_state,
            "snapshot_d_minus": a.snapshot_d_minus,
            "snapshot_ia730": float(a.snapshot_ia730) if a.snapshot_ia730 is not None else None,
            "snapshot_rolling14d": float(a.snapshot_rolling14d) if a.snapshot_rolling14d is not None else None,
            "snapshot_curva_percent": float(a.snapshot_curva_percent) if a.snapshot_curva_percent is not None else None,
            "snapshot_vendas_acumuladas": a.snapshot_vendas_acumuladas,
            "snapshot_playbook_letter": a.snapshot_playbook_letter,
        })
    return result


_cortesia_cache_result: set = set()
_cortesia_cache_ts: float = 0.0
_CORTESIA_CACHE_TTL: float = 60.0

def _get_cortesia_magento_ids(db: Session) -> set:
    """Return set of Magento event IDs (as strings) whose projeto/grupo has incluir_cortesias=True.
    
    Results are memoized for 60s to avoid repeated DB round-trips in hot paths.
    """
    global _cortesia_cache_result, _cortesia_cache_ts
    import time as _time
    now = _time.monotonic()
    if _cortesia_cache_result and (now - _cortesia_cache_ts) < _CORTESIA_CACHE_TTL:
        return _cortesia_cache_result

    cortesia_ids: set = set()
    proj_cortesia = db.query(DimProjeto).filter(DimProjeto.incluir_cortesias == True).all()
    proj_skus = set()
    for proj in proj_cortesia:
        if proj.codigo:
            proj_skus.add(proj.codigo.upper().strip())
    if proj_skus:
        mappings = db.query(SkuMapping).filter(
            SkuMapping.sku.in_(proj_skus),
            SkuMapping.fonte == 'MAGENTO',
            SkuMapping.ativo == True,
        ).all()
        for sm in mappings:
            if sm.id_externo:
                cortesia_ids.add(str(sm.id_externo))

    grupos_cortesia = db.query(EventoGrupoModel).filter(EventoGrupoModel.incluir_cortesias == True).all()
    if grupos_cortesia:
        grupo_nomes = [g.nome for g in grupos_cortesia]
        grupo_projs = db.query(DimProjeto).filter(DimProjeto.evento.in_(grupo_nomes)).all()
        grupo_proj_map: dict = {}
        for proj in grupo_projs:
            grupo_proj_map.setdefault(proj.evento, []).append(proj)

        grupo_skus = set()
        direct_grupo_nomes = []
        for grupo in grupos_cortesia:
            projs = grupo_proj_map.get(grupo.nome, [])
            if projs:
                for proj in projs:
                    if proj.codigo:
                        grupo_skus.add(proj.codigo.upper().strip())
            else:
                direct_grupo_nomes.append(grupo.nome)
        if grupo_skus:
            mappings = db.query(SkuMapping).filter(
                SkuMapping.sku.in_(grupo_skus),
                SkuMapping.fonte == 'MAGENTO',
                SkuMapping.ativo == True,
            ).all()
            for sm in mappings:
                if sm.id_externo:
                    cortesia_ids.add(str(sm.id_externo))
        if direct_grupo_nomes:
            mappings = db.query(SkuMapping).filter(
                SkuMapping.evento_grupo.in_(direct_grupo_nomes),
                SkuMapping.fonte == 'MAGENTO',
                SkuMapping.ativo == True,
            ).all()
            for sm in mappings:
                if sm.id_externo:
                    cortesia_ids.add(str(sm.id_externo))

    _cortesia_cache_result = cortesia_ids
    _cortesia_cache_ts = now
    return cortesia_ids

def _invalidate_cortesia_cache():
    global _cortesia_cache_result, _cortesia_cache_ts
    _cortesia_cache_result = set()
    _cortesia_cache_ts = 0.0


# ── TTL cache (60s) para o payload final do detalhe de evento ──────────────
# Evita reaplicar overlay e re-renderizar o JSON em rajadas de acessos ao mesmo
# evento. Invalidado automaticamente quando save_persisted_detail grava.
_detail_final_cache: dict = {}
_DETAIL_FINAL_TTL: float = 60.0


# ── Cooldown por (usuário, evento, ano) — 30s ────────────────────────────────
# Anti-spam: se o mesmo usuário reabrir/atualizar a mesma página de evento em
# <30s, devolvemos qualquer payload cacheado (snapshot ou final cache) sem
# disparar refresh em background nem bypass por version_mismatch. Se nada
# cacheado existir, devolvemos HTTP 429. Não se aplica a force_refresh
# (já protegido pelo rate-limit global de 6/min) nem a chamadas internas
# (warmup/scheduler com current_user=None).
import threading as _user_cd_threading
_user_event_cooldown: dict = {}
_user_event_cooldown_lock = _user_cd_threading.Lock()
_USER_EVENT_COOLDOWN_S: float = 30.0


def _user_event_cooldown_active(user_id, evento_id: str, ano) -> bool:
    """Retorna True e marca a entrada se (user, evento, ano) foi acessado
    nos últimos _USER_EVENT_COOLDOWN_S segundos. Caso contrário, marca o
    momento atual e retorna False."""
    import time as _t
    if user_id is None:
        return False
    key = (user_id, evento_id, ano)
    now = _t.monotonic()
    with _user_event_cooldown_lock:
        last = _user_event_cooldown.get(key, 0.0)
        if (now - last) < _USER_EVENT_COOLDOWN_S:
            return True
        _user_event_cooldown[key] = now
        # housekeeping leve — limita o dict a ~5000 entradas
        if len(_user_event_cooldown) > 5000:
            cutoff = now - (_USER_EVENT_COOLDOWN_S * 4)
            for k in [k for k, v in _user_event_cooldown.items() if v < cutoff]:
                _user_event_cooldown.pop(k, None)
        return False


def _detail_final_cache_get(key: str):
    import time as _t
    entry = _detail_final_cache.get(key)
    if entry and (_t.monotonic() - entry[0]) < _DETAIL_FINAL_TTL:
        return entry[1]
    return None


def _detail_final_cache_set(key: str, payload: dict) -> None:
    import time as _t
    _detail_final_cache[key] = (_t.monotonic(), payload)


def invalidate_detail_final_cache(evento_id: str | None = None, ano: int | None = None) -> None:
    """Invalida o cache TTL do payload final. Chamada pelo save_persisted_detail."""
    if evento_id is None or ano is None:
        _detail_final_cache.clear()
        return
    _detail_final_cache.pop(f"{ano}_{evento_id}_detail_final", None)


def _bust_commercial_actions_cache_for_projeto(db: Session, projeto_id: int) -> None:
    """Após mutação em AcaoComercial, garante que o próximo GET do detalhe
    recompute commercialActions. Limpa o cache TTL em memória e remove a chave
    commercialActions dos snapshots que referenciam o projeto, forçando o hot
    path a re-buscar via _fetch_commercial_actions_from_db (fallback legacy)."""
    try:
        _detail_final_cache.clear()
    except Exception:
        pass
    try:
        from ...models.evento_detail_snapshot import EventoDetailSnapshot
        from sqlalchemy import text as _sql_text

        db.execute(
            _sql_text(
                """
                UPDATE evento_detail_snapshot
                SET payload = payload - 'commercialActions'
                WHERE payload -> 'projetos_vinculados' @> CAST(:p AS jsonb)
                """
            ),
            {"p": f'[{{"id": {int(projeto_id)}}}]'},
        )
        db.commit()
    except Exception as _e:
        logger.warning(f"[CacheBust] commercialActions snapshot strip falhou projeto={projeto_id}: {_e}")
        try:
            db.rollback()
        except Exception:
            pass


def _populate_cenarios_from_bundles(
    db: Session,
    bundle_to_cenario: dict,
    cenarios: dict,
    incluir_cortesias: bool = False,
) -> bool:
    """Populate cenarios dict with real sales data per bundle from Magento.

    First tries SkuMapping-based ISC lookup (legacy path). If no SkuMappings
    exist for bundles, falls back to direct Magento queries — using the same
    canonical filters as get_margem_por_kit (status set, state, GRUPOS, etc.).
    Returns True if data was populated.
    """
    from app.models.dimensoes import SkuMapping as _SM

    _sku_maps = db.query(_SM).filter(
        func.upper(_SM.fonte) == 'MAGENTO',
        _SM.id_externo.in_(list(bundle_to_cenario.keys())),
        _SM.ativo == True,
    ).all()
    _sku_to_cenario = {}
    for sm_row in _sku_maps:
        cenario_val = bundle_to_cenario.get(sm_row.id_externo)
        if cenario_val and sm_row.sku:
            _sku_to_cenario[normalize_sku(sm_row.sku)] = cenario_val

    if _sku_to_cenario:
        isc_data_cic = fetch_isc_pricing_data(db=db)
        for _sku_cic, _cenario_cic in _sku_to_cenario.items():
            _cic_info = isc_data_cic.get(_sku_cic, {})
            if _cic_info and _cenario_cic in cenarios:
                cenarios[_cenario_cic]["real_vendas"] = cenarios[_cenario_cic].get("real_vendas", 0) + _cic_info.get("qtd_site", 0)
                cenarios[_cenario_cic]["real_receita"] = round(cenarios[_cenario_cic].get("real_receita", 0) + _cic_info.get("receita_liquida_site", 0), 2)
        return True

    if not bundle_to_cenario or db_module.engine_magento is None:
        return False

    bundle_ids_int = [int(b) for b in bundle_to_cenario.keys()]

    # Cortesia filters use a SQL-level boolean parameter so query strings are static.
    # :skip_cortesia_filter = True  → OR short-circuits, filter is skipped
    # :skip_cortesia_filter = False → the filter condition is enforced
    _skip_cortesia_filter = bool(incluir_cortesias)

    # OTIMIZAÇÃO (broad fix): lidera com sales_order_item.product_id IN.
    _cic_count_q = text(
        "SELECT /*+ MAX_EXECUTION_TIME(20000) */ STRAIGHT_JOIN\n"
        "    soi_parent.product_id AS bundle_id,\n"
        "    COUNT(DISTINCT soi_parent.item_id) AS qtd\n"
        "FROM sales_order_item soi_parent\n"
        "INNER JOIN sales_order so\n"
        "       ON so.entity_id = soi_parent.order_id\n"
        "WHERE\n"
        "    soi_parent.product_type = 'bundle'\n"
        "AND soi_parent.product_id   IN :bundle_ids\n"
        "AND so.created_at >= DATE_SUB(CURDATE(), INTERVAL 2 YEAR)\n"
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
        skip_cortesia_filter=_skip_cortesia_filter,
    )

    # OTIMIZAÇÃO (broad fix): lidera com sales_order_item.product_id IN.
    _cic_rev_q = text(
        "SELECT /*+ MAX_EXECUTION_TIME(90000) */ STRAIGHT_JOIN\n"
        "    soi_parent.product_id AS bundle_id,\n"
        "    ROUND(SUM(soi_child.price - soi_child.discount_amount), 2) AS receita\n"
        "FROM sales_order_item soi_parent\n"
        "INNER JOIN sales_order so\n"
        "       ON so.entity_id = soi_parent.order_id\n"
        "INNER JOIN sales_order_item soi_child\n"
        "       ON soi_child.parent_item_id = soi_parent.item_id\n"
        "      AND soi_child.product_type   = 'simple'\n"
        "WHERE\n"
        "    soi_parent.product_type = 'bundle'\n"
        "AND soi_parent.product_id   IN :bundle_ids\n"
        "AND so.created_at >= DATE_SUB(CURDATE(), INTERVAL 2 YEAR)\n"
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
        skip_cortesia_filter=_skip_cortesia_filter,
    )

    def _cic_count_work(conn):
        return conn.execute(_cic_count_q, {"bundle_ids": bundle_ids_int}).mappings().all()
    try:
        count_rows = magento_run(_cic_count_work, label="cenarios-ciclismo:count", profile="background")
        for row in count_rows:
            bid = row['bundle_id']
            cen = bundle_to_cenario.get(bid) or bundle_to_cenario.get(str(bid))
            if cen and cen in cenarios:
                cenarios[cen]["real_vendas"] = cenarios[cen].get("real_vendas", 0) + int(row['qtd'] or 0)
        logger.info(f"[CenariosCiclismo] Magento count: {len(count_rows)} bundles")
    except Exception as e:
        logger.warning(f"[CenariosCiclismo] Magento count failed: {e}")
        return False

    def _cic_rev_work(conn):
        return conn.execute(_cic_rev_q, {"bundle_ids": bundle_ids_int}).mappings().all()
    try:
        rev_rows = magento_run(_cic_rev_work, label="cenarios-ciclismo:revenue", profile="background")
        for row in rev_rows:
            bid = row['bundle_id']
            cen = bundle_to_cenario.get(bid) or bundle_to_cenario.get(str(bid))
            if cen and cen in cenarios:
                cenarios[cen]["real_receita"] = round(cenarios[cen].get("real_receita", 0) + float(row['receita'] or 0), 2)
        logger.info(f"[CenariosCiclismo] Magento revenue: {len(rev_rows)} bundles")
        return len(count_rows) > 0
    except Exception as e:
        logger.warning(f"[CenariosCiclismo] Magento revenue failed: {e}")
        return len(count_rows) > 0


@router.patch("/eventos/{evento_id}/cortesias")
def toggle_cortesias(
    evento_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin()),
):
    from ...services.snapshot_service import consolidar_vendas_grupo as _consolidar
    from datetime import date as _date_cls

    is_grouped = evento_id.startswith("grp_")
    reconsolidate_grupos: list = []
    ano = _date_cls.today().year

    if is_grouped:
        grupo_nome = evento_id.replace("grp_", "")
        grupo = db.query(EventoGrupoModel).filter(EventoGrupoModel.nome == grupo_nome).first()
        if not grupo:
            raise HTTPException(status_code=404, detail="Grupo de evento não encontrado")
        grupo.incluir_cortesias = not grupo.incluir_cortesias
        db.commit()
        db.refresh(grupo)
        reconsolidate_grupos.append(grupo_nome)
        event_detail_cache.invalidate()
        eventos_list_cache.invalidate()
        result_flag = grupo.incluir_cortesias
    else:
        projeto = db.query(DimProjeto).filter(DimProjeto.id == int(evento_id)).first()
        if not projeto:
            raise HTTPException(status_code=404, detail="Projeto não encontrado")
        projeto.incluir_cortesias = not projeto.incluir_cortesias
        db.commit()
        db.refresh(projeto)
        if projeto.evento:
            reconsolidate_grupos.append(projeto.evento)
        event_detail_cache.invalidate()
        eventos_list_cache.invalidate()
        result_flag = projeto.incluir_cortesias

    _invalidate_cortesia_cache()

    def _reconsolidate_snapshot(grupos: list, year: int):
        try:
            from ...core.database import SessionLocal
            with SessionLocal() as snap_db:
                for g in grupos:
                    _consolidar(snap_db, g, year)
                    logger.info(f"[Cortesia Toggle] Reconsolidated snapshot for grupo='{g}', ano={year}")
            event_detail_cache.invalidate()
            eventos_list_cache.invalidate()
            logger.info("[Cortesia Toggle] Caches re-invalidated after snapshot reconsolidation")
        except Exception as e:
            logger.error(f"[Cortesia Toggle] Snapshot reconsolidation failed: {e}")

    if reconsolidate_grupos:
        background_tasks.add_task(_reconsolidate_snapshot, reconsolidate_grupos, ano)

    return {"incluirCortesias": result_flag}


def _resolve_evento_ano_efetivo(db: Session, evento_id: str, ano: Optional[int]) -> int:
    """Resolve o ano efetivo de um evento para leitura/reconsolidação.

    Mesma lógica usada pelo fast-path de `get_marketing_event_by_id`: usa o
    `ano` explícito quando informado; para eventos agrupados (`grp_`) sem ano
    explícito cai no ano corrente do servidor (ambíguo — grupo cobre vários
    anos); para eventos individuais resolve pela data cadastrada em
    `dim_projeto`. Compartilhada com o endpoint de reconsolidação manual para
    que ambos os fluxos (leitura e escrita) usem sempre a mesma chave de ano,
    evitando que a reconsolidação recalcule/persista um ano diferente do que
    a tela está exibindo.
    """
    if ano is not None:
        return ano
    if evento_id.startswith("grp_"):
        return datetime.now().year
    try:
        _proj = _wq_dim_projeto_by_id(db, int(evento_id))
        return (_proj.data_evento.year
                if _proj and _proj.data_evento
                else datetime.now().year)
    except Exception:
        return datetime.now().year


@router.get("/eventos/{evento_id}")
def get_marketing_event_by_id(
    evento_id: str,
    ano: int = Query(default=None, description="Ano para evento consolidado"),
    force_refresh: bool = Query(default=False, description="Forçar atualização dos dados ignorando cache"),
    force_magento_refresh: bool = Query(default=False, description="Bypass do snapshot para eventos finalizados — vai direto ao Magento"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing_dashboard", "pode_visualizar")),
    response: Response = None
):
    """
    Retorna os dados de um evento específico pelo ID.
    Suporta IDs de EventoGrupo (prefixo 'grp_') e DimProjeto (número puro).
    """
    isc_cfg = _get_isc_settings(db)
    is_grouped = evento_id.startswith("grp_")

    # ── FAST PATH: snapshot persistente em PostgreSQL ──────────────────────────
    # Sobrevive a restarts do servidor e à invalidação do cache em memória.
    # O scheduler atualiza este snapshot a cada 30 min em background.
    # Resolve o `ano` efetivo aqui (mesma lógica usada nos branches abaixo)
    # para garantir que a chave de leitura/escrita seja consistente.
    _ano_for_persist = _resolve_evento_ano_efetivo(db, evento_id, ano)

    # ── Cooldown early-demote do force_magento_refresh ───────────────────────
    # Helpers internos (fetch_real_daily_sales_for_projetos, get_margem_por_kit)
    # já têm seu próprio cooldown, mas o endpoint dispara muita orquestração
    # (cpev1 prefetch, kit-alignment, atualizar-hoje, etc.) antes de chegar
    # nesses helpers. Aplicar o demote já na entrada evita o trabalho duplo
    # quando o mesmo grupo é re-disparado dentro da janela.
    # Compartilha o dict/lock com o cooldown interno (mesma chave grupo|ano)
    # para que os dois níveis enxerguem o mesmo timestamp.
    if force_magento_refresh and is_grouped:
        import time as _ep_time
        _grupo_for_cd = evento_id.replace("grp_", "")
        _cd_key = f"{_grupo_for_cd}|{_ano_for_persist}"
        _now_cd = _ep_time.time()
        with _force_refresh_lock:
            _last_cd = _force_refresh_last_ts.get(_cd_key)
            if _last_cd is not None and (_now_cd - _last_cd) < _FORCE_REFRESH_COOLDOWN_SECONDS:
                force_magento_refresh = False
                logger.info(
                    f"[force_magento_refresh] DEMOTED-EARLY p/ grupo='{_grupo_for_cd}' "
                    f"ano={_ano_for_persist} — cooldown {int(_now_cd - _last_cd)}s "
                    f"< {_FORCE_REFRESH_COOLDOWN_SECONDS}s (endpoint entry, evita fan-out)"
                )
            else:
                _force_refresh_last_ts[_cd_key] = _now_cd
    # Snapshot-first read. O recomputo "force_refresh=True" só faz bypass quando
    # disparado internamente (scheduler/warmup com current_user=None). Cliques de
    # usuário com force_refresh=True são tratados como pedido de refresh em
    # background: servimos snapshot+overlay imediatamente e enfileiramos recompute.
    _internal_recompute = force_refresh and current_user is None
    _user_refresh_request = force_refresh and current_user is not None
    _USE_SNAPSHOT_FIRST = os.getenv("USE_SNAPSHOT_FIRST_READ", "true").lower() not in ("0", "false", "no")

    # ── Cooldown anti-spam por (usuário, evento, ano) ────────────────────────
    # Se o mesmo usuário reabriu/atualizou essa página em <30s sem force_refresh,
    # forçamos modo "serve qualquer coisa cacheada": sem bypass de version_mismatch
    # e sem disparar bg refresh. Se nada cacheado existir, devolvemos 429.
    _user_cd_active = False
    if (
        current_user is not None
        and not force_refresh
        and not force_magento_refresh
    ):
        _user_cd_active = _user_event_cooldown_active(
            getattr(current_user, 'id', None), evento_id, _ano_for_persist
        )
    # Bootstrap fallback: quando o snapshot completo for descartado, ainda assim
    # podemos servir os dados básicos do "evento" (nome, data, local, vendas/meta
    # da lista) para o usuário ver algo. Capturado abaixo.
    _bootstrap_evento_partial = None
    _bootstrap_partial_computed_at = None
    if _USE_SNAPSHOT_FIRST and not _internal_recompute:
        # TTL cache (60s) do payload final já com overlay: serve eventos populares
        # em ~5ms sem reabrir o snapshot nem recomputar overlay.
        _final_key = f"{_ano_for_persist}_{evento_id}_detail_final"
        _final_cached = _detail_final_cache_get(_final_key)
        if _final_cached is not None:
            if response is not None:
                response.headers["X-Data-Stale"] = "false"
                response.headers["X-Cache-Hit"] = "memory"
            return _final_cached
        try:
            from ...services.event_detail_snapshot_service import (
                get_persisted_detail as _gpd,
                apply_today_overlay as _apply_overlay,
            )
            _persisted = _gpd(db, evento_id, _ano_for_persist)
        except Exception:
            _persisted = None
        if _persisted is not None:
            from app.core.cache import (
                get_last_full_refresh as _gpd_lfr,
                get_last_sync_hoje as _gpd_lsh,
            )
            _gpd_lfr_ts = _gpd_lfr() or 0
            _gpd_lsh_ts = _gpd_lsh() or 0
            _gpd_comp = _persisted.get("computed_at")
            _gpd_comp_ts = _gpd_comp.timestamp() if _gpd_comp else 0
            _gpd_completed = _persisted.get("is_completed", False)
            _gpd_payload_version = (_persisted["payload"] or {}).get("_cache_version") if isinstance(_persisted["payload"], dict) else None
            _gpd_version_mismatch = _gpd_payload_version != _DETAIL_CACHE_VERSION
            # Safety guard: se a versão mudou, descartamos o snapshot se ele for
            # um "bootstrap" incompleto (salvo pela lista de eventos com apenas
            # {"evento": {...}}, sem dailySales nem _cache_version). Esses payloads
            # causam Controle Diário vazio pois dailySales é undefined no frontend.
            # Snapshots completos mas com versão antiga são servidos via SWR para
            # evitar o loop "preparing" quando o recompute demora 2-3 min.
            if _gpd_version_mismatch and not _user_cd_active:
                _pl = _persisted["payload"] if isinstance(_persisted["payload"], dict) else {}
                _evt_chk = _pl.get("evento") if isinstance(_pl, dict) else None
                _has_evt = isinstance(_evt_chk, dict) and bool(_evt_chk)
                # Um snapshot completo deve ter pelo menos a chave dailySales.
                # Payloads sem ela são bootstraps da lista (só têm "evento")
                # e devem ser descartados para triggerar recompute completo.
                _has_daily_sales_key = "dailySales" in _pl if isinstance(_pl, dict) else False
                _has_essentials = _has_evt and _has_daily_sales_key
                if not _has_essentials:
                    _dbg_pl_keys = list(_pl.keys())[:10] if isinstance(_pl, dict) else None
                    _dbg_reason = "bootstrap (sem dailySales)" if _has_evt else "payload inválido"
                    logger.warning(
                        f"[Persist] '{_ano_for_persist}_{evento_id}' version mismatch "
                        f"({_gpd_payload_version} != {_DETAIL_CACHE_VERSION}) AND {_dbg_reason} "
                        f"— bypassing snapshot. payload_keys={_dbg_pl_keys}"
                    )
                    # Captura bootstrap evento para servir como payload parcial.
                    if _has_evt:
                        _bootstrap_evento_partial = _evt_chk
                        _bootstrap_partial_computed_at = _gpd_comp
                    _persisted = None
        # Descarta snapshot se dailySales está vazio/ausente/null mesmo com versão correta —
        # snapshots salvos antes do fallback podiam persistir [] e travar o Controle Diário.
        # Também cobre os casos em que a chave nem existe ou veio como null (None), que
        # produzem charts vazios no frontend mesmo quando os KPIs do `evento` estão preenchidos.
        if _persisted is not None:
            _pl_check = _persisted.get("payload") if isinstance(_persisted, dict) else None
            _has_ds_key = isinstance(_pl_check, dict) and "dailySales" in _pl_check
            _ds_check = _pl_check.get("dailySales") if isinstance(_pl_check, dict) else None
            _ds_empty_or_missing = (
                not _has_ds_key
                or _ds_check is None
                or (isinstance(_ds_check, list) and len(_ds_check) == 0)
            )
            if _ds_empty_or_missing:
                logger.warning(
                    f"[Persist] '{_ano_for_persist}_{evento_id}' snapshot com dailySales "
                    f"vazio/ausente (key_present={_has_ds_key}, type={type(_ds_check).__name__}) "
                    f"— descartando para forçar recompute com fallback de snapshot."
                )
                # Captura bootstrap evento para servir como payload parcial.
                _evt_partial2 = _pl_check.get("evento") if isinstance(_pl_check, dict) else None
                if isinstance(_evt_partial2, dict) and _evt_partial2:
                    _bootstrap_evento_partial = _evt_partial2
                    _bootstrap_partial_computed_at = _persisted.get("computed_at") if isinstance(_persisted, dict) else None
                _persisted = None
        if _persisted is not None:
            # Stale APENAS se: (a) usuário pediu refresh explícito (botão Atualizar),
            # ou (b) versão do schema mudou. Não dispara bg refresh automático por
            # idade — a atualização periódica fica a cargo do warmup/scheduler e o
            # usuário decide quando rebuscar Magento clicando em "Atualizar".
            # Mantemos _gpd_age só para diagnóstico em logs.
            _gpd_age = (datetime.now() - _gpd_comp.replace(tzinfo=None)).total_seconds() if _gpd_comp else 9999
            # Snapshot-only mode: pedidos de usuário (incluindo admin com force_refresh)
            # NÃO disparam recompute Magento aqui. Apenas mudança de versão de schema
            # justifica refresh em background. Reconsolidação completa só via POST
            # /eventos/{id}/recalcular-snapshot (admin explícito).
            # Cooldown anti-spam: suprime bg refresh quando o mesmo usuário
            # acabou de acessar este evento (<30s). O snapshot serve como está.
            _gpd_stale = _gpd_version_mismatch and not _user_cd_active
            _gpd_key = f"{_ano_for_persist}_{evento_id}_detail"
            if _gpd_stale and _gpd_key not in _swr_recompute_in_progress:
                _reason = (
                    "user refresh" if _user_refresh_request
                    else "version mismatch" if _gpd_version_mismatch
                    else f"age={_gpd_age:.0f}s"
                )
                logger.info(f"[Persist] '{_gpd_key}' stale ({_reason}) — serving snapshot+overlay + bg refresh")
                _swr_recompute_in_progress.add(_gpd_key)
                import threading as _gpd_threading
                def _gpd_bg():
                    from ...core.database import SessionLocal as _GPD_SL
                    _gpd_db = _GPD_SL()
                    try:
                        get_marketing_event_by_id(
                            evento_id=evento_id, ano=_ano_for_persist,
                            force_refresh=True, force_magento_refresh=force_magento_refresh,
                            db=_gpd_db, current_user=None,
                        )
                    except Exception as _gpd_e:
                        logger.warning(f"[Persist] bg refresh '{_gpd_key}' failed: {_gpd_e}")
                    finally:
                        _gpd_db.close()
                        _swr_recompute_in_progress.discard(_gpd_key)
                _gpd_threading.Thread(target=_gpd_bg, daemon=True).start()
            _gpd_payload = _persisted["payload"] if isinstance(_persisted["payload"], dict) else {}
            # Aplica overlay de HOJE (currentSales, dailySales[hoje], averageTicket)
            try:
                _gpd_payload = _apply_overlay(db, _gpd_payload, evento_id, ano=_ano_for_persist)
            except Exception as _ov_e:
                logger.warning(f"[Persist] apply_today_overlay '{_gpd_key}' falhou: {_ov_e}")
            _gpd_result = dict(_gpd_payload)
            _gpd_result["ultima_atualizacao_completa"] = (
                datetime.fromtimestamp(_gpd_lfr_ts, tz=ZoneInfo('America/Sao_Paulo')).isoformat()
                if _gpd_lfr_ts else None
            )
            # snapshot computed_at (timestamp do recompute completo deste evento)
            if _gpd_comp:
                try:
                    _gpd_comp_aware = _gpd_comp if _gpd_comp.tzinfo else _gpd_comp.replace(tzinfo=ZoneInfo('America/Sao_Paulo'))
                    _gpd_result["snapshot_computed_at"] = _gpd_comp_aware.isoformat()
                except Exception:
                    pass
            _gpd_pids = [p["id"] for p in _gpd_result.get("projetos_vinculados", [])]
            if not _gpd_pids and not is_grouped:
                try:
                    _gpd_pids = [int(evento_id)]
                except (ValueError, TypeError):
                    pass
            # Snapshot agora persiste commercialActions e faixas_preco_site
            # (calculados no recompute/reconsolidar). Só refazemos a query
            # quando o snapshot é legado (não tem o campo).
            if "commercialActions" not in _gpd_result:
                _gpd_result["commercialActions"] = _fetch_commercial_actions_from_db(db, _gpd_pids)
            if "faixas_preco_site" not in _gpd_result and _gpd_pids:
                try:
                    _gpd_result["faixas_preco_site"] = _get_faixas_preco_site_for_projeto_ids(db, _gpd_pids)
                except Exception as _fps_e:
                    logger.warning(f"[Persist] faixas_preco_site fallback falhou: {_fps_e}")
            if response is not None:
                response.headers["X-Data-Stale"] = "true" if _gpd_stale else "false"
                if _gpd_version_mismatch:
                    response.headers["X-Schema-Stale"] = "true"
            # Guarda no TTL cache (60s) — próximos GETs do mesmo evento batem em memória.
            try:
                _detail_final_cache_set(_final_key, _gpd_result)
            except Exception:
                pass
            return _gpd_result

    # NOTA: o cooldown anti-spam por (usuário, evento, ano) já entregou seu valor
    # acima — suprimiu o bypass por version_mismatch e o bg refresh (que tocariam
    # Magento). Se chegarmos aqui, é porque genuinamente NÃO há snapshot persistido
    # (evento ainda não consolidado). O caminho `no_snapshot/partial` abaixo serve
    # mensagem útil ao usuário SEM tocar Magento, então deixamos seguir.

    # ── PAYLOAD PARCIAL OU "SEM SNAPSHOT" PARA REQUEST DE USUÁRIO ─────────────
    # Não dispara recompute automático (consumiria Magento sem o usuário pedir).
    # Se tivermos um bootstrap (cabeçalho do evento da lista), servimos como
    # payload parcial com aviso. Caso contrário, devolvemos status no_snapshot
    # com erro pedindo que o administrador faça a atualização (clique em
    # Reconsolidar). O recompute só ocorre quando force_refresh=True (botão
    # Atualizar / Reconsolidar do admin) — esse caminho cai no fluxo abaixo.
    if (
        _USE_SNAPSHOT_FIRST
        and current_user is not None
        and not _internal_recompute
    ):
        _prep_key = f"{_ano_for_persist}_{evento_id}_detail"
        _partial_iso = None
        if _bootstrap_partial_computed_at:
            try:
                _bp_aware = (
                    _bootstrap_partial_computed_at
                    if _bootstrap_partial_computed_at.tzinfo
                    else _bootstrap_partial_computed_at.replace(tzinfo=ZoneInfo('America/Sao_Paulo'))
                )
                _partial_iso = _bp_aware.isoformat()
            except Exception:
                pass
        if _bootstrap_evento_partial is not None:
            logger.info(f"[Prepare] '{_prep_key}' sem snapshot completo — servindo dados parciais (bootstrap)")
            # Bootstrap salvo antes de mudanças em _fetch_ticket_atual_map pode ter
            # ticketAtual stale (ex: R$129,99 do lot_value fantasma em vez do R$99,99
            # real). Como bootstraps não são reescritos quando já existem no DB
            # (cf. line ~6173), recomputamos ticketAtual/ticketKitNome inline aqui
            # usando o _get_ticket_atual_map (que tem cache TTL 15min e já aplica
            # Regra B). Cobre tanto grupo (evento_id="grp_<nome>") quanto standalone.
            try:
                _btp_proj_ids: list = []
                if isinstance(evento_id, str) and evento_id.startswith("grp_"):
                    _btp_grupo_nome = evento_id.replace("grp_", "", 1)
                    _btp_sku_map = _build_sku_to_grupo_map(db, _ano_for_persist)
                    _btp_skus_do_grupo = {
                        sku for sku, g in _btp_sku_map.items() if g == _btp_grupo_nome
                    }
                    if _btp_skus_do_grupo:
                        # Janela ±1 ano para evitar full scan de DimProjeto.
                        # SKUs do grupo são do _ano_for_persist, então projetos
                        # relevantes têm data_evento em janela próxima a esse ano.
                        from datetime import date as _date
                        _btp_y = int(_ano_for_persist)
                        _btp_dt_lo = _date(_btp_y - 1, 1, 1)
                        _btp_dt_hi = _date(_btp_y + 1, 12, 31)
                        _btp_projetos = db.query(DimProjeto.id, DimProjeto.codigo).filter(
                            DimProjeto.data_evento >= _btp_dt_lo,
                            DimProjeto.data_evento <= _btp_dt_hi,
                        ).all()
                        for _bp in _btp_projetos:
                            if _bp.codigo and normalize_sku(str(_bp.codigo)) in _btp_skus_do_grupo:
                                _btp_proj_ids.append(_bp.id)
                else:
                    try:
                        _btp_proj_ids = [int(evento_id)]
                    except (TypeError, ValueError):
                        _btp_proj_ids = []
                if _btp_proj_ids:
                    _btp_map = _get_ticket_atual_map(db)
                    _btp_ticket_new = _get_ticket_atual_for_event(_btp_map, _btp_proj_ids)
                    _btp_kit_nome_new = _get_ticket_atual_kit_nome_for_event(_btp_map, _btp_proj_ids)
                    _btp_old = _bootstrap_evento_partial.get("ticketAtual")
                    if _btp_ticket_new and _btp_ticket_new > 0:
                        _bootstrap_evento_partial["ticketAtual"] = _btp_ticket_new
                        _bootstrap_evento_partial["ticketKitNome"] = _btp_kit_nome_new
                        if _btp_old != _btp_ticket_new:
                            logger.info(
                                f"[Bootstrap] '{_prep_key}' ticketAtual recomputado: "
                                f"{_btp_old} → {_btp_ticket_new} (kit={_btp_kit_nome_new})"
                            )
            except Exception as _btp_e:
                logger.warning(f"[Bootstrap] '{_prep_key}' recompute ticketAtual falhou: {_btp_e}")
            if response is not None:
                response.headers["X-Data-Stale"] = "true"
                response.headers["X-Data-Partial"] = "true"
            # Mesmo sem snapshot completo, tentamos popular dailySales lendo o
            # VendasDiariaSnapshot (PostgreSQL local) via apply_today_overlay.
            # Isso permite que os gráficos "Atingimento da Meta", "Curva no Tempo"
            # e a aba "Controle Diário" exibam o histórico diário já disponível,
            # em vez de aparecerem vazios até o admin clicar em Reconsolidar.
            _partial_payload = {
                "status": "partial",
                "evento_id": evento_id,
                "ano": _ano_for_persist,
                "evento": _bootstrap_evento_partial,
                "dailySales": [],
                "commercialActions": [],
                "snapshot_computed_at": _partial_iso,
                "message": (
                    "Detalhes diários ainda não foram consolidados para este evento. "
                    "Solicite ao administrador clicar em 'Reconsolidar' para buscar os dados completos."
                ),
            }
            try:
                from ...services.event_detail_snapshot_service import (
                    apply_today_overlay as _apply_overlay_partial,
                )
                _partial_payload = _apply_overlay_partial(db, _partial_payload, evento_id, ano=_ano_for_persist)
                _ds_after = _partial_payload.get("dailySales") or []
                _ds_count = len(_ds_after)
                if _ds_count > 0:
                    logger.info(
                        f"[Prepare] '{_prep_key}' partial enriquecido com {_ds_count} dias "
                        f"de VendasDiariaSnapshot"
                    )
                    # Enriquecimento adicional: como o overlay só preenche `sales` e
                    # `date`, calculamos `expected`/`cumulativeExpected`/`dMinus`/`dif`
                    # /`atingimento*` usando distribuição linear da meta sobre a
                    # janela [primeiro dia com snapshot .. data do evento]. Mesma
                    # lógica do fallback usado quando daily_sales_list vem vazio
                    # (L10005+) — assim a aba Atingimento da Meta por D- já mostra
                    # algo útil no estado parcial.
                    try:
                        from datetime import date as _date_cls
                        _evt_part = _partial_payload.get("evento") or {}
                        _sales_goal = int(_evt_part.get("salesGoal") or 0)
                        _evt_date_str = _evt_part.get("date") or ""
                        _evt_date = None
                        if _evt_date_str:
                            try:
                                _evt_date = _date_cls.fromisoformat(_evt_date_str[:10])
                            except Exception:
                                _evt_date = None
                        if _sales_goal > 0 and _ds_after:
                            _dates_iso = [r.get("date") for r in _ds_after if isinstance(r, dict) and r.get("date")]
                            if _dates_iso:
                                _first_d = _date_cls.fromisoformat(_dates_iso[0][:10])
                                _last_in_snap = _date_cls.fromisoformat(_dates_iso[-1][:10])
                                _close_d = _evt_date if _evt_date else _last_in_snap
                                _total_days = max(1, (_close_d - _first_d).days + 1)
                                _exp_per_day = round(_sales_goal / _total_days, 1)
                                _cum_sales = 0
                                _enriched: list = []
                                for _i, _row in enumerate(_ds_after):
                                    if not isinstance(_row, dict):
                                        _enriched.append(_row)
                                        continue
                                    _row_d_str = _row.get("date")
                                    try:
                                        _row_d = _date_cls.fromisoformat(_row_d_str[:10]) if _row_d_str else None
                                    except Exception:
                                        _row_d = None
                                    _qty = int(_row.get("sales") or 0)
                                    _cum_sales += _qty
                                    _day_index = ((_row_d - _first_d).days + 1) if _row_d else (_i + 1)
                                    _cum_exp = round(_exp_per_day * _day_index, 1)
                                    _dm = (_close_d - _row_d).days if _row_d and _close_d else None
                                    _ating_dia = round(((_qty - _exp_per_day) / _exp_per_day) * 100, 1) if _exp_per_day > 0 else 0.0
                                    _ating_acum = round(((_cum_sales - _cum_exp) / _cum_exp) * 100, 1) if _cum_exp > 0 else 0.0
                                    _new_row = dict(_row)
                                    # IMPORTANTE: atribuição direta (não setdefault).
                                    # apply_today_overlay no caminho sem-base já adiciona
                                    # rows com expected=0/cumulativeExpected=0 como placeholder;
                                    # setdefault deixaria esses zeros e META DIA/ACUM. apareceriam
                                    # como 0 e os ATING. como "—" (derivados de zeros).
                                    _new_row["expected"] = _exp_per_day
                                    _new_row["cumulativeSales"] = _cum_sales
                                    _new_row["cumulativeExpected"] = _cum_exp
                                    _new_row["dMinus"] = _dm
                                    _new_row.setdefault("curvaAnoAnterior", None)
                                    _new_row["dif"] = round(_cum_sales - _cum_exp, 1)
                                    _new_row["atingimentoAcumulado"] = _ating_acum
                                    _new_row["atingimentoDiario"] = _ating_dia
                                    _new_row.setdefault("normalizedSales", _qty)
                                    _new_row.setdefault("cumulativeNormalized", _cum_sales)
                                    _new_row.setdefault("localMedian", None)
                                    _new_row.setdefault("outlierLimit", None)
                                    _new_row.setdefault("isOutlier", False)
                                    _new_row.setdefault("excessRemoved", 0)
                                    _new_row.setdefault("excessReceived", 0)
                                    _enriched.append(_new_row)
                                _partial_payload["dailySales"] = _enriched
                                logger.info(
                                    f"[Prepare] '{_prep_key}' partial expected linear: "
                                    f"meta={_sales_goal}, dias={_total_days}, exp/dia={_exp_per_day}"
                                )
                    except Exception as _enrich_e:
                        logger.warning(f"[Prepare] enriquecimento expected partial '{_prep_key}' falhou: {_enrich_e}")
            except Exception as _ov_e:
                logger.warning(f"[Prepare] apply_today_overlay partial '{_prep_key}' falhou: {_ov_e}")
            return _partial_payload
        logger.info(f"[Prepare] '{_prep_key}' sem snapshot e sem bootstrap — retornando no_snapshot")
        if response is not None:
            response.headers["X-Data-Stale"] = "true"
            response.headers["X-Data-Preparing"] = "true"
        return {
            "status": "no_snapshot",
            "evento_id": evento_id,
            "ano": _ano_for_persist,
            "message": (
                "Não há dados consolidados para este evento. "
                "Solicite ao administrador clicar em 'Reconsolidar' para buscar os dados."
            ),
        }

    def _swr_detail_refresh(_swr_key: str):
        from ...core.database import SessionLocal
        _db = SessionLocal()
        try:
            get_marketing_event_by_id(evento_id=evento_id, ano=ano, force_refresh=True, force_magento_refresh=force_magento_refresh, db=_db, current_user=None)
        finally:
            _db.close()
            _swr_recompute_in_progress.discard(_swr_key)

    if is_grouped:
        grupo_nome = evento_id.replace("grp_", "")
        grupo = db.query(EventoGrupoModel).filter(EventoGrupoModel.nome == grupo_nome).first()
        if not grupo:
            raise HTTPException(status_code=404, detail="Grupo de evento não encontrado")
        # Capture scalar attrs immediately. Several downstream calls (notably
        # consolidar_vendas_grupo) commit/refresh the session, which can expire
        # or detach this instance — causing DetachedInstanceError when we read
        # grupo.nome / grupo.incluir_cortesias later in this function.
        _grupo_nome_attr = grupo.nome
        _grupo_incluir_cortesias_attr = bool(grupo.incluir_cortesias)

        if ano is None:
            ano = _resolve_default_ano_for_grupo(db, grupo_nome, datetime.now().year)
        
        detail_cache_key = f"{ano}_{evento_id}_detail"
        if not force_refresh:
            cached_detail, is_stale = event_detail_cache.get_or_revalidate(detail_cache_key, refresh_fn=None)
            if cached_detail is not None:
                # Validate that cached data has a non-empty event date.
                # Entries cached before DimProjeto was synced may have date="" which
                # causes NaN/missing info on the frontend.
                # Strategy: return stale data immediately (avoids long blocking load)
                # and trigger a background refresh so the frontend re-fetches with
                # correct data in a few seconds (stale-while-revalidate pattern).
                _cached_evt = cached_detail.get("evento", {})
                _cached_date = (
                    _cached_evt.get("date", "") if isinstance(_cached_evt, dict)
                    else getattr(_cached_evt, "date", "")
                )
                # SWR trigger: recompute when _computed_at_date is missing or cache version is outdated.
                # Freshness is also owned by:
                #   (a) event_detail_cache.invalidate() called by sincronizar_hoje_batch after sync
                #   (b) SmartCache TTL-based SWR for natural expiry
                _cached_version = cached_detail.get("_cache_version")
                _needs_recompute = not _cached_date or _cached_version != _DETAIL_CACHE_VERSION
                if _needs_recompute:
                    if detail_cache_key not in _swr_recompute_in_progress:
                        reason = "empty date" if not _cached_date else f"version mismatch ({_cached_version} != {_DETAIL_CACHE_VERSION})"
                        logger.info(f"[Cache] event_detail '{detail_cache_key}' {reason} — serving stale + triggering background recompute")
                        _swr_recompute_in_progress.add(detail_cache_key)
                        import threading as _threading
                        _threading.Thread(target=_swr_detail_refresh, args=(detail_cache_key,), daemon=True).start()
                    else:
                        logger.info(f"[Cache] event_detail '{detail_cache_key}' SWR already in progress — skipping duplicate thread")
                    is_stale = True  # force stale header

                if response is not None:
                    response.headers["X-Data-Stale"] = "true" if is_stale else "false"
                # Always inject current ultima_atualizacao_completa so frontend can detect stale event caches
                from app.core.cache import get_last_full_refresh as _get_lfr
                _lfr_ts = _get_lfr()
                _lfr_str = (
                    datetime.fromtimestamp(_lfr_ts, tz=ZoneInfo('America/Sao_Paulo')).isoformat()
                    if _lfr_ts else None
                )
                result_hit = {k: v for k, v in cached_detail.items() if k != "__is_completed"}
                result_hit["ultima_atualizacao_completa"] = _lfr_str
                # Force cacheTime < systemRefresh so frontend's stale check triggers a silent re-fetch
                if _needs_recompute:
                    result_hit["ultima_atualizacao"] = "2000-01-01T00:00:00-03:00"
                # Always fetch commercial actions fresh (never from cache)
                _ca_pids = [p["id"] for p in result_hit.get("projetos_vinculados", [])]
                if not _ca_pids:
                    try:
                        _ca_pids = [int(evento_id)]
                    except (ValueError, TypeError):
                        pass
                result_hit["commercialActions"] = _fetch_commercial_actions_from_db(db, _ca_pids)
                # Sempre injeta faixas_preco_site frescas do banco para refletir edições no cadastro.
                if _ca_pids:
                    try:
                        result_hit["faixas_preco_site"] = _get_faixas_preco_site_for_projeto_ids(db, _ca_pids)
                    except Exception as _fps_e2:
                        logger.warning(f"[Cache] faixas_preco_site refresh falhou: {_fps_e2}")
                return result_hit

        # Concurrent computation guard: if another request is already computing this
        # event detail, wait for it instead of launching a duplicate Magento query.
        _should_compute = True
        _wait_computing_event = None
        if not force_refresh:
            with _event_computing_lock:
                if detail_cache_key in _event_computing_events:
                    _wait_computing_event = _event_computing_events[detail_cache_key]
                else:
                    _compute_done_event = _threading_module.Event()
                    _event_computing_events[detail_cache_key] = _compute_done_event

        if _wait_computing_event is not None:
            logger.info(f"[Cache] event_detail '{detail_cache_key}' being computed by another thread — waiting (max 5min)")
            _wait_computing_event.wait(timeout=300)
            # Try cache now that the other thread finished
            _cached2, _ = event_detail_cache.get_or_revalidate(detail_cache_key, refresh_fn=None)
            if _cached2 is not None:
                from app.core.cache import get_last_full_refresh as _get_lfr2
                _lfr_ts2 = _get_lfr2()
                _lfr_str2 = datetime.fromtimestamp(_lfr_ts2, tz=ZoneInfo('America/Sao_Paulo')).isoformat() if _lfr_ts2 else None
                _res2 = {k: v for k, v in _cached2.items() if k != "__is_completed"}
                _res2["ultima_atualizacao_completa"] = _lfr_str2
                _ca_pids2 = [p["id"] for p in _res2.get("projetos_vinculados", [])]
                if not _ca_pids2:
                    try:
                        _ca_pids2 = [int(evento_id)]
                    except (ValueError, TypeError):
                        pass
                _res2["commercialActions"] = _fetch_commercial_actions_from_db(db, _ca_pids2)
                return _res2
            # Computing thread failed or timed out — fall through to compute ourselves
            with _event_computing_lock:
                if detail_cache_key not in _event_computing_events:
                    _compute_done_event = _threading_module.Event()
                    _event_computing_events[detail_cache_key] = _compute_done_event
            _should_compute = True

        mappings = _wq_sku_mappings_by_grupo_single_year(db, grupo_nome, ano)
        
        skus = [m.sku for m in mappings]
        
        proj_skus = list(set(m.sku for m in mappings))
        projetos_raw = _wq_dim_projetos_by_codigos(db, proj_skus)
        seen_proj_ids = set()
        projetos = []
        for p in projetos_raw:
            if p.id not in seen_proj_ids:
                seen_proj_ids.add(p.id)
                projetos.append(p)
        
        latest_date = None
        rep_projeto = projetos[0] if projetos else None
        for p in projetos:
            if p.data_evento:
                if latest_date is None or p.data_evento > latest_date:
                    latest_date = p.data_evento
                    rep_projeto = p
        
        total_capacity = get_meta_orcada_projetos(db, projetos)
        projeto_data_evento = latest_date
        dias_enc = get_dias_encerramento(db, projeto_id=rep_projeto.id) if rep_projeto else 2
        d_minus_inscricoes = calculate_d_minus(projeto_data_evento, reference_year=ano, dias_encerramento=dias_enc) if projeto_data_evento else 0
        d_minus = calculate_d_minus(projeto_data_evento, reference_year=ano, dias_encerramento=0) if projeto_data_evento else 0
        is_active = d_minus_inscricoes > 0 if ano == datetime.now().year else True
        sales_goal = total_capacity
        
        data_fim_inscricoes = projeto_data_evento - timedelta(days=dias_enc) if projeto_data_evento else None
        detail_regime = get_data_regime(projeto_data_evento, dias_enc) if projeto_data_evento else "live"
        
        detail_hist_pattern = None
        detail_curva_info = {"tipo_curva": "linear", "fonte_curva": None, "ano_referencia": None}
        _rep_estado = str(rep_projeto.estado) if rep_projeto and rep_projeto.estado else None
        try:
            detail_hist_pattern, detail_curva_info = _resolve_hist_pattern(db, grupo_nome, ano, estado=_rep_estado)
        except Exception:
            pass
        
        current_year = datetime.now().year
        if force_refresh and ano == current_year and detail_regime != "consolidated":
            _should_rebuild = True
            try:
                from ...models.vendas_snapshot import VendasDiariaSnapshot as _VDS
                # Cooldown restrito ao ano-edição: sem isso, atualizar a edição
                # anterior do mesmo grupo (ex.: 2025) bloqueia o rebuild da
                # edição atual (2026) por 10min — cross-edition cooldown.
                _last_updated = db.query(func.max(_VDS.updated_at)).filter(
                    _VDS.evento_grupo == grupo_nome,
                    _VDS.ano == ano,
                ).scalar()
                if _last_updated and (datetime.now() - _last_updated).total_seconds() < 600:
                    _should_rebuild = False
                    logger.info(f"Snapshot cooldown: '{grupo_nome}' atualizado há {(datetime.now() - _last_updated).total_seconds():.0f}s, pulando rebuild")
            except Exception:
                pass
            if _should_rebuild:
                try:
                    from ...services.snapshot_service import consolidar_vendas_grupo, _snapshot_lookback_days
                    # incremental=True + lookback_days: reprocessa janela rolante
                    # (default 7 dias) para corrigir snapshots parciais (ex: Magento
                    # em timeout quando o dia foi gravado pela primeira vez). Sem o
                    # lookback, o botão "Reconsolidar" só busca dias > max_dia e
                    # nunca corrige um dia antigo que ficou com valor errado.
                    # Mesmo comportamento do batch noturno das 04h BRT.
                    _lb = _snapshot_lookback_days()
                    consolidar_vendas_grupo(db, grupo_nome, ano, incremental=True, lookback_days=_lb)
                    logger.info(f"Snapshot atualizado incremental+lookback={_lb} (force_refresh) para '{grupo_nome}' ano={ano}")
                except Exception as _e:
                    logger.warning(f"Falha ao reconstruir snapshot para '{grupo_nome}': {_e}")
        elif detail_regime == "consolidated" and ano == current_year:
            _existing_snap = _get_snapshot_metrics_for_grupo(db, grupo_nome, ano=ano)
            if not _existing_snap:
                logger.info(f"[Hybrid] Evento '{grupo_nome}' é consolidated sem snapshot — construindo")
                try:
                    from ...services.snapshot_service import consolidar_vendas_grupo
                    # Sem snapshot prévio: incremental=True cai para full rebuild automaticamente.
                    consolidar_vendas_grupo(db, grupo_nome, ano, incremental=True)
                    logger.info(f"Snapshot construído (consolidated, sem snapshot) para '{grupo_nome}' ano={ano}")
                except Exception as _e:
                    logger.warning(f"Falha ao construir snapshot consolidated para '{grupo_nome}': {_e}")
            else:
                logger.info(f"[Hybrid] Evento '{grupo_nome}' é consolidated — snapshot existente, pulando rebuild")

        # When normalized-ISC mode is ON, also use the normalized historical pattern
        # for the per-day expected curve so visualizations compare normalized current
        # sales against a normalized reference (apples-to-apples).
        _detail_hist_for_daily = detail_hist_pattern
        if isc_cfg.get("useNormalizedCurveForISC", False):
            try:
                _norm_pat_daily, _ = _resolve_hist_pattern(db, grupo_nome, ano, estado=_rep_estado, use_normalized=True)
                if _norm_pat_daily:
                    _detail_hist_for_daily = _norm_pat_daily
            except Exception as _e_norm_daily:
                logger.warning(f"Falha ao obter hist_pattern normalizado p/ daily curve: {_e_norm_daily}")
        daily_sales_list = fetch_real_daily_sales_for_projetos(db, projetos, sales_goal=sales_goal, ano=ano, evento_grupo=grupo_nome, data_evento=data_fim_inscricoes, preloaded_hist_pattern=_detail_hist_for_daily, data_evento_real=projeto_data_evento, force_magento_refresh=force_magento_refresh)

        # ── Snapshot como piso de segurança para dailySales ───────────────
        # Carrega o snapshot consolidado (vendas_diaria_snapshot) uma vez por
        # request. É uma consulta PG indexada (grupo_nome+ano) — barata o
        # suficiente para rodar sempre. Em troca ganhamos robustez total:
        # mesmo nos casos raros em que a carga interna do snapshot dentro de
        # `fetch_real_daily_sales_for_projetos` falhar silenciosamente, o piso
        # ainda se aplica. O merge abaixo só dispara quando há divergência
        # real (snapshot_total > live_total + 5), então o overhead em fluxo
        # saudável é só a leitura. Filosofia: mesma do MargemBundleRevSnapshot
        # (GREATEST) e do currentSales alignment documentados no replit.md —
        # o valor só pode subir, nunca cair.
        if grupo_nome:
            try:
                from ...services.snapshot_service import get_snapshot_vendas as _gsv_fallback
                _fb_snap = _gsv_fallback(db, grupo_nome, data_fim=today_brazil(), ano=ano)
            except Exception as _fb_load_e:
                logger.warning(f"[DailySales] Falha ao carregar snapshot p/ fallback '{grupo_nome}': {_fb_load_e}")
                _fb_snap = None
        else:
            _fb_snap = None

        if grupo_nome:

            # ── Caso 1: live vazio ────────────────────────────────────────
            if not daily_sales_list:
                try:
                    if _fb_snap:
                        logger.warning(f"[DailySales] Fallback: daily_sales_list vazio para '{grupo_nome}' mas snapshot tem {len(_fb_snap)} dias — reconstruindo do snapshot")
                        _fb_today = today_brazil()
                        _fb_earliest = min(_fb_snap.keys())
                        _fb_latest = max(_fb_snap.keys())
                        _fb_end = _fb_today if (_fb_today - _fb_latest).days <= 30 else _fb_latest
                        _fb_start = _fb_earliest
                        _fb_dates = [_fb_start + timedelta(days=i) for i in range((_fb_end - _fb_start).days + 1)]
                        _fb_cum = 0
                        _fb_goal = sales_goal or 1000
                        _fb_total = len(_fb_dates)
                        _fb_result = []
                        for _fd in _fb_dates:
                            _fs = _fb_snap.get(_fd, 0)
                            _fb_cum += _fs
                            _fb_exp = round(_fb_goal / _fb_total, 1) if _fb_total > 0 else 0
                            _fb_dm = (data_fim_inscricoes - _fd).days if data_fim_inscricoes else None
                            _fb_result.append({
                                "date": _fd.isoformat(),
                                "sales": _fs,
                                "expected": _fb_exp,
                                "cumulativeSales": _fb_cum,
                                "cumulativeExpected": round(_fb_exp * (_fb_dates.index(_fd) + 1), 1),
                                "dMinus": _fb_dm,
                                "curvaAnoAnterior": None,
                                "dif": round(_fb_cum - _fb_exp * (_fb_dates.index(_fd) + 1), 1),
                                "atingimentoAcumulado": 0.0,
                                "atingimentoDiario": 0.0,
                                "normalizedSales": _fs,
                                "cumulativeNormalized": _fb_cum,
                                "localMedian": None,
                                "outlierLimit": None,
                                "isOutlier": False,
                                "excessRemoved": 0,
                                "excessReceived": 0,
                            })
                        daily_sales_list = _fb_result
                    else:
                        # Sem snapshot algum — garante pelo menos a linha de hoje com 0
                        logger.warning(f"[DailySales] Sem snapshot e sem daily_sales para '{grupo_nome}' — injetando linha de hoje com 0")
                        _fb_today = today_brazil()
                        _fb_exp = round((sales_goal or 1000) / 1, 1)
                        daily_sales_list = [{
                            "date": _fb_today.isoformat(),
                            "sales": 0,
                            "expected": _fb_exp,
                            "cumulativeSales": 0,
                            "cumulativeExpected": _fb_exp,
                            "dMinus": (data_fim_inscricoes - _fb_today).days if data_fim_inscricoes else None,
                            "curvaAnoAnterior": None,
                            "dif": round(-_fb_exp, 1),
                            "atingimentoAcumulado": -100.0,
                            "atingimentoDiario": -100.0,
                            "normalizedSales": 0,
                            "cumulativeNormalized": 0,
                            "localMedian": None,
                            "outlierLimit": None,
                            "isOutlier": False,
                            "excessRemoved": 0,
                            "excessReceived": 0,
                        }]
                except Exception as _fb_e:
                    logger.warning(f"[DailySales] Fallback de snapshot falhou para '{grupo_nome}': {_fb_e}")

            # ── Caso 2: live veio incompleto (total < snapshot) ───────────
            # Merge per-day pegando o MAX entre live e snapshot. Preserva os
            # campos cosméticos do live (expected, curvaAnoAnterior, etc) e
            # apenas eleva sales/cumulativeSales nas datas afetadas. Também
            # adiciona dias que só existem no snapshot (live com janela mais
            # curta por timeout/parcial), reordenando ao final.
            elif _fb_snap:
                try:
                    _live_total = sum(float(d.get('sales') or 0) for d in daily_sales_list)
                    _snap_total = sum(float(v or 0) for v in _fb_snap.values())
                    # Threshold de 5 inscrições evita ruído por arredondamento
                    # ou última hora; diferenças maiores indicam resposta parcial.
                    if _snap_total > _live_total + 5:
                        _today_local = today_brazil()
                        # União de datas: linhas existentes do live + dias do
                        # snapshot (<= hoje) que estão faltando. Garante que
                        # janelas live truncadas sejam estendidas.
                        _live_by_date: dict = {}
                        for _row in daily_sales_list:
                            try:
                                _rd = date.fromisoformat(_row['date'])
                                _live_by_date[_rd] = _row
                            except Exception:
                                pass
                        _missing_dates = [d for d in _fb_snap.keys() if d <= _today_local and d not in _live_by_date]
                        for _md in _missing_dates:
                            _snap_v = float(_fb_snap.get(_md, 0) or 0)
                            _dm = (data_fim_inscricoes - _md).days if data_fim_inscricoes else None
                            _new_row = {
                                "date": _md.isoformat(),
                                "sales": _snap_v,
                                "expected": 0.0,
                                "cumulativeSales": 0.0,
                                "cumulativeExpected": 0.0,
                                "dMinus": _dm,
                                "curvaAnoAnterior": None,
                                "dif": 0.0,
                                "atingimentoAcumulado": 0.0,
                                "atingimentoDiario": 0.0,
                                "normalizedSales": _snap_v,
                                "cumulativeNormalized": 0.0,
                                "localMedian": None,
                                "outlierLimit": None,
                                "isOutlier": False,
                                "excessRemoved": 0,
                                "excessReceived": 0,
                            }
                            daily_sales_list.append(_new_row)
                            _live_by_date[_md] = _new_row
                        # Reordena por data antes de recomputar cumulativos.
                        daily_sales_list.sort(key=lambda r: r.get('date', ''))

                        _raised_days = 0
                        _added_days = len(_missing_dates)
                        _cum_sales = 0.0
                        _cum_norm = 0.0
                        for _row in daily_sales_list:
                            try:
                                _row_date = date.fromisoformat(_row['date'])
                            except Exception:
                                continue
                            _live_s = float(_row.get('sales') or 0)
                            _snap_s = float(_fb_snap.get(_row_date, 0) or 0)
                            # Snapshot só é piso confiável p/ datas <= hoje
                            # (datas futuras não foram persistidas pelo job).
                            if _row_date <= _today_local and _snap_s > _live_s:
                                _row['sales'] = _snap_s
                                # normalizedSales acompanha o piso (sem
                                # recomputar mediana local aqui — coerência
                                # mínima já basta). Usa float p/ não truncar.
                                if float(_row.get('normalizedSales') or 0) < _snap_s:
                                    _row['normalizedSales'] = _snap_s
                                _raised_days += 1
                            _cum_sales += float(_row.get('sales') or 0)
                            _cum_norm += float(_row.get('normalizedSales') or 0)
                            _row['cumulativeSales'] = _cum_sales
                            _row['cumulativeNormalized'] = _cum_norm
                            # Recalcula dif/atingimentoAcumulado com o novo cum.
                            _row_exp_cum = float(_row.get('cumulativeExpected') or 0)
                            _row['dif'] = round(_cum_sales - _row_exp_cum, 1)
                            if _row_exp_cum > 0:
                                _row['atingimentoAcumulado'] = round((_cum_sales / _row_exp_cum - 1.0) * 100, 1)
                        logger.warning(f"[DailySales] Resposta parcial detectada p/ '{grupo_nome}': live={_live_total:.0f} < snapshot={_snap_total:.0f} — snapshot aplicado como piso em {_raised_days} dia(s), {_added_days} dia(s) adicionados")
                except Exception as _merge_e:
                    logger.warning(f"[DailySales] Merge snapshot-floor falhou para '{grupo_nome}': {_merge_e}")

        daily_sales_dict = {date.fromisoformat(d['date']): d['sales'] for d in daily_sales_list}
        
        _today_detail = today_brazil()
        current_sales = 0
        if daily_sales_dict and len(daily_sales_dict) > 0:
            current_sales = sum(v for k, v in daily_sales_dict.items() if k <= _today_detail)
        
        if ano == current_year and detail_regime == "consolidated":
            snap = _get_snapshot_metrics_for_grupo(db, grupo_nome, ano=ano)
            if snap is not None:
                current_receita = snap['receita_liquida_site']
                if current_sales == 0:
                    current_sales = snap['qtd_site']
            else:
                isc_data = fetch_isc_pricing_data(db=db)
                current_receita = 0.0
                seen_norms = set()
                for s_sku in skus:
                    s_norm = normalize_sku(s_sku)
                    if s_norm in seen_norms:
                        continue
                    seen_norms.add(s_norm)
                    info = isc_data.get(s_norm, {})
                    current_receita += info.get('receita_liquida_site', 0.0)
            grupo_media_14d = 0.0
            grupo_media_7d = 0.0
            grupo_media_30d = 0.0
        elif ano == current_year:
            isc_data = fetch_isc_pricing_data(db=db)
            current_receita = 0.0
            current_sales_isc = 0  # from ISC cache, same source as list view
            grupo_media_14d = 0.0
            grupo_media_7d = 0.0
            grupo_media_30d = 0.0
            seen_norms = set()
            for s_sku in skus:
                s_norm = normalize_sku(s_sku)
                if s_norm in seen_norms:
                    continue
                seen_norms.add(s_norm)
                info = isc_data.get(s_norm, {})
                current_receita += info.get('receita_liquida_site', 0.0)
                current_sales_isc += info.get('qtd_site', 0)
                grupo_media_14d += info.get('media_14d', 0.0)
                grupo_media_7d += info.get('media_7d', 0.0)
                grupo_media_30d += info.get('media_30d', 0.0)
            # Align current_sales with ISC cache so ISC calc is identical to list view.
            # Take the higher value: ISC cache (snapshot-based, updated every 30 min) vs
            # daily_sales live query (which may include inscriptions made since last sync).
            # Using max() ensures new inscriptions made after the last auto-sync are visible.
            if current_sales_isc > current_sales:
                current_sales = current_sales_isc
        else:
            ativo_ids = [str(m.id_externo) for m in mappings if m.fonte == 'ATIVO' and m.id_externo]
            magento_ids = [str(m.id_externo) for m in mappings if m.fonte == 'MAGENTO' and m.id_externo]
            
            current_receita = 0.0
            
            if ativo_ids:
                ativo_rows = _fetch_daily_sales_ativo_by_ids(list(set(ativo_ids)))
                for row in ativo_rows:
                    current_receita += row.get('receita', 0.0)
            
            if magento_ids:
                _cort_det = _get_cortesia_magento_ids(db)
                _mag_cort_det = set(magento_ids) & _cort_det if _cort_det else None
                magento_rows = _fetch_daily_sales_magento_by_ids(list(set(magento_ids)), cortesia_magento_ids=_mag_cort_det if _mag_cort_det else None, db=db, ano=ano, force_magento_refresh=force_magento_refresh)
                for row in magento_rows:
                    current_receita += row.get('receita', 0.0)
            
            grupo_media_14d = 0.0
            grupo_media_7d = 0.0
            grupo_media_30d = 0.0
        
        # ── Snapshot-first: âncora estável do total de inscritos ─────────────
        # Para eventos do ano corrente ainda NÃO concluídos (regime hybrid/live),
        # o total de inscritos deve ter como PISO o snapshot consolidado
        # (vendas_diaria_snapshot, atualizado no batch noturno + sincronizar_hoje) —
        # a MESMA fonte da curva diária. Resolve o caso em que a leitura ao vivo /
        # ISC-cache vem parcial (ex.: Night Run Campo Grande exibindo 1.594 enquanto
        # o snapshot já tem 1.872) e elimina a oscilação: sem venda nova, o número
        # servido é sempre o do snapshot. O piso só SOBE (nunca rebaixa) e a leitura
        # ao vivo de hoje (já aplicada em daily_sales_list acima) pode elevá-lo.
        # NÃO se aplica a eventos consolidados (concluídos): esses usam a correção
        # autoritativa PARA BAIXO (force_magento_refresh + leitura verificada) e não
        # podem ser re-inflados pelo snapshot — cf. Eco Run - Pederneiras.
        if ano == current_year and detail_regime != "consolidated" and grupo_nome:
            try:
                _snap_base = _get_snapshot_metrics_for_grupo(db, grupo_nome, ano=ano)
            except Exception as _sb_e:
                logger.warning(f"[SnapshotFirst] Falha ao ler snapshot base '{grupo_nome}': {_sb_e}")
                _snap_base = None
            if _snap_base:
                _snap_qty = int(_snap_base.get('qtd_site') or 0)
                _snap_rev = float(_snap_base.get('receita_liquida_site') or 0.0)
                if _snap_qty > current_sales:
                    logger.info(
                        f"[SnapshotFirst] '{grupo_nome}': ancorando currentSales "
                        f"{current_sales} → {_snap_qty} (piso do snapshot consolidado)"
                    )
                    current_sales = _snap_qty
                    # Receita em lockstep para o ticket médio permanecer coerente.
                    if _snap_rev > current_receita:
                        current_receita = _snap_rev

        avg_ticket = round(current_receita / current_sales, 2) if current_sales > 0 else 0.0
        detail_bt_total_receita = 0.0
        detail_bt_total_qtd = 0
        for p in projetos:
            detail_cad = _wq_cadastro_by_projeto_id(db, p.id)
            if detail_cad and detail_cad.atletas_site_tkt_medio and detail_cad.atletas_site_pago:
                detail_bt_total_receita += float(detail_cad.atletas_site_tkt_medio) * int(detail_cad.atletas_site_pago)
                detail_bt_total_qtd += int(detail_cad.atletas_site_pago)
        detail_budget_ticket = round(detail_bt_total_receita / detail_bt_total_qtd, 2) if detail_bt_total_qtd > 0 else 0.0
        # Use ISC cache medias for the ISC component calculation so that the
        # detail view produces the same ISC value as the list view (consistency).
        # When normalized-ISC mode is ON, the normalized run instead uses
        # daily_sales_dict + a freshly-rebuilt normalized hist_pattern so the
        # flag actually affects curvaDPercent.
        _has_cache_medias = (grupo_media_14d > 0 or grupo_media_7d > 0)
        _use_norm_isc = isc_cfg.get("useNormalizedCurveForISC", False)
        detail_hist_pattern_norm = detail_hist_pattern
        if _use_norm_isc:
            try:
                _norm_pat, _ = _resolve_hist_pattern(db, grupo_nome, ano, estado=_rep_estado, use_normalized=True)
                if _norm_pat:
                    detail_hist_pattern_norm = _norm_pat
            except Exception as _e_norm_hist:
                logger.warning(f"Falha ao obter hist_pattern normalizado (detail group): {_e_norm_hist}")
        if _use_norm_isc:
            # In normalized mode, prefer daily_sales_dict so progress_percent + curvaD
            # are computed on the smoothed series (IA/rolling become daily-derived too,
            # which is the correct behavior for the normalized comparison value).
            isc_components = calculate_isc_components(
                current_sales, sales_goal, d_minus_inscricoes,
                daily_sales_dict=daily_sales_dict,
                hist_pattern=detail_hist_pattern_norm,
                registration_close_date=data_fim_inscricoes,
                curva_info=detail_curva_info,
                use_normalized_curve=True)
        elif _has_cache_medias:
            isc_components = calculate_isc_components(
                current_sales, sales_goal, d_minus_inscricoes,
                media_7d=grupo_media_7d if grupo_media_7d > 0 else None,
                media_14d=grupo_media_14d if grupo_media_14d > 0 else None,
                media_30d=grupo_media_30d if grupo_media_30d > 0 else None,
                hist_pattern=detail_hist_pattern,
                registration_close_date=data_fim_inscricoes,
                curva_info=detail_curva_info,
                use_normalized_curve=False)
        else:
            isc_components = calculate_isc_components(current_sales, sales_goal, d_minus_inscricoes,
                                                       daily_sales_dict=daily_sales_dict,
                                                       hist_pattern=detail_hist_pattern,
                                                       registration_close_date=data_fim_inscricoes,
                                                       curva_info=detail_curva_info,
                use_normalized_curve=False)
        isc = calculate_isc(isc_components, isc_cfg["ia730Weight"], isc_cfg["curvaDWeight"], isc_cfg["rolling14dWeight"])
        isc_raw: Optional[float] = None
        # Always compute BOTH raw and normalized component sets so the frontend
        # "Normalizar Meta" toggle can switch between them (Curva D-%, IA, Rolling).
        # Using daily_sales_dict for both keeps the only difference being the
        # normalization itself (smoothing + normalized hist_pattern).
        isc_components_raw_alt: Optional[ISCComponents] = None
        isc_components_norm_alt: Optional[ISCComponents] = None
        try:
            isc_components_raw_alt = calculate_isc_components(
                current_sales, sales_goal, d_minus_inscricoes,
                daily_sales_dict=daily_sales_dict,
                hist_pattern=detail_hist_pattern,
                registration_close_date=data_fim_inscricoes,
                curva_info=detail_curva_info,
                use_normalized_curve=False)
        except Exception as _e_raw:
            logger.warning(f"Falha ao calcular iscComponentsRaw (detail group): {_e_raw}")
        try:
            isc_components_norm_alt = calculate_isc_components(
                current_sales, sales_goal, d_minus_inscricoes,
                daily_sales_dict=daily_sales_dict,
                hist_pattern=detail_hist_pattern_norm or detail_hist_pattern,
                registration_close_date=data_fim_inscricoes,
                curva_info=detail_curva_info,
                use_normalized_curve=True)
        except Exception as _e_norm:
            logger.warning(f"Falha ao calcular iscComponentsNormalized (detail group): {_e_norm}")
        if _use_norm_isc and isc_components_raw_alt is not None:
            try:
                isc_raw = calculate_isc(isc_components_raw_alt, isc_cfg["ia730Weight"], isc_cfg["curvaDWeight"], isc_cfg["rolling14dWeight"])
            except Exception as _e_raw_isc:
                logger.warning(f"Falha ao calcular iscRaw para evento (detail group): {_e_raw_isc}")
        isc_status = get_isc_status(isc, isc_cfg["greenThreshold"], isc_cfg["yellowThreshold"])
        suggested_action = get_suggested_action(isc, d_minus_inscricoes, isc_cfg["greenThreshold"], isc_cfg["yellowThreshold"], isc_cfg["promotionDeadline"])
        
        projeto_modalidade = str(rep_projeto.modalidade) if rep_projeto and rep_projeto.modalidade else None
        projeto_cidade = str(rep_projeto.cidade) if rep_projeto and rep_projeto.cidade else None
        projeto_estado = str(rep_projeto.estado) if rep_projeto and rep_projeto.estado else None
        
        detail_kit_ids = [p.id for p in projetos]
        detail_kit_costs = get_kit_basico_costs_batch(db, detail_kit_ids) if detail_kit_ids else {}
        detail_kit_w_num = 0.0
        detail_kit_w_den = 0
        for p in projetos:
            p_cad_d = _wq_cadastro_by_projeto_id(db, p.id)
            p_cap_d = get_meta_from_cadastro(p_cad_d) if p_cad_d else get_meta_orcada(db, p.id)
            p_kc_d = detail_kit_costs.get(p.id, 50.0)
            detail_kit_w_num += p_kc_d * p_cap_d
            detail_kit_w_den += p_cap_d
        detail_kit_cost_avg = (detail_kit_w_num / detail_kit_w_den) if detail_kit_w_den > 0 else 50.0
        detail_margin = _calc_margin_fields(detail_budget_ticket, detail_kit_cost_avg, sales_goal,
                                             avg_ticket, current_sales, current_receita)
        
        detail_ticket_atual_map = _get_ticket_atual_map(db)
        detail_ticket_atual = _get_ticket_atual_for_event(detail_ticket_atual_map, [p.id for p in projetos])
        detail_ticket_kit_nome = _get_ticket_atual_kit_nome_for_event(detail_ticket_atual_map, [p.id for p in projetos])
        
        grupo_projeto_ids = [p.id for p in projetos]
        _grupo_incluir_cortesias = _grupo_incluir_cortesias_attr
        _detail_margem_avisos: list = []
        _detail_margem_meta: dict = {}
        detail_margem_por_kit = get_margem_por_kit(
            db,
            grupo_projeto_ids,
            ano=ano,
            card_total_qty=current_sales,
            card_total_receita=current_receita,
            card_kit_cost_avg=detail_kit_cost_avg,
            avisos_out=_detail_margem_avisos,
            force_refresh=force_refresh or force_magento_refresh,
            incluir_cortesias=_grupo_incluir_cortesias,
            meta_out=_detail_margem_meta,
        )
        # Align currentSales with the kit table total so the card and the
        # "Margem por Tipo de Kit" table always display the same number of athletes.
        # The kit table counts only Magento bundles registered in KitConfig; the
        # snapshot/ISC-cache count is broader. ISC was already calculated above, so
        # changing current_sales here does NOT affect the displayed ISC value.
        # GUARDA: nunca rebaixar current_sales abaixo do que o snapshot+sync_hoje
        # já conhece. O snapshot consolidado (atualizado às 4h + sincronizar_hoje
        # ao longo do dia) é piso confiável; a tabela de kits pode flutuar para
        # baixo quando o Magento responde parcial sem lançar exceção. Só
        # ajustamos para CIMA quando a tabela enxerga vendas mais novas.
        _kit_rows_aligned = [r for r in (detail_margem_por_kit or []) if r.get('tipoKit') != 'CONSOLIDADO']
        _kit_total_qty_aligned = sum(int(r.get('qtd', 0) or 0) for r in _kit_rows_aligned)
        # Sinal de "leitura ao vivo verificadamente completa": só uma leitura que
        # foi realmente buscada no Magento (count E receita == "live"), sem avisos
        # de resposta parcial/stale e sem tabela degradada, autoriza BAIXAR o
        # valor de um evento concluído. Em qualquer outro caso (cache/snapshot/
        # parcial/cooldown), preservamos o piso — exatamente como hoje.
        # A correção autoritativa PARA BAIXO só faz sentido em evento CONCLUÍDO
        # (regime consolidated): aí a tabela de kits (bundles Magento mapeados) é
        # autoritativa. Em evento ainda em venda (live/hybrid) o total legítimo
        # pode exceder a tabela de kits (Ativo + bundles não mapeados), então uma
        # leitura Magento parcial "verificada" não pode rebaixar o snapshot-first.
        _live_read_verified_complete = bool(
            force_magento_refresh
            and detail_regime == "consolidated"
            and _detail_margem_meta.get("count_source") == "live"
            and _detail_margem_meta.get("revenue_source") == "live"
            and not _detail_margem_avisos
            and not _margem_por_kit_is_degraded(detail_margem_por_kit)
            and _kit_total_qty_aligned > 0
        )
        # Flag de baixa autoritativa: quando True, afrouxa os guards de "só sobe"
        # (Guard B / piso de margem) mais abaixo, para que o valor corrigido
        # persista mesmo em evento concluído/congelado.
        _authoritative_downcorrect = False
        if _kit_total_qty_aligned > current_sales:
            logger.info(
                f"[Detalhe] Alinhando currentSales '{grupo_nome}': {current_sales} → {_kit_total_qty_aligned} "
                f"(diff={current_sales - _kit_total_qty_aligned})"
            )
            current_sales = _kit_total_qty_aligned
            avg_ticket = round(current_receita / current_sales, 2) if current_sales > 0 else avg_ticket
            detail_margin = _calc_margin_fields(detail_budget_ticket, detail_kit_cost_avg, sales_goal,
                                                 avg_ticket, current_sales, current_receita)
        elif _kit_total_qty_aligned > 0 and _kit_total_qty_aligned < current_sales:
            if _live_read_verified_complete:
                # CORREÇÃO AUTORITATIVA PARA BAIXO — leitura ao vivo verificada
                # completa. Executa sob o lock global de reconsolidação para que
                # nenhuma outra reconsolidação interleave e re-infle o evento.
                from .admin import _try_acquire_evento_slot, _release_evento_slot
                _adc_slot = str(evento_id)
                _adc_acq, _adc_waited, _adc_busy = _try_acquire_evento_slot(
                    _adc_slot, check_cooldown=False
                )
                if _adc_acq:
                    try:
                        logger.warning(
                            f"[Detalhe] CORREÇÃO AUTORITATIVA '{grupo_nome}': "
                            f"{current_sales} → {_kit_total_qty_aligned} "
                            f"(leitura ao vivo verificada completa; baixando inscritos inflados)"
                        )
                        current_sales = _kit_total_qty_aligned
                        avg_ticket = round(current_receita / current_sales, 2) if current_sales > 0 else avg_ticket
                        detail_margin = _calc_margin_fields(detail_budget_ticket, detail_kit_cost_avg, sales_goal,
                                                             avg_ticket, current_sales, current_receita)
                        _authoritative_downcorrect = True
                        # Persiste a contagem corrigida no snapshot de margem por
                        # bundle (escopado a este evento, ignorando freeze), para
                        # que a correção sobreviva e leituras futuras não re-inflem.
                        try:
                            _adc_bundle_ids = _bundle_ids_for_projetos(db, grupo_projeto_ids, ano=ano)
                            if _adc_bundle_ids:
                                from ...services.snapshot_service import (
                                    sincronizar_margem_bundle_rev_batch as _adc_smbr,
                                )
                                _adc_res = _adc_smbr(db, only_bundle_ids=_adc_bundle_ids)
                                logger.info(
                                    f"[Detalhe] sync escopado de margem '{grupo_nome}': {_adc_res}"
                                )
                            else:
                                logger.warning(
                                    f"[Detalhe] correção autoritativa '{grupo_nome}': nenhum bundle "
                                    f"mapeado encontrado — snapshot de margem não regenerado"
                                )
                        except Exception as _adc_sync_e:
                            logger.warning(
                                f"[Detalhe] sync escopado de margem '{grupo_nome}' falhou: {_adc_sync_e}"
                            )
                    finally:
                        _release_evento_slot(_adc_slot)
                else:
                    logger.info(
                        f"[Detalhe] Correção autoritativa adiada '{grupo_nome}': lock global ocupado "
                        f"(busy={_adc_busy}) — preservando piso do snapshot, usuário pode tentar de novo"
                    )
                    _adc_aviso = (
                        "Outra atualização está em andamento — o valor não foi corrigido agora. "
                        "Tente novamente em instantes."
                    )
                    if _adc_aviso not in _detail_margem_avisos:
                        _detail_margem_avisos.append(_adc_aviso)
            else:
                logger.info(
                    f"[Detalhe] Alinhamento ignorado '{grupo_nome}': kit_table={_kit_total_qty_aligned} "
                    f"< snapshot={current_sales} (provável resposta parcial Magento — preservando piso do snapshot)"
                )
                if force_magento_refresh:
                    # A tabela parcial mistura contagem ao vivo incompleta com
                    # receita de snapshot e SUBESTIMA a Margem Realizada exibida.
                    # Restaura a última tabela íntegra persistida, coerente com o
                    # piso do card que acabamos de preservar.
                    _prev_rows_partial = _load_prev_margem_rows(db, evento_id, ano)
                    if _prev_rows_partial:
                        _prev_qtd_partial = sum(
                            int(r.get('qtd', 0) or 0) for r in _prev_rows_partial
                            if isinstance(r, dict) and r.get('tipoKit') != 'CONSOLIDADO'
                        )
                        if _prev_qtd_partial >= _kit_total_qty_aligned:
                            logger.info(
                                f"[Detalhe] margemPorKit parcial '{grupo_nome}' substituída pela última "
                                f"íntegra persistida (qtd {_kit_total_qty_aligned} → {_prev_qtd_partial})"
                            )
                            detail_margem_por_kit = _prev_rows_partial
                    _adc_partial_aviso = (
                        "Leitura ao vivo veio incompleta — o total não foi corrigido para baixo. "
                        "Tente atualizar novamente em alguns instantes."
                    )
                    if _adc_partial_aviso not in _detail_margem_avisos:
                        _detail_margem_avisos.append(_adc_partial_aviso)

        detail_consistency_warning = None  # aligned above; retained field for API compatibility
        detail_detalhe_vendas = []
        detail_kit_query_failed = False
        if detail_regime == "consolidated":
            detail_detalhe_ativo = []
        else:
            detail_detalhe_ativo = get_detalhe_vendas_ativo(db, grupo_projeto_ids, ano=ano)
        
        # Um único banner claro no painel de margem (era possível acumular
        # AVISO de instabilidade + INFO de idade do snapshot + mensagem de
        # leitura parcial, todos descrevendo o mesmo estado).
        _detail_margem_avisos = _consolidate_margem_avisos(_detail_margem_avisos)

        evento = MarketingEvent(
            id=evento_id,
            name=_grupo_nome_attr,
            date=projeto_data_evento.isoformat() if projeto_data_evento else "",
            location=projeto_cidade or projeto_estado or "Não definido",
            category=projeto_modalidade or "Corrida",
            totalCapacity=sales_goal,
            currentSales=current_sales,
            salesGoal=sales_goal,
            averageTicket=round(avg_ticket, 2),
            budgetTicket=detail_budget_ticket,
            dMinus=d_minus,
            dMinusInscricoes=d_minus_inscricoes,
            isc=isc,
            iscRaw=isc_raw,
            iscComponents=isc_components,
            iscComponentsRaw=isc_components_raw_alt,
            iscComponentsNormalized=isc_components_norm_alt,
            iscStatus=isc_status,
            suggestedAction=suggested_action,
            isActive=is_active,
            sku=",".join(skus),
            ticketAtual=detail_ticket_atual,
            ticketKitNome=detail_ticket_kit_nome,
            margemPorKit=detail_margem_por_kit if detail_margem_por_kit else None,
            margemAvisos=_detail_margem_avisos if _detail_margem_avisos else None,
            consistencyWarning=detail_consistency_warning,
            kitQueryFailed=detail_kit_query_failed,
            detalheVendasPorKit=detail_detalhe_vendas if detail_detalhe_vendas else None,
            detalheVendasAtivoKit=detail_detalhe_ativo if detail_detalhe_ativo else None,
            dataRegime=detail_regime,
            incluirCortesias=_grupo_incluir_cortesias,
            **detail_margin
        )
        
        daily_sales = daily_sales_list
        
        from ...models.dimensoes import AcaoComercial
        commercial_actions = []
        projeto_ids = [p.id for p in projetos]
        if projeto_ids:
            acoes = db.query(AcaoComercial).filter(
                AcaoComercial.projeto_id.in_(projeto_ids)
            ).order_by(AcaoComercial.data_acao.desc()).all()
            
            for a in acoes:
                tipo_map = {
                    'AUMENTO_PRECO': 'price_increase',
                    'REDUCAO_PRECO': 'price_decrease',
                    'PROMOCAO': 'promotion',
                    'CAMPANHA': 'campaign',
                    'COMUNICACAO': 'communication'
                }
                impacto = calculate_action_impact(db, a)
                impacto_percentual = impacto.get("impacto_percentual")
                vendas_antes = impacto.get("vendas_antes")
                vendas_depois = impacto.get("vendas_depois")
                impact_str = f"+{impacto_percentual}%" if impacto_percentual and impacto_percentual > 0 else (f"{impacto_percentual}%" if impacto_percentual is not None else None)
                commercial_actions.append({
                    "id": str(a.id),
                    "type": tipo_map.get(a.tipo, 'communication'),
                    "description": a.descricao,
                    "date": a.data_acao.isoformat() if a.data_acao else None,
                    "impact": impact_str,
                    "vendas_antes": vendas_antes,
                    "vendas_depois": vendas_depois,
                    "impacto_percentual": impacto_percentual,
                    "status_impacto": impacto.get("status", "calculado") if impacto_percentual is not None else "aguardando_dados",
                    "ponto_corte": a.ponto_corte,
                    "estagio": a.estagio,
                    "snapshot_isc": float(a.snapshot_isc) if a.snapshot_isc is not None else None,
                    "snapshot_isc_state": a.snapshot_isc_state,
                    "snapshot_d_minus": a.snapshot_d_minus,
                    "snapshot_ia730": float(a.snapshot_ia730) if a.snapshot_ia730 is not None else None,
                    "snapshot_rolling14d": float(a.snapshot_rolling14d) if a.snapshot_rolling14d is not None else None,
                    "snapshot_curva_percent": float(a.snapshot_curva_percent) if a.snapshot_curva_percent is not None else None,
                    "snapshot_vendas_acumuladas": a.snapshot_vendas_acumuladas,
                    "snapshot_playbook_letter": a.snapshot_playbook_letter,
                })
        
        ano_anterior = ano - 1
        mappings_anterior = _wq_sku_mappings_by_grupo_single_year(db, grupo_nome, ano_anterior)
        
        comparacao_anual = None
        if mappings_anterior:
            skus_anterior = [m.sku for m in mappings_anterior]
            
            vendas_anterior = 0
            receita_anterior = 0.0
            
            if ano_anterior == current_year:
                isc_data_comp = fetch_isc_pricing_data(db=db) if ano != current_year else isc_data
                seen_norms_ant = set()
                for s_sku in skus_anterior:
                    s_norm = normalize_sku(s_sku)
                    if s_norm in seen_norms_ant:
                        continue
                    seen_norms_ant.add(s_norm)
                    info = isc_data_comp.get(s_norm, {})
                    vendas_anterior += info.get('qtd_site', 0)
                    receita_anterior += info.get('receita_liquida_site', 0.0)
            else:
                ant_ativo_ids = [str(m.id_externo) for m in mappings_anterior if m.fonte == 'ATIVO' and m.id_externo]
                ant_magento_ids = [str(m.id_externo) for m in mappings_anterior if m.fonte == 'MAGENTO' and m.id_externo]
                if ant_ativo_ids:
                    for row in _fetch_daily_sales_ativo_by_ids(list(set(ant_ativo_ids))):
                        vendas_anterior += row.get('qtd', 0)
                        receita_anterior += row.get('receita', 0.0)
                if ant_magento_ids:
                    _cort_ant = _get_cortesia_magento_ids(db)
                    _mag_cort_ant = set(ant_magento_ids) & _cort_ant if _cort_ant else None
                    for row in _fetch_daily_sales_magento_by_ids(list(set(ant_magento_ids)), cortesia_magento_ids=_mag_cort_ant if _mag_cort_ant else None, db=db, ano=(ano - 1) if ano else None):
                        vendas_anterior += row.get('qtd', 0)
                        receita_anterior += row.get('receita', 0.0)
            
            proj_skus_anterior = [m.sku for m in mappings_anterior]
            projetos_anterior = _wq_dim_projetos_by_codigos(db, proj_skus_anterior)
            
            cap_anterior = get_meta_orcada_projetos(db, projetos_anterior)
            meta_anterior = cap_anterior
            ticket_anterior = round(receita_anterior / vendas_anterior, 2) if vendas_anterior > 0 else 0.0
            
            variacao_vendas = ((current_sales - vendas_anterior) / vendas_anterior * 100) if vendas_anterior > 0 else None
            
            comparacao_anual = {
                "ano_atual": ano,
                "ano_anterior": ano_anterior,
                "atual": {
                    "vendas": current_sales,
                    "receita": round(current_receita, 2),
                    "meta": sales_goal,
                    "ticket_medio": round(avg_ticket, 2),
                    "ocupacao_pct": round(current_sales / sales_goal * 100, 1) if sales_goal > 0 else 0
                },
                "anterior": {
                    "vendas": vendas_anterior,
                    "receita": round(receita_anterior, 2),
                    "meta": meta_anterior,
                    "ticket_medio": round(ticket_anterior, 2),
                    "ocupacao_pct": round(vendas_anterior / meta_anterior * 100, 1) if meta_anterior > 0 else 0
                },
                "variacao": {
                    "vendas_pct": round(variacao_vendas, 1) if variacao_vendas is not None else None,
                    "receita_pct": round(((current_receita - receita_anterior) / receita_anterior * 100), 1) if receita_anterior > 0 else None
                }
            }
        
        all_grupo_mappings_for_anos = _wq_sku_mappings_by_grupo(db, grupo_nome, list(range(2018, ano + 2)))
        if all_grupo_mappings_for_anos:
            anos_set = sorted(set(m.ano for m in all_grupo_mappings_for_anos if m.ano), reverse=True)
            anos_disponiveis = [(a,) for a in anos_set]
        else:
            anos_disponiveis = db.query(SkuMapping.ano).filter(
                SkuMapping.evento_grupo == grupo_nome,
                SkuMapping.ativo == True
            ).distinct().order_by(SkuMapping.ano.desc()).all()
        
        _today_now = today_brazil()
        _event_is_past = bool(projeto_data_evento and projeto_data_evento < _today_now)
        from app.core.cache import get_last_full_refresh as _get_last_full_refresh
        _last_full_ts = _get_last_full_refresh()
        _last_full_str = (
            datetime.fromtimestamp(_last_full_ts, tz=ZoneInfo('America/Sao_Paulo')).isoformat()
            if _last_full_ts else None
        )
        _grupo_faixas_preco_site = _get_faixas_preco_site_for_projeto_ids(db, [p.id for p in projetos])

        grp_cenarios_ciclismo = None
        if projeto_modalidade and projeto_modalidade.lower() == 'ciclismo':
            grp_cad = _wq_cadastro_by_projeto_id(db, rep_projeto.id) if rep_projeto else None
            if grp_cad:
                grp_cenarios_ciclismo = {
                    "participacao": {
                        "orcado_pago": int(grp_cad.ciclismo_participacao_pago or 0),
                        "tkt_medio_orcado": 0,
                    },
                    "sem_bike": {
                        "orcado_pago": int(grp_cad.ciclismo_sem_bike_pago or 0),
                        "tkt_medio_orcado": float(grp_cad.ciclismo_sem_bike_tkt_medio or 0),
                    },
                    "com_bike": {
                        "orcado_pago": int(grp_cad.ciclismo_com_bike_pago or 0),
                        "tkt_medio_orcado": float(grp_cad.ciclismo_com_bike_tkt_medio or 0),
                    },
                }
                from app.models.kit_config import KitConfig as _KC
                from app.models.dimensoes import SkuMapping as _SM
                _grp_ext_ids = []
                for _gp in projetos:
                    _gp_sku = normalize_sku(str(_gp.codigo)) if _gp.codigo else None
                    if _gp_sku:
                        _gp_sm = db.query(_SM).filter(
                            func.upper(_SM.sku) == _gp_sku,
                            _SM.ativo == True,
                        ).all()
                        _grp_ext_ids.extend([str(sm_r.id_externo) for sm_r in _gp_sm if sm_r.id_externo])
                if _grp_ext_ids:
                    _grp_kits = db.query(_KC).filter(
                        _KC.id_evento.in_(_grp_ext_ids),
                        _KC.cenario_ciclismo.isnot(None),
                    ).all()
                else:
                    _grp_kits = []
                _grp_bundle_ids = {k.bundle_entity_id: k.cenario_ciclismo for k in _grp_kits}
                _grp_cenario_costs: dict = {}
                for _gk in _grp_kits:
                    _gcn = _gk.cenario_ciclismo
                    if _gcn and _gk.custo_kit is not None:
                        _grp_cenario_costs.setdefault(_gcn, []).append(float(_gk.custo_kit))
                for _gcn_key in grp_cenarios_ciclismo:
                    cost_vals = _grp_cenario_costs.get(_gcn_key, [])
                    grp_cenarios_ciclismo[_gcn_key]["custo_kit"] = round(sum(cost_vals) / len(cost_vals), 2) if cost_vals else 0
                if _grp_bundle_ids:
                    _grp_cic_populated = _populate_cenarios_from_bundles(
                        db, _grp_bundle_ids, grp_cenarios_ciclismo,
                        _grupo_incluir_cortesias,
                    )
                for _gcn in grp_cenarios_ciclismo:
                    _gcd = grp_cenarios_ciclismo[_gcn]
                    rv = _gcd.get("real_vendas", 0)
                    rr = _gcd.get("real_receita", 0)
                    _gcd.setdefault("real_vendas", 0)
                    _gcd.setdefault("real_receita", 0)
                    _gcd["real_tkt_medio"] = round(rr / rv, 2) if rv > 0 else 0
                    _gck_cost = _gcd.get("custo_kit", 0)
                    _gcd["margem_orcada"] = round((_gcd["tkt_medio_orcado"] - _gck_cost) * _gcd["orcado_pago"], 2) if _gcd["orcado_pago"] > 0 else 0
                    _gcd["margem_realizada"] = round(rr - (_gck_cost * rv), 2) if rv > 0 else 0

        grouped_result = {
            "status": "success",
            "evento": evento,
            "dailySales": daily_sales,
            # commercialActions intentionally excluded from cache — always fetched fresh per request
            "projetos_vinculados": [{"id": p.id, "nome": p.evento, "sku": p.codigo} for p in projetos],
            "comparacao_anual": comparacao_anual,
            "anos_disponiveis": [a[0] for a in anos_disponiveis],
            "faixas_preco_site": _grupo_faixas_preco_site,
            "cenarios_ciclismo": grp_cenarios_ciclismo,
            "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(),
            "ultima_atualizacao_completa": _last_full_str,
            "avisos": get_isc_warnings(),
            "_cache_version": _DETAIL_CACHE_VERSION
        }
        # For completed events: preserve the highest currentSales ever computed.
        # If the Magento count_query failed this recompute (kit total = 0, so
        # current_sales fell back to the Ativo-only snapshot value), the previously
        # persisted snapshot may hold the correct kit-aligned figure and must not
        # be overwritten with a lower stale value.
        if _event_is_past and not _authoritative_downcorrect:
            try:
                from ...models.evento_detail_snapshot import EventoDetailSnapshot as _EDS_guard
                _guard_row = db.query(_EDS_guard).filter(
                    _EDS_guard.evento_id == evento_id,
                    _EDS_guard.ano == ano,
                ).first()
                if _guard_row and isinstance(_guard_row.payload, dict):
                    _guard_evt = _guard_row.payload.get("evento")
                    _prev_cs = int(_guard_evt.get("currentSales", 0) or 0) if isinstance(_guard_evt, dict) else 0
                    _new_cs = int(getattr(grouped_result.get("evento"), "currentSales", 0) or 0)
                    if _prev_cs > _new_cs > 0:
                        logger.info(
                            f"[Persist] Preservando currentSales anterior '{grupo_nome}': "
                            f"{_new_cs} → {_prev_cs} (kit count_query falhou no recompute)"
                        )
                        grouped_result["evento"] = grouped_result["evento"].model_copy(
                            update={"currentSales": _prev_cs}
                        )
            except Exception as _guard_e:
                logger.debug(f"[Persist] guard prev_sales '{evento_id}/{ano}': {_guard_e}")

        # Salvaguarda margemPorKit: se o cálculo recém-feito ficou degradado
        # (qtd > 0 e receita = 0 — Magento devolveu dados parciais sem erro),
        # preserva a margemPorKit do snapshot anterior em vez de exibir margem
        # negativa para o usuário. Espelha o padrão da guarda de currentSales.
        try:
            _new_evt_mpk = grouped_result.get("evento")
            _new_mpk_rows = getattr(_new_evt_mpk, "margemPorKit", None) if _new_evt_mpk is not None else None
            if _margem_por_kit_is_degraded(_new_mpk_rows):
                from ...models.evento_detail_snapshot import EventoDetailSnapshot as _EDS_mpk
                _mpk_prev_row = db.query(_EDS_mpk).filter(
                    _EDS_mpk.evento_id == evento_id,
                    _EDS_mpk.ano == ano,
                ).first()
                _prev_mpk_rows = None
                if _mpk_prev_row and isinstance(_mpk_prev_row.payload, dict):
                    _prev_evt_mpk = _mpk_prev_row.payload.get("evento")
                    if isinstance(_prev_evt_mpk, dict):
                        _prev_mpk_rows = _prev_evt_mpk.get("margemPorKit")
                if _prev_mpk_rows and not _margem_por_kit_is_degraded(_prev_mpk_rows):
                    logger.info(
                        f"[Persist] Preservando margemPorKit anterior '{grupo_nome}': "
                        f"nova tabela degradada (qtd>0 com receita=0)"
                    )
                    _existing_avisos = list(getattr(_new_evt_mpk, "margemAvisos", None) or [])
                    _aviso_mpk_pres = (
                        "AVISO: Receita por kit indisponível no Magento — exibindo última "
                        "margem conhecida do snapshot."
                    )
                    if _aviso_mpk_pres not in _existing_avisos:
                        _existing_avisos.append(_aviso_mpk_pres)
                    _existing_avisos = _consolidate_margem_avisos(_existing_avisos)
                    grouped_result["evento"] = grouped_result["evento"].model_copy(
                        update={
                            "margemPorKit": _prev_mpk_rows,
                            "margemAvisos": _existing_avisos,
                        }
                    )
        except Exception as _mpk_g_e:
            logger.debug(f"[Persist] guard margemPorKit '{evento_id}/{ano}': {_mpk_g_e}")

        # Computa commercialActions ANTES de persistir, para que o snapshot
        # contenha os impactos já calculados — eliminando N+1 (queries Magento
        # por ação) no GET subsequente.
        try:
            grouped_result["commercialActions"] = _fetch_commercial_actions_from_db(
                db, [p.id for p in projetos]
            )
        except Exception as _ca_e:
            logger.warning(f"[Persist] grouped commercialActions falhou: {_ca_e}")
            grouped_result.setdefault("commercialActions", [])

        if _event_is_past:
            grouped_result["__is_completed"] = True
            event_detail_cache.set_permanent(detail_cache_key, grouped_result)
            logger.info(f"Event '{grupo_nome}' ({projeto_data_evento}) cached permanently (completed event)")
        else:
            event_detail_cache.set(detail_cache_key, grouped_result)
        # Persiste em PostgreSQL para sobreviver a restarts e cache invalidations
        try:
            from ...services.event_detail_snapshot_service import save_persisted_detail as _spd
            _spd(db, evento_id, ano, grouped_result, data_evento=projeto_data_evento,
                 is_completed=_event_is_past, bypass_completed_guard=_authoritative_downcorrect)
        except Exception as _spd_e:
            logger.warning(f"[Persist] save grouped '{evento_id}/{ano}' falhou: {_spd_e}")
        # ISC e eventos_list NÃO são invalidados aqui: o STEP 4b em fetch_isc_pricing_data
        # lê EventoDetailSnapshot dinamicamente na próxima reconstrução natural do ISC.
        # Invalidar a cada evento concluído causa cascata de rebuilds durante warm-up.
        # Signal any waiting threads that computation is done
        with _event_computing_lock:
            _done_evt = _event_computing_events.pop(detail_cache_key, None)
        if _done_evt is not None:
            _done_evt.set()
        response_result = {k: v for k, v in grouped_result.items() if k != "__is_completed"}
        return response_result
    
    projeto = _wq_dim_projeto_by_id(db, int(evento_id))
    
    if not projeto:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    
    projeto_codigo = str(projeto.codigo) if projeto.codigo else None
    sku = projeto_codigo
    projeto_data_evento = projeto.data_evento
    
    if ano is None:
        ano = projeto_data_evento.year if projeto_data_evento else datetime.now().year
    
    detail_standalone_cad = _wq_cadastro_by_projeto_id(db, projeto.id)
    dias_enc = get_dias_encerramento(db, projeto_id=projeto.id, cadastro=detail_standalone_cad)
    d_minus_inscricoes = calculate_d_minus(projeto_data_evento, reference_year=ano, dias_encerramento=dias_enc) if projeto_data_evento else 0
    d_minus = calculate_d_minus(projeto_data_evento, reference_year=ano, dias_encerramento=0) if projeto_data_evento else 0
    is_active = d_minus_inscricoes > 0 if ano == datetime.now().year else True
    standalone_detail_regime = get_data_regime(projeto_data_evento, dias_enc) if projeto_data_evento else "live"
    
    standalone_cache_key = f"{ano}_{evento_id}_detail"
    if not force_refresh:
        cached_standalone, is_stale = event_detail_cache.get_or_revalidate(standalone_cache_key, refresh_fn=None)
        if cached_standalone is not None:
            # Validate that cached data has a non-empty event date.
            _cached_evt_sa = cached_standalone.get("evento", {})
            _cached_date_sa = (
                _cached_evt_sa.get("date", "") if isinstance(_cached_evt_sa, dict)
                else getattr(_cached_evt_sa, "date", "")
            )
            # SWR trigger: recompute when _computed_at_date is missing or cache version is outdated.
            # Freshness is also owned by event_detail_cache.invalidate() (called after sync) + SmartCache TTL.
            _sa_cached_version = cached_standalone.get("_cache_version")
            _sa_needs_recompute = not _cached_date_sa or _sa_cached_version != _DETAIL_CACHE_VERSION
            if _sa_needs_recompute:
                if standalone_cache_key not in _swr_recompute_in_progress:
                    sa_reason = "empty date" if not _cached_date_sa else f"version mismatch ({_sa_cached_version} != {_DETAIL_CACHE_VERSION})"
                    logger.info(f"[Cache] standalone event_detail '{standalone_cache_key}' {sa_reason} — serving stale + triggering background recompute")
                    _swr_recompute_in_progress.add(standalone_cache_key)
                    import threading as _threading
                    _threading.Thread(target=_swr_detail_refresh, args=(standalone_cache_key,), daemon=True).start()
                else:
                    logger.info(f"[Cache] standalone event_detail '{standalone_cache_key}' SWR already in progress — skipping duplicate thread")
                is_stale = True
            if response is not None:
                response.headers["X-Data-Stale"] = "true" if is_stale else "false"
            result_sa = {k: v for k, v in cached_standalone.items() if k != "__is_completed"}
            if _sa_needs_recompute:
                result_sa["ultima_atualizacao"] = "2000-01-01T00:00:00-03:00"
            # Sempre injeta faixas_preco_site frescas do banco para refletir edições no cadastro.
            try:
                _sa_pids = [int(evento_id)]
                result_sa["faixas_preco_site"] = _get_faixas_preco_site_for_projeto_ids(db, _sa_pids)
            except Exception as _fps_e3:
                logger.warning(f"[Cache-SA] faixas_preco_site refresh falhou: {_fps_e3}")
            return result_sa
    
    standalone_evento_grupo = None
    if sku:
        standalone_mappings = _wq_sku_mappings_by_sku(db, sku)
        for sm in standalone_mappings:
            if sm.evento_grupo and sm.evento_grupo.strip():
                standalone_evento_grupo = sm.evento_grupo
                break

    if standalone_detail_regime == "consolidated":
        snap_key = standalone_evento_grupo or normalize_sku(sku or "")
        snap = _get_snapshot_metrics_for_grupo(db, snap_key, ano=ano) if snap_key else None
        if snap is not None:
            current_sales = snap['qtd_site']
            current_receita = snap['receita_liquida_site']
        else:
            isc_data_sa = fetch_isc_pricing_data(db=db)
            sales_info = isc_data_sa.get(normalize_sku(sku), {}) if sku else {}
            current_sales = sales_info.get('qtd_site', 0)
            current_receita = sales_info.get('receita_liquida_site', 0.0)
    else:
        isc_data_sa = fetch_isc_pricing_data(db=db)
        sales_info = isc_data_sa.get(normalize_sku(sku), {}) if sku else {}
        current_sales = sales_info.get('qtd_site', 0)
        current_receita = sales_info.get('receita_liquida_site', 0.0)
    
    # ── Snapshot-first (standalone): mesmo piso estável do caminho de grupo ──
    # Evento standalone do ano corrente ainda NÃO concluído usa apenas o ISC-cache
    # (pode vir parcial/defasado). Ancora o total no snapshot consolidado quando
    # este é maior — só SOBE, nunca rebaixa. Não afeta eventos consolidados.
    if standalone_detail_regime != "consolidated" and ano == datetime.now().year:
        _sa_snap_key = standalone_evento_grupo or (normalize_sku(sku) if sku else None)
        if _sa_snap_key:
            try:
                _sa_snap_base = _get_snapshot_metrics_for_grupo(db, _sa_snap_key, ano=ano)
            except Exception as _sa_sb_e:
                logger.warning(f"[SnapshotFirst SA] Falha ao ler snapshot base '{_sa_snap_key}': {_sa_sb_e}")
                _sa_snap_base = None
            if _sa_snap_base:
                _sa_snap_qty = int(_sa_snap_base.get('qtd_site') or 0)
                _sa_snap_rev = float(_sa_snap_base.get('receita_liquida_site') or 0.0)
                if _sa_snap_qty > current_sales:
                    logger.info(
                        f"[SnapshotFirst SA] '{_sa_snap_key}': ancorando currentSales "
                        f"{current_sales} → {_sa_snap_qty} (piso do snapshot consolidado)"
                    )
                    current_sales = _sa_snap_qty
                    if _sa_snap_rev > current_receita:
                        current_receita = _sa_snap_rev

    sales_goal = get_meta_from_cadastro(detail_standalone_cad) if detail_standalone_cad else get_meta_orcada(db, projeto.id)
    avg_ticket = round(current_receita / current_sales, 2) if current_sales > 0 else 0.0
    detail_standalone_bt = round(float(detail_standalone_cad.atletas_site_tkt_medio), 2) if detail_standalone_cad and detail_standalone_cad.atletas_site_tkt_medio and detail_standalone_cad.atletas_site_pago and detail_standalone_cad.atletas_site_pago > 0 else 0.0

    data_fim_inscricoes_standalone = projeto_data_evento - timedelta(days=dias_enc) if projeto_data_evento else None

    if force_refresh and standalone_evento_grupo and ano == datetime.now().year and standalone_detail_regime != "consolidated":
        _should_rebuild_standalone = True
        try:
            from ...models.vendas_snapshot import VendasDiariaSnapshot as _VDS
            # Cooldown restrito ao ano-edição (mesmo motivo do bloco grouped acima).
            _last_updated_s = db.query(func.max(_VDS.updated_at)).filter(
                _VDS.evento_grupo == standalone_evento_grupo,
                _VDS.ano == ano,
            ).scalar()
            if _last_updated_s and (datetime.now() - _last_updated_s).total_seconds() < 600:
                _should_rebuild_standalone = False
                logger.info(f"Snapshot cooldown standalone: '{standalone_evento_grupo}' atualizado há {(datetime.now() - _last_updated_s).total_seconds():.0f}s, pulando rebuild")
        except Exception:
            pass
        if _should_rebuild_standalone:
            try:
                from ...services.snapshot_service import consolidar_vendas_grupo
                # incremental=True: apenas dias novos — evita rebuild síncrono de 1-2min.
                # Cai para full rebuild automaticamente se não houver snapshot prévio.
                consolidar_vendas_grupo(db, standalone_evento_grupo, ano, incremental=True)
                logger.info(f"Snapshot atualizado incremental (force_refresh standalone) para '{standalone_evento_grupo}' ano={ano}")
            except Exception as _e:
                logger.warning(f"Falha ao reconstruir snapshot standalone para '{standalone_evento_grupo}': {_e}")
    elif standalone_detail_regime == "consolidated":
        logger.info(f"[Hybrid] Standalone evento {evento_id} é consolidated — pulando rebuild de snapshot")

    daily_sales_list = fetch_real_daily_sales_for_projetos(db, [projeto], sales_goal=sales_goal, ano=ano, evento_grupo=standalone_evento_grupo, data_evento=data_fim_inscricoes_standalone, data_evento_real=projeto_data_evento, force_magento_refresh=force_magento_refresh)
    daily_sales_dict = {date.fromisoformat(d['date']): d['sales'] for d in daily_sales_list}
    
    standalone_detail_hist = None
    standalone_detail_hist_norm = None
    standalone_detail_curva_info = {"tipo_curva": "linear", "fonte_curva": None, "ano_referencia": None}
    _use_norm_isc_sa = isc_cfg.get("useNormalizedCurveForISC", False)
    if standalone_evento_grupo:
        try:
            _sa_estado = str(projeto.estado) if projeto and projeto.estado else None
            standalone_detail_hist, standalone_detail_curva_info = _resolve_hist_pattern(db, standalone_evento_grupo, ano, estado=_sa_estado)
            if _use_norm_isc_sa:
                try:
                    _sa_norm_pat, _ = _resolve_hist_pattern(db, standalone_evento_grupo, ano, estado=_sa_estado, use_normalized=True)
                    standalone_detail_hist_norm = _sa_norm_pat or standalone_detail_hist
                except Exception as _e_sa_norm:
                    logger.warning(f"Falha ao obter hist_pattern normalizado (standalone): {_e_sa_norm}")
                    standalone_detail_hist_norm = standalone_detail_hist
        except Exception:
            pass
    
    isc_components = calculate_isc_components(current_sales, sales_goal, d_minus_inscricoes,
                                               daily_sales_dict=daily_sales_dict,
                                               hist_pattern=(standalone_detail_hist_norm if _use_norm_isc_sa else standalone_detail_hist),
                                               registration_close_date=data_fim_inscricoes_standalone,
                                               curva_info=standalone_detail_curva_info,
                                               use_normalized_curve=_use_norm_isc_sa)
    isc = calculate_isc(isc_components, isc_cfg["ia730Weight"], isc_cfg["curvaDWeight"], isc_cfg["rolling14dWeight"])
    isc_raw: Optional[float] = None
    # Always compute BOTH raw and normalized component sets so the frontend
    # "Normalizar Meta" toggle can switch between them.
    isc_components_raw_alt_sa: Optional[ISCComponents] = None
    isc_components_norm_alt_sa: Optional[ISCComponents] = None
    try:
        isc_components_raw_alt_sa = calculate_isc_components(
            current_sales, sales_goal, d_minus_inscricoes,
            daily_sales_dict=daily_sales_dict,
            hist_pattern=standalone_detail_hist,
            registration_close_date=data_fim_inscricoes_standalone,
            curva_info=standalone_detail_curva_info,
            use_normalized_curve=False)
    except Exception as _e_raw:
        logger.warning(f"Falha ao calcular iscComponentsRaw (detail standalone): {_e_raw}")
    try:
        isc_components_norm_alt_sa = calculate_isc_components(
            current_sales, sales_goal, d_minus_inscricoes,
            daily_sales_dict=daily_sales_dict,
            hist_pattern=(standalone_detail_hist_norm or standalone_detail_hist),
            registration_close_date=data_fim_inscricoes_standalone,
            curva_info=standalone_detail_curva_info,
            use_normalized_curve=True)
    except Exception as _e_norm:
        logger.warning(f"Falha ao calcular iscComponentsNormalized (detail standalone): {_e_norm}")
    if isc_cfg.get("useNormalizedCurveForISC", False) and isc_components_raw_alt_sa is not None:
        try:
            isc_raw = calculate_isc(isc_components_raw_alt_sa, isc_cfg["ia730Weight"], isc_cfg["curvaDWeight"], isc_cfg["rolling14dWeight"])
        except Exception as _e_raw_isc:
            logger.warning(f"Falha ao calcular iscRaw para evento (detail standalone): {_e_raw_isc}")
    isc_status = get_isc_status(isc, isc_cfg["greenThreshold"], isc_cfg["yellowThreshold"])
    suggested_action = get_suggested_action(isc, d_minus_inscricoes, isc_cfg["greenThreshold"], isc_cfg["yellowThreshold"], isc_cfg["promotionDeadline"])
    
    projeto_modalidade = str(projeto.modalidade) if projeto.modalidade else None
    projeto_cidade = str(projeto.cidade) if projeto.cidade else None
    projeto_estado = str(projeto.estado) if projeto.estado else None
    projeto_nome = str(projeto.evento) if projeto.evento else "Evento sem nome"
    projeto_limite = sales_goal
    
    detail_sa_kit_cost = get_kit_basico_cost(db, projeto.id)
    detail_sa_margin = _calc_margin_fields(detail_standalone_bt, detail_sa_kit_cost, sales_goal,
                                            avg_ticket, current_sales, current_receita)
    
    sa_ticket_atual_map = _get_ticket_atual_map(db)
    sa_detail_ticket_atual = _get_ticket_atual_for_event(sa_ticket_atual_map, projeto.id)
    sa_detail_ticket_kit_nome = _get_ticket_atual_kit_nome_for_event(sa_ticket_atual_map, projeto.id)
    
    _sa_incluir_cortesias = bool(getattr(projeto, 'incluir_cortesias', False))
    _sa_margem_avisos: list = []
    sa_margem_por_kit = get_margem_por_kit(
        db,
        [projeto.id],
        ano=ano,
        card_total_qty=current_sales,
        card_total_receita=current_receita,
        card_kit_cost_avg=detail_sa_kit_cost,
        avisos_out=_sa_margem_avisos,
        force_refresh=force_refresh or force_magento_refresh,
        incluir_cortesias=_sa_incluir_cortesias,
    )
    # Align currentSales with the kit table total (same logic + guard as consolidated group branch).
    _sa_kit_rows_aligned = [r for r in (sa_margem_por_kit or []) if r.get('tipoKit') != 'CONSOLIDADO']
    _sa_kit_total_qty_aligned = sum(int(r.get('qtd', 0) or 0) for r in _sa_kit_rows_aligned)
    if _sa_kit_total_qty_aligned > current_sales:
        logger.info(
            f"[Detalhe SA] Alinhando currentSales '{projeto_nome}': {current_sales} → {_sa_kit_total_qty_aligned} "
            f"(diff={current_sales - _sa_kit_total_qty_aligned})"
        )
        current_sales = _sa_kit_total_qty_aligned
        avg_ticket = round(current_receita / current_sales, 2) if current_sales > 0 else avg_ticket
        detail_sa_margin = _calc_margin_fields(detail_standalone_bt, detail_sa_kit_cost, sales_goal,
                                               avg_ticket, current_sales, current_receita)
    elif _sa_kit_total_qty_aligned > 0 and _sa_kit_total_qty_aligned < current_sales:
        logger.info(
            f"[Detalhe SA] Alinhamento ignorado '{projeto_nome}': kit_table={_sa_kit_total_qty_aligned} "
            f"< snapshot={current_sales} (provável resposta parcial Magento — preservando piso do snapshot)"
        )
        if force_refresh or force_magento_refresh:
            # Mesma proteção do caminho consolidado: tabela parcial subestima a
            # Margem Realizada — restaura a última tabela íntegra persistida.
            _sa_prev_rows_partial = _load_prev_margem_rows(db, evento_id, ano)
            if _sa_prev_rows_partial:
                _sa_prev_qtd_partial = sum(
                    int(r.get('qtd', 0) or 0) for r in _sa_prev_rows_partial
                    if isinstance(r, dict) and r.get('tipoKit') != 'CONSOLIDADO'
                )
                if _sa_prev_qtd_partial >= _sa_kit_total_qty_aligned:
                    logger.info(
                        f"[Detalhe SA] margemPorKit parcial '{projeto_nome}' substituída pela última "
                        f"íntegra persistida (qtd {_sa_kit_total_qty_aligned} → {_sa_prev_qtd_partial})"
                    )
                    sa_margem_por_kit = _sa_prev_rows_partial
            _sa_partial_aviso = (
                "Leitura ao vivo veio incompleta — o total não foi corrigido para baixo. "
                "Tente atualizar novamente em alguns instantes."
            )
            if _sa_partial_aviso not in _sa_margem_avisos:
                _sa_margem_avisos.append(_sa_partial_aviso)

    sa_detalhe_vendas = []
    sa_kit_query_failed = False
    if standalone_detail_regime == "consolidated":
        sa_detalhe_ativo = []
    else:
        sa_detalhe_ativo = get_detalhe_vendas_ativo(db, [projeto.id], ano=ano)

    # Um único banner claro no painel de margem (era possível acumular
    # AVISO de instabilidade + INFO de idade do snapshot + mensagem de
    # leitura parcial, todos descrevendo o mesmo estado).
    _sa_margem_avisos = _consolidate_margem_avisos(_sa_margem_avisos)
    
    evento = MarketingEvent(
        id=str(projeto.id),
        name=projeto_nome,
        date=projeto_data_evento.isoformat() if projeto_data_evento else "",
        location=projeto_cidade or projeto_estado or "Não definido",
        category=projeto_modalidade or "Corrida",
        totalCapacity=projeto_limite,
        currentSales=current_sales,
        salesGoal=sales_goal,
        averageTicket=round(avg_ticket, 2),
        budgetTicket=detail_standalone_bt,
        dMinus=d_minus,
        dMinusInscricoes=d_minus_inscricoes,
        isc=isc,
        iscRaw=isc_raw,
        iscComponents=isc_components,
        iscComponentsRaw=isc_components_raw_alt_sa,
        iscComponentsNormalized=isc_components_norm_alt_sa,
        iscStatus=isc_status,
        suggestedAction=suggested_action,
        isActive=is_active,
        sku=sku,
        ticketAtual=sa_detail_ticket_atual,
        ticketKitNome=sa_detail_ticket_kit_nome,
        margemPorKit=sa_margem_por_kit if sa_margem_por_kit else None,
        margemAvisos=_sa_margem_avisos if _sa_margem_avisos else None,
        consistencyWarning=None,  # aligned above; retained field for API compatibility
        kitQueryFailed=sa_kit_query_failed,
        detalheVendasPorKit=sa_detalhe_vendas if sa_detalhe_vendas else None,
        detalheVendasAtivoKit=sa_detalhe_ativo if sa_detalhe_ativo else None,
        dataRegime=standalone_detail_regime,
        incluirCortesias=_sa_incluir_cortesias,
        **detail_sa_margin
    )
    
    daily_sales = daily_sales_list
    
    from ...models.dimensoes import AcaoComercial
    acoes = db.query(AcaoComercial).filter(
        AcaoComercial.projeto_id == int(evento_id)
    ).order_by(AcaoComercial.data_acao.desc()).all()
    
    commercial_actions = []
    for a in acoes:
        tipo_map = {
            'AUMENTO_PRECO': 'price_increase',
            'REDUCAO_PRECO': 'price_decrease',
            'PROMOCAO': 'promotion',
            'CAMPANHA': 'campaign',
            'COMUNICACAO': 'communication'
        }
        
        impacto = calculate_action_impact(db, a)
        impacto_percentual = impacto.get("impacto_percentual")
        vendas_antes = impacto.get("vendas_antes")
        vendas_depois = impacto.get("vendas_depois")
        
        if impacto_percentual is not None:
            if impacto_percentual > 0:
                impact_str = f"+{impacto_percentual}%"
            else:
                impact_str = f"{impacto_percentual}%"
        else:
            impact_str = None
        
        commercial_actions.append({
            "id": str(a.id),
            "type": tipo_map.get(a.tipo, 'communication'),
            "description": a.descricao,
            "date": a.data_acao.isoformat() if a.data_acao else None,
            "impact": impact_str,
            "vendas_antes": vendas_antes,
            "vendas_depois": vendas_depois,
            "impacto_percentual": impacto_percentual,
            "status_impacto": impacto.get("status", "calculado") if impacto_percentual is not None else "aguardando_dados",
            "ponto_corte": a.ponto_corte,
            "estagio": a.estagio,
            "snapshot_isc": float(a.snapshot_isc) if a.snapshot_isc is not None else None,
            "snapshot_isc_state": a.snapshot_isc_state,
            "snapshot_d_minus": a.snapshot_d_minus,
            "snapshot_ia730": float(a.snapshot_ia730) if a.snapshot_ia730 is not None else None,
            "snapshot_rolling14d": float(a.snapshot_rolling14d) if a.snapshot_rolling14d is not None else None,
            "snapshot_curva_percent": float(a.snapshot_curva_percent) if a.snapshot_curva_percent is not None else None,
            "snapshot_vendas_acumuladas": a.snapshot_vendas_acumuladas,
            "snapshot_playbook_letter": a.snapshot_playbook_letter,
        })
    
    _sa_faixas_preco_site = _get_faixas_preco_site_for_projeto_ids(db, [projeto.id])

    cenarios_ciclismo = None
    if projeto_modalidade and projeto_modalidade.lower() == 'ciclismo' and detail_standalone_cad:
        cenarios_ciclismo = {
            "participacao": {
                "orcado_pago": int(detail_standalone_cad.ciclismo_participacao_pago or 0),
                "tkt_medio_orcado": 0,
            },
            "sem_bike": {
                "orcado_pago": int(detail_standalone_cad.ciclismo_sem_bike_pago or 0),
                "tkt_medio_orcado": float(detail_standalone_cad.ciclismo_sem_bike_tkt_medio or 0),
            },
            "com_bike": {
                "orcado_pago": int(detail_standalone_cad.ciclismo_com_bike_pago or 0),
                "tkt_medio_orcado": float(detail_standalone_cad.ciclismo_com_bike_tkt_medio or 0),
            },
        }
        from app.models.kit_config import KitConfig as _KC
        from app.models.dimensoes import SkuMapping as _SM
        _proj_sku = normalize_sku(str(projeto.codigo)) if projeto.codigo else None
        _cic_ext_ids = []
        if _proj_sku:
            _cic_sm = db.query(_SM).filter(
                func.upper(_SM.sku) == _proj_sku,
                _SM.ativo == True,
            ).all()
            _cic_ext_ids = [str(sm_r.id_externo) for sm_r in _cic_sm if sm_r.id_externo]
        if _cic_ext_ids:
            _cic_kits = db.query(_KC).filter(
                _KC.id_evento.in_(_cic_ext_ids),
                _KC.cenario_ciclismo.isnot(None),
            ).all()
        else:
            _cic_kits = []
        _cic_bundle_to_kit = {k.bundle_entity_id: k for k in _cic_kits}
        _cic_bundle_ids = {k.bundle_entity_id: k.cenario_ciclismo for k in _cic_kits}
        _cic_cenario_costs: dict = {}
        for _ck in _cic_kits:
            _cn_val = _ck.cenario_ciclismo
            if _cn_val and _ck.custo_kit is not None:
                _cic_cenario_costs.setdefault(_cn_val, []).append(float(_ck.custo_kit))
        for _cn_key in cenarios_ciclismo:
            cost_vals = _cic_cenario_costs.get(_cn_key, [])
            cenarios_ciclismo[_cn_key]["custo_kit"] = round(sum(cost_vals) / len(cost_vals), 2) if cost_vals else 0
        if _cic_bundle_ids:
            _sa_cic_populated = _populate_cenarios_from_bundles(
                db, _cic_bundle_ids, cenarios_ciclismo,
                _sa_incluir_cortesias,
            )
        for _cn in cenarios_ciclismo:
            _cd = cenarios_ciclismo[_cn]
            rv = _cd.get("real_vendas", 0)
            rr = _cd.get("real_receita", 0)
            _cd.setdefault("real_vendas", 0)
            _cd.setdefault("real_receita", 0)
            _cd["real_tkt_medio"] = round(rr / rv, 2) if rv > 0 else 0
            _ck_cost = _cd.get("custo_kit", 0)
            _cd["margem_orcada"] = round((_cd["tkt_medio_orcado"] - _ck_cost) * _cd["orcado_pago"], 2) if _cd["orcado_pago"] > 0 else 0
            _cd["margem_realizada"] = round(rr - (_ck_cost * rv), 2) if rv > 0 else 0

    standalone_result = {
        "status": "success",
        "evento": evento,
        "dailySales": daily_sales,
        "faixas_preco_site": _sa_faixas_preco_site,
        "cenarios_ciclismo": cenarios_ciclismo,
        "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(),
        "avisos": get_isc_warnings(),
        "_cache_version": _DETAIL_CACHE_VERSION
    }
    _sa_today = today_brazil()
    _sa_event_is_past = bool(projeto_data_evento and projeto_data_evento < _sa_today)

    # Salvaguarda margemPorKit (espelho da guarda no caminho consolidado).
    # Se o cálculo recém-feito ficou degradado (qtd > 0 e receita = 0),
    # preserva a margemPorKit do snapshot anterior em vez de exibir margem
    # negativa para o usuário.
    try:
        _sa_new_evt_mpk = standalone_result.get("evento")
        _sa_new_mpk_rows = (
            getattr(_sa_new_evt_mpk, "margemPorKit", None)
            if _sa_new_evt_mpk is not None else None
        )
        if _margem_por_kit_is_degraded(_sa_new_mpk_rows):
            from ...models.evento_detail_snapshot import EventoDetailSnapshot as _EDS_mpk_sa
            _sa_mpk_prev_row = db.query(_EDS_mpk_sa).filter(
                _EDS_mpk_sa.evento_id == evento_id,
                _EDS_mpk_sa.ano == ano,
            ).first()
            _sa_prev_mpk_rows = None
            if _sa_mpk_prev_row and isinstance(_sa_mpk_prev_row.payload, dict):
                _sa_prev_evt_mpk = _sa_mpk_prev_row.payload.get("evento")
                if isinstance(_sa_prev_evt_mpk, dict):
                    _sa_prev_mpk_rows = _sa_prev_evt_mpk.get("margemPorKit")
            if _sa_prev_mpk_rows and not _margem_por_kit_is_degraded(_sa_prev_mpk_rows):
                logger.info(
                    f"[Persist] Preservando margemPorKit anterior '{evento_id}': "
                    f"nova tabela degradada (qtd>0 com receita=0)"
                )
                _sa_existing_avisos = list(
                    getattr(_sa_new_evt_mpk, "margemAvisos", None) or []
                )
                _sa_aviso_mpk_pres = (
                    "AVISO: Receita por kit indisponível no Magento — exibindo última "
                    "margem conhecida do snapshot."
                )
                if _sa_aviso_mpk_pres not in _sa_existing_avisos:
                    _sa_existing_avisos.append(_sa_aviso_mpk_pres)
                _sa_existing_avisos = _consolidate_margem_avisos(_sa_existing_avisos)
                standalone_result["evento"] = standalone_result["evento"].model_copy(
                    update={
                        "margemPorKit": _sa_prev_mpk_rows,
                        "margemAvisos": _sa_existing_avisos,
                    }
                )
    except Exception as _sa_mpk_g_e:
        logger.debug(f"[Persist] guard margemPorKit standalone '{evento_id}/{ano}': {_sa_mpk_g_e}")

    # Computa commercialActions ANTES de persistir, para que o snapshot já carregue
    # os impactos calculados — elimina N+1 (queries Magento por ação) no GET.
    try:
        standalone_result["commercialActions"] = _fetch_commercial_actions_from_db(
            db, [int(evento_id)]
        )
    except Exception as _ca_sa_e:
        logger.warning(f"[Persist] standalone commercialActions falhou: {_ca_sa_e}")
        standalone_result.setdefault("commercialActions", [])

    if _sa_event_is_past:
        standalone_result["__is_completed"] = True
        event_detail_cache.set_permanent(standalone_cache_key, standalone_result)
        logger.info(f"Standalone event {evento_id} ({projeto_data_evento}) cached permanently (completed event)")
    else:
        event_detail_cache.set(standalone_cache_key, standalone_result)
    # Persiste em PostgreSQL para sobreviver a restarts e cache invalidations
    try:
        from ...services.event_detail_snapshot_service import save_persisted_detail as _spd_sa
        _spd_sa(db, evento_id, ano, standalone_result, data_evento=projeto_data_evento, is_completed=_sa_event_is_past)
    except Exception as _spd_sa_e:
        logger.warning(f"[Persist] save standalone '{evento_id}/{ano}' falhou: {_spd_sa_e}")
    sa_result = {k: v for k, v in standalone_result.items() if k != "__is_completed"}
    return sa_result


@router.get("/eventos/{evento_id}/version")
def get_evento_version(
    evento_id: str,
    ano: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing_dashboard", "pode_visualizar")),
):
    """Endpoint leve de versionamento — usado pelo frontend para polling de
    propagação cross-user. Retorna apenas timestamps; não recomputa nada.

    Frontend chama a cada ~60s. Se snapshot_updated_at ou last_sync_hoje
    mudar em relação ao baseline capturado no primeiro carregamento, exibe
    um banner "Há atualizações novas — clique para recarregar".
    """
    if ano is None:
        if evento_id.startswith("grp_"):
            ano = _resolve_default_ano_for_grupo(db, evento_id.replace("grp_", ""), today_brazil().year)
        else:
            ano = today_brazil().year
    from ...models.evento_detail_snapshot import EventoDetailSnapshot as _EDS_v
    snap_at = None
    try:
        # Coluna correta no model é `computed_at` (atualizada via onupdate=func.now()
        # pelo scheduler/reconsolidar). Não confundir com `created_at`.
        row = db.query(_EDS_v.computed_at).filter(
            _EDS_v.evento_id == evento_id,
            _EDS_v.ano == ano,
        ).first()
        if row and row[0]:
            snap_at = row[0].astimezone(ZoneInfo('America/Sao_Paulo')).isoformat() if row[0].tzinfo else row[0].replace(tzinfo=ZoneInfo('America/Sao_Paulo')).isoformat()
    except Exception as _v_e:
        logger.debug(f"get_evento_version: snapshot lookup falhou para '{evento_id}/{ano}': {_v_e}")
    _lsh_ts = get_last_sync_hoje()
    last_sync_iso = (
        datetime.fromtimestamp(_lsh_ts, tz=ZoneInfo('America/Sao_Paulo')).isoformat()
        if _lsh_ts else None
    )
    return {
        "evento_id": evento_id,
        "ano": ano,
        "snapshot_updated_at": snap_at,
        "last_sync_hoje": last_sync_iso,
        "server_now": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(),
    }


@router.post("/eventos/{evento_id}/atualizar-hoje")
def atualizar_vendas_hoje(
    evento_id: str,
    ano: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing_dashboard", "pode_editar"))
):
    """
    Atualização leve: busca apenas as vendas de HOJE (data atual) do Ativo e Magento
    para este evento, atualiza o snapshot e recalcula médias móveis.
    Não toca no ISC global nem em dados históricos.
    """
    hoje = today_brazil()
    is_grouped = evento_id.startswith("grp_")

    if ano is None:
        if is_grouped:
            ano = _resolve_default_ano_for_grupo(db, evento_id.replace("grp_", ""), hoje.year)
        else:
            ano = hoje.year

    # --- Collect IDs ---
    if is_grouped:
        grupo_nome = evento_id.replace("grp_", "")
        mappings = db.query(SkuMapping).filter(
            SkuMapping.evento_grupo == grupo_nome,
            SkuMapping.ano == ano,
            SkuMapping.ativo == True
        ).all()
    else:
        try:
            proj_id = int(evento_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="ID de evento inválido")
        projeto = db.query(DimProjeto).filter(DimProjeto.id == proj_id).first()
        if not projeto:
            raise HTTPException(status_code=404, detail="Evento não encontrado")
        grupo_nome = None
        _sku_raw = str(projeto.codigo) if projeto.codigo else None
        _sku_norm = normalize_sku(_sku_raw) if _sku_raw else None
        for _sku_q in filter(None, [_sku_raw, _sku_norm]):
            mappings = db.query(SkuMapping).filter(
                SkuMapping.sku == _sku_q,
                SkuMapping.ano == ano,
                SkuMapping.ativo == True
            ).all()
            if not mappings:
                mappings = db.query(SkuMapping).filter(
                    SkuMapping.sku == _sku_q,
                    SkuMapping.ativo == True
                ).order_by(SkuMapping.ano.desc()).all()
            if mappings:
                break

    if not mappings:
        raise HTTPException(status_code=404, detail="Nenhum SKU mapeado para este evento")

    ativo_ids = list(set(str(m.id_externo) for m in mappings if m.fonte == 'ATIVO' and m.id_externo))
    magento_ids = list(set(str(m.id_externo) for m in mappings if m.fonte == 'MAGENTO' and m.id_externo))

    if not grupo_nome and mappings:
        grupo_nome = next((m.evento_grupo for m in mappings if m.evento_grupo), None)

    if not grupo_nome:
        raise HTTPException(
            status_code=422,
            detail="Este evento não possui grupo mapeado. A atualização de hoje requer um grupo para persistir o snapshot."
        )

    # ── 1. Bloqueia se o batch global de sync-hoje está rodando ──────────────
    if is_sync_hoje_running():
        quem = get_sync_hoje_running_by() or "sistema"
        from fastapi.responses import JSONResponse as _JR_ah
        return _JR_ah(status_code=409, content={
            "status": "busy",
            "message": f"Sincronização global em andamento (por {quem}). Os dados serão atualizados em instantes — tente novamente em alguns segundos.",
        })

    import time as _time_ah
    _now_ah = _time_ah.time()
    _user_nome_ah = getattr(current_user, 'nome', None) or getattr(current_user, 'email', '') or 'usuário'
    _user_email_ah = getattr(current_user, 'email', '') or ''

    # ── 2. Bloqueia se QUALQUER sync manual já está rodando (lock global) ────
    if is_user_sync_running():
        _ui = get_user_sync_info()
        _quem_ip = _ui.get("by") or 'outro usuário'
        _ev_ip = _ui.get("evento") or ''
        _msg_ip = f"Atualização já em andamento por {_quem_ip}"
        if _ev_ip:
            _msg_ip += f" ({_ev_ip})"
        _msg_ip += ". Aguarde a conclusão antes de solicitar outra atualização."
        from fastapi.responses import JSONResponse as _JR_ip
        return _JR_ip(status_code=409, content={
            "status": "busy",
            "message": _msg_ip,
            "blocked_by": _quem_ip,
        })

    # ── 3. Verifica cooldown de 30 min (só aplicado após sucesso) ────────────
    # Admin bypassa o cooldown e pode sincronizar a qualquer momento.
    from app.core.security import is_user_admin as _is_user_admin
    _is_admin_user = _is_user_admin(current_user)
    _cool = _atualizar_hoje_cooldown.get(evento_id)
    if _cool and not _is_admin_user:
        _cool_ts, _cool_email, _cool_nome = _cool
        _elapsed_ah = _now_ah - _cool_ts
        if _elapsed_ah < _ATUALIZAR_HOJE_COOLDOWN_S:
            _remaining_ah = int(_ATUALIZAR_HOJE_COOLDOWN_S - _elapsed_ah)
            _min_ah = _remaining_ah // 60
            _sec_ah = _remaining_ah % 60
            _next_ah = datetime.fromtimestamp(
                _cool_ts + _ATUALIZAR_HOJE_COOLDOWN_S,
                tz=ZoneInfo('America/Sao_Paulo')
            ).isoformat()
            _quem_ah = _cool_nome or _cool_email
            from fastapi.responses import JSONResponse as _JR_cool
            return _JR_cool(status_code=429, content={
                "status": "cooldown",
                "retry_after": _remaining_ah,
                "detail": (
                    f"Atualização já realizada por {_quem_ah}. "
                    f"Disponível novamente em {_min_ah}min {_sec_ah}s."
                ),
                "next_allowed_at": _next_ah,
                "blocked_by": _quem_ah,
            })

    # ── 4. Adquire o lock global de sync manual ───────────────────────────────
    _caller_ah = f"{_user_nome_ah} ({_user_email_ah})" if _user_email_ah else _user_nome_ah
    if not try_acquire_user_sync(caller=_caller_ah, evento=grupo_nome or evento_id):
        # Raro: outra thread adquiriu o lock entre a checagem acima e aqui.
        _ui2 = get_user_sync_info()
        _quem2 = _ui2.get("by") or 'outro usuário'
        from fastapi.responses import JSONResponse as _JR_race
        return _JR_race(status_code=409, content={
            "status": "busy",
            "message": f"Atualização já em andamento por {_quem2}. Aguarde a conclusão.",
            "blocked_by": _quem2,
        })

    # Gera ciclo_id para o log de sincronização (aparece no painel).
    from ...services.sync_log_service import new_ciclo_id as _new_ciclo_ah
    _ciclo_id_ah = _new_ciclo_ah()

    _sf_key = (evento_id, ano, hoje.isoformat())

    def _do_atualizar_hoje():
        return _atualizar_hoje_inner(
            db=db,
            evento_id=evento_id,
            ano=ano,
            hoje=hoje,
            grupo_nome=grupo_nome,
            ativo_ids=ativo_ids,
            magento_ids=magento_ids,
            ciclo_id=_ciclo_id_ah,
        )

    try:
        _ah_result = _atualizar_hoje_cache.get_or_compute(_sf_key, _do_atualizar_hoje)
    finally:
        # ── 5. Libera o lock global sempre (sucesso ou exceção) ───────────────
        release_user_sync()

    # ── 6. Aplica cooldown SOMENTE após sucesso pleno ─────────────────────────
    # Falha ou parcial: sem cooldown — permite nova tentativa imediata.
    try:
        _ah_status = (_ah_result or {}).get("status") if isinstance(_ah_result, dict) else None
        if _ah_status == "ok":
            # Sucesso: bloqueia por 30 min.
            _atualizar_hoje_cooldown[evento_id] = (_now_ah, _user_email_ah, _user_nome_ah)
        elif _ah_status in ("failed", "partial"):
            # Falha/parcial: remove qualquer cooldown residual para liberar nova tentativa.
            _atualizar_hoje_cooldown.pop(evento_id, None)
        # status desconhecido: mantém estado anterior sem alterar.
    except Exception as _cd_e:
        logger.debug(f"atualizar-hoje: erro ao ajustar cooldown: {_cd_e}")

    return _ah_result


def _atualizar_hoje_inner(
    *,
    db: Session,
    evento_id: str,
    ano: int,
    hoje,
    grupo_nome: str,
    ativo_ids: list,
    magento_ids: list,
    ciclo_id: Optional[str] = None,
):
    """Fetch today's sales + UPSERT snapshot + return refreshed totals.

    Extracted from atualizar_vendas_hoje() so the logic can be invoked under
    the single-flight CoalescingCache wrapper.
    """
    import time as _time_inner
    _t_start_inner = _time_inner.time()
    from ...models.vendas_snapshot import VendasDiariaSnapshot as _VDS
    from sqlalchemy import func as _sa_func

    # Log de início de ciclo (painel de Sincronizações).
    # Fire-and-forget: log_evento abre sua própria sessão PG internamente —
    # não bloqueamos o caminho crítico do fetch por uma escrita de auditoria.
    if ciclo_id:
        try:
            import threading as _thr_log_init
            from ...services.sync_log_service import log_evento as _log_ev
            _thr_log_init.Thread(
                target=_log_ev,
                args=(ciclo_id, "atualizar_hoje", "iniciado"),
                kwargs={"nivel": "ciclo", "grupo": grupo_nome},
                daemon=True,
            ).start()
        except Exception:
            pass

    # --- Freeze guard: skip upstream call entirely for finished events ---
    # Eventos finalizados (data_evento + EVENTO_FREEZE_AFTER_DAYS < hoje) não
    # têm vendas novas hoje. Bater no Magento/Ativo apenas consome capacidade
    # dos sistemas externos sem benefício real. Retornamos o snapshot existente
    # imediatamente para esses casos.
    try:
        from ...services.snapshot_service import _freeze_after_days as _fad
        _freeze_days_h = _fad()
    except Exception:
        _freeze_days_h = 30
    # Conservador: só consideramos frozen quando TODOS os magento_ids deste
    # evento estão cobertos por cadastro_evento com data_evento NOT NULL e
    # TODAS as datas estão expiradas. Qualquer id sem cadastro OU com
    # data_evento NULL → NÃO freeze (permite o fetch normal). Isso evita
    # mascarar eventos novos que ainda não foram cadastrados.
    _evt_dates: list = []
    _evt_has_null = False
    _covered_mag_ids: set = set()
    _safe_mag_ids: list = []
    try:
        from ...models.cadastro_evento import CadastroEvento
        _safe_mag_ids = [int(i) for i in magento_ids if str(i).isdigit()]
        if _safe_mag_ids:
            _rows_dt = db.query(
                CadastroEvento.id_evento_magento,
                CadastroEvento.data_evento,
            ).filter(
                CadastroEvento.id_evento_magento.in_(_safe_mag_ids),
                CadastroEvento.deleted_at.is_(None),
            ).all()
            for (_mag_id, _dt) in _rows_dt:
                _covered_mag_ids.add(int(_mag_id))
                if _dt is None:
                    _evt_has_null = True
                else:
                    _evt_dates.append(_dt)
    except Exception as _e_fz:
        logger.debug(f"atualizar-hoje: freeze lookup falhou para {grupo_nome}: {_e_fz}")

    _cutoff_h = hoje - timedelta(days=_freeze_days_h)
    _fully_covered = bool(_safe_mag_ids) and (set(_safe_mag_ids) <= _covered_mag_ids)
    _is_frozen = (
        _fully_covered
        and bool(_evt_dates)
        and (not _evt_has_null)
        and all(d < _cutoff_h for d in _evt_dates)
    )
    logger.debug(
        f"atualizar-hoje: freeze-check grupo='{grupo_nome}' mag_ids={len(_safe_mag_ids)} "
        f"covered={len(_covered_mag_ids)} dates={len(_evt_dates)} nulls={_evt_has_null} "
        f"frozen={_is_frozen}"
    )
    if _is_frozen:
        logger.info(
            f"atualizar-hoje: evento '{grupo_nome}' finalizado (>{_freeze_days_h}d) — "
            f"pulando chamadas Magento/Ativo, devolvendo snapshot existente"
        )
        existing = None
        try:
            existing = db.query(_VDS).filter(
                _VDS.evento_grupo == grupo_nome,
                _VDS.fonte == 'CONSOLIDADO',
                _VDS.data_venda == hoje,
            ).first()
        except Exception:
            pass
        _hoje_total_fz = int(existing.quantidade) if existing else 0
        _hoje_receita_fz = float(existing.receita) if existing else 0.0
        _total_acum = 0
        try:
            _total_acum = int(db.query(_sa_func.coalesce(_sa_func.sum(_VDS.quantidade), 0)).filter(
                _VDS.evento_grupo == grupo_nome,
                _VDS.fonte == 'CONSOLIDADO',
                _VDS.ano == ano,
            ).scalar() or 0)
        except Exception:
            pass
        return {
            "status": "frozen",
            "evento_id": evento_id,
            "data": hoje.isoformat(),
            "hoje_ativo": 0,
            "hoje_magento": 0,
            "hoje_total": _hoje_total_fz,
            "media_7d": 0,
            "media_14d": 0,
            "media_30d": 0,
            "total_acumulado": _total_acum,
            "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(),
            "ativo_ok": True,
            "magento_ok": True,
            "fontes_indisponiveis": [],
        }

    # --- Fetch today's data from both sources IN PARALLEL ---
    # Ativo and Magento are independent upstream systems — run concurrently
    # so total latency ≈ max(t_ativo, t_magento) instead of t_ativo + t_magento.
    # Circuit breakers are checked before submitting each task so an open
    # breaker never blocks a thread unnecessarily.
    from concurrent.futures import ThreadPoolExecutor as _TPE, as_completed as _as_completed
    hoje_ativo = 0
    hoje_magento = 0
    hoje_receita = 0.0
    ativo_ok = True
    magento_ok = True
    sources_failed: list = []

    def _run_ativo():
        _qtd, _rec = 0, 0.0
        if not ativo_ids:
            return _qtd, _rec, True
        if ativo_breaker.is_open():
            logger.warning(f"atualizar-hoje: Ativo circuit aberto — pulando fetch para {evento_id}")
            return _qtd, _rec, False
        try:
            _rows = ativo_breaker.call(
                _fetch_today_sales_ativo_grouped, ativo_ids, raise_on_error=True
            )
            for _entry in _rows.values():
                _qtd += _entry["qtd"]
                _rec += _entry["receita"]
            return _qtd, _rec, True
        except CircuitOpenError:
            return _qtd, _rec, False
        except Exception as _e:
            logger.warning(f"atualizar-hoje: erro Ativo para {evento_id}: {_e}")
            return _qtd, _rec, False

    def _run_magento():
        _qtd, _rec = 0, 0.0
        if not magento_ids:
            return _qtd, _rec, True
        if magento_breaker.is_open():
            logger.warning(f"atualizar-hoje: Magento circuit aberto — pulando fetch para {evento_id}")
            return _qtd, _rec, False
        try:
            _rows = magento_breaker.call(
                _fetch_today_sales_magento_grouped, magento_ids, raise_on_error=True,
                acquire_timeout=_MAGENTO_ACQUIRE_BUDGET_S, max_exec_ms=_MAGENTO_EXEC_BUDGET_MS,
            )
            for _entry in _rows.values():
                _qtd += _entry["qtd"]
                _rec += _entry["receita"]
            return _qtd, _rec, True
        except CircuitOpenError:
            return _qtd, _rec, False
        except Exception as _e:
            logger.warning(f"atualizar-hoje: erro Magento para {evento_id}: {_e}")
            return _qtd, _rec, False

    # Timeouts de aplicação: garantem que o endpoint retorna mesmo se o MySQL
    # ignorar o hint MAX_EXECUTION_TIME (query na fila, SSH congestionado, etc.).
    # Ativo:   SQL 20s  → Python 24s (SSH tunnel pode ser instável).
    # Magento: orçamento DESACOPLADO em fila + execução para não dar timeout
    #          falso (o problema de produção era a query estourar 12s de execução
    #          — erro 3024 — mesmo com o slot livre). "once" é interativo e tem
    #          PRIORIDADE no slot único do túnel (db_retry), mas não dá pra
    #          preemptar uma query de background em voo. Orçamento:
    #            - fila (acquire):   13s  → cobre ~1 query de background em voo
    #            - execução (SQL):   20s  → MAX_EXECUTION_TIME do today-sales
    #            - thread (Python):  35s  → fila + execução + margem (13+20+2)
    #          Antes era 14s de thread, curto demais: estourava sempre que havia
    #          qualquer concorrência. O STRAIGHT_JOIN no today-sales deve deixar
    #          a query em poucos segundos; o orçamento generoso é rede de segurança.
    # shutdown(wait=False) libera o pool sem bloquear; threads daemon concluem sozinhas.
    import concurrent.futures as _cf_ah
    _ATIVO_TIMEOUT_S = 24
    _MAGENTO_ACQUIRE_BUDGET_S = 13
    _MAGENTO_EXEC_BUDGET_MS = 20000
    _MAGENTO_TIMEOUT_S = 35
    _t_parallel_start = _time_inner.time()
    _pool_ah = _TPE(max_workers=2)
    _fut_ativo   = _pool_ah.submit(_run_ativo)
    _fut_magento = _pool_ah.submit(_run_magento)
    try:
        _a_qtd, _a_rec, _a_ok = _fut_ativo.result(timeout=_ATIVO_TIMEOUT_S)
        logger.info(
            f"atualizar-hoje: Ativo OK em {_time_inner.time()-_t_parallel_start:.1f}s "
            f"para {evento_id} (qtd={_a_qtd})"
        )
    except _cf_ah.TimeoutError:
        _a_qtd, _a_rec, _a_ok = 0, 0.0, False
        logger.warning(f"atualizar-hoje: Ativo timeout ({_ATIVO_TIMEOUT_S}s) para {evento_id}")
    try:
        _m_qtd, _m_rec, _m_ok = _fut_magento.result(timeout=_MAGENTO_TIMEOUT_S)
        logger.info(
            f"atualizar-hoje: Magento OK em {_time_inner.time()-_t_parallel_start:.1f}s "
            f"para {evento_id} (qtd={_m_qtd})"
        )
    except _cf_ah.TimeoutError:
        _m_qtd, _m_rec, _m_ok = 0, 0.0, False
        logger.warning(f"atualizar-hoje: Magento timeout ({_MAGENTO_TIMEOUT_S}s) para {evento_id}")
    _pool_ah.shutdown(wait=False)
    logger.info(
        f"atualizar-hoje: bloco paralelo concluído em "
        f"{_time_inner.time()-_t_parallel_start:.1f}s para {evento_id} "
        f"(ativo_ok={_a_ok} magento_ok={_m_ok})"
    )

    if ativo_ids:
        if _a_ok:
            hoje_ativo   += _a_qtd
            hoje_receita += _a_rec
        else:
            ativo_ok = False
            sources_failed.append("ativo")
    # Último valor Magento conhecido (snapshot local) — usado quando Magento está indisponível
    _magento_ultimo_conhecido: Optional[int] = None
    _magento_ultimo_data: Optional[str] = None

    if magento_ids:
        if _m_ok:
            hoje_magento += _m_qtd
            hoje_receita += _m_rec
        else:
            magento_ok = False
            sources_failed.append("magento")
            # Busca último registro Magento no VendasDiariaSnapshot para exibir no modal
            try:
                _ult = (
                    db.query(_VDS.data_venda, _VDS.quantidade)
                    .filter(
                        _VDS.evento_grupo == grupo_nome,
                        _VDS.fonte == "magento",
                        _VDS.quantidade > 0,
                    )
                    .order_by(_VDS.data_venda.desc())
                    .first()
                )
                if _ult:
                    _magento_ultimo_conhecido = int(_ult.quantidade)
                    _magento_ultimo_data = _ult.data_venda.isoformat()
            except Exception as _ue:
                logger.debug(f"atualizar-hoje: falha ao buscar último Magento para {grupo_nome}: {_ue}")

    hoje_total = hoje_ativo + hoje_magento
    _pre_greatest_total = hoje_total  # save before any GREATEST() UPSERT may raise it

    grupo_needs_ativo = bool(ativo_ids)
    grupo_needs_magento = bool(magento_ids)

    ativo_healthy = not grupo_needs_ativo or ativo_ok
    magento_healthy = not grupo_needs_magento or magento_ok
    all_sources_ok = ativo_healthy and magento_healthy
    # Partial sync: at least one source healthy, one failed
    sync_partial = (not all_sources_ok) and (ativo_healthy or magento_healthy)
    # Full failure: nothing to work with
    sync_failed = not all_sources_ok and not sync_partial

    # --- Update snapshot for today ---
    # Full sync → overwrite with complete consolidated value.
    # Partial sync (one source down) → GREATEST() so we never lower a total
    #   previously persisted from a successful full sync, but always surface
    #   whatever the healthy source has (e.g. Ativo's 20 sales when Magento
    #   is timing out).
    # Both down → read existing row and return it without touching the DB.
    _HOJE_FONTE = 'CONSOLIDADO'
    _snapshot_updated_at = None  # set when partial UPSERT re-reads the row
    if grupo_nome and all_sources_ok:
        # Use pg INSERT ... ON CONFLICT DO UPDATE (1 SQL + COMMIT) instead of
        # SELECT + conditional UPDATE/INSERT + COMMIT (2-3 round trips).
        # The partial path already does this; align the full-sync path for consistency.
        try:
            from sqlalchemy.dialects.postgresql import insert as _pg_insert_full
            _stmt_full = _pg_insert_full(_VDS).values(
                evento_grupo=grupo_nome,
                fonte=_HOJE_FONTE,
                data_venda=hoje,
                quantidade=hoje_total,
                receita=hoje_receita,
                ano=ano,
                updated_at=datetime.now()
            ).on_conflict_do_update(
                index_elements=["evento_grupo", "fonte", "data_venda"],
                set_={
                    "quantidade": hoje_total,
                    "receita": hoje_receita,
                    "ano": ano,
                    "updated_at": datetime.now(),
                }
            )
            db.execute(_stmt_full)
            db.commit()
        except Exception as _e:
            logger.warning(f"atualizar-hoje: erro ao salvar snapshot para {grupo_nome}: {_e}")
            db.rollback()
    elif grupo_nome and sync_partial:
        # Partial UPSERT using GREATEST() — surfaces the healthy source data
        # without ever lowering a value from a previous full sync.
        missing = sources_failed[0] if sources_failed else "unknown"
        logger.warning(
            f"atualizar-hoje: UPSERT parcial para '{grupo_nome}' "
            f"({missing} indisponível) — usando GREATEST() para preservar total anterior"
        )
        try:
            from sqlalchemy.dialects.postgresql import insert as _pg_insert
            from sqlalchemy import func as _sa_func
            _stmt = _pg_insert(_VDS).values(
                evento_grupo=grupo_nome,
                fonte=_HOJE_FONTE,
                data_venda=hoje,
                quantidade=hoje_total,
                receita=hoje_receita,
                ano=ano,
                updated_at=datetime.now()
            ).on_conflict_do_update(
                index_elements=["evento_grupo", "fonte", "data_venda"],
                set_={
                    "quantidade": _sa_func.greatest(
                        _VDS.__table__.c.quantidade, hoje_total
                    ),
                    "receita": _sa_func.greatest(
                        _VDS.__table__.c.receita, hoje_receita
                    ),
                    "ano": ano,
                    "updated_at": datetime.now(),
                }
            )
            db.execute(_stmt)
            db.commit()
            # Re-read the final persisted value so hoje_total reflects what's
            # actually in the DB (may be higher due to GREATEST).
            existing_after = db.query(_VDS).filter(
                _VDS.evento_grupo == grupo_nome,
                _VDS.fonte == _HOJE_FONTE,
                _VDS.data_venda == hoje,
            ).first()
            if existing_after:
                hoje_total = int(existing_after.quantidade or 0)
                hoje_receita = float(existing_after.receita or 0.0)
                _snapshot_updated_at = existing_after.updated_at
        except Exception as _e:
            logger.warning(f"atualizar-hoje: erro no UPSERT parcial para '{grupo_nome}': {_e}")
            try:
                db.rollback()
            except Exception:
                pass
            # Fallback: read existing row for the response
            try:
                existing = db.query(_VDS).filter(
                    _VDS.evento_grupo == grupo_nome,
                    _VDS.fonte == _HOJE_FONTE,
                    _VDS.data_venda == hoje,
                ).first()
                if existing:
                    hoje_total = int(existing.quantidade or 0)
                    hoje_receita = float(existing.receita or 0.0)
                    _snapshot_updated_at = existing.updated_at
            except Exception:
                pass
    elif sync_failed and grupo_nome:
        # Both sources down — read existing row so response shows real data.
        try:
            existing = db.query(_VDS).filter(
                _VDS.evento_grupo == grupo_nome,
                _VDS.fonte == _HOJE_FONTE,
                _VDS.data_venda == hoje,
            ).first()
            if existing:
                hoje_total = int(existing.quantidade or 0)
                hoje_receita = float(existing.receita or 0.0)
        except Exception:
            pass
        logger.warning(
            f"atualizar-hoje: pulando UPSERT para '{grupo_nome}' — ambas fontes indisponíveis: {sources_failed}"
        )

    # --- Snapshot bridge: reclassify "parcial" → "concluido" when prior snapshot covered the gap ---
    # Conditions (ALL must be true):
    #   1. sync_partial — at least one source was healthy, one failed
    #   2. _pre_greatest_total > 0 — the live source(s) returned actual positive data, not zeros.
    #      If the live total is 0 the live fetch effectively did nothing useful, so we must NOT
    #      call this "concluido" even if a prior snapshot exists.
    #   3. hoje_total > _pre_greatest_total — the DB snapshot (from a prior same-day batch)
    #      had a higher value. GREATEST() preserved it, meaning the failed source's data is
    #      already in the DB from a previous full sync today.
    # Together these guarantee: (a) a live fetch ran and confirmed real Ativo sales, AND
    # (b) a same-day full-sync snapshot is covering the failed source's portion.
    _snapshot_bridge = False
    if sync_partial and _pre_greatest_total > 0 and hoje_total > _pre_greatest_total:
        logger.info(
            f"atualizar-hoje: snapshot bridge '{grupo_nome}' — "
            f"DB={hoje_total} > live={_pre_greatest_total} > 0 "
            f"(falhou: {sources_failed}) → reclassificando para concluido"
        )
        all_sources_ok = True
        sync_partial = False
        sync_failed = False
        _snapshot_bridge = True
    elif sync_partial and _pre_greatest_total == 0 and hoje_total > _pre_greatest_total:
        # Live source returned 0 (or all zeros), snapshot has prior data but no live confirmation.
        # Keep as "parcial" — we cannot confirm the live sources captured anything today.
        logger.info(
            f"atualizar-hoje: snapshot disponível para '{grupo_nome}' mas live=0 "
            f"— mantendo status parcial (sem confirmação de dados ao vivo)"
        )

    # --- Recalculate rolling averages from snapshot (no external DB) ---
    media_7d = 0.0
    media_14d = 0.0
    media_30d = 0.0
    total_acumulado = 0

    if grupo_nome:
        try:
            cutoff_30 = hoje - timedelta(days=30)
            # Filter exclusively by CONSOLIDADO to avoid double-counting entries
            # from other fontes (ATIVO, MAGENTO) that may coexist in the same table.
            # Restringe ao ano-edição: sem isso, grupos recorrentes (mesmo
            # evento_grupo em 2025 e 2026) somariam vendas de outra edição
            # quando o cutoff de 30 dias cair próximo de virada de ano.
            snap_rows = db.query(_VDS).filter(
                _VDS.evento_grupo == grupo_nome,
                _VDS.fonte == _HOJE_FONTE,
                _VDS.data_venda >= cutoff_30,
                _VDS.data_venda <= hoje,
                _VDS.ano == ano,
            ).order_by(_VDS.data_venda).all()

            daily_map: dict = {}
            for r in snap_rows:
                daily_map[r.data_venda] = daily_map.get(r.data_venda, 0) + int(r.quantidade or 0)

            def _avg_last_n(n: int) -> float:
                cutoff = hoje - timedelta(days=n)
                total = sum(v for d, v in daily_map.items() if d >= cutoff and d <= hoje)
                return round(total / n, 2)

            media_7d = _avg_last_n(7)
            media_14d = _avg_last_n(14)
            media_30d = _avg_last_n(30)

            # Total acumulado: filter by ano to avoid cross-year double-counting for
            # recurring annual events (same evento_grupo reused in 2025 and 2026).
            total_all = db.query(_sa_func.sum(_VDS.quantidade)).filter(
                _VDS.evento_grupo == grupo_nome,
                _VDS.fonte == _HOJE_FONTE,
                _VDS.ano == ano,
            ).scalar() or 0
            total_acumulado = int(total_all)
        except Exception as _e:
            logger.warning(f"atualizar-hoje: erro ao recalcular médias para {grupo_nome}: {_e}")

    # Invalidate the eventos list cache so the main table shows fresh counts immediately,
    # and the ISC cache so projected totals reflect the new today-sync data.
    # Also invalidate the event_detail_cache so the next fetch returns fresh data.
    try:
        eventos_list_cache.invalidate()
        _smart_isc_cache.invalidate()
        event_detail_cache.invalidate(f"{ano}_{evento_id}_detail")
        # Também limpa o cache do "Ticket Atual (Kit)" para que o preço/kits
        # reflitam mudanças de mapeamento (SKU/cadastro) imediatamente após o
        # sync manual — sem ter que esperar o TTL de 30min ou republicar o app.
        clear_ticket_atual_cache()
        logger.info(f"atualizar-hoje: caches invalidated for {evento_id} (incl. ticket_atual)")
    except Exception as _ci:
        logger.warning(f"atualizar-hoje: cache invalidation error: {_ci}")

    # Check whether this event has historical data in VendasDiariaSnapshot (excluding today).
    # If it has < 3 days of history, we trigger a full consolidar in background so that
    # the Controle Diário tab populates with the complete historical curve after the first sync.
    _has_history = False
    try:
        # Restringe ao ano-edição: detecção de "primeiro sync" precisa olhar
        # apenas a edição atual; rows da edição anterior do mesmo grupo não
        # devem mascarar como "histórico existe" e bloquear o consolidar full.
        _hist_count = db.query(func.count(_VDS.id)).filter(
            _VDS.evento_grupo == grupo_nome,
            _VDS.fonte == 'CONSOLIDADO',
            _VDS.data_venda < hoje,
            _VDS.ano == ano,
        ).scalar() or 0
        _has_history = _hist_count >= 3
    except Exception:
        _has_history = True  # assume has history on error to avoid unnecessary consolidar

    # Patch the persisted EventoDetailSnapshot in background using apply_today_overlay.
    # This is a lightweight operation (<100ms, zero Magento queries) that updates
    # dailySales[today] and currentSales directly in the PostgreSQL snapshot so that
    # the "Controle Diário" tab and event detail page reflect fresh data immediately.
    # When the event has NO historical data (first sync ever), we skip the patch and
    # run a full consolidar_vendas_grupo instead, which builds the complete history.
    if all_sources_ok or sync_partial:
        if not _has_history:
            # First-time sync: build full historical snapshot so Controle Diário populates
            try:
                import threading as _thread_consolidar_ah
                def _bg_consolidar_ah():
                    from ...core.database import SessionLocal as _CG_SL
                    _cg_db = _CG_SL()
                    try:
                        from ...services.snapshot_service import consolidar_vendas_grupo as _cvg
                        _cvg(_cg_db, grupo_nome, ano)
                        logger.info(f"atualizar-hoje: consolidar completo para '{grupo_nome}' (sem histórico) — Controle Diário populado")
                        # Invalidate caches so next re-fetch picks up the full history
                        event_detail_cache.invalidate(f"{ano}_{evento_id}_detail")
                        _smart_isc_cache.invalidate()
                    except Exception as _cg_e:
                        logger.warning(f"atualizar-hoje: consolidar falhou para '{grupo_nome}': {_cg_e}")
                    finally:
                        _cg_db.close()
                _thread_consolidar_ah.Thread(target=_bg_consolidar_ah, daemon=True).start()
                logger.info(f"atualizar-hoje: sem histórico para '{grupo_nome}' — consolidar agendado em background")
            except Exception as _cg_start_e:
                logger.warning(f"atualizar-hoje: erro ao enfileirar consolidar: {_cg_start_e}")
        else:
            # Has history: lightweight patch of today's entry only
            try:
                import threading as _thread_patch_ah
                def _bg_patch_snapshot_ah():
                    from ...core.database import SessionLocal as _PS_SL
                    _ps_db = _PS_SL()
                    try:
                        from ...services.event_detail_snapshot_service import (
                            get_persisted_detail as _gpd_patch,
                            save_persisted_detail as _spd_patch,
                            apply_today_overlay as _ov_patch,
                        )
                        _ps_persisted = _gpd_patch(_ps_db, evento_id, ano)
                        if _ps_persisted:
                            _ps_payload = _ps_persisted.get("payload") or {}
                            _ps_patched = _ov_patch(_ps_db, _ps_payload, evento_id, ano=ano)
                            _spd_patch(
                                _ps_db, evento_id, ano, _ps_patched,
                                data_evento=_ps_persisted.get("data_evento"),
                                is_completed=_ps_persisted.get("is_completed", False),
                            )
                            logger.info(f"atualizar-hoje: snapshot patched for {evento_id}")
                    except Exception as _ps_e:
                        logger.warning(f"atualizar-hoje: snapshot patch falhou para {evento_id}: {_ps_e}")
                    finally:
                        _ps_db.close()
                _thread_patch_ah.Thread(target=_bg_patch_snapshot_ah, daemon=True).start()
            except Exception as _ps_start_e:
                logger.warning(f"atualizar-hoje: erro ao enfileirar snapshot patch: {_ps_start_e}")

    # Atualiza o carimbo "Inscrições às HH:MM" exibido no detalhe do evento
    # para refletir a hora do clique. Faz isso quando pelo menos uma fonte
    # funcionou (full ou partial) — só omite quando ambas falharam.
    if all_sources_ok or sync_partial:
        try:
            from app.core.cache import set_last_sync_hoje as _set_lsh_a
            import time as _t_lsh_a
            _set_lsh_a(_t_lsh_a.time())
        except Exception as _e_lsh_a:
            logger.warning(f"atualizar-hoje: erro ao atualizar last_sync_hoje: {_e_lsh_a}")

    _response_status = "ok" if all_sources_ok else ("partial" if sync_partial else "failed")

    # Log de conclusão + grupo (painel de Sincronizações).
    # O log do ciclo é síncrono: o frontend faz re-fetch logo após receber a
    # resposta e precisa encontrar o status 'concluido' já gravado no banco.
    # O log do grupo é fire-and-forget (não afeta o status exibido na tabela).
    if ciclo_id:
        try:
            from ...services.sync_log_service import log_evento as _log_ev_end
            _duracao_ms_inner = int((_time_inner.time() - _t_start_inner) * 1000)
            _status_ciclo = "concluido" if all_sources_ok else ("parcial" if sync_partial else "falha")
            _status_grupo = "ok" if all_sources_ok else ("parcial" if sync_partial else "falha")
            _motivo_grupo = None if all_sources_ok else ("magento_indisponivel" if not magento_ok else "ativo_indisponivel")
            _detalhes_log = (
                f"ativo={hoje_ativo} magento={hoje_magento} total={hoje_total}"
                + (f" | indisponível: {', '.join(sources_failed)}" if sources_failed else "")
            )
            # Ciclo terminal: síncrono — deve estar no banco antes do return.
            _log_ev_end(ciclo_id, "atualizar_hoje", _status_ciclo, nivel="ciclo",
                        grupo=grupo_nome, duracao_ms=_duracao_ms_inner, detalhes=_detalhes_log)
            # Grupo: fire-and-forget (não afeta status do ciclo na UI).
            import threading as _thr_log_grp
            _thr_log_grp.Thread(
                target=_log_ev_end,
                args=(ciclo_id, "atualizar_hoje", _status_grupo),
                kwargs=dict(nivel="grupo", grupo=grupo_nome, qtd_antes=None,
                            qtd_depois=hoje_total, motivo=_motivo_grupo, duracao_ms=_duracao_ms_inner),
                daemon=True,
            ).start()
        except Exception:
            pass

    return {
        "status": _response_status,
        "evento_id": evento_id,
        "data": hoje.isoformat(),
        "hoje_ativo": hoje_ativo,
        "hoje_magento": hoje_magento,
        "hoje_total": hoje_total,
        "media_7d": media_7d,
        "media_14d": media_14d,
        "media_30d": media_30d,
        "total_acumulado": total_acumulado,
        "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(),
        "ativo_ok": ativo_ok,
        "magento_ok": magento_ok,
        "fontes_indisponiveis": sources_failed,
        "magento_ultimo_conhecido": _magento_ultimo_conhecido,
        "magento_ultimo_data": _magento_ultimo_data,
        "snapshot_bridge": _snapshot_bridge,
        "snapshot_atualizado_em": (
            _snapshot_updated_at.astimezone(ZoneInfo('America/Sao_Paulo')).isoformat()
            if _snapshot_bridge and _snapshot_updated_at else None
        ),
    }


@router.post("/eventos/{evento_id}/recalcular-snapshot")
def recalcular_snapshot_evento(
    evento_id: str,
    ano: Optional[int] = Query(
        default=None,
        description=(
            "Ano do evento a reconsolidar. Se omitido, resolve automaticamente "
            "pela mesma lógica da leitura (data cadastrada em dim_projeto para "
            "eventos individuais; ano corrente para eventos agrupados sem ano "
            "explícito). Sem isso, eventos agrupados cuja edição sendo exibida "
            "difere do ano corrente do servidor (ex.: próxima edição já com "
            "carrinho aberto) nunca conseguem reconsolidar a edição certa."
        ),
    ),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Força a recomputação completa do snapshot de um evento específico.

    Disponível para perfis **Admin** e **Diretoria**. Para a Diretoria, após
    sucesso o botão entra em cooldown de 20 min para evitar clique compulsivo.
    Aplica também um gate global: apenas UMA reconsolidação por vez no sistema
    inteiro (qualquer evento). Se outro evento estiver rodando, retorna 429.
    """
    from ...core.security import is_user_admin
    from .admin import (
        _user_is_diretoria, _try_acquire_evento_slot, _release_evento_slot,
        _set_evento_cooldown, _diretoria_cooldown_sec,
        _recalc_job_start, _recalc_job_finish,
    )

    is_diretoria = _user_is_diretoria(current_user)
    if not (is_user_admin(current_user) or is_diretoria):
        raise HTTPException(
            status_code=403,
            detail="Permissão insuficiente — requer perfil Admin ou Diretoria.",
        )

    # Resolve o ano ANTES do gate/job: mesma lógica usada na leitura, para que
    # a reconsolidação sempre recalcule/persista a edição que a tela está
    # exibindo (não o ano corrente do servidor). Chave de job/cooldown inclui
    # o ano para que reconsolidar uma edição não gere cooldown/estado cruzado
    # com outra edição do mesmo evento agrupado.
    ano_efetivo = _resolve_evento_ano_efetivo(db, evento_id, ano)
    _recalc_key = f"{evento_id}::{ano_efetivo}"

    # ── Gate ATÔMICO GLOBAL: só permite UMA reconsolidação por vez ─────────
    # Compartilha o mesmo _evento_inflight do admin.py (chave = evento_id::ano).
    # Cooldown da Diretoria só se aplica à mesma chave evento+ano.
    acquired, remaining, busy_evento = _try_acquire_evento_slot(
        _recalc_key, check_cooldown=is_diretoria
    )
    if not acquired:
        if busy_evento is not None:
            if busy_evento == _recalc_key:
                msg = (
                    "Já existe uma reconsolidação em andamento para este "
                    "evento. Aguarde a conclusão."
                )
                code = "reconsolidacao_em_andamento"
            else:
                msg = (
                    f"Outro evento está sendo reconsolidado agora. "
                    f"Aguarde a conclusão antes de iniciar uma nova reconsolidação."
                )
                code = "outro_evento_em_andamento"
            raise HTTPException(
                status_code=429,
                detail={
                    "code": code,
                    "message": msg,
                    "evento_id": evento_id,
                    "evento_em_andamento": busy_evento,
                },
            )
        mins = remaining // 60
        secs = remaining % 60
        tempo = f"{mins}min {secs}s" if mins else f"{secs}s"
        raise HTTPException(
            status_code=429,
            detail={
                "code": "cooldown_diretoria",
                "message": (
                    f"Este evento foi reconsolidado recentemente. "
                    f"Aguarde {tempo} antes de tentar novamente."
                ),
                "remaining_sec": remaining,
                "evento_id": evento_id,
            },
        )

    # ── Execução ASSÍNCRONA em thread ──────────────────────────────────────
    # O pipeline completo (Ativo + Magento + recálculos + persistência) pode
    # levar vários minutos quando o Magento está lento (fila concorrência=1,
    # SSH tunnel, retries). Rodando dentro do request, o proxy na frente do
    # backend cortava a conexão e o cliente recebia 502 mesmo com o trabalho
    # terminando com sucesso aqui. Agora o POST retorna {status:'started'}
    # imediatamente e o front acompanha via
    # GET /eventos/{evento_id}/recalcular-snapshot/status. O slot global é
    # liberado pela própria thread ao final.
    ano = ano_efetivo
    try:
        _recalc_job_start(_recalc_key, "recalcular-snapshot")

        def _run_recalc_job():
            from app.core.database import SessionLocal
            local_db = None
            try:
                local_db = SessionLocal()
                result = get_marketing_event_by_id(
                    evento_id=evento_id,
                    ano=ano,
                    force_refresh=True,
                    db=local_db,
                    current_user=None,
                    response=None,
                )

                margem_nova = None
                try:
                    from ...services.event_detail_snapshot_service import _extract_margem_total
                    from fastapi.encoders import jsonable_encoder
                    payload_json = jsonable_encoder(result)
                    margem_nova = _extract_margem_total(payload_json)
                except Exception:
                    pass

                # Cooldown só pra Diretoria após sucesso
                cooldown_until = None
                cooldown_sec_used = 0
                if is_diretoria:
                    cooldown_sec_used = _diretoria_cooldown_sec()
                    if cooldown_sec_used > 0:
                        cooldown_until = _set_evento_cooldown(_recalc_key, cooldown_sec_used)

                _recalc_job_finish(_recalc_key, result={
                    "status": "ok",
                    "evento_id": evento_id,
                    "ano": ano,
                    "margem_recalculada": margem_nova,
                    "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(),
                    "cooldown_aplicado": cooldown_until is not None,
                    "cooldown_until_epoch": cooldown_until,
                    "cooldown_total_sec": cooldown_sec_used,
                })
            except Exception as e:
                logger.error(f"[recalcular-snapshot] falhou para '{evento_id}' ano={ano}: {e}")
                _recalc_job_finish(_recalc_key, error=f"Erro ao recalcular snapshot: {str(e)[:400]}")
            finally:
                # Slot global liberado pela thread (não mais pelo request).
                _release_evento_slot(_recalc_key)
                if local_db is not None:
                    try:
                        local_db.close()
                    except Exception:
                        pass

        _threading.Thread(
            target=_run_recalc_job, daemon=True,
            name=f"recalc-snapshot-{evento_id[:40]}",
        ).start()
    except Exception as e:
        # Falha ANTES da thread assumir (ex.: Thread.start): libera o slot
        # aqui, senão ficaria preso para sempre.
        _release_evento_slot(_recalc_key)
        _recalc_job_finish(_recalc_key, error=f"Falha ao iniciar reconsolidação: {e}")
        logger.error(f"[recalcular-snapshot] falha ao iniciar thread p/ '{evento_id}' ano={ano}: {e}")
        raise HTTPException(status_code=500, detail=f"Falha ao iniciar reconsolidação: {e}")

    return {"status": "started", "evento_id": evento_id, "ano": ano}


@router.get("/eventos/{evento_id}/recalcular-snapshot/status")
def get_recalcular_snapshot_status(
    evento_id: str,
    ano: Optional[int] = Query(
        default=None,
        description="Ano usado ao disparar o POST /recalcular-snapshot. Deve ser o mesmo valor para localizar o job correto.",
    ),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Status do job assíncrono de reconsolidação disparado pelo POST acima
    (ou pelo /admin/snapshots/consolidar-evento, que registra o job sob o
    nome do grupo sem prefixo).

    `state`: 'idle' (nenhum job conhecido — ex.: servidor reiniciou),
    'running', 'done' (com `result`) ou 'error' (com `error`). Apenas
    leitura de metadados — exige somente usuário autenticado."""
    from .admin import _recalc_job_get
    # O POST /recalcular-snapshot registra o job sob a chave "evento_id::ano"
    # (evita misturar status entre edições diferentes do mesmo evento
    # agrupado). Tenta, nesta ordem: (1) ano explícito informado, (2) ano
    # resolvido pela mesma lógica do POST (rede de segurança para clientes
    # que ainda não repassam `ano` no polling), (3) chave legada sem ano —
    # usada pelo fluxo do admin /consolidar-evento.
    rec = _recalc_job_get(f"{evento_id}::{ano}") if ano is not None else None
    if rec is None and ano is None:
        try:
            ano_fallback = _resolve_evento_ano_efetivo(db, evento_id, None)
            rec = _recalc_job_get(f"{evento_id}::{ano_fallback}")
        except Exception:
            rec = None
    if rec is None:
        rec = _recalc_job_get(evento_id)
    if rec is None:
        return {"evento_id": evento_id, "state": "idle"}
    return {
        "evento_id": evento_id,
        "kind": rec.get("kind"),
        "state": rec.get("state"),
        "started_at": rec.get("started_at"),
        "finished_at": rec.get("finished_at"),
        "error": rec.get("error"),
        "result": rec.get("result"),
    }


@router.get("/eventos/{evento_id}/reconsolidar-cooldown")
def get_reconsolidar_cooldown(
    evento_id: str,
    ano: Optional[int] = Query(
        default=None,
        description="Ano da edição sendo exibida. Quando informado, cooldown/gate são verificados por evento+ano, não por evento sozinho.",
    ),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Retorna o status do cooldown/gate de reconsolidação para a UI.

    **Acesso restrito a Admin ou Diretoria** — usuários sem privilégio
    recebem 403 (não vazamos qual evento está sendo reconsolidado no momento
    para operadores comuns).
    - `can_reconsolidar`: sempre true neste endpoint (gate de 403 já filtrou).
    - `is_diretoria`: usuário é Diretoria (sujeito a cooldown).
    - `locked`/`remaining_sec`: cooldown ativo na mesma edição (evento+ano).
    - `evento_em_andamento`/`outro_em_andamento`: se há reconsolidação rodando.
    """
    from ...core.security import is_user_admin
    from .admin import (
        _user_is_diretoria, _evento_cooldown_remaining,
        _current_evento_inflight, _diretoria_cooldown_sec,
    )

    is_diretoria = _user_is_diretoria(current_user)
    if not (is_user_admin(current_user) or is_diretoria):
        raise HTTPException(
            status_code=403,
            detail="Permissão insuficiente — requer perfil Admin ou Diretoria.",
        )

    # Mesma chave evento_id::ano usada pelo POST /recalcular-snapshot. Sem
    # `ano` explícito, resolve pela mesma lógica da leitura para não checar
    # cooldown de um ano diferente do que a tela está exibindo.
    ano_efetivo = _resolve_evento_ano_efetivo(db, evento_id, ano)
    _cooldown_key = f"{evento_id}::{ano_efetivo}"

    remaining = _evento_cooldown_remaining(_cooldown_key) if is_diretoria else 0
    busy_evento = _current_evento_inflight()
    return {
        "evento_id": evento_id,
        "can_reconsolidar": True,
        "is_diretoria": is_diretoria,
        "locked": remaining > 0,
        "remaining_sec": remaining,
        "cooldown_total_sec": _diretoria_cooldown_sec(),
        "evento_em_andamento": busy_evento,
        "outro_em_andamento": (busy_evento is not None and busy_evento != _cooldown_key),
    }


@router.post("/cache/refresh")
def refresh_cache(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin())
):
    _smart_isc_cache.invalidate()
    event_detail_cache.invalidate()
    daily_sales_cache.invalidate()
    curva_cache.invalidate()
    medias_cache.invalidate()
    clear_warmup_daily_cache()
    clear_ticket_atual_cache()

    global _isc_cache, _isc_cache_timestamp, _sales_cache, _cache_timestamp
    _isc_cache = {}
    _isc_cache_timestamp = None
    _sales_cache = {}
    _cache_timestamp = None

    fetch_isc_pricing_data(db=db, force_refresh=True)

    cache_info = _smart_isc_cache.get_info(f"{datetime.now().year}_isc")

    return {
        "status": "success",
        "message": "Cache do ano atual atualizado com sucesso. Dados históricos preservados.",
        "cache_info": cache_info,
        "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat()
    }


@router.post("/cache/sync-hoje")
def sync_hoje_todos(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin())
):
    """Sincroniza apenas os dados de HOJE do MySQL para o snapshot PostgreSQL de todos os
    eventos ativos, depois reconstrói o ISC cache. Muito mais rápido que o refresh completo."""
    from app.services.snapshot_service import sincronizar_hoje_batch
    from app.core.cache import set_last_sync_hoje as _set_lsh
    import time as _time_lsh

    caller_name = getattr(current_user, "nome", None) or getattr(current_user, "email", "admin")

    if not try_acquire_sync_hoje(caller_name):
        quem = get_sync_hoje_running_by() or "outro usuário"
        from fastapi.responses import JSONResponse as _JR
        return _JR(status_code=409, content={
            "status": "busy",
            "message": f"Sincronização já em andamento (iniciada por {quem}). Aguarde o término antes de tentar novamente.",
            "synced": 0,
        })
    try:
        synced = sincronizar_hoje_batch(db)
    except Exception as e:
        logger.error(f"sync-hoje: erro em sincronizar_hoje_batch: {e}")
        return {"status": "error", "message": str(e), "synced": 0}
    finally:
        release_sync_hoje()

    # Atualiza o carimbo "Inscrições às HH:MM" para refletir o horário do clique
    # — caso contrário o badge fica preso no último tick automático do agendador.
    _set_lsh(_time_lsh.time())

    _smart_isc_cache.invalidate()
    eventos_list_cache.invalidate()
    event_detail_cache.invalidate()

    try:
        fetch_isc_pricing_data(db=db, force_refresh=True)
    except Exception as e:
        logger.warning(f"sync-hoje: erro ao reconstruir ISC cache: {e}")

    return {
        "status": "ok",
        "synced": synced,
        "message": f"Dados de hoje sincronizados para {synced} grupos. Tabela principal atualizada.",
        "ultima_atualizacao": datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat()
    }


@router.post("/cache/refresh-all")
def refresh_all_caches(
    current_user: Usuario = Depends(require_admin())
):
    from app.core.cache import (
        is_full_refresh_in_progress,
        trigger_full_warmup_async,
        get_warmup_progress,
        is_full_refresh_pending,
    )

    # Sempre aceita o clique. Se já tem rodada em andamento, enfileira a próxima.
    result = trigger_full_warmup_async()
    now_iso = datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat()
    progress = get_warmup_progress() if is_full_refresh_in_progress() else None

    if result == "queued":
        return {
            "status": "in_progress",
            "queued_next": True,
            "message": "Atualização em andamento — sua nova solicitação foi enfileirada e iniciará logo após.",
            "progress": progress,
            "ultima_atualizacao": now_iso,
        }
    if result == "started":
        return {
            "status": "started",
            "queued_next": is_full_refresh_pending(),
            "message": "Atualização completa iniciada em background.",
            "progress": progress,
            "ultima_atualizacao": now_iso,
        }
    return {
        "status": "error",
        "message": "Não foi possível iniciar a atualização (warmup não disponível).",
        "ultima_atualizacao": now_iso,
    }


@router.get("/debug/snapshot-grupo")
def debug_snapshot_grupo(
    grupo: str,
    ano: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin()),
):
    """
    Diagnostic endpoint: returns a breakdown of vendas_diaria_snapshot rows
    for a specific grupo, grouped by calendar year and date range.
    Useful for identifying pre-sale orders or data contamination.
    """
    from app.models.vendas_snapshot import VendasDiariaSnapshot
    import datetime as _diag_dt

    _ano = ano or today_brazil().year

    rows = db.query(
        VendasDiariaSnapshot.data_venda,
        VendasDiariaSnapshot.quantidade,
        VendasDiariaSnapshot.receita,
        VendasDiariaSnapshot.ano,
        VendasDiariaSnapshot.fonte,
    ).filter(
        VendasDiariaSnapshot.evento_grupo == grupo,
    ).order_by(VendasDiariaSnapshot.data_venda).all()

    year_start      = _diag_dt.date(_ano, 1, 1)
    presale_start   = _diag_dt.date(_ano - 1, 9, 1)
    year_end        = _diag_dt.date(_ano + 1, 1, 1)

    in_year         = [r for r in rows if r.data_venda >= year_start and r.data_venda < year_end]
    presale         = [r for r in rows if r.data_venda >= presale_start and r.data_venda < year_start]
    before_presale  = [r for r in rows if r.data_venda < presale_start]
    after_year      = [r for r in rows if r.data_venda >= year_end]

    def _summarize(subset):
        return {
            "count_days": len(subset),
            "total_qtd": sum(r.quantidade or 0 for r in subset),
            "total_receita": round(sum(float(r.receita or 0) for r in subset), 2),
            "date_min": str(subset[0].data_venda) if subset else None,
            "date_max": str(subset[-1].data_venda) if subset else None,
            "rows": [{"data_venda": str(r.data_venda), "qtd": r.quantidade, "ano_col": r.ano, "fonte": r.fonte}
                     for r in subset],
        }

    isc_total = sum(r.quantidade or 0 for r in rows
                    if (r.ano == _ano) or (r.data_venda >= presale_start and r.data_venda < year_end))

    return {
        "grupo": grupo,
        "ano_consultado": _ano,
        "isc_total_atual": isc_total,
        "total_snapshot_sem_filtro": sum(r.quantidade or 0 for r in rows),
        "breakdown": {
            f"em_{_ano}": _summarize(in_year),
            f"pre_venda_{_ano - 1}_set_dez": _summarize(presale),
            f"antes_set_{_ano - 1}": _summarize(before_presale),
            f"depois_{_ano}": _summarize(after_year),
        },
        "by_ano_col": {
            str(yr): sum(r.quantidade or 0 for r in rows if r.ano == yr)
            for yr in sorted(set(r.ano for r in rows if r.ano is not None))
        },
    }


@router.get("/cache/status")
def get_cache_status(
    current_user: Usuario = Depends(require_admin())
):
    import time as _cst_time
    from app.core.cache import get_last_full_refresh, get_last_sync_hoje, is_full_refresh_in_progress, get_warmup_progress, get_last_refresh_error, get_warmup_event_results, get_warmup_summary, get_gap_detection_result, get_known_tier1_ids

    current_year = datetime.now().year
    last_refresh = get_last_full_refresh()
    last_refresh_str = None
    if last_refresh:
        last_refresh_str = datetime.fromtimestamp(last_refresh, tz=ZoneInfo('America/Sao_Paulo')).isoformat()

    last_sync_hoje = get_last_sync_hoje()
    last_sync_hoje_str = None
    if last_sync_hoje:
        last_sync_hoje_str = datetime.fromtimestamp(last_sync_hoje, tz=ZoneInfo('America/Sao_Paulo')).isoformat()

    in_progress = is_full_refresh_in_progress()
    progress = get_warmup_progress() if in_progress else None
    last_error = get_last_refresh_error()
    warmup_summary = get_warmup_summary()
    warmup_results = get_warmup_event_results()
    gap_result = get_gap_detection_result()

    STALE_THRESHOLD = 25 * 3600
    now_ts = _cst_time.time()
    all_timestamps = event_detail_cache.get_all_timestamps()

    def _extract_event_id(cache_key: str) -> str:
        """Strip '{ano}_' prefix and '_detail' suffix from cache key to get event ID."""
        parts = cache_key.split("_", 1)
        raw = parts[1] if len(parts) == 2 else cache_key
        if raw.endswith("_detail"):
            raw = raw[:-7]
        return raw

    current_year_ages = {}
    for k, ts in all_timestamps.items():
        if not event_detail_cache._is_historical(k):
            current_year_ages[k] = now_ts - ts

    oldest_hours = round(max(current_year_ages.values()) / 3600, 1) if current_year_ages else None
    newest_hours = round(min(current_year_ages.values()) / 3600, 1) if current_year_ages else None
    stale_event_ids = [_extract_event_id(k) for k, age in current_year_ages.items() if age > STALE_THRESHOLD]

    known_tier1 = get_known_tier1_ids()
    missing_tier1 = []
    stale_tier1 = []
    for eid in known_tier1:
        key = f"{current_year}_{eid}_detail"
        ts = all_timestamps.get(key)
        if ts is None:
            missing_tier1.append(eid)
        elif (now_ts - ts) > STALE_THRESHOLD:
            stale_tier1.append(eid)

    return {
        "status": "success",
        "refresh_in_progress": in_progress,
        "progress": progress,
        "last_error": last_error,
        "ultima_atualizacao_completa": last_refresh_str,
        "last_sync_hoje": last_sync_hoje_str,
        "warmup_duration_seconds": warmup_summary.get("duration_seconds"),
        "warmup_completed_at": warmup_summary.get("completed_at"),
        "warmup_summary": warmup_summary,
        "warmup_results": warmup_results,
        "gap_detection": {
            **gap_result,
            "missing_tier1_events": missing_tier1,
            "stale_tier1_events": stale_tier1,
        },
        "missing_tier1_events": missing_tier1,
        "stale_tier1_events": stale_tier1,
        "oldest_event_detail_age_hours": oldest_hours,
        "newest_event_detail_age_hours": newest_hours,
        "stale_events": stale_event_ids,
        "caches": {
            "isc_pricing": _smart_isc_cache.get_info(f"{current_year}_isc"),
            "event_detail": {
                "entries": event_detail_cache.entry_count(),
                "historical": sum(1 for k in event_detail_cache.get_all_keys() if event_detail_cache._is_historical(k)),
                "current_year": sum(1 for k in event_detail_cache.get_all_keys() if not event_detail_cache._is_historical(k)),
                "oldest_event_detail_age_hours": oldest_hours,
                "newest_event_detail_age_hours": newest_hours,
                "stale_events": stale_event_ids,
            },
            "curva_comparativa": {
                "entries": curva_cache.entry_count(),
            },
            "medias_vendas": {
                "entries": medias_cache.entry_count(),
            }
        },
        "config": {
            "historical_ttl": "permanent",
            "current_year_ttl_seconds": CURRENT_YEAR_TTL,
            "auto_refresh_interval_seconds": 2700,
            "daily_refresh_time": "05:00 BRT"
        }
    }


class AcaoComercialCreate(BaseModel):
    projeto_id: int
    tipo: str
    descricao: str
    data_acao: date
    ponto_corte: Optional[str] = None
    estagio: Optional[str] = None
    snapshot_isc: Optional[float] = None
    snapshot_isc_state: Optional[str] = None
    snapshot_d_minus: Optional[int] = None
    snapshot_ia730: Optional[float] = None
    snapshot_rolling14d: Optional[float] = None
    snapshot_curva_percent: Optional[float] = None
    snapshot_vendas_acumuladas: Optional[int] = None
    snapshot_playbook_letter: Optional[str] = None

class AcaoComercialUpdate(BaseModel):
    tipo: Optional[str] = None
    descricao: Optional[str] = None
    data_acao: Optional[date] = None

class AcaoComercialResponse(BaseModel):
    id: int
    projeto_id: int
    tipo: str
    descricao: str
    data_acao: str
    impacto_percentual: Optional[float] = None
    vendas_antes: Optional[int] = None
    vendas_depois: Optional[int] = None
    ponto_corte: Optional[str] = None
    estagio: Optional[str] = None
    snapshot_isc: Optional[float] = None
    snapshot_isc_state: Optional[str] = None
    snapshot_d_minus: Optional[int] = None
    snapshot_ia730: Optional[float] = None
    snapshot_rolling14d: Optional[float] = None
    snapshot_curva_percent: Optional[float] = None
    snapshot_vendas_acumuladas: Optional[int] = None
    snapshot_playbook_letter: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("/acoes-comerciais/{projeto_id}")
def get_acoes_comerciais(
    projeto_id: int,
    calcular_impacto: bool = Query(default=True, description="Calcular impacto em tempo real"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing_dashboard", "pode_visualizar"))
):
    """Lista todas as ações comerciais de um projeto/evento com cálculo de impacto"""
    from ...models.dimensoes import AcaoComercial
    
    acoes = db.query(AcaoComercial).filter(
        AcaoComercial.projeto_id == projeto_id
    ).order_by(AcaoComercial.data_acao.desc()).all()
    
    acoes_list = []
    for a in acoes:
        acao_data = {
            "id": a.id,
            "projeto_id": a.projeto_id,
            "tipo": a.tipo,
            "descricao": a.descricao,
            "data_acao": a.data_acao.isoformat() if a.data_acao else None,
            "impacto_percentual": float(a.impacto_percentual) if a.impacto_percentual else None,
            "vendas_antes": a.vendas_antes,
            "vendas_depois": a.vendas_depois,
            "ponto_corte": a.ponto_corte,
            "estagio": a.estagio,
            "snapshot_isc": float(a.snapshot_isc) if a.snapshot_isc is not None else None,
            "snapshot_isc_state": a.snapshot_isc_state,
            "snapshot_d_minus": a.snapshot_d_minus,
            "snapshot_ia730": float(a.snapshot_ia730) if a.snapshot_ia730 is not None else None,
            "snapshot_rolling14d": float(a.snapshot_rolling14d) if a.snapshot_rolling14d is not None else None,
            "snapshot_curva_percent": float(a.snapshot_curva_percent) if a.snapshot_curva_percent is not None else None,
            "snapshot_vendas_acumuladas": a.snapshot_vendas_acumuladas,
            "snapshot_playbook_letter": a.snapshot_playbook_letter,
            "created_at": a.created_at.isoformat() if a.created_at else None
        }
        
        if calcular_impacto and a.data_acao:
            impacto = calculate_action_impact(db, a)
            acao_data["vendas_antes"] = impacto.get("vendas_antes")
            acao_data["vendas_depois"] = impacto.get("vendas_depois")
            acao_data["impacto_percentual"] = impacto.get("impacto_percentual")
            acao_data["status_impacto"] = impacto.get("status", "calculado")
        
        acoes_list.append(acao_data)
    
    return {
        "status": "success",
        "acoes": acoes_list
    }


@router.post("/acoes-comerciais")
def create_acao_comercial(
    acao: AcaoComercialCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing_dashboard", "pode_editar"))
):
    """Cria uma nova ação comercial vinculada ao ponto de corte e com snapshot dos dados ISC"""
    from ...models.dimensoes import AcaoComercial
    
    projeto = db.query(DimProjeto).filter(DimProjeto.id == acao.projeto_id).first()
    if not projeto:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    
    nova_acao = AcaoComercial(
        projeto_id=acao.projeto_id,
        tipo=acao.tipo,
        descricao=acao.descricao,
        data_acao=acao.data_acao,
        ponto_corte=acao.ponto_corte,
        estagio=acao.estagio,
        snapshot_isc=acao.snapshot_isc,
        snapshot_isc_state=acao.snapshot_isc_state,
        snapshot_d_minus=acao.snapshot_d_minus,
        snapshot_ia730=acao.snapshot_ia730,
        snapshot_rolling14d=acao.snapshot_rolling14d,
        snapshot_curva_percent=acao.snapshot_curva_percent,
        snapshot_vendas_acumuladas=acao.snapshot_vendas_acumuladas,
        snapshot_playbook_letter=acao.snapshot_playbook_letter,
    )
    
    db.add(nova_acao)
    db.commit()
    db.refresh(nova_acao)
    _bust_commercial_actions_cache_for_projeto(db, nova_acao.projeto_id)

    return {
        "status": "success",
        "message": "Ação comercial criada com sucesso",
        "acao": {
            "id": nova_acao.id,
            "projeto_id": nova_acao.projeto_id,
            "tipo": nova_acao.tipo,
            "descricao": nova_acao.descricao,
            "data_acao": nova_acao.data_acao.isoformat() if nova_acao.data_acao else None,
            "ponto_corte": nova_acao.ponto_corte,
            "estagio": nova_acao.estagio,
        }
    }


@router.put("/acoes-comerciais/{acao_id}")
def update_acao_comercial(
    acao_id: int,
    acao_update: AcaoComercialUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing_dashboard", "pode_editar"))
):
    """Atualiza uma ação comercial existente"""
    from ...models.dimensoes import AcaoComercial
    
    acao = db.query(AcaoComercial).filter(AcaoComercial.id == acao_id).first()
    if not acao:
        raise HTTPException(status_code=404, detail="Ação comercial não encontrada")
    
    if acao_update.tipo is not None:
        acao.tipo = acao_update.tipo
    if acao_update.descricao is not None:
        acao.descricao = acao_update.descricao
    if acao_update.data_acao is not None:
        acao.data_acao = acao_update.data_acao
    
    db.commit()
    db.refresh(acao)
    _bust_commercial_actions_cache_for_projeto(db, acao.projeto_id)

    return {
        "status": "success",
        "message": "Ação comercial atualizada com sucesso",
        "acao": {
            "id": acao.id,
            "projeto_id": acao.projeto_id,
            "tipo": acao.tipo,
            "descricao": acao.descricao,
            "data_acao": acao.data_acao.isoformat() if acao.data_acao else None
        }
    }


@router.delete("/acoes-comerciais/{acao_id}")
def delete_acao_comercial(
    acao_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing_dashboard", "pode_deletar"))
):
    """Remove uma ação comercial"""
    from ...models.dimensoes import AcaoComercial
    
    acao = db.query(AcaoComercial).filter(AcaoComercial.id == acao_id).first()
    if not acao:
        raise HTTPException(status_code=404, detail="Ação comercial não encontrada")
    
    _proj_id_for_bust = acao.projeto_id
    db.delete(acao)
    db.commit()
    _bust_commercial_actions_cache_for_projeto(db, _proj_id_for_bust)

    return {
        "status": "success",
        "message": "Ação comercial removida com sucesso"
    }


class AnaliseDiariaCreate(BaseModel):
    projeto_id: int
    data_analise: date
    ponto_corte: Optional[str] = None
    estagio: Optional[str] = None
    analise_texto: str
    ponto_critico: Optional[str] = None
    tipo_acao_sugerida: str
    acao_sugerida_descricao: Optional[str] = None
    retorno_estimado_tipo: Optional[str] = None
    retorno_estimado_valor: Optional[float] = None
    snapshot_isc: Optional[float] = None
    snapshot_isc_state: Optional[str] = None
    snapshot_d_minus: Optional[int] = None
    snapshot_ia730: Optional[float] = None
    snapshot_rolling14d: Optional[float] = None
    snapshot_curva_percent: Optional[float] = None
    snapshot_vendas_acumuladas: Optional[int] = None
    snapshot_playbook_letter: Optional[str] = None
    snapshot_media_semana_atual: Optional[float] = None
    snapshot_ticket_medio_realizado: Optional[float] = None


class AnaliseDiariaUpdate(BaseModel):
    analise_texto: Optional[str] = None
    ponto_critico: Optional[str] = None
    tipo_acao_sugerida: Optional[str] = None
    acao_sugerida_descricao: Optional[str] = None
    retorno_estimado_tipo: Optional[str] = None
    retorno_estimado_valor: Optional[float] = None


def _analise_diaria_to_dict(a) -> dict:
    from datetime import timezone as _tz_analise

    def _naive_utc_iso(dt):
        # created_at/updated_at são gravados via func.now() numa coluna sem
        # timezone; a sessão do Postgres roda em UTC (mesmo TZ do container),
        # então o valor naive representa um instante UTC. Sem marcar o tzinfo
        # explicitamente, new Date(...) no frontend interpreta a string como
        # horário LOCAL do navegador (ex.: Brasília), exibindo a hora errada
        # (3h adiantada). Marcar como UTC aqui permite a conversão correta.
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_tz_analise.utc)
        return dt.isoformat()

    return {
        "id": a.id,
        "projeto_id": a.projeto_id,
        "autor_id": a.autor_id,
        "autor_nome": a.autor_nome,
        "data_analise": a.data_analise.isoformat() if a.data_analise else None,
        "ponto_corte": a.ponto_corte,
        "estagio": a.estagio,
        "analise_texto": a.analise_texto,
        "ponto_critico": a.ponto_critico,
        "tipo_acao_sugerida": a.tipo_acao_sugerida,
        "acao_sugerida_descricao": a.acao_sugerida_descricao,
        "retorno_estimado_tipo": a.retorno_estimado_tipo,
        "retorno_estimado_valor": float(a.retorno_estimado_valor) if a.retorno_estimado_valor is not None else None,
        "snapshot_isc": float(a.snapshot_isc) if a.snapshot_isc is not None else None,
        "snapshot_isc_state": a.snapshot_isc_state,
        "snapshot_d_minus": a.snapshot_d_minus,
        "snapshot_ia730": float(a.snapshot_ia730) if a.snapshot_ia730 is not None else None,
        "snapshot_rolling14d": float(a.snapshot_rolling14d) if a.snapshot_rolling14d is not None else None,
        "snapshot_curva_percent": float(a.snapshot_curva_percent) if a.snapshot_curva_percent is not None else None,
        "snapshot_vendas_acumuladas": a.snapshot_vendas_acumuladas,
        "snapshot_playbook_letter": a.snapshot_playbook_letter,
        "snapshot_media_semana_atual": float(a.snapshot_media_semana_atual) if a.snapshot_media_semana_atual is not None else None,
        "snapshot_ticket_medio_realizado": float(a.snapshot_ticket_medio_realizado) if a.snapshot_ticket_medio_realizado is not None else None,
        "created_at": _naive_utc_iso(a.created_at),
        "updated_at": _naive_utc_iso(a.updated_at),
    }


@router.get("/analises-diarias/{projeto_id}")
def get_analises_diarias(
    projeto_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing_dashboard", "pode_visualizar"))
):
    """Lista todas as análises diárias de um projeto/evento, mais recentes primeiro"""
    from ...models.dimensoes import AnaliseDiaria

    analises = db.query(AnaliseDiaria).filter(
        AnaliseDiaria.projeto_id == projeto_id
    ).order_by(AnaliseDiaria.data_analise.desc()).all()

    return {
        "status": "success",
        "analises": [_analise_diaria_to_dict(a) for a in analises]
    }


@router.post("/analises-diarias")
def create_or_update_analise_diaria(
    analise: AnaliseDiariaCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing_dashboard", "pode_editar"))
):
    """Cria a análise diária do evento com snapshot ISC congelado. Se já existir uma
    análise para o mesmo projeto no mesmo dia, atualiza o registro existente em vez
    de criar um duplicado (regra: 1 análise por evento por dia, editável no mesmo dia)."""
    from ...models.dimensoes import AnaliseDiaria

    projeto = db.query(DimProjeto).filter(DimProjeto.id == analise.projeto_id).first()
    if not projeto:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    if not analise.analise_texto.strip():
        raise HTTPException(status_code=422, detail="Análise Simplificada é obrigatória")
    if not analise.tipo_acao_sugerida:
        raise HTTPException(status_code=422, detail="Tipo de Ação Sugerida é obrigatório")

    existente = db.query(AnaliseDiaria).filter(
        AnaliseDiaria.projeto_id == analise.projeto_id,
        AnaliseDiaria.data_analise == analise.data_analise
    ).first()

    dados_conteudo = dict(
        ponto_corte=analise.ponto_corte,
        estagio=analise.estagio,
        analise_texto=analise.analise_texto,
        ponto_critico=analise.ponto_critico,
        tipo_acao_sugerida=analise.tipo_acao_sugerida,
        acao_sugerida_descricao=analise.acao_sugerida_descricao,
        retorno_estimado_tipo=analise.retorno_estimado_tipo,
        retorno_estimado_valor=analise.retorno_estimado_valor,
        snapshot_isc=analise.snapshot_isc,
        snapshot_isc_state=analise.snapshot_isc_state,
        snapshot_d_minus=analise.snapshot_d_minus,
        snapshot_ia730=analise.snapshot_ia730,
        snapshot_rolling14d=analise.snapshot_rolling14d,
        snapshot_curva_percent=analise.snapshot_curva_percent,
        snapshot_vendas_acumuladas=analise.snapshot_vendas_acumuladas,
        snapshot_playbook_letter=analise.snapshot_playbook_letter,
        snapshot_media_semana_atual=analise.snapshot_media_semana_atual,
        snapshot_ticket_medio_realizado=analise.snapshot_ticket_medio_realizado,
    )

    if existente:
        for campo, valor in dados_conteudo.items():
            setattr(existente, campo, valor)
        existente.autor_id = current_user.id
        existente.autor_nome = current_user.nome
        db.commit()
        db.refresh(existente)
        return {
            "status": "success",
            "message": "Análise diária atualizada com sucesso",
            "analise": _analise_diaria_to_dict(existente)
        }

    nova_analise = AnaliseDiaria(
        projeto_id=analise.projeto_id,
        data_analise=analise.data_analise,
        autor_id=current_user.id,
        autor_nome=current_user.nome,
        **dados_conteudo,
    )
    db.add(nova_analise)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Corrida rara: outra requisição criou a análise do dia entre o SELECT e o INSERT.
        existente = db.query(AnaliseDiaria).filter(
            AnaliseDiaria.projeto_id == analise.projeto_id,
            AnaliseDiaria.data_analise == analise.data_analise
        ).first()
        if not existente:
            raise
        for campo, valor in dados_conteudo.items():
            setattr(existente, campo, valor)
        existente.autor_id = current_user.id
        existente.autor_nome = current_user.nome
        db.commit()
        db.refresh(existente)
        return {
            "status": "success",
            "message": "Análise diária atualizada com sucesso",
            "analise": _analise_diaria_to_dict(existente)
        }

    db.refresh(nova_analise)
    return {
        "status": "success",
        "message": "Análise diária registrada com sucesso",
        "analise": _analise_diaria_to_dict(nova_analise)
    }


@router.put("/analises-diarias/{analise_id}")
def update_analise_diaria(
    analise_id: int,
    analise_update: AnaliseDiariaUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing_dashboard", "pode_editar"))
):
    """Atualiza uma análise diária existente — permitido apenas no mesmo dia do registro."""
    from ...models.dimensoes import AnaliseDiaria

    analise = db.query(AnaliseDiaria).filter(AnaliseDiaria.id == analise_id).first()
    if not analise:
        raise HTTPException(status_code=404, detail="Análise diária não encontrada")

    if analise.data_analise != date.today():
        raise HTTPException(status_code=409, detail="Só é possível editar a análise no mesmo dia do registro")

    if analise_update.analise_texto is not None:
        if not analise_update.analise_texto.strip():
            raise HTTPException(status_code=422, detail="Análise Simplificada é obrigatória")
        analise.analise_texto = analise_update.analise_texto
    if analise_update.tipo_acao_sugerida is not None:
        analise.tipo_acao_sugerida = analise_update.tipo_acao_sugerida
    if analise_update.ponto_critico is not None:
        analise.ponto_critico = analise_update.ponto_critico or None
    if analise_update.acao_sugerida_descricao is not None:
        analise.acao_sugerida_descricao = analise_update.acao_sugerida_descricao
    if analise_update.retorno_estimado_tipo is not None:
        analise.retorno_estimado_tipo = analise_update.retorno_estimado_tipo or None
    if analise_update.retorno_estimado_valor is not None:
        analise.retorno_estimado_valor = analise_update.retorno_estimado_valor

    analise.autor_id = current_user.id
    analise.autor_nome = current_user.nome

    db.commit()
    db.refresh(analise)

    return {
        "status": "success",
        "message": "Análise diária atualizada com sucesso",
        "analise": _analise_diaria_to_dict(analise)
    }


@router.delete("/analises-diarias/{analise_id}")
def delete_analise_diaria(
    analise_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing_dashboard", "pode_deletar"))
):
    """Remove uma análise diária"""
    from ...models.dimensoes import AnaliseDiaria

    analise = db.query(AnaliseDiaria).filter(AnaliseDiaria.id == analise_id).first()
    if not analise:
        raise HTTPException(status_code=404, detail="Análise diária não encontrada")

    db.delete(analise)
    db.commit()

    return {
        "status": "success",
        "message": "Análise diária removida com sucesso"
    }


class PricingMetrics(BaseModel):
    rollingIndex: float
    rollingAvg14d: float
    rollingAvg14dLastYear: float
    paceRequired: float
    ied: float
    projection: float
    paceSeguranca: float
    fem: float
    ia: float

class ElasticityScenario(BaseModel):
    priceIncrease: float
    newPrice: float
    newMargin: float
    acceptableVolumeDrop: float
    minPace: float

class PricingDecision(BaseModel):
    action: str
    reason: str
    confidence: str

class KitBreakdownItem(BaseModel):
    tipoKit: str
    custoKit: Optional[float] = None

class PricingEvent(BaseModel):
    id: str
    name: str
    date: str
    location: str
    category: str
    totalCapacity: int
    currentSales: int
    salesGoal: int
    averageTicket: float
    kitCost: float
    dMinus: int
    isActive: bool
    sku: Optional[str] = None
    pricingMetrics: PricingMetrics
    elasticityScenarios: List[ElasticityScenario]
    decision: PricingDecision
    iscStatus: str
    kitBreakdown: Optional[List[KitBreakdownItem]] = None

class PricingSummary(BaseModel):
    totalEvents: int
    eventsToIncrease: int
    eventsToMaintain: int
    eventsToDecrease: int

class PricingEventsResponse(BaseModel):
    status: str
    eventos: List[PricingEvent]
    resumo: PricingSummary
    categorias: List[str]
    ultima_atualizacao: str
    avisos: List[str] = []


def calculate_pricing_metrics(
    current_sales: int, 
    sales_goal: int, 
    d_minus: int, 
    average_ticket: float,
    kit_cost: float,
    total_capacity: int,
    rolling_avg_14d_real: Optional[float] = None,
    rolling_avg_14d_last_year: float = 0.0
) -> PricingMetrics:
    if d_minus <= 0:
        d_minus = 1
    
    total_days = 90
    elapsed_days = max(1, total_days - d_minus)
    inscricoes_restantes = max(1, sales_goal - current_sales)
    
    if rolling_avg_14d_real is not None:
        rolling_avg_14d = rolling_avg_14d_real
    else:
        if elapsed_days > 14:
            rolling_avg_14d = current_sales / elapsed_days
        else:
            rolling_avg_14d = current_sales / max(1, elapsed_days)
    
    pace_required = inscricoes_restantes / max(1, d_minus)
    
    if pace_required > 0:
        rolling_index = rolling_avg_14d / pace_required
    else:
        rolling_index = 2.0
    
    if rolling_avg_14d > 0 and sales_goal > 0:
        projection = current_sales + (rolling_avg_14d * d_minus)
    elif elapsed_days > 0 and sales_goal > 0:
        projection = (current_sales / elapsed_days) * total_days
    else:
        projection = current_sales
    
    expected_daily = sales_goal / max(1, total_days)
    if expected_daily > 0:
        ia = rolling_avg_14d / expected_daily
    else:
        ia = 1.0
    
    if sales_goal > 0:
        ied = projection / sales_goal
    else:
        ied = 1.0
    
    current_margin = average_ticket - kit_cost
    new_margin = (average_ticket * 1.10) - kit_cost
    
    if new_margin > 0:
        fem = current_margin / new_margin
    else:
        fem = 1.0
    
    pace_seguranca = rolling_avg_14d * fem
    
    return PricingMetrics(
        rollingIndex=round(rolling_index, 2),
        rollingAvg14d=round(rolling_avg_14d, 2),
        rollingAvg14dLastYear=round(rolling_avg_14d_last_year, 2),
        paceRequired=round(pace_required, 2),
        ied=round(ied, 2),
        projection=round(projection, 0),
        paceSeguranca=round(pace_seguranca, 2),
        fem=round(fem, 3),
        ia=round(ia, 2)
    )


def calculate_elasticity_scenarios(
    average_ticket: float,
    kit_cost: float,
    rolling_avg_14d: float
) -> List[ElasticityScenario]:
    """
    Calcula cenários de elasticidade para diferentes aumentos de preço.
    Mostra a queda de volume aceitável para cada cenário.
    """
    scenarios = []
    increases = [5, 10, 15, 20]
    
    current_margin = average_ticket - kit_cost
    
    for inc in increases:
        new_price = average_ticket * (1 + inc / 100)
        new_margin = new_price - kit_cost
        
        if current_margin > 0 and new_margin > 0:
            fem = current_margin / new_margin
            acceptable_drop = (1 - fem) * 100
            min_pace = rolling_avg_14d * fem
        else:
            acceptable_drop = 0
            min_pace = rolling_avg_14d
        
        scenarios.append(ElasticityScenario(
            priceIncrease=inc,
            newPrice=round(new_price, 2),
            newMargin=round(new_margin, 2),
            acceptableVolumeDrop=round(acceptable_drop, 1),
            minPace=round(min_pace, 2)
        ))
    
    return scenarios


def get_pricing_decision(
    metrics: PricingMetrics,
    d_minus: int
) -> PricingDecision:
    """
    Determina a decisão de pricing baseada na matriz do documento:
    
    | IA (Aceleração) | Projeção vs Meta | Ação Recomendada |
    |-----------------|------------------|------------------|
    | Alto (> 1.2)    | Projeção > Meta  | Subir Preço Agora |
    | Estável (1.0)   | Projeção > Meta  | Subir Gradual |
    | Caindo (< 0.9)  | Projeção > Meta  | Manter / Focar Volume |
    """
    ia = metrics.ia
    ied = metrics.ied
    rolling_index = metrics.rollingIndex
    
    if ia > 1.2 and ied > 1.0:
        return PricingDecision(
            action="increase_now",
            reason=f"IA alto ({ia:.2f}) e projeção acima da meta (IED {ied:.2f}). Demanda inelástica detectada.",
            confidence="high"
        )
    
    if ia >= 0.95 and ia <= 1.2 and ied > 1.0:
        return PricingDecision(
            action="increase_gradual",
            reason=f"IA estável ({ia:.2f}) com projeção acima da meta. Capture margem nos próximos lotes.",
            confidence="medium"
        )
    
    if ia < 0.9 and ied > 1.0:
        return PricingDecision(
            action="maintain",
            reason=f"IA em queda ({ia:.2f}), mas projeção ainda acima da meta. Priorize volume.",
            confidence="medium"
        )
    
    if rolling_index > 1.3 and ied > 1.1:
        return PricingDecision(
            action="increase_now",
            reason=f"Rolling Index muito alto ({rolling_index:.2f}). Ritmo excelente para sell-out.",
            confidence="high"
        )
    
    if ied < 0.9 or rolling_index < 0.8:
        if d_minus >= 40:
            return PricingDecision(
                action="decrease",
                reason=f"Vendas abaixo do esperado (IED {ied:.2f}). Janela aberta para promoção.",
                confidence="medium"
            )
        else:
            return PricingDecision(
                action="maintain",
                reason=f"Vendas fracas, mas fora da janela de promoção (D-{d_minus}).",
                confidence="low"
            )
    
    return PricingDecision(
        action="maintain",
        reason="Métricas dentro do esperado. Continue monitorando.",
        confidence="medium"
    )


@router.get("/pricing", response_model=PricingEventsResponse)
def get_pricing_analysis(
    ano: int = Query(default=None, description="Ano dos eventos"),
    status: Optional[str] = Query(None, description="Filtrar por status: active, closed, all"),
    categoria: Optional[str] = Query(None, description="Filtrar por categoria/modalidade"),
    busca: Optional[str] = Query(None, description="Buscar por nome do evento"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing_pricing", "pode_visualizar"))
):
    """
    Retorna análise de pricing avançada para eventos.
    Inclui Rolling Index, IED, Pace de Segurança e matriz de elasticidade.
    """
    if ano is None:
        ano = datetime.now().year
    
    isc_cfg = _get_isc_settings(db)
    
    cadastro_query = db.query(CadastroEvento)
    if categoria and categoria != 'all':
        cadastro_query = cadastro_query.filter(CadastroEvento.modalidade == categoria)
    if busca:
        cadastro_query = cadastro_query.filter(CadastroEvento.nome.ilike(f'%{busca}%'))
    cadastros = cadastro_query.all()
    
    cadastro_by_projeto_id = {}
    for cad in cadastros:
        if cad.projeto_id:
            cadastro_by_projeto_id[cad.projeto_id] = cad
    
    projeto_ids = [cad.projeto_id for cad in cadastros if cad.projeto_id]
    projetos = db.query(DimProjeto).filter(DimProjeto.id.in_(projeto_ids)).all() if projeto_ids else []
    
    isc_data = fetch_isc_pricing_data(db=db)
    
    kit_costs = get_kit_basico_costs_batch(db, projeto_ids)
    kit_breakdowns = get_kit_breakdown_for_projetos(db, projeto_ids, ano)

    sku_to_grupo = _build_sku_to_grupo_map(db, ano)
    
    grupo_names_set = set(sku_to_grupo.values())
    grupo_details = {}
    if grupo_names_set:
        grupo_list = db.query(EventoGrupoModel).filter(
            EventoGrupoModel.nome.in_(list(grupo_names_set)),
            EventoGrupoModel.ativo == True
        ).all()
        for g in grupo_list:
            grupo_details[g.nome] = g
    
    grupo_projetos = {}
    standalone_projetos = []
    
    for projeto in projetos:
        projeto_codigo = str(projeto.codigo) if projeto.codigo else None
        if not projeto_codigo:
            continue
        sku_norm = normalize_sku(projeto_codigo)
        grupo_nome = sku_to_grupo.get(sku_norm)
        if grupo_nome and grupo_nome in grupo_details:
            if grupo_nome not in grupo_projetos:
                grupo_projetos[grupo_nome] = []
            grupo_projetos[grupo_nome].append(projeto)
        else:
            standalone_projetos.append(projeto)
    
    eventos = []
    categorias_set: set[str] = set()
    events_increase = 0
    events_maintain = 0
    events_decrease = 0

    for grupo_nome, proj_list in grupo_projetos.items():
        grupo = grupo_details[grupo_nome]
        
        latest_date = None
        rep_projeto = proj_list[0]
        rep_cadastro = cadastro_by_projeto_id.get(rep_projeto.id)
        total_kit_cost = 0.0
        kit_count = 0
        
        for p in proj_list:
            if p.data_evento:
                if latest_date is None or p.data_evento > latest_date:
                    latest_date = p.data_evento
                    rep_projeto = p
                    rep_cadastro = cadastro_by_projeto_id.get(p.id)
            kc = kit_costs.get(p.id, 50.0)
            total_kit_cost += kc
            kit_count += 1
        
        total_capacity = 0
        for p in proj_list:
            cad = cadastro_by_projeto_id.get(p.id)
            if cad:
                total_capacity += get_meta_from_cadastro(cad)
            else:
                total_capacity += get_meta_orcada(db, p.id)
        
        projeto_data_evento = latest_date or rep_projeto.data_evento
        dias_enc = get_dias_encerramento(db, projeto_id=rep_projeto.id, cadastro=rep_cadastro) if rep_projeto else 2
        d_minus_inscricoes = calculate_d_minus(projeto_data_evento, dias_encerramento=dias_enc) if projeto_data_evento else 0
        d_minus = calculate_d_minus(projeto_data_evento, dias_encerramento=0) if projeto_data_evento else 0
        is_active = bool(
            projeto_data_evento and
            (projeto_data_evento - timedelta(days=dias_enc)) >= today_brazil()
        )
        
        if status == 'active' and not is_active:
            continue
        if status == 'closed' and is_active:
            continue
        
        grupo_modalidade = str(rep_cadastro.modalidade) if rep_cadastro and rep_cadastro.modalidade else (rep_projeto.modalidade or 'OUTROS')
        categorias_set.add(grupo_modalidade)
        
        current_sales = 0
        current_receita = 0.0
        combined_rolling_14d = 0.0
        combined_rolling_14d_ly = 0.0
        combined_m7d = 0.0
        combined_m30d = 0.0
        seen_pricing_norms = set()
        for p in proj_list:
            p_sku = normalize_sku(str(p.codigo)) if p.codigo else None
            if p_sku and p_sku not in seen_pricing_norms and p_sku in isc_data:
                seen_pricing_norms.add(p_sku)
                current_sales += isc_data[p_sku].get('qtd_site', 0)
                current_receita += isc_data[p_sku].get('receita_liquida_site', 0.0)
                combined_rolling_14d += isc_data[p_sku].get('media_14d', 0.0)
                combined_rolling_14d_ly += isc_data[p_sku].get('media_14d_ano_passado', 0.0)
                combined_m7d += isc_data[p_sku].get('media_7d', 0.0)
                combined_m30d += isc_data[p_sku].get('media_30d', 0.0)
        
        average_ticket = round(current_receita / current_sales, 2) if current_sales > 0 else 0.0
        sales_goal = total_capacity
        kit_cost = total_kit_cost / kit_count if kit_count > 0 else 50.0
        
        all_skus = [str(p.codigo) for p in proj_list if p.codigo]
        
        grupo_location = str(rep_cadastro.localizacao_evento) if rep_cadastro and rep_cadastro.localizacao_evento else (rep_projeto.cidade or "Local não definido")
        
        pricing_metrics = calculate_pricing_metrics(
            current_sales=current_sales,
            sales_goal=sales_goal,
            d_minus=d_minus,
            average_ticket=average_ticket,
            kit_cost=kit_cost,
            total_capacity=total_capacity if total_capacity > 0 else sales_goal if sales_goal > 0 else 10000,
            rolling_avg_14d_real=combined_rolling_14d,
            rolling_avg_14d_last_year=combined_rolling_14d_ly
        )
        
        elasticity_scenarios = calculate_elasticity_scenarios(
            average_ticket=average_ticket,
            kit_cost=kit_cost,
            rolling_avg_14d=pricing_metrics.rollingAvg14d
        )
        
        decision = get_pricing_decision(pricing_metrics, d_minus)
        
        if decision.action in ['increase_now', 'increase_gradual']:
            events_increase += 1
        elif decision.action == 'decrease':
            events_decrease += 1
        else:
            events_maintain += 1
        
        pricing_hist_pattern = None
        pricing_curva_info = {"tipo_curva": "linear", "fonte_curva": None, "ano_referencia": None}
        try:
            pricing_hist_pattern, pricing_curva_info = _resolve_hist_pattern(db, grupo_nome, ano)
        except Exception:
            pass

        pricing_grupo_reg_close = (projeto_data_evento - timedelta(days=dias_enc)) if projeto_data_evento else None
        isc_components = calculate_isc_components(
            current_sales, sales_goal, d_minus,
            media_7d=combined_m7d,
            media_14d=combined_rolling_14d,
            media_30d=combined_m30d,
            hist_pattern=pricing_hist_pattern,
            registration_close_date=pricing_grupo_reg_close,
            curva_info=pricing_curva_info,
            use_normalized_curve=isc_cfg.get("useNormalizedCurveForISC", False)
        )
        isc = calculate_isc(isc_components, isc_cfg["ia730Weight"], isc_cfg["curvaDWeight"], isc_cfg["rolling14dWeight"])
        isc_status = get_isc_status(isc, isc_cfg["greenThreshold"], isc_cfg["yellowThreshold"])
        
        # Merge kit breakdown from all projetos in the group (unique by tipoKit)
        grupo_breakdown_map: dict = {}
        for p in proj_list:
            for item in kit_breakdowns.get(p.id, []):
                if item["tipoKit"] not in grupo_breakdown_map:
                    grupo_breakdown_map[item["tipoKit"]] = item["custoKit"]
        grupo_kit_breakdown = (
            [KitBreakdownItem(tipoKit=t, custoKit=c) for t, c in grupo_breakdown_map.items()]
            if grupo_breakdown_map else None
        )

        evento = PricingEvent(
            id=f"grp_{grupo_nome}",
            name=grupo.nome,
            date=projeto_data_evento.isoformat() if projeto_data_evento else "",
            location=grupo_location,
            category=grupo_modalidade,
            totalCapacity=total_capacity,
            currentSales=current_sales,
            salesGoal=sales_goal,
            averageTicket=round(average_ticket, 2),
            kitCost=round(kit_cost, 2),
            dMinus=d_minus,
            isActive=is_active,
            sku=",".join(all_skus),
            pricingMetrics=pricing_metrics,
            elasticityScenarios=elasticity_scenarios,
            decision=decision,
            iscStatus=isc_status,
            kitBreakdown=grupo_kit_breakdown,
        )
        eventos.append(evento)
    
    for projeto in standalone_projetos:
        projeto_codigo = str(projeto.codigo) if projeto.codigo else None
        if not projeto_codigo:
            continue
        
        cad = cadastro_by_projeto_id.get(projeto.id)
        sku = projeto_codigo
        sku_normalized = normalize_sku(sku)
        projeto_data_evento = projeto.data_evento
        dias_enc = get_dias_encerramento(db, projeto_id=projeto.id, cadastro=cad)
        d_minus_inscricoes = calculate_d_minus(projeto_data_evento, dias_encerramento=dias_enc) if projeto_data_evento else 0
        d_minus = calculate_d_minus(projeto_data_evento, dias_encerramento=0) if projeto_data_evento else 0
        is_active = bool(
            projeto_data_evento and
            (projeto_data_evento - timedelta(days=dias_enc)) >= today_brazil()
        )
        
        if status == 'active' and not is_active:
            continue
        if status == 'closed' and is_active:
            continue
        
        modalidade = str(cad.modalidade) if cad and cad.modalidade else (projeto.modalidade or 'OUTROS')
        categorias_set.add(modalidade)
        
        sales_info = isc_data.get(sku_normalized, {})
        current_sales = sales_info.get('qtd_site', 0)
        current_receita = sales_info.get('receita_liquida_site', 0.0)
        
        average_ticket = round(current_receita / current_sales, 2) if current_sales > 0 else 0.0
        sales_goal = get_meta_from_cadastro(cad) if cad else get_meta_orcada(db, projeto.id)
        total_capacity = sales_goal
        
        kit_cost = kit_costs.get(projeto.id, 50.0)
        
        rolling_avg_14d_real = sales_info.get('media_14d', None)
        rolling_avg_14d_last_year = sales_info.get('media_14d_ano_passado', 0.0)
        
        evento_location = str(cad.localizacao_evento) if cad and cad.localizacao_evento else (projeto.cidade or "Local não definido")
        evento_nome = str(cad.nome) if cad and cad.nome else (projeto.evento or f"Evento {sku}")
        
        pricing_metrics = calculate_pricing_metrics(
            current_sales=current_sales,
            sales_goal=sales_goal,
            d_minus=d_minus,
            average_ticket=average_ticket,
            kit_cost=kit_cost,
            total_capacity=total_capacity,
            rolling_avg_14d_real=rolling_avg_14d_real if rolling_avg_14d_real is not None else None,
            rolling_avg_14d_last_year=rolling_avg_14d_last_year
        )
        
        elasticity_scenarios = calculate_elasticity_scenarios(
            average_ticket=average_ticket,
            kit_cost=kit_cost,
            rolling_avg_14d=pricing_metrics.rollingAvg14d
        )
        
        decision = get_pricing_decision(pricing_metrics, d_minus)
        
        if decision.action in ['increase_now', 'increase_gradual']:
            events_increase += 1
        elif decision.action == 'decrease':
            events_decrease += 1
        else:
            events_maintain += 1
        
        standalone_pricing_eg = None
        standalone_pricing_eg_mapping = db.query(SkuMapping).filter(
            SkuMapping.sku == sku, SkuMapping.evento_grupo.isnot(None), SkuMapping.evento_grupo != '', SkuMapping.ativo == True
        ).first()
        if standalone_pricing_eg_mapping:
            standalone_pricing_eg = standalone_pricing_eg_mapping.evento_grupo

        standalone_pricing_hist = None
        standalone_pricing_curva_info = {"tipo_curva": "linear", "fonte_curva": None, "ano_referencia": None}
        if standalone_pricing_eg:
            try:
                standalone_pricing_hist, standalone_pricing_curva_info = _resolve_hist_pattern(db, standalone_pricing_eg, ano)
            except Exception:
                pass

        standalone_sales_info = isc_data.get(sku_normalized, {})
        standalone_m7d = standalone_sales_info.get('media_7d', 0.0)
        standalone_rolling_14d = standalone_sales_info.get('media_14d', 0.0)
        standalone_m30d = standalone_sales_info.get('media_30d', 0.0)

        pricing_standalone_reg_close = (projeto_data_evento - timedelta(days=dias_enc)) if projeto_data_evento else None
        isc_components = calculate_isc_components(
            current_sales, sales_goal, d_minus,
            media_7d=standalone_m7d,
            media_14d=standalone_rolling_14d,
            media_30d=standalone_m30d,
            hist_pattern=standalone_pricing_hist,
            registration_close_date=pricing_standalone_reg_close,
            curva_info=standalone_pricing_curva_info,
            use_normalized_curve=isc_cfg.get("useNormalizedCurveForISC", False)
        )
        isc = calculate_isc(isc_components, isc_cfg["ia730Weight"], isc_cfg["curvaDWeight"], isc_cfg["rolling14dWeight"])
        isc_status = get_isc_status(isc, isc_cfg["greenThreshold"], isc_cfg["yellowThreshold"])
        
        standalone_bd_raw = kit_breakdowns.get(projeto.id, [])
        standalone_kit_breakdown = (
            [KitBreakdownItem(tipoKit=i["tipoKit"], custoKit=i["custoKit"]) for i in standalone_bd_raw]
            if standalone_bd_raw else None
        )

        evento = PricingEvent(
            id=sku,
            name=evento_nome,
            date=projeto_data_evento.isoformat() if projeto_data_evento else "",
            location=evento_location,
            category=modalidade,
            totalCapacity=total_capacity,
            currentSales=current_sales,
            salesGoal=sales_goal,
            averageTicket=round(average_ticket, 2),
            kitCost=kit_cost,
            dMinus=d_minus,
            isActive=is_active,
            sku=sku,
            pricingMetrics=pricing_metrics,
            elasticityScenarios=elasticity_scenarios,
            decision=decision,
            iscStatus=isc_status,
            kitBreakdown=standalone_kit_breakdown,
        )
        
        eventos.append(evento)
    
    if status == 'active':
        eventos = [e for e in eventos if e.isActive]
    
    eventos.sort(key=lambda x: (-1 if x.decision.action == 'increase_now' else 0 if x.decision.action == 'increase_gradual' else 1, -x.pricingMetrics.ied))
    
    resumo = PricingSummary(
        totalEvents=len([e for e in eventos if e.isActive]),
        eventsToIncrease=events_increase,
        eventsToMaintain=events_maintain,
        eventsToDecrease=events_decrease
    )
    
    return PricingEventsResponse(
        status="success",
        eventos=eventos,
        resumo=resumo,
        categorias=sorted(list(categorias_set)),
        ultima_atualizacao=datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(),
        avisos=get_isc_warnings()
    )


@router.get("/settings/{key}")
def get_marketing_setting(
    key: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing_configuracoes", "pode_visualizar")),
):
    setting = db.query(MarketingSettings).filter(MarketingSettings.key == key).first()
    if setting:
        return {"status": "success", "key": key, "value": setting.value}
    return {"status": "success", "key": key, "value": None}


@router.put("/settings/{key}")
def update_marketing_setting(
    key: str,
    body: dict,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing_configuracoes", "pode_editar")),
):
    setting = db.query(MarketingSettings).filter(MarketingSettings.key == key).first()
    if setting:
        setting.value = body.get("value", {})
    else:
        setting = MarketingSettings(key=key, value=body.get("value", {}))
        db.add(setting)
    db.commit()
    if key == "isc_parameters":
        _isc_settings_cache["value"] = None
        _isc_settings_cache["ts"] = 0
        _smart_isc_cache.invalidate()
        event_detail_cache.invalidate()
        eventos_list_cache.invalidate()
    return {"status": "success", "key": key, "value": setting.value}


class ProjetadoFaixaItem(BaseModel):
    id: str
    nome: str
    preco: str
    qtd: str


class ProjetadoFaixasUpsert(BaseModel):
    faixas: List[ProjetadoFaixaItem]


@router.get("/eventos/{evento_id}/projetado-faixas")
def get_projetado_faixas(
    evento_id: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing_dashboard", "pode_visualizar")),
):
    from ...models.projecao import SimuladorProjetadoFaixas
    import json
    record = db.query(SimuladorProjetadoFaixas).filter(
        SimuladorProjetadoFaixas.evento_id == evento_id,
        SimuladorProjetadoFaixas.usuario_id == current_user.id,
    ).first()
    if not record:
        return {"status": "ok", "faixas": []}
    try:
        faixas = json.loads(record.faixas)
    except Exception:
        faixas = []
    return {"status": "ok", "faixas": faixas}


@router.put("/eventos/{evento_id}/projetado-faixas")
def upsert_projetado_faixas(
    evento_id: str,
    body: ProjetadoFaixasUpsert,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing_dashboard", "pode_editar")),
):
    from ...models.projecao import SimuladorProjetadoFaixas
    import json
    record = db.query(SimuladorProjetadoFaixas).filter(
        SimuladorProjetadoFaixas.evento_id == evento_id,
        SimuladorProjetadoFaixas.usuario_id == current_user.id,
    ).first()
    serialized = json.dumps([f.model_dump() for f in body.faixas])
    if record:
        record.faixas = serialized
    else:
        record = SimuladorProjetadoFaixas(
            evento_id=evento_id,
            usuario_id=current_user.id,
            faixas=serialized,
        )
        db.add(record)
    db.commit()
    return {"status": "ok"}


@router.delete("/eventos/{evento_id}/projetado-faixas")
def delete_projetado_faixas(
    evento_id: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("marketing_dashboard", "pode_deletar")),
):
    from ...models.projecao import SimuladorProjetadoFaixas
    db.query(SimuladorProjetadoFaixas).filter(
        SimuladorProjetadoFaixas.evento_id == evento_id,
        SimuladorProjetadoFaixas.usuario_id == current_user.id,
    ).delete()
    db.commit()
    return {"status": "ok"}


@router.get("/diagnostico-inscricoes")
def diagnostico_inscricoes(
    ativo_id: int,
    magento_id: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin()),
):
    """
    Endpoint de diagnóstico restrito a administradores para investigar discrepâncias
    entre o sistema e controles externos. Executa múltiplas variações de queries para
    isolar o filtro causador da diferença.

    Restrição de acesso: somente administradores (require_admin) podem invocar este
    endpoint. IDs são validados contra registros conhecidos para evitar enumeração
    arbitrária de eventos.
    """
    if ativo_id <= 0:
        raise HTTPException(status_code=422, detail="ativo_id deve ser um inteiro positivo")

    projeto_exists = db.query(DimProjeto).filter(DimProjeto.id == ativo_id).first()
    if not projeto_exists:
        raise HTTPException(status_code=404, detail="Projeto/evento não encontrado para o ativo_id informado")

    logger.info(
        "[diagnostico-inscricoes] admin=%s (id=%s) consultou ativo_id=%s magento_id=%s",
        current_user.email, current_user.id, ativo_id, magento_id,
    )

    result = {"ativo_id": ativo_id, "magento_id": magento_id, "ativo": {}, "magento": {}}

    cupom_join = """
        LEFT JOIN (
            SELECT e.id_cupom_desconto_item, f.en_cupom_classificacao
            FROM sa_cupom_desconto_item AS e
            INNER JOIN sa_cupom_desconto AS f ON f.id_cupom_desconto = e.id_cupom_desconto
        ) AS cupom ON cupom.id_cupom_desconto_item = a.id_cupom_individual
        LEFT JOIN sa_modalidade_categoria AS h ON h.id_categoria = a.id_categoria
    """

    canal_case = """
        CASE
            WHEN a.nr_preco = 0 THEN 'Cortesia'
            WHEN cupom.en_cupom_classificacao IN ('Funcionário','Cortesia Faturada','Coligados') THEN 'Cortesia'
            WHEN cupom.en_cupom_classificacao = 'Grupos' THEN 'Grupos/B2B'
            WHEN h.ds_categoria LIKE '%%Grup%%' THEN 'Grupos/B2B'
            ELSE 'Site'
        END
    """

    sf_filter = "AND (b.id_campanha_salesforce IS NULL OR b.id_campanha_salesforce NOT LIKE '701d0000000%%')"

    if db_module.engine_ssh is None:
        result["ativo"]["error"] = "engine_ssh not available"
    else:
        try:
            with db_module.engine_ssh.connect() as conn:
                scenarios = [
                    ("A1_site_fl1_status12", "fl_local_inscricao = '1' AND c.id_pedido_status IN (2)", "Site"),
                    ("A2_site_nofl_status12", "c.id_pedido_status IN (1, 2)", "Site"),
                    ("A3_site_fl1_status123", "fl_local_inscricao = '1' AND c.id_pedido_status IN (1, 2, 3)", "Site"),
                    ("A4_site_nofl_status123", "c.id_pedido_status IN (1, 2, 3)", "Site"),
                    ("A5_todos_canais_fl1_status12", "fl_local_inscricao = '1' AND c.id_pedido_status IN (2)", None),
                    ("A6_todos_canais_nofl_status12", "c.id_pedido_status IN (1, 2)", None),
                    ("A7_todos_canais_nofl_status123", "c.id_pedido_status IN (1, 2, 3)", None),
                ]
                for name, pedido_filter, canal_filter in scenarios:
                    canal_clause = f"AND {canal_case} = 'Site'" if canal_filter == "Site" else ""
                    # All interpolated fragments (canal_case, cupom_join, sf_filter,
                    # pedido_filter, canal_clause) are hardcoded SQL constants defined
                    # above — none originate from user input. Only :eid (ativo_id) is
                    # user-supplied and is passed as a named parameter below.
                    sql_scenario = (
                        "SELECT COUNT(DISTINCT a.id_pedido_evento) AS total\n"
                        "FROM sa_pedido_evento AS a\n"
                        "INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento\n"
                        f"INNER JOIN sa_pedido AS c ON c.id_pedido = a.id_pedido AND {pedido_filter}\n"
                        f"{cupom_join}\n"
                        f"WHERE b.id_evento = :eid {sf_filter} {canal_clause}\n"
                    )
                    q = text(sql_scenario)
                    r = conn.execute(q, {"eid": ativo_id}).scalar()
                    result["ativo"][name] = int(r or 0)

                # Breakdown por status e fl_local (sem filtro de canal para ver tudo)
                # All interpolated fragments are hardcoded SQL constants; :eid is the
                # only user-supplied value and is passed as a named parameter.
                sql_breakdown = (
                    "SELECT c.id_pedido_status, c.fl_local_inscricao,\n"
                    f"       {canal_case} AS canal,\n"
                    "       COUNT(DISTINCT a.id_pedido_evento) AS cnt\n"
                    "FROM sa_pedido_evento AS a\n"
                    "INNER JOIN sa_evento AS b ON b.id_evento = a.id_evento\n"
                    "INNER JOIN sa_pedido AS c ON c.id_pedido = a.id_pedido\n"
                    f"{cupom_join}\n"
                    f"WHERE b.id_evento = :eid {sf_filter}\n"
                    f"GROUP BY c.id_pedido_status, c.fl_local_inscricao, {canal_case}\n"
                    f"ORDER BY c.id_pedido_status, c.fl_local_inscricao, canal\n"
                )
                q_breakdown = text(sql_breakdown)
                rows = conn.execute(q_breakdown, {"eid": ativo_id}).fetchall()
                result["ativo"]["breakdown"] = [
                    {"status": r[0], "fl_local": r[1], "canal": r[2], "cnt": int(r[3])}
                    for r in rows
                ]
        except Exception as e:
            result["ativo"]["error"] = str(e)

    if db_module.engine_magento is None:
        result["magento"]["error"] = "engine_magento not available"
    else:
        try:
            safe_mid = str(int(magento_id))
            def _debug_magento_work(conn):
                # M1 - query atual (com todos os filtros)
                q_m1 = text("""
SELECT
    COUNT(CASE WHEN so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')
        AND soi.price > 0 THEN 1 END) AS qtd_site,
    COUNT(soi.item_id) AS qtd_total_bundle,
    COUNT(CASE WHEN so.base_grand_total > 0 THEN 1 END) AS qtd_grand_total_pos,
    COUNT(CASE WHEN soi.price > 0 THEN 1 END) AS qtd_price_pos
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
  AND so.state != 'canceled'
  AND cpev1.value = :mid
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
""")
                r_m1 = conn.execute(q_m1, {"mid": safe_mid}).fetchone()
                result["magento"]["M1_atual"] = {
                    "qtd_site": int(r_m1[0] or 0),
                    "qtd_total_bundle": int(r_m1[1] or 0),
                    "qtd_grand_total_pos": int(r_m1[2] or 0),
                    "qtd_price_pos": int(r_m1[3] or 0),
                }

                # M2 - sem filtro de cortesia/grupos no CASE (todos os válidos por status)
                q_m2 = text("""
SELECT COUNT(soi.item_id) AS qtd_all_status
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'pending_payment')
  AND so.state != 'canceled'
  AND cpev1.value = :mid
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
""")
                r_m2 = conn.execute(q_m2, {"mid": safe_mid}).scalar()
                result["magento"]["M2_all_statuses"] = int(r_m2 or 0)

                # M3 - breakdown por status Magento
                q_m3 = text("""
SELECT so.status, COUNT(soi.item_id) AS cnt
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
WHERE cpev1.value = :mid
  AND so.state != 'canceled'
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
GROUP BY so.status
ORDER BY cnt DESC
""")
                rows_m3 = conn.execute(q_m3, {"mid": safe_mid}).fetchall()
                result["magento"]["M3_breakdown_status"] = [
                    {"status": r[0], "cnt": int(r[1])} for r in rows_m3
                ]

                # M4 - sem filtro increment_id (inclui sub-pedidos com hífen)
                q_m4 = text("""
SELECT COUNT(soi.item_id) AS qtd_com_subpedidos
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
  AND so.state != 'canceled'
  AND cpev1.value = :mid
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
""")
                r_m4 = conn.execute(q_m4, {"mid": safe_mid}).scalar()
                result["magento"]["M4_sem_regexp_filter"] = int(r_m4 or 0)
                # M5 - breakdown do que está sendo filtrado (cortesia vs grupos vs preco_zero)
                q_m5 = text("""
SELECT
    SUM(CASE WHEN soi.price = 0 THEN 1 ELSE 0 END) AS excluidos_price_zero,
    SUM(CASE WHEN soi.price > 0 AND so.base_grand_total = 0 THEN 1 ELSE 0 END) AS excluidos_grand_total_zero,
    SUM(CASE WHEN soi.price > 0 AND so.base_grand_total > 0
        AND (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50) THEN 1 ELSE 0 END) AS excluidos_cortesia_barato,
    SUM(CASE WHEN soi.price > 0 AND so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description LIKE '%%GRUPOS%%') THEN 1 ELSE 0 END) AS excluidos_desc_grupos,
    SUM(CASE WHEN soi.price > 0 AND so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code LIKE 'GRUP%%') THEN 1 ELSE 0 END) AS excluidos_cupom_grupos,
    SUM(CASE WHEN soi.price > 0 AND so.base_grand_total > 0
        AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
        AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
        AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%') THEN 1 ELSE 0 END) AS incluidos_site
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
  AND so.state != 'canceled'
  AND cpev1.value = :mid
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
""")
                r_m5 = conn.execute(q_m5, {"mid": safe_mid}).fetchone()
                result["magento"]["M5_exclusao_breakdown"] = {
                    "excluidos_price_zero": int(r_m5[0] or 0),
                    "excluidos_grand_total_zero": int(r_m5[1] or 0),
                    "excluidos_cortesia_barato": int(r_m5[2] or 0),
                    "excluidos_desc_grupos": int(r_m5[3] or 0),
                    "excluidos_cupom_grupos": int(r_m5[4] or 0),
                    "incluidos_site": int(r_m5[5] or 0),
                }

                # M6 - amostras dos pedidos excluidos por discount_description GRUPOS
                q_m6 = text("""
SELECT so.increment_id, so.discount_description, so.coupon_code, so.base_grand_total, soi.price, soi.name
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
  AND so.state != 'canceled'
  AND cpev1.value = :mid
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
  AND soi.price > 0
  AND so.base_grand_total > 0
  AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
  AND so.discount_description LIKE '%%GRUPOS%%'
LIMIT 10
""")
                rows_m6 = conn.execute(q_m6, {"mid": safe_mid}).fetchall()
                result["magento"]["M6_amostras_excluidos_desc_grupos"] = [
                    {
                        "increment_id": r[0],
                        "discount_description": r[1],
                        "coupon_code": r[2],
                        "base_grand_total": float(r[3] or 0),
                        "soi_price": float(r[4] or 0),
                        "item_name": r[5],
                    }
                    for r in rows_m6
                ]

                # M7 - amostras dos pedidos excluidos por coupon_code GRUP%
                q_m7 = text("""
SELECT so.increment_id, so.discount_description, so.coupon_code, so.base_grand_total, soi.price
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
  AND so.state != 'canceled'
  AND cpev1.value = :mid
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
  AND soi.price > 0
  AND so.base_grand_total > 0
  AND NOT (so.discount_description LIKE '%%CORTESIA%%' AND so.base_grand_total < 50)
  AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
  AND so.coupon_code LIKE 'GRUP%%'
LIMIT 10
""")
                rows_m7 = conn.execute(q_m7, {"mid": safe_mid}).fetchall()
                result["magento"]["M7_amostras_excluidos_cupom_grupos"] = [
                    {
                        "increment_id": r[0],
                        "discount_description": r[1],
                        "coupon_code": r[2],
                        "base_grand_total": float(r[3] or 0),
                        "soi_price": float(r[4] or 0),
                    }
                    for r in rows_m7
                ]

                # M8 - amostras dos 169 com grand_total=0 mas soi.price>0
                # (para entender se são cortesia, grupos ou site com desconto 100%)
                q_m8 = text("""
SELECT so.increment_id, so.discount_description, so.coupon_code,
       so.base_grand_total, soi.price, soi.name,
       so.customer_email
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
  AND so.state != 'canceled'
  AND cpev1.value = :mid
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
  AND soi.price > 0
  AND so.base_grand_total = 0
LIMIT 20
""")
                rows_m8 = conn.execute(q_m8, {"mid": safe_mid}).fetchall()
                result["magento"]["M8_amostras_grand_total_zero"] = [
                    {
                        "increment_id": r[0],
                        "discount_description": r[1],
                        "coupon_code": r[2],
                        "base_grand_total": float(r[3] or 0),
                        "soi_price": float(r[4] or 0),
                        "item_name": r[5],
                        "email": (r[6] or "")[:30],
                    }
                    for r in rows_m8
                ]

                # M9 - breakdown do grand_total=0 por discount_description pattern
                q_m9 = text("""
SELECT
    CASE
        WHEN so.discount_description LIKE '%%CORTESIA%%' THEN 'CORTESIA'
        WHEN so.discount_description LIKE '%%GRUPOS%%' THEN 'GRUPOS'
        WHEN so.coupon_code LIKE 'GRUP%%' THEN 'CUPOM_GRUP'
        WHEN so.coupon_code LIKE '%%CORTESIA%%' THEN 'CUPOM_CORTESIA'
        WHEN so.discount_description IS NULL AND so.coupon_code IS NULL THEN 'SEM_DESC_SEM_CUPOM'
        ELSE CONCAT('outros_desc:', COALESCE(LEFT(so.discount_description,30),'NULL'))
    END AS categoria,
    COUNT(*) AS cnt
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
  AND so.state != 'canceled'
  AND cpev1.value = :mid
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
  AND soi.price > 0
  AND so.base_grand_total = 0
GROUP BY categoria
ORDER BY cnt DESC
""")
                rows_m9 = conn.execute(q_m9, {"mid": safe_mid}).fetchall()
                result["magento"]["M9_grand_total_zero_por_categoria"] = [
                    {"categoria": r[0], "cnt": int(r[1])} for r in rows_m9
                ]

                # M10 - quantidade de CORTESIA com grand_total >= 50 (incluídas na nossa query mas talvez excluídas no controle externo)
                q_m10 = text("""
SELECT
    COUNT(*) AS cortesia_com_total_alto,
    MIN(so.base_grand_total) AS min_total,
    MAX(so.base_grand_total) AS max_total
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
  AND so.state != 'canceled'
  AND cpev1.value = :mid
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
  AND soi.price > 0
  AND so.base_grand_total > 0
  AND so.discount_description LIKE '%%CORTESIA%%'
""")
                r_m10 = conn.execute(q_m10, {"mid": safe_mid}).fetchone()
                result["magento"]["M10_cortesia_grand_total_alto"] = {
                    "count": int(r_m10[0] or 0),
                    "min_total": float(r_m10[1] or 0),
                    "max_total": float(r_m10[2] or 0),
                }

                # M11 - query simples sem filtros de cortesia/grupos (apenas price > 0 e grand_total > 0)
                # Para ver se o controle externo conta de forma mais simples
                q_m11 = text("""
SELECT COUNT(*) AS qtd_sem_filtros_desc
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
  AND so.state != 'canceled'
  AND cpev1.value = :mid
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
  AND soi.price > 0
  AND so.base_grand_total > 0
""")
                r_m11 = conn.execute(q_m11, {"mid": safe_mid}).scalar()
                result["magento"]["M11_sem_filtros_desc_coupon"] = int(r_m11 or 0)

                # M12 - breakdown por discount_description das ordens com grand_total > 0 e price > 0
                # (incluindo CORTESIA e GRUPOS para ver exatamente o que está sendo contado)
                q_m12 = text("""
SELECT
    CASE
        WHEN so.discount_description IS NULL AND so.coupon_code IS NULL THEN 'SEM_DESCONTO'
        WHEN so.discount_description LIKE '%%CORTESIA%%' THEN 'CORTESIA'
        WHEN so.discount_description LIKE '%%GRUPOS%%' THEN 'GRUPOS'
        WHEN so.coupon_code LIKE 'GRUP%%' THEN 'CUPOM_GRUPO'
        ELSE 'OUTROS_DESC'
    END AS categoria,
    COUNT(*) AS cnt
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
  AND so.state != 'canceled'
  AND cpev1.value = :mid
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
  AND soi.price > 0
  AND so.base_grand_total > 0
GROUP BY categoria
ORDER BY cnt DESC
""")
                rows_m12 = conn.execute(q_m12, {"mid": safe_mid}).fetchall()
                result["magento"]["M12_breakdown_com_grand_total_pos"] = [
                    {"categoria": r[0], "cnt": int(r[1])} for r in rows_m12
                ]

                # M13 - query usando a lógica do controle externo:
                # Cortesia = soi_child.price - soi_child.discount_amount = 0
                # Usa MAX(soi_child.price - soi_child.discount_amount) por bundle
                # para evitar multiplicar linhas com múltiplos filhos
                q_m13 = text("""
SELECT
    SUM(CASE
        WHEN child_agg.net_price > 0
            AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
            AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')
        THEN 1 ELSE 0 END) AS qtd_site_logica_externa,
    SUM(CASE WHEN child_agg.net_price = 0 THEN 1 ELSE 0 END) AS cortesia_child_zero,
    SUM(CASE WHEN so.discount_description LIKE '%%GRUPOS%%' THEN 1 ELSE 0 END) AS excluidos_grupos_desc,
    SUM(CASE WHEN so.coupon_code LIKE 'GRUP%%' THEN 1 ELSE 0 END) AS excluidos_cupom_grupo,
    COUNT(*) AS total_bundles
FROM sales_order so
INNER JOIN sales_order_item soi
       ON soi.order_id = so.entity_id AND soi.product_type = 'bundle'
INNER JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = soi.product_id AND cpev1.attribute_id = 321 AND cpev1.store_id = 0
LEFT JOIN (
    SELECT parent_item_id,
           MAX(price - COALESCE(discount_amount, 0)) AS net_price
    FROM sales_order_item
    WHERE product_type != 'bundle'
    GROUP BY parent_item_id
) AS child_agg ON child_agg.parent_item_id = soi.item_id
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
  AND so.state != 'canceled'
  AND cpev1.value = :mid
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
""")
                r_m13 = conn.execute(q_m13, {"mid": safe_mid}).fetchone()
                result["magento"]["M13_logica_externa_child"] = {
                    "qtd_site": int(r_m13[0] or 0),
                    "cortesia_child_zero": int(r_m13[1] or 0),
                    "excluidos_grupos_desc": int(r_m13[2] or 0),
                    "excluidos_cupom_grupo": int(r_m13[3] or 0),
                    "total_com_child": int(r_m13[4] or 0),
                }

                # M14 - lógica EXATA do controle externo do usuário:
                # - JOIN soi com price > 0 (bundle)
                # - JOIN soi_child com product_type='simple', price > 0, nome Distância/Modalidade
                # - CASE: cortesia = grand_total=0 AND child net=0; Grupos = desc/coupon; Else Site
                q_m14 = text("""
SELECT
    COUNT(CASE
        WHEN NOT (so.base_grand_total = 0 AND (soi_child.price - soi_child.discount_amount) = 0)
            AND (so.discount_description IS NULL OR so.discount_description NOT LIKE '%%GRUPOS%%')
            AND (so.coupon_code IS NULL OR so.coupon_code NOT LIKE 'GRUP%%')
        THEN 1 END) AS qtd_site,
    COUNT(CASE
        WHEN so.base_grand_total = 0 AND (soi_child.price - soi_child.discount_amount) = 0
        THEN 1 END) AS cortesia,
    COUNT(CASE
        WHEN NOT (so.base_grand_total = 0 AND (soi_child.price - soi_child.discount_amount) = 0)
            AND (so.discount_description LIKE '%%GRUPOS%%' OR so.coupon_code LIKE 'GRUP%%')
        THEN 1 END) AS grupos,
    COUNT(*) AS total
FROM sales_order so
JOIN sales_order_item soi
    ON soi.order_id = so.entity_id
    AND soi.product_type = 'bundle'
    AND soi.price > 0
JOIN catalog_product_entity_varchar cpev1
    ON cpev1.entity_id = soi.product_id
    AND cpev1.attribute_id = 321
    AND cpev1.store_id = 0
    AND cpev1.value = :mid
JOIN sales_order_item soi_child
    ON soi_child.parent_item_id = soi.item_id
    AND soi_child.product_type = 'simple'
    AND soi_child.price > 0
    AND (
        soi_child.name LIKE '%%Distância%%'
     OR soi_child.name LIKE '%%Distancia%%'
     OR soi_child.name LIKE '%%Distâncias%%'
     OR soi_child.name LIKE '%%Modalidade%%'
     OR soi_child.name REGEXP '-[0-9]+[Kk]m$'
     OR soi_child.name REGEXP '^[0-9]+[Kk]m?$'
     OR soi_child.name LIKE 'Kit Participação%%'
     OR soi_child.name LIKE 'Olímpico%%'
     OR soi_child.name LIKE 'Yoga%%'
    )
WHERE so.status IN ('processing', 'complete', 'approved', 'aprovado_link', 'reembolso_parcial', 'closed', 'retirado')
  AND so.state NOT IN ('canceled')
  AND so.increment_id NOT REGEXP '-[0-9]'
  AND so.created_at < CURDATE() + INTERVAL 1 DAY
""")
                r_m14 = conn.execute(q_m14, {"mid": safe_mid}).fetchone()
                result["magento"]["M14_logica_exata_externa"] = {
                    "qtd_site": int(r_m14[0] or 0),
                    "cortesia": int(r_m14[1] or 0),
                    "grupos": int(r_m14[2] or 0),
                    "total": int(r_m14[3] or 0),
                }

            magento_run(_debug_magento_work, label="debug-vendas-bundle", profile="request")
        except Exception as e:
            result["magento"]["error"] = str(e)

    return result
