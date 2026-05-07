from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from datetime import date
from app.core.database import get_db
from app.core.security import get_current_user, require_permission
from app.models.kit_config import KitConfig
from app.models.cadastro_evento import CadastroEvento, CadastroKitProduto, CadastroKitProdutoItem
from app.models.dimensoes import SkuMapping, DimProjeto
from app.schemas.kit_config import KitConfigUpsert, KitRow, KitConfigResponse, KitConfigBulkUpsert, KitConfigBulkResult
import app.core.database as db_module
import logging
import time as _time
import unicodedata
import hashlib


def _normalize_kit_name(s: Optional[str]) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return " ".join(s.upper().split())


def _ativo_synthetic_id(id_evento_ativo: int, kit_name: str) -> int:
    """ID sintético estável para kits do Ativo sem CadastroKitProduto.

    Deriva um inteiro negativo de sha1(eid|nome_kit_normalizado), garantindo
    que o mesmo kit sempre receba o mesmo ID entre execuções (necessário
    para que KitConfig persistido continue válido). A magnitude é grande
    (até ~2.8e14) para nunca colidir com `-CadastroKitProduto.id`, que
    fica na faixa de poucos milhares.
    """
    raw = f"ativo|{id_evento_ativo}|{_normalize_kit_name(kit_name)}".encode("utf-8")
    digest = hashlib.sha1(raw).hexdigest()[:12]  # 48 bits
    return -int(digest, 16)

logger = logging.getLogger(__name__)

_kits_cache: dict = {"data": None, "ts": 0.0}
_KITS_TTL = 120

_unconfigured_cache: dict = {"data": None, "ts": 0.0}
_UNCONFIGURED_TTL = 300  # 5 minutes

router = APIRouter(prefix="/api/kit-config", tags=["Kit Config"])

MAGENTO_KITS_QUERY = """
SELECT 
    cpev1.value                             AS id_evento,
    cpev_kit.value                          AS nome_evento,
    cpe_parent.entity_id                    AS bundle_entity_id,
    cpev_kit_name.value                     AS nome_kit,
    eaov_tipo.value                         AS tipo_categoria,
    lote.lot_name                           AS lote_atual,

    (
        MAX(CASE 
            WHEN (
                cpev_simple.value LIKE '%Distancia%'
             OR cpev_simple.value LIKE '%Distância%'
             OR cpev_simple.value LIKE '%Modalidade%'
            )
             AND cpep.value > 0
            THEN cpep.value ELSE NULL 
        END)
        +
        COALESCE(MAX(CASE 
            WHEN cpep.value > 0
             AND cpev_simple.value NOT LIKE '%Distancia%'
             AND cpev_simple.value NOT LIKE '%Distância%'
             AND cpev_simple.value NOT LIKE '%Modalidade%'
             AND cpev_simple.value NOT LIKE '%Personaliz%'
             AND cpev_simple.value NOT LIKE '%Aceite%'
             AND cpev_simple.value NOT LIKE '%aceito%'
             AND cpev_simple.value NOT LIKE '%Treinão%'
             AND cpev_simple.value NOT LIKE '%Horário%'
             AND cpev_simple.value NOT LIKE '%Bateria%'
             AND cpev_simple.value NOT LIKE '%Doar%'
             AND cpev_simple.value NOT LIKE '%Tênis%'
             AND cpev_simple.value NOT LIKE '%Tenis%'
             AND cpev_simple.value NOT LIKE '%Bike%'
             AND cpev_simple.value NOT LIKE '%Biciclet%'
             AND cpev_simple.value NOT LIKE '%Festival%'
             AND cpev_simple.value NOT LIKE '%Bag%'
             AND cpev_simple.value NOT LIKE '%Inscrição%'
             AND cpev_simple.value NOT LIKE '%Declaro%'
             AND cpev_simple.value NOT LIKE '%Pochete%'
             AND cpev_simple.value NOT LIKE '%Tarifa%'
             AND cpev_simple.value NOT LIKE '%Skate%'
             AND cpev_simple.value NOT LIKE '%Obstáculo%'
             AND cpev_simple.value NOT LIKE '%Bravinhos%'
             AND cpev_simple.value NOT LIKE '%teste%'
             AND cpev_simple.value NOT LIKE '%Porta%'
             AND cpev_simple.value NOT LIKE '%Luva%'
             AND cpev_simple.value NOT LIKE '%Toalha%'
             AND cpev_simple.value NOT LIKE '%Corrida +%'
            THEN cpep.value ELSE NULL 
        END), 0)
    )                                       AS price,

    -- special_price: usa min_price do bundle pai (já reflete catalog price rules ativas)
    -- Fallback para pi_filho quando kit inativo (não indexado pelo Magento)
    COALESCE(pi_pai.min_price, (
        MAX(CASE 
            WHEN (
                cpev_simple.value LIKE '%Distancia%'
             OR cpev_simple.value LIKE '%Distância%'
             OR cpev_simple.value LIKE '%Modalidade%'
            )
             AND pi_filho.final_price > 0
            THEN pi_filho.final_price ELSE NULL 
        END)
        +
        COALESCE(MAX(CASE 
            WHEN pi_filho.final_price > 0
             AND cpev_simple.value NOT LIKE '%Distancia%'
             AND cpev_simple.value NOT LIKE '%Distância%'
             AND cpev_simple.value NOT LIKE '%Modalidade%'
             AND cpev_simple.value NOT LIKE '%Personaliz%'
             AND cpev_simple.value NOT LIKE '%Aceite%'
             AND cpev_simple.value NOT LIKE '%aceito%'
             AND cpev_simple.value NOT LIKE '%Treinão%'
             AND cpev_simple.value NOT LIKE '%Horário%'
             AND cpev_simple.value NOT LIKE '%Bateria%'
             AND cpev_simple.value NOT LIKE '%Doar%'
             AND cpev_simple.value NOT LIKE '%Tênis%'
             AND cpev_simple.value NOT LIKE '%Tenis%'
             AND cpev_simple.value NOT LIKE '%Bike%'
             AND cpev_simple.value NOT LIKE '%Biciclet%'
             AND cpev_simple.value NOT LIKE '%Festival%'
             AND cpev_simple.value NOT LIKE '%Bag%'
             AND cpev_simple.value NOT LIKE '%Inscrição%'
             AND cpev_simple.value NOT LIKE '%Declaro%'
             AND cpev_simple.value NOT LIKE '%Pochete%'
             AND cpev_simple.value NOT LIKE '%Tarifa%'
             AND cpev_simple.value NOT LIKE '%Skate%'
             AND cpev_simple.value NOT LIKE '%Obstáculo%'
             AND cpev_simple.value NOT LIKE '%Bravinhos%'
             AND cpev_simple.value NOT LIKE '%teste%'
             AND cpev_simple.value NOT LIKE '%Porta%'
             AND cpev_simple.value NOT LIKE '%Luva%'
             AND cpev_simple.value NOT LIKE '%Toalha%'
             AND cpev_simple.value NOT LIKE '%Corrida +%'
            THEN pi_filho.final_price ELSE NULL 
        END), 0)
    ))                                      AS special_price,

    CASE cpei_status.value
        WHEN 1 THEN 'ativo'
        WHEN 2 THEN 'inativo'
    END                                     AS status_kit

FROM catalog_product_entity cpe_parent

JOIN catalog_product_entity_varchar cpev1
       ON cpev1.entity_id = cpe_parent.entity_id
      AND cpev1.attribute_id = 321

JOIN catalog_product_entity_varchar cpev_kit_name
       ON cpev_kit_name.entity_id = cpe_parent.entity_id
      AND cpev_kit_name.attribute_id = 73

JOIN catalog_product_entity_varchar cpev_kit
       ON cpev_kit.entity_id = cpev1.value
      AND cpev_kit.attribute_id = 73

JOIN catalog_product_entity_datetime cped_date
       ON cped_date.entity_id = cpev1.value
      AND cped_date.attribute_id = 195

LEFT JOIN catalog_product_entity_int cpei_tipo
       ON cpei_tipo.entity_id = cpe_parent.entity_id
      AND cpei_tipo.attribute_id = (
            SELECT attribute_id FROM eav_attribute 
            WHERE attribute_code = 'tipo_categoria'
            AND entity_type_id = (
                SELECT entity_type_id FROM eav_entity_type 
                WHERE entity_type_code = 'catalog_product'
            )
      )

LEFT JOIN eav_attribute_option_value eaov_tipo
       ON eaov_tipo.option_id = cpei_tipo.value

JOIN catalog_product_bundle_option cpeo
       ON cpeo.parent_id = cpe_parent.entity_id

JOIN catalog_product_bundle_selection cpeos
       ON cpeos.option_id = cpeo.option_id

LEFT JOIN catalog_product_entity_varchar cpev_simple
       ON cpev_simple.entity_id = cpeos.product_id
      AND cpev_simple.attribute_id = 73

LEFT JOIN catalog_product_entity_decimal cpep
       ON cpep.entity_id = cpeos.product_id
      AND cpep.attribute_id = 77

-- Preço dos filhos simples: fallback para kits inativos
LEFT JOIN catalog_product_index_price pi_filho
       ON pi_filho.entity_id = cpeos.product_id
      AND pi_filho.website_id = 1
      AND pi_filho.customer_group_id = 0

-- Preço do bundle pai: min_price já reflete catalog price rules ativas
LEFT JOIN catalog_product_index_price pi_pai
       ON pi_pai.entity_id = cpe_parent.entity_id
      AND pi_pai.website_id = 1
      AND pi_pai.customer_group_id = 0

LEFT JOIN catalog_product_entity_event_lot_price lote
       ON lote.entity_id = cpev1.value
      AND lote.lot_id = (
            SELECT lot_id
            FROM catalog_product_entity_event_lot_price
            WHERE entity_id = cpev1.value
            ORDER BY record_id DESC
            LIMIT 1
      )

LEFT JOIN catalog_product_entity_int cpei_status
       ON cpei_status.entity_id = cpe_parent.entity_id
      AND cpei_status.attribute_id = (
            SELECT attribute_id 
            FROM eav_attribute 
            WHERE attribute_code = 'status'
              AND entity_type_id = (
                    SELECT entity_type_id 
                    FROM eav_entity_type 
                    WHERE entity_type_code = 'catalog_product'
              )
      )

WHERE cpe_parent.type_id = 'bundle'
  AND cped_date.value >= DATE_FORMAT(CURDATE(), '%Y-01-01')
  AND cped_date.value <  DATE_FORMAT(CURDATE(), '%Y-01-01') + INTERVAL 1 YEAR

GROUP BY
    cpev1.value,
    cpev_kit.value,
    cpe_parent.entity_id,
    cpev_kit_name.value,
    eaov_tipo.value,
    lote.lot_name,
    lote.lot_value,
    lote.lot_sell_ends,
    pi_pai.min_price

ORDER BY
    cpev1.value,
    special_price
"""


