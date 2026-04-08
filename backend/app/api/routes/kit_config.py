from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from typing import List
from datetime import date
from app.core.database import get_db
from app.core.security import get_current_user, require_permission
from app.models.kit_config import KitConfig
from app.models.cadastro_evento import CadastroEvento, CadastroKitProduto, CadastroKitProdutoItem
from app.models.dimensoes import SkuMapping, DimProjeto
from app.schemas.kit_config import KitConfigUpsert, KitRow, KitConfigResponse
import app.core.database as db_module
import logging
import time as _time

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

    try:
        with db_module.engine_magento.connect() as conn:
            result = conn.execute(text(MAGENTO_KITS_QUERY))
            magento_rows = result.fetchall()
            columns = result.keys()
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

    for sm in ativo_maps:
        sku = (sm.sku or "").upper().strip()
        if not sku or sku in current_magento_skus:
            continue

        projeto_id = sku_to_projeto_id.get(sku)
        if not projeto_id:
            continue
        cadastro_id = projeto_to_cadastro_id.get(projeto_id)
        if not cadastro_id:
            continue

        # Year guard: require CadastroEvento.ano_evento to match current year
        cadastro = cadastro_by_id.get(cadastro_id)
        if not cadastro:
            continue
        if cadastro.ano_evento and cadastro.ano_evento != current_year:
            continue

        kps = kps_by_cadastro_id.get(cadastro_id, [])
        if not kps:
            continue

        for kp in kps:
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

            kits.append(KitRow(
                id_evento=str(sm.id_externo),
                nome_evento=sm.nome_evento,
                bundle_entity_id=synthetic_bundle_id,
                nome_kit=kp.kit,
                tipo_kit=tipo_kit,
                tipo_categoria=None,
                lote_atual=None,
                multiplicador_sugerido=1,
                multiplicador=multiplicador,
                price_base=None,
                special_price_base=None,
                price=None,
                special_price=None,
                is_configured=is_configured,
                is_kit_basico=is_kit_basico,
                is_promo_principal=is_promo_principal,
                custo_cadastro=custo_cadastro_val,
                custo_kit=custo_kit_val,
                ativo_categoria=kp.ativo_categoria or (cfg.ativo_categoria if cfg else None),
                status_kit=None,
                fonte="ativo",
            ))

    _kits_cache["data"] = kits
    _kits_cache["ts"] = _time.time()
    logger.info(f"[KitConfig] Kit list refreshed and cached ({len(kits)} kits)")
    return kits


@router.get("/unconfigured-summary")
def get_unconfigured_summary(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
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
        unconfigured = [k for k in all_kits if not k.is_configured]
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
                cpev_kit_name.value             AS nome_kit
            FROM catalog_product_entity cpe
            JOIN catalog_product_entity_varchar cpev1
                ON cpe.entity_id = cpev1.entity_id
               AND cpev1.attribute_id = 321
            LEFT JOIN catalog_product_entity_varchar cpev_event_name
                ON cpe.entity_id = cpev_event_name.entity_id
               AND cpev_event_name.attribute_id = 73
            LEFT JOIN catalog_product_entity_varchar cpev_kit_name
                ON cpe.entity_id = cpev_kit_name.entity_id
               AND cpev_kit_name.attribute_id = 73
            WHERE cpe.type_id = 'bundle'
        """
        try:
            with db_module.engine_magento.connect() as conn:
                res = conn.execute(text(_LIGHT_QUERY))
                rows = [dict(zip(res.keys(), r)) for r in res.fetchall()]
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

        all_kits = [_FakeKit(r) for r in rows]
        unconfigured = [k for k in all_kits if not k.is_configured]

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


def _invalidate_event_detail_for_bundle(
    db: Session,
    bundle_entity_id: int,
    id_evento: int = None,
) -> bool:
    """Invalidate only the event_detail cache entries affected by this bundle change.

    Strategy:
    1. Look up SkuMapping (fonte=magento) for this bundle → find grupo + ano → targeted key.
    2. If not found via Magento mapping, fall back to id_evento → DimProjeto.data_evento.year.
    3. If still unresolvable, fall back to full cache invalidation.

    Returns True when targeted invalidation succeeded, False when fell back to full invalidation.
    """
    from ...core.cache import event_detail_cache
    from datetime import datetime

    invalidated_keys: list[str] = []

    sku_rows = (
        db.query(SkuMapping)
        .filter(
            SkuMapping.fonte == "magento",
            SkuMapping.id_externo == bundle_entity_id,
            SkuMapping.ativo == True,
        )
        .all()
    )

    for row in sku_rows:
        if row.evento_grupo and row.ano:
            key = f"{row.ano}_grp_{row.evento_grupo}_detail"
            event_detail_cache.invalidate(key)
            invalidated_keys.append(key)

    if invalidated_keys:
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