# ============================================================
# Tickets por evento no banco do Ativo: COMBO + Modalidade Simples
# Preço do lote vigente (menor dt_limite >= hoje).
# Uma linha por kit (COMBO expande por tipo_categoria; modalidade simples
# agrupa por nome do kit).
# Usado para enriquecer eventos Ativo-only no Mapeamento de Kits e para
# alimentar o ticket atual desses eventos no Dash ISC.
# ============================================================
ATIVO_KITS_QUERY = """
SELECT
    e.id_evento                                         AS id_evento,
    e.ds_evento                                         AS nome_evento,
    c.ds_titulo                                         AS nome_kit,
    cec.ds_categoria                                    AS tipo_categoria,
    l_atual.ds_lote                                     AS lote_atual,
    c.nr_valor_de                                       AS price,
    c.nr_valor                                          AS special_price,
    el_atual.dt_limite                                  AS lote_dt_limite,
    el_atual.ds_classificacao                           AS lote_classificacao,
    'combo'                                             AS origem
FROM sa_combo c
JOIN sa_combo_evento_categoria cec
       ON cec.id_combo = c.id_combo
JOIN sa_evento e
       ON e.id_evento = cec.id_evento
JOIN sa_evento_lote el_atual
       ON el_atual.id_evento = cec.id_evento
      AND el_atual.id_evento_lote = (
            SELECT id_evento_lote
            FROM sa_evento_lote
            WHERE id_evento = cec.id_evento
              AND dt_limite >= CURDATE()
            ORDER BY dt_limite ASC
            LIMIT 1
      )
JOIN sa_lotes l_atual
       ON l_atual.id_lote = el_atual.id_lote
WHERE YEAR(e.dt_evento) = YEAR(CURDATE())
GROUP BY
    e.id_evento,
    e.ds_evento,
    c.id_combo,
    c.ds_titulo,
    cec.ds_categoria,
    c.nr_valor_de,
    c.nr_valor,
    l_atual.ds_lote,
    el_atual.dt_limite,
    el_atual.ds_classificacao

UNION ALL

SELECT
    e.id_evento                                         AS id_evento,
    e.ds_evento                                         AS nome_evento,
    mc.ds_categoria                                     AS nome_kit,
    ''                                                  AS tipo_categoria,
    l_atual.ds_lote                                     AS lote_atual,
    MIN(mck.vl_kit)                                     AS price,
    MIN(mck.vl_kit)                                     AS special_price,
    el_atual.dt_limite                                  AS lote_dt_limite,
    el_atual.ds_classificacao                           AS lote_classificacao,
    'modalidade'                                        AS origem
FROM sa_evento_modalidade em
JOIN sa_evento e
       ON e.id_evento = em.id_evento
JOIN sa_modalidade_categoria mc
       ON mc.id_modalidade = em.id_modalidade
JOIN sa_evento_lote el_atual
       ON el_atual.id_evento = em.id_evento
      AND el_atual.id_evento_lote = (
            SELECT id_evento_lote
            FROM sa_evento_lote
            WHERE id_evento = em.id_evento
              AND dt_limite >= CURDATE()
            ORDER BY dt_limite ASC
            LIMIT 1
      )
JOIN sa_modalidade_categoria_kit mck
       ON mck.id_categoria  = mc.id_categoria
      AND mck.id_evento_lote = el_atual.id_evento_lote
JOIN sa_lotes l_atual
       ON l_atual.id_lote = el_atual.id_lote
WHERE YEAR(e.dt_evento) = YEAR(CURDATE())
  AND NOT EXISTS (
        SELECT 1
        FROM sa_combo_evento_categoria cec2
        WHERE cec2.id_evento = em.id_evento
  )
GROUP BY
    e.id_evento,
    e.ds_evento,
    mc.ds_categoria,
    l_atual.ds_lote,
    el_atual.dt_limite,
    el_atual.ds_classificacao
ORDER BY
    id_evento,
    nome_kit,
    special_price ASC
"""


_ativo_kits_cache: dict = {"data": None, "ts": 0.0}
_ATIVO_KITS_TTL = 120


def fetch_ativo_kits_indexed(force_refresh: bool = False) -> dict:
    """Roda ATIVO_KITS_QUERY no banco do Ativo e devolve um índice:

        {(id_evento_ativo:int, nome_kit_normalizado:str): [variant_dict, ...]}

    Cada variant_dict contém: tipo_categoria, lote_atual, price,
    special_price, origem. Quando uma chave tem combo + modalidade, o
    NOT EXISTS da Parte 2 da query garante que só uma das duas aparece
    por evento. Se o engine do Ativo não estiver configurado ou a
    consulta falhar, devolve {} (e o caller cai no fallback atual).
    """
    now = _time.time()
    if (
        not force_refresh
        and _ativo_kits_cache["data"] is not None
        and (now - _ativo_kits_cache["ts"]) < _ATIVO_KITS_TTL
    ):
        return _ativo_kits_cache["data"]

    # As tabelas sa_evento/sa_combo/sa_modalidade* ficam no banco "0_transfer"
    # acessado via SSH tunnel (mesma conexão usada por fetch_eventos_ativo).
    if db_module.engine_ssh is None:
        logger.info("[KitConfig] engine_ssh não configurado; pulando ATIVO_KITS_QUERY")
        return {}

    try:
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(text(ATIVO_KITS_QUERY))
            rows = result.fetchall()
            columns = list(result.keys())
    except Exception as e:
        logger.error(f"[KitConfig] Erro ao buscar kits do Ativo: {e}")
        return {}

    indexed: dict = {}
    for row in rows:
        rd = dict(zip(columns, row))
        try:
            evt_id = int(rd["id_evento"])
        except (TypeError, ValueError):
            continue
        kit_display_raw = rd.get("nome_kit") or ""
        key = (evt_id, _normalize_kit_name(kit_display_raw))
        indexed.setdefault(key, []).append({
            "kit_display": kit_display_raw,
            "nome_evento": rd.get("nome_evento") or "",
            "tipo_categoria": rd.get("tipo_categoria") or None,
            "lote_atual": rd.get("lote_atual"),
            "price": float(rd["price"]) if rd.get("price") is not None else None,
            "special_price": float(rd["special_price"]) if rd.get("special_price") is not None else None,
            "origem": rd.get("origem"),
        })

    _ativo_kits_cache["data"] = indexed
    _ativo_kits_cache["ts"] = _time.time()
    logger.info(f"[KitConfig] ATIVO_KITS_QUERY indexada: {len(indexed)} chaves (evento, kit)")
    return indexed


@router.get("/kits", response_model=List[KitRow])
def get_kits_with_config(
    db: Session = Depends(get_db),
    force_refresh: bool = False,
    current_user=Depends(require_permission("admin_kit_config", "pode_visualizar")),
):
    now = _time.time()
    if not force_refresh and _kits_cache["data"] is not None and (now - _kits_cache["ts"]) < _KITS_TTL:
        logger.info(f"[KitConfig] Returning cached kit list (age={now - _kits_cache['ts']:.0f}s)")
        return _kits_cache["data"]

    if db_module.engine_magento is None:
        raise HTTPException(
            status_code=503,
            detail="Conexão Magento não configurada. Verifique as credenciais MAGENTO_DB_*",
        )

    from app.core.db_retry import magento_run, MagentoEngineUnavailable

    def _kits_work(conn):
        result = conn.execute(text(MAGENTO_KITS_QUERY))
        return result.fetchall(), list(result.keys())

    try:
        magento_rows, columns = magento_run(_kits_work, label="kit_config:list-magento", profile="request")
    except MagentoEngineUnavailable:
        raise HTTPException(status_code=503, detail="Conexão Magento indisponível")
    except Exception as e:
        logger.error(f"Erro ao buscar kits do Magento: {e}")
        raise HTTPException(status_code=500, detail="Erro ao consultar dados do Magento")

    all_configs = db.query(KitConfig).all()
    config_map = {c.bundle_entity_id: c for c in all_configs}

    # Custo por tipo_kit calculado do Cadastro — resolvido por evento específico
    # SkuMapping MAGENTO: id_externo (= cpev1.value do Magento) → sku → DimProjeto → CadastroEvento
    all_sku_maps = db.query(SkuMapping).filter(
        SkuMapping.fonte == 'MAGENTO',
        SkuMapping.ativo == True,
    ).all()
    externo_to_sku: dict = {sm.id_externo: (sm.sku or "").upper().strip() for sm in all_sku_maps if sm.id_externo}

    all_projs = db.query(DimProjeto).all()
    sku_to_projeto_id: dict = {(p.codigo or "").upper().strip(): p.id for p in all_projs if p.codigo}

    all_cadastros = db.query(CadastroEvento).all()
    projeto_to_cadastro_id: dict = {c.projeto_id: c.id for c in all_cadastros if c.projeto_id}

    all_kit_produtos = db.query(CadastroKitProduto).all()
    kp_ids = [kp.id for kp in all_kit_produtos]
    all_items = (
        db.query(CadastroKitProdutoItem)
        .filter(CadastroKitProdutoItem.kit_produto_id.in_(kp_ids))
        .all()
    ) if kp_ids else []
    items_by_kit: dict = {}
    for item in all_items:
        items_by_kit.setdefault(item.kit_produto_id, []).append(item)

    # cadastro_id -> {kit_name -> custo}
    cadastro_kit_costs: dict = {}
    # cadastro_id -> [CadastroKitProduto] — pre-indexed to avoid O(n*m) scans later
    kps_by_cadastro_id: dict = {}
    for kp in all_kit_produtos:
        kit_name = (kp.kit or "").strip()
        cost = sum(float(i.valor_unitario or 0) for i in items_by_kit.get(kp.id, []))
        cadastro_kit_costs.setdefault(kp.cadastro_id, {})[kit_name] = cost
        kps_by_cadastro_id.setdefault(kp.cadastro_id, []).append(kp)

    def _get_custo_for_event(id_evento_raw, tipo_kit: str | None) -> float | None:
        """Retorna custo do kit para o evento específico vinculado ao bundle."""
        if not id_evento_raw or not tipo_kit:
            return None
        try:
            id_externo = int(id_evento_raw)
        except (ValueError, TypeError):
            return None
        sku = externo_to_sku.get(id_externo)
        if not sku:
            return None
        projeto_id = sku_to_projeto_id.get(sku)
        if not projeto_id:
            return None
        cadastro_id = projeto_to_cadastro_id.get(projeto_id)
        if not cadastro_id:
            return None
        return cadastro_kit_costs.get(cadastro_id, {}).get(tipo_kit)

    kits: List[KitRow] = []
    for row in magento_rows:
        row_dict = dict(zip(columns, row))
        bundle_id = int(row_dict["bundle_entity_id"])

        price_raw = float(row_dict["price"]) if row_dict.get("price") is not None else None
        special_price_raw = float(row_dict["special_price"]) if row_dict.get("special_price") is not None else None

        cfg = config_map.get(bundle_id)
        multiplicador = cfg.multiplicador if cfg else 1
        is_configured = cfg is not None
        is_kit_basico = cfg.is_kit_basico if cfg else False
        is_promo_principal = cfg.is_promo_principal if cfg else False
        tipo_kit = cfg.tipo_kit if cfg else None

        custo_cadastro = _get_custo_for_event(row_dict.get("id_evento"), tipo_kit)
        custo_kit_val = float(cfg.custo_kit) if cfg and cfg.custo_kit is not None else None

        kits.append(KitRow(
            id_evento=str(row_dict.get("id_evento")) if row_dict.get("id_evento") is not None else None,
            nome_evento=row_dict.get("nome_evento"),
            bundle_entity_id=bundle_id,
            nome_kit=row_dict.get("nome_kit"),
            tipo_kit=tipo_kit,
            tipo_categoria=row_dict.get("tipo_categoria"),
            lote_atual=row_dict.get("lote_atual"),
            multiplicador_sugerido=1,
            multiplicador=multiplicador,
            price_base=price_raw,
            special_price_base=special_price_raw,
            price=price_raw,
            special_price=special_price_raw,
            is_configured=is_configured,
            is_kit_basico=is_kit_basico,
            is_promo_principal=is_promo_principal,
            custo_cadastro=custo_cadastro,
            custo_kit=custo_kit_val,
            ativo_categoria=cfg.ativo_categoria if cfg else None,
            status_kit=row_dict.get("status_kit"),
            fonte="magento",
            cenario_ciclismo=cfg.cenario_ciclismo if cfg else None,
            ignorado=cfg.ignorado if cfg else False,
        ))

    # --- Ativo-only events ---
    # Find events that exist only in Ativo (no corresponding Magento bundle).
    # Path: SkuMapping(fonte='ATIVO') → DimProjeto → CadastroEvento → CadastroKitProduto
    #
    # Exclusion is based on SKUs that actually appeared in the current Magento query
    # results (not all historical MAGENTO SkuMappings), to avoid hiding Ativo events
    # that share a SKU with a Magento mapping from a different year.
    current_year = date.today().year

    # Build SKU set from the actual Magento rows returned by this request
    current_magento_event_ids: set = set()
    for row in magento_rows:
        row_d = dict(zip(columns, row))
        ev_id = row_d.get("id_evento")
        if ev_id is not None:
            try:
                current_magento_event_ids.add(int(ev_id))
            except (ValueError, TypeError):
                pass
    current_magento_skus: set = {
        externo_to_sku[eid]
        for eid in current_magento_event_ids
        if eid in externo_to_sku
    }

    # Build lookup: cadastro_id → CadastroEvento (for year filtering)
    cadastro_by_id: dict = {c.id: c for c in all_cadastros}

    ativo_maps = db.query(SkuMapping).filter(
        SkuMapping.fonte == 'ATIVO',
        SkuMapping.ativo == True,
        SkuMapping.ano == current_year,
    ).all()

    # Índice (id_evento_ativo, nome_kit_normalizado) → variantes com preço/lote.
    # Vazio quando o engine_ssh não está configurado ou a query falha — o loop
    # abaixo então mantém o comportamento histórico (preços nulos).
    ativo_kits_index = fetch_ativo_kits_indexed(force_refresh=force_refresh)

    # Diagnóstico temporário: amostra de chaves do índice e quais id_externo de
    # SkuMapping ATIVO estão sendo tentados.
    if ativo_kits_index:
        sample_idx_keys = list(ativo_kits_index.keys())[:5]
        idx_event_ids = sorted({k[0] for k in ativo_kits_index.keys()})
        logger.info(f"[KitConfig][DEBUG] Index: {len(ativo_kits_index)} chaves, {len(idx_event_ids)} id_eventos distintos. Primeiros: {idx_event_ids[:10]}. Amostra de chaves: {sample_idx_keys}")
    _debug_match_attempts = []
    _debug_match_hits = 0

    _dbg = {"total": len(ativo_maps), "no_sku": 0, "in_magento": 0, "no_projeto": 0,
            "no_cadastro_id": 0, "no_cadastro": 0, "wrong_year": 0, "no_kps": 0,
            "passed": 0, "id_externo_none": 0}

    # Rastreia (id_evento_ativo, kit_normalizado) já emitidos pelo path com
    # cadastro, para que o path direto (abaixo) não duplique linhas para o
    # mesmo kit.
    emitted_ativo_keys: set = set()
    # SkuMappings ATIVO indexados por id_externo_int, usados pelo path direto
    # logo abaixo. Preenche aqui ANTES dos filtros para que o path direto
    # consiga emitir kits mesmo quando o evento Ativo não tem cadastro/projeto.
    sm_ativo_by_eid: dict = {}
    for _sm in ativo_maps:
        try:
            _eid = int(_sm.id_externo) if _sm.id_externo is not None else None
        except (ValueError, TypeError):
            _eid = None
        if _eid is not None and _eid not in sm_ativo_by_eid:
            sm_ativo_by_eid[_eid] = _sm

    for sm in ativo_maps:
        sku = (sm.sku or "").upper().strip()
        if not sku:
            _dbg["no_sku"] += 1
            continue
        if sku in current_magento_skus:
            _dbg["in_magento"] += 1
            continue

        projeto_id = sku_to_projeto_id.get(sku)
        if not projeto_id:
            _dbg["no_projeto"] += 1
            continue
        cadastro_id = projeto_to_cadastro_id.get(projeto_id)
        if not cadastro_id:
            _dbg["no_cadastro_id"] += 1
            continue

        # Year guard: require CadastroEvento.ano_evento to match current year
        cadastro = cadastro_by_id.get(cadastro_id)
        if not cadastro:
            _dbg["no_cadastro"] += 1
            continue
        if cadastro.ano_evento and cadastro.ano_evento != current_year:
            _dbg["wrong_year"] += 1
            continue

        kps = kps_by_cadastro_id.get(cadastro_id, [])
        if not kps:
            _dbg["no_kps"] += 1
            continue
        _dbg["passed"] += 1

        try:
            id_externo_int = int(sm.id_externo) if sm.id_externo is not None else None
        except (ValueError, TypeError):
            id_externo_int = None

        for kp in kps:
            if id_externo_int is not None:
                emitted_ativo_keys.add((id_externo_int, _normalize_kit_name(kp.kit)))
            synthetic_bundle_id = -kp.id
            cfg = config_map.get(synthetic_bundle_id)
            multiplicador = cfg.multiplicador if cfg else 1
            is_configured = cfg is not None
            is_kit_basico = cfg.is_kit_basico if cfg else False
            is_promo_principal = cfg.is_promo_principal if cfg else False
            tipo_kit = cfg.tipo_kit if cfg else None

            kit_cost = sum(float(i.valor_unitario or 0) for i in items_by_kit.get(kp.id, []))
            custo_cadastro_val = kit_cost if kit_cost > 0 else None
            custo_kit_val = float(cfg.custo_kit) if cfg and cfg.custo_kit is not None else None

            # Procura variantes do kit no banco do Ativo. Se houver match,
            # expande em N linhas (uma por tipo_categoria, espelhando o
            # comportamento do Magento). Sem match, mantém o fallback de
            # preço nulo. O synthetic_bundle_id continua o mesmo em todas
            # as variantes, então o KitConfig salvo permanece intacto.
            variants = []
            if id_externo_int is not None:
                lookup_key = (id_externo_int, _normalize_kit_name(kp.kit))
                variants = ativo_kits_index.get(lookup_key, [])
                if len(_debug_match_attempts) < 10:
                    _debug_match_attempts.append((lookup_key, kp.kit, len(variants)))
                if variants:
                    _debug_match_hits += 1

            if not variants:
                variants = [{
                    "tipo_categoria": None,
                    "lote_atual": None,
                    "price": None,
                    "special_price": None,
                    "origem": None,
                }]

            for v in variants:
                kits.append(KitRow(
                    id_evento=str(sm.id_externo),
                    nome_evento=sm.nome_evento,
                    bundle_entity_id=synthetic_bundle_id,
                    nome_kit=kp.kit,
                    tipo_kit=tipo_kit,
                    tipo_categoria=v["tipo_categoria"],
                    lote_atual=v["lote_atual"],
                    multiplicador_sugerido=1,
                    multiplicador=multiplicador,
                    price_base=v["price"],
                    special_price_base=v["special_price"],
                    price=v["price"],
                    special_price=v["special_price"],
                    is_configured=is_configured,
                    is_kit_basico=is_kit_basico,
                    is_promo_principal=is_promo_principal,
                    custo_cadastro=custo_cadastro_val,
                    custo_kit=custo_kit_val,
                    ativo_categoria=kp.ativo_categoria or (cfg.ativo_categoria if cfg else None),
                    status_kit=None,
                    fonte="ativo",
                    cenario_ciclismo=cfg.cenario_ciclismo if cfg else None,
                    ignorado=cfg.ignorado if cfg else False,
                ))

    # ── PATH DIRETO (Ativo-only sem cadastro) ─────────────────────────────
    # Para todo (id_evento, kit) presente em ATIVO_KITS_QUERY que tenha
    # SkuMapping ATIVO no ano corrente e ainda não tenha sido emitido pelo
    # path com cadastro, gera UMA linha por variante (tipo_categoria),
    # todas com o mesmo synthetic_bundle_id estável (sha1-derivado). Isso
    # permite que o usuário configure o kit nessa tela mesmo quando não
    # existe CadastroEvento/CadastroKitProduto no sistema.
    direct_emitted = 0
    direct_skipped_in_magento = 0
    direct_skipped_already = 0
    direct_no_sm_but_emitted = 0
    for (eid, norm_kit), variants in ativo_kits_index.items():
        sm = sm_ativo_by_eid.get(eid)  # pode ser None — evento não mapeado em SkuMapping
        if sm is not None:
            sm_sku = (sm.sku or "").upper().strip()
            # Precedência Magento só pode ser aplicada quando temos SKU ATIVO
            # para comparar; sem SkuMapping cadastrado, emitimos o kit do
            # Ativo de qualquer forma (o evento pode até existir no Magento,
            # mas como não há vínculo formal aqui, deixamos visível para o
            # usuário decidir).
            if sm_sku and sm_sku in current_magento_skus:
                direct_skipped_in_magento += 1
                continue
        else:
            direct_no_sm_but_emitted += 1

        if (eid, norm_kit) in emitted_ativo_keys:
            direct_skipped_already += 1
            continue

        kit_display = variants[0].get("kit_display") or norm_kit
        nome_evento = (sm.nome_evento if sm else None) or variants[0].get("nome_evento") or ""
        id_evento_str = str(sm.id_externo) if sm else str(eid)
        synth_id = _ativo_synthetic_id(eid, kit_display)
        cfg = config_map.get(synth_id)
        multiplicador = cfg.multiplicador if cfg else 1
        is_configured = cfg is not None
        is_kit_basico = cfg.is_kit_basico if cfg else False
        is_promo_principal = cfg.is_promo_principal if cfg else False
        tipo_kit = cfg.tipo_kit if cfg else None
        custo_kit_val = float(cfg.custo_kit) if cfg and cfg.custo_kit is not None else None
        ativo_categoria_val = cfg.ativo_categoria if cfg else None
        cenario_ciclismo_val = cfg.cenario_ciclismo if cfg else None

        for v in variants:
            kits.append(KitRow(
                id_evento=id_evento_str,
                nome_evento=nome_evento,
                bundle_entity_id=synth_id,
                nome_kit=kit_display,
                tipo_kit=tipo_kit,
                tipo_categoria=v["tipo_categoria"],
                lote_atual=v["lote_atual"],
                multiplicador_sugerido=1,
                multiplicador=multiplicador,
                price_base=v["price"],
                special_price_base=v["special_price"],
                price=v["price"],
                special_price=v["special_price"],
                is_configured=is_configured,
                is_kit_basico=is_kit_basico,
                is_promo_principal=is_promo_principal,
                custo_cadastro=None,
                custo_kit=custo_kit_val,
                ativo_categoria=ativo_categoria_val,
                status_kit=None,
                fonte="ativo",
                cenario_ciclismo=cenario_ciclismo_val,
                ignorado=cfg.ignorado if cfg else False,
            ))
            direct_emitted += 1

    _kits_cache["data"] = kits
    _kits_cache["ts"] = _time.time()
    # Invalidate the unconfigured summary cache so it is rebuilt from fresh kit data
    _unconfigured_cache["data"] = None
    _unconfigured_cache["ts"] = 0.0
    logger.info(f"[KitConfig] Kit list refreshed and cached ({len(kits)} kits)")
    logger.info(f"[KitConfig][DEBUG] Ativo match: {_debug_match_hits} hits / {len(_debug_match_attempts)} (mostrando até 10) tentativas. Amostra: {_debug_match_attempts}")
    logger.info(f"[KitConfig][DEBUG] Ativo filter funnel: {_dbg}")
    logger.info(f"[KitConfig][DEBUG] Ativo direct path: emitidos={direct_emitted} linhas, no_sm_but_emitted={direct_no_sm_but_emitted}, skip_in_magento={direct_skipped_in_magento}, skip_already_emitted={direct_skipped_already}")
    _ativo_only_sample = [
        {"id_evento": k.id_evento, "nome_evento": k.nome_evento, "nome_kit": k.nome_kit}
        for k in kits if k.fonte == "ativo"
    ][:8]
    _ativo_only_empty = sum(1 for k in kits if k.fonte == "ativo" and not (k.nome_evento or "").strip())
    logger.info(f"[KitConfig][DEBUG] Ativo-only sample names: {_ativo_only_sample}")
    logger.info(f"[KitConfig][DEBUG] Ativo-only com nome_evento vazio: {_ativo_only_empty}")
    return kits


@router.get("/unconfigured-summary")
def get_unconfigured_summary(
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("admin_kit_config", "pode_visualizar")),
):
    """Returns a lightweight summary of bundles without KitConfig mapping.

    Reuses the in-memory cache from /kits when available so it does not
    hit the Magento database on every call.  Falls back to a direct query
    only when the cache is cold.
    """
    now = _time.time()

    # ── served from the detailed-kits cache when it is hot ──────────────
    if (
        _kits_cache["data"] is not None
        and (now - _kits_cache["ts"]) < _KITS_TTL
    ):
        source = "cache"
        all_kits = _kits_cache["data"]
        unconfigured = [
            k for k in all_kits
            if not k.is_configured
            and getattr(k, "status_kit", None) != "inativo"
            and not getattr(k, "ignorado", False)
        ]
    elif (
        _unconfigured_cache["data"] is not None
        and (now - _unconfigured_cache["ts"]) < _UNCONFIGURED_TTL
    ):
        return _unconfigured_cache["data"]
    else:
        # ── lightweight fallback: only bundle_entity_id + name ──────────
        source = "query"
        if db_module.engine_magento is None:
            result = {"total_unconfigured": 0, "events": [], "magento_available": False}
            _unconfigured_cache["data"] = result
            _unconfigured_cache["ts"] = now
            return result

        _LIGHT_QUERY = """
            SELECT
                cpe.entity_id                   AS bundle_entity_id,
                cpev_event_name.value           AS nome_evento,
                cpev_kit_name.value             AS nome_kit,
                CASE cpei_status.value
                    WHEN 1 THEN 'ativo'
                    WHEN 2 THEN 'inativo'
                END                             AS status_kit
            FROM catalog_product_entity cpe
            JOIN catalog_product_entity_varchar cpev1
                ON cpe.entity_id = cpev1.entity_id
               AND cpev1.attribute_id = 321
            JOIN catalog_product_entity_datetime cped_date
                ON cped_date.entity_id = cpev1.value
               AND cped_date.attribute_id = 195
            LEFT JOIN catalog_product_entity_varchar cpev_event_name
                ON cpev_event_name.entity_id = cpev1.value
               AND cpev_event_name.attribute_id = 73
            LEFT JOIN catalog_product_entity_varchar cpev_kit_name
                ON cpev_kit_name.entity_id = cpe.entity_id
               AND cpev_kit_name.attribute_id = 73
            LEFT JOIN catalog_product_entity_int cpei_status
                ON cpei_status.entity_id = cpe.entity_id
               AND cpei_status.attribute_id = (
                    SELECT attribute_id FROM eav_attribute
                    WHERE attribute_code = 'status'
                      AND entity_type_id = (
                            SELECT entity_type_id FROM eav_entity_type
                            WHERE entity_type_code = 'catalog_product'
                      )
               )
            WHERE cpe.type_id = 'bundle'
              AND cped_date.value >= DATE_FORMAT(CURDATE(), '%Y-01-01')
              AND cped_date.value <  DATE_FORMAT(CURDATE(), '%Y-01-01') + INTERVAL 1 YEAR
        """
        from app.core.db_retry import magento_run as _magento_run

        def _light_work(conn):
            res = conn.execute(text(_LIGHT_QUERY))
            return [dict(zip(res.keys(), r)) for r in res.fetchall()]

        try:
            rows = _magento_run(_light_work, label="kit_config:unconfigured-summary", profile="request")
        except Exception as exc:
            logger.error(f"[UnconfiguredSummary] Magento query error: {exc}")
            result = {"total_unconfigured": 0, "events": [], "magento_available": False}
            _unconfigured_cache["data"] = result
            _unconfigured_cache["ts"] = now
            return result

        all_configs = {c.bundle_entity_id for c in db.query(KitConfig).all()}

        class _FakeKit:
            def __init__(self, row):
                self.is_configured = int(row["bundle_entity_id"]) in all_configs
                self.nome_evento = row.get("nome_evento") or "Evento desconhecido"
                self.status_kit = row.get("status_kit")

        all_kits = [_FakeKit(r) for r in rows]
        unconfigured = [
            k for k in all_kits
            if not k.is_configured
            and k.status_kit != "inativo"
        ]

    # ── build summary ────────────────────────────────────────────────────
    event_counts: dict = {}
    for k in unconfigured:
        nome = getattr(k, "nome_evento", None) or "Evento desconhecido"
        event_counts[nome] = event_counts.get(nome, 0) + 1

    events_list = [
        {"nome_evento": nome, "count": cnt}
        for nome, cnt in sorted(event_counts.items(), key=lambda x: -x[1])
    ]

    result = {
        "total_unconfigured": len(unconfigured),
        "events": events_list,
        "magento_available": True,
        "source": source,
    }

    _unconfigured_cache["data"] = result
    _unconfigured_cache["ts"] = now
    logger.info(
        f"[UnconfiguredSummary] {len(unconfigured)} unconfigured kits across "
        f"{len(events_list)} events (source={source})"
    )
    return result


def _resolve_affected_grupo_anos(
    db: Session,
    bundle_entity_id: int,
    id_evento: Optional[int],
) -> list[tuple[str, int]]:
    """Resolve (evento_grupo, ano) pairs affected by a kit_config change.

    Looks up SkuMapping rows by both ``id_externo == bundle_entity_id`` (raro:
    poucos kits têm SKU mapping próprio) e ``id_externo == id_evento`` (caso
    comum: o evento pai do kit no Magento ou no Ativo está mapeado). Cobre as
    duas fontes (MAGENTO e ATIVO) sem assumir caixa, já que dados antigos
    podem ter sido gravados em minúsculas.
    """
    from sqlalchemy import func as _sa_func

    candidate_ids: list[int] = []
    try:
        if bundle_entity_id is not None:
            candidate_ids.append(int(bundle_entity_id))
    except (TypeError, ValueError):
        pass
    try:
        if id_evento is not None:
            candidate_ids.append(int(id_evento))
    except (TypeError, ValueError):
        pass
    if not candidate_ids:
        return []

    rows = (
        db.query(SkuMapping)
        .filter(
            _sa_func.upper(SkuMapping.fonte).in_(("MAGENTO", "ATIVO")),
            SkuMapping.id_externo.in_(candidate_ids),
            SkuMapping.ativo == True,
        )
        .all()
    )
    pairs: set[tuple[str, int]] = set()
    for row in rows:
        if row.evento_grupo and row.ano:
            pairs.add((row.evento_grupo, row.ano))
    return sorted(pairs)


def _invalidate_persisted_snapshot_for_grupos(
    db: Session,
    grupo_anos: list[tuple[str, int]],
) -> int:
    """Apaga EventoDetailSnapshot persistido dos grupos afetados.

    O endpoint `/marketing/eventos/{id}` serve do snapshot persistido como
    fast path, mesmo quando o cache em memória foi invalidado. Sem apagar
    o snapshot, mudanças em kit_config (renomeação, marcação de promo/básico,
    custo, multiplicador) só aparecem no próximo refresh agendado (30 min).
    """
    if not grupo_anos:
        return 0
    from ...models.evento_detail_snapshot import EventoDetailSnapshot

    total = 0
    try:
        for grupo, ano in grupo_anos:
            evt_id = f"grp_{grupo}"
            deleted = (
                db.query(EventoDetailSnapshot)
                .filter(
                    EventoDetailSnapshot.evento_id == evt_id,
                    EventoDetailSnapshot.ano == ano,
                )
                .delete(synchronize_session=False)
            )
            total += deleted or 0
        if total:
            db.commit()
            logger.info(
                f"[KitConfig] EventoDetailSnapshot persistido removido para "
                f"{[f'grp_{g}|{a}' for g, a in grupo_anos]} ({total} linha(s))"
            )
    except Exception as e:
        db.rollback()
        logger.warning(f"[KitConfig] Falha ao apagar EventoDetailSnapshot persistido: {e}")
    return total


def _invalidate_event_detail_for_bundle(
    db: Session,
    bundle_entity_id: int,
    id_evento: Optional[int] = None,
) -> bool:
    """Invalida cache em memória + snapshot persistido afetados pelo bundle.

    Estratégia:
    1. Resolve (evento_grupo, ano) via SkuMapping (cobre por bundle e por id_evento).
    2. Invalida event_detail_cache em memória para cada chave.
    3. Apaga EventoDetailSnapshot persistido dos mesmos grupos (snapshot é o
       fast path do endpoint, sem isso o usuário continua vendo dados antigos).
    4. Fallback por DimProjeto quando id_evento bate com um projeto (cobre
       eventos standalone numéricos).
    5. Último recurso: invalidação total do cache em memória (snapshots
       persistidos são deixados intactos para o scheduler atualizar; evita
       apagar tudo por uma operação isolada).

    Retorna True quando a invalidação direcionada (passos 1–3 ou 4) ocorreu.
    """
    from ...core.cache import event_detail_cache
    from datetime import datetime

    grupo_anos = _resolve_affected_grupo_anos(db, bundle_entity_id, id_evento)
    invalidated_keys: list[str] = []
    for grupo, ano in grupo_anos:
        key = f"{ano}_grp_{grupo}_detail"
        event_detail_cache.invalidate(key)
        invalidated_keys.append(key)

    if invalidated_keys:
        _invalidate_persisted_snapshot_for_grupos(db, grupo_anos)
        logger.info(
            f"[KitConfig] Targeted event_detail invalidation for bundle {bundle_entity_id}: {invalidated_keys}"
        )
        return True

    if id_evento:
        projeto = db.query(DimProjeto).filter(DimProjeto.id == id_evento).first()
        if projeto:
            year = projeto.data_evento.year if projeto.data_evento else datetime.now().year
            key = f"{year}_{id_evento}_detail"
            event_detail_cache.invalidate(key)
            try:
                from ...models.evento_detail_snapshot import EventoDetailSnapshot
                deleted = (
                    db.query(EventoDetailSnapshot)
                    .filter(
                        EventoDetailSnapshot.evento_id == str(id_evento),
                        EventoDetailSnapshot.ano == year,
                    )
                    .delete(synchronize_session=False)
                )
                if deleted:
                    db.commit()
                    logger.info(
                        f"[KitConfig] EventoDetailSnapshot persistido removido para "
                        f"projeto {id_evento} ano={year}"
                    )
            except Exception as e:
                db.rollback()
                logger.warning(
                    f"[KitConfig] Falha ao apagar snapshot persistido (projeto {id_evento}): {e}"
                )
            logger.info(
                f"[KitConfig] Fallback targeted event_detail invalidation for bundle {bundle_entity_id} "
                f"via id_evento={id_evento}: {key}"
            )
            return True

    event_detail_cache.invalidate()
    logger.info(
        f"[KitConfig] Full event_detail invalidation for bundle {bundle_entity_id} (no SKU mapping found)"
    )
    return False


@router.post("/bulk", response_model=KitConfigBulkResult)
def upsert_kit_config_bulk(
    body: KitConfigBulkUpsert,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("admin_kit_config", "pode_editar")),
):
    from .marketing import clear_ticket_atual_cache
    from ...core.cache import event_detail_cache

    if not body.items:
        return KitConfigBulkResult(saved=0, errors=0)

    basico_por_evento: dict[int, int] = {}
    promo_por_evento: dict[int, int] = {}
    for item in body.items:
        if item.id_evento is None:
            continue
        if item.is_kit_basico:
            basico_por_evento[item.id_evento] = basico_por_evento.get(item.id_evento, 0) + 1
        if item.is_promo_principal:
            promo_por_evento[item.id_evento] = promo_por_evento.get(item.id_evento, 0) + 1

    eventos_basico_dup = [eid for eid, n in basico_por_evento.items() if n > 1]
    eventos_promo_dup = [eid for eid, n in promo_por_evento.items() if n > 1]
    if eventos_basico_dup or eventos_promo_dup:
        partes = []
        if eventos_basico_dup:
            partes.append(f"Kit Básico marcado em mais de um kit para o(s) evento(s): {eventos_basico_dup}")
        if eventos_promo_dup:
            partes.append(f"Promo Principal marcado em mais de um kit para o(s) evento(s): {eventos_promo_dup}")
        raise HTTPException(status_code=409, detail=" | ".join(partes))

    bundle_ids = [item.bundle_entity_id for item in body.items]

    existing_map: dict[int, KitConfig] = {
        row.bundle_entity_id: row
        for row in db.query(KitConfig).filter(KitConfig.bundle_entity_id.in_(bundle_ids)).all()
    }

    from sqlalchemy import func as _sa_func
    id_evento_set = {item.id_evento for item in body.items if item.id_evento is not None}
    lookup_ids = list({*bundle_ids, *id_evento_set})
    sku_map: dict[int, list[SkuMapping]] = {}
    for row in (
        db.query(SkuMapping)
        .filter(
            _sa_func.upper(SkuMapping.fonte).in_(("MAGENTO", "ATIVO")),
            SkuMapping.id_externo.in_(lookup_ids),
            SkuMapping.ativo == True,
        )
        .all()
    ):
        sku_map.setdefault(row.id_externo, []).append(row)

    basico_evento_ids = {item.id_evento for item in body.items if item.is_kit_basico and item.id_evento is not None}
    promo_evento_ids = {item.id_evento for item in body.items if item.is_promo_principal and item.id_evento is not None}
    basico_bundle_ids = {item.bundle_entity_id for item in body.items if item.is_kit_basico}
    promo_bundle_ids = {item.bundle_entity_id for item in body.items if item.is_promo_principal}

    if basico_evento_ids:
        db.query(KitConfig).filter(
            KitConfig.id_evento.in_(basico_evento_ids),
            KitConfig.bundle_entity_id.notin_(basico_bundle_ids),
            KitConfig.is_kit_basico == True,
        ).update({"is_kit_basico": False}, synchronize_session="fetch")

    if promo_evento_ids:
        db.query(KitConfig).filter(
            KitConfig.id_evento.in_(promo_evento_ids),
            KitConfig.bundle_entity_id.notin_(promo_bundle_ids),
            KitConfig.is_promo_principal == True,
        ).update({"is_promo_principal": False}, synchronize_session="fetch")

    db.flush()

    saved = 0
    errors = 0
    invalidated_keys: set[str] = set()
    affected_grupo_anos: set[tuple[str, int]] = set()
    full_invalidation_needed = False

    for item in body.items:
        try:
            existing = existing_map.get(item.bundle_entity_id)
            if existing:
                existing.multiplicador = item.multiplicador
                existing.is_kit_basico = item.is_kit_basico
                existing.is_promo_principal = item.is_promo_principal
                if item.id_evento is not None:
                    existing.id_evento = item.id_evento
                existing.tipo_kit = item.tipo_kit
                if item.custo_kit is not None:
                    existing.custo_kit = item.custo_kit
                existing.ativo_categoria = item.ativo_categoria or None
                valid_cenarios = {'participacao', 'sem_bike', 'com_bike', None, ''}
                existing.cenario_ciclismo = item.cenario_ciclismo if item.cenario_ciclismo in valid_cenarios else None
                existing.ignorado = item.ignorado
            else:
                new_config = KitConfig(
                    bundle_entity_id=item.bundle_entity_id,
                    multiplicador=item.multiplicador,
                    is_kit_basico=item.is_kit_basico,
                    is_promo_principal=item.is_promo_principal,
                    id_evento=item.id_evento,
                    tipo_kit=item.tipo_kit,
                    custo_kit=item.custo_kit,
                    ativo_categoria=item.ativo_categoria or None,
                    cenario_ciclismo=item.cenario_ciclismo if item.cenario_ciclismo in {'participacao', 'sem_bike', 'com_bike'} else None,
                    ignorado=item.ignorado,
                )
                db.add(new_config)

            sku_rows = list(sku_map.get(item.bundle_entity_id, []))
            if item.id_evento is not None:
                sku_rows.extend(sku_map.get(item.id_evento, []))
            if sku_rows:
                for row in sku_rows:
                    if row.evento_grupo and row.ano:
                        invalidated_keys.add(f"{row.ano}_grp_{row.evento_grupo}_detail")
                        affected_grupo_anos.add((row.evento_grupo, row.ano))
            else:
                full_invalidation_needed = True

            saved += 1
        except Exception as e:
            errors += 1
            logger.exception(
                f"[KitConfig] Erro processando item bundle_entity_id={item.bundle_entity_id}: {e}"
            )

    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        logger.exception(f"[KitConfig] IntegrityError no commit do bulk upsert: {e}")
        msg = str(getattr(e, "orig", e))
        if "uq_kit_basico_per_evento" in msg:
            detail = "Já existe um Kit Básico marcado para esse evento. Desmarque o anterior antes de salvar."
        else:
            detail = "Conflito ao salvar configurações (violação de restrição única)."
        raise HTTPException(status_code=409, detail=detail)
    except Exception as e:
        db.rollback()
        logger.exception(f"[KitConfig] Erro no commit do bulk upsert: {e}")
        raise HTTPException(status_code=500, detail="Erro ao salvar configurações em lote")

    _kits_cache["data"] = None
    _kits_cache["ts"] = 0.0
    _unconfigured_cache["data"] = None
    _unconfigured_cache["ts"] = 0.0
    clear_ticket_atual_cache()

    if full_invalidation_needed:
        event_detail_cache.invalidate()
        logger.info(f"[KitConfig] Bulk save: full event_detail invalidation ({len(bundle_ids)} bundles, some had no SKU mapping)")
    else:
        for key in invalidated_keys:
            event_detail_cache.invalidate(key)
        logger.info(f"[KitConfig] Bulk save: targeted invalidation of {len(invalidated_keys)} keys")

    if affected_grupo_anos:
        _invalidate_persisted_snapshot_for_grupos(db, sorted(affected_grupo_anos))

    logger.info(f"[KitConfig] Bulk upsert complete: {saved} saved, {errors} errors out of {len(body.items)} items")
    return KitConfigBulkResult(saved=saved, errors=errors)


@router.post("/{bundle_entity_id}", response_model=KitConfigResponse)
def upsert_kit_config(
    bundle_entity_id: int,
    body: KitConfigUpsert,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("admin_kit_config", "pode_editar")),
):
    from .marketing import clear_ticket_atual_cache

    if body.is_kit_basico and body.id_evento is not None:
        db.query(KitConfig).filter(
            KitConfig.id_evento == body.id_evento,
            KitConfig.bundle_entity_id != bundle_entity_id,
            KitConfig.is_kit_basico == True,
        ).update({"is_kit_basico": False})

    if body.is_promo_principal and body.id_evento is not None:
        db.query(KitConfig).filter(
            KitConfig.id_evento == body.id_evento,
            KitConfig.bundle_entity_id != bundle_entity_id,
            KitConfig.is_promo_principal == True,
        ).update({"is_promo_principal": False})

    existing = db.query(KitConfig).filter(KitConfig.bundle_entity_id == bundle_entity_id).first()
    try:
        if existing:
            existing.multiplicador = body.multiplicador
            existing.is_kit_basico = body.is_kit_basico
            existing.is_promo_principal = body.is_promo_principal
            if body.id_evento is not None:
                existing.id_evento = body.id_evento
            existing.tipo_kit = body.tipo_kit
            if body.custo_kit is not None:
                existing.custo_kit = body.custo_kit
            existing.ativo_categoria = body.ativo_categoria or None
            existing.cenario_ciclismo = body.cenario_ciclismo if body.cenario_ciclismo in {'participacao', 'sem_bike', 'com_bike'} else None
            existing.ignorado = body.ignorado
            db.commit()
            db.refresh(existing)
            _kits_cache["data"] = None
            _kits_cache["ts"] = 0.0
            _unconfigured_cache["data"] = None
            _unconfigured_cache["ts"] = 0.0
            clear_ticket_atual_cache()
            _invalidate_event_detail_for_bundle(db, bundle_entity_id, body.id_evento)
            return existing

        new_config = KitConfig(
            bundle_entity_id=bundle_entity_id,
            multiplicador=body.multiplicador,
            is_kit_basico=body.is_kit_basico,
            is_promo_principal=body.is_promo_principal,
            id_evento=body.id_evento,
            tipo_kit=body.tipo_kit,
            custo_kit=body.custo_kit,
            ativo_categoria=body.ativo_categoria or None,
            cenario_ciclismo=body.cenario_ciclismo if body.cenario_ciclismo in {'participacao', 'sem_bike', 'com_bike'} else None,
            ignorado=body.ignorado,
        )
        db.add(new_config)
        db.commit()
        db.refresh(new_config)
        _kits_cache["data"] = None
        _kits_cache["ts"] = 0.0
        _unconfigured_cache["data"] = None
        _unconfigured_cache["ts"] = 0.0
        clear_ticket_atual_cache()
        _invalidate_event_detail_for_bundle(db, bundle_entity_id, body.id_evento)
        return new_config
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Já existe um Kit Básico para este evento. Desmarque o outro antes de marcar este.",
        )


@router.get("/configs", response_model=List[KitConfigResponse])
def get_all_configs(
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("admin_kit_config", "pode_visualizar")),
):
    return db.query(KitConfig).all()
