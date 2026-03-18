from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from typing import List
from app.core.database import get_db
from app.core.security import get_current_user, require_permission
from app.models.kit_config import KitConfig
from app.models.cadastro_evento import CadastroEvento, CadastroKitProduto, CadastroKitProdutoItem
from app.models.dimensoes import SkuMapping, DimProjeto
from app.schemas.kit_config import KitConfigUpsert, KitRow, KitConfigResponse
import app.core.database as db_module
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/kit-config", tags=["Kit Config"])

MAGENTO_KITS_QUERY = """
SELECT
    cpev1.value                             AS id_evento,
    cpev_kit.value                          AS nome_evento,
    cpe_parent.entity_id                    AS bundle_entity_id,
    cpev_kit_name.value                     AS nome_kit,
    eaov_tipo.value                         AS tipo_categoria,
    lote.lot_name                           AS lote_atual,

    CASE cpei_tipo.value
        WHEN 1606 THEN 2
        WHEN 1607 THEN 3
        WHEN 1608 THEN 4
        WHEN 1609 THEN 2
        WHEN 1700 THEN 2
        WHEN 1701 THEN 4
        ELSE 1
    END                                     AS multiplicador,

    (
        COALESCE(MAX(CASE 
            WHEN (
                cpev_simple.value LIKE '%Distancia%'
             OR cpev_simple.value LIKE '%Distância%'
             OR cpev_simple.value LIKE '%Modalidade%'
            )
             AND cpep.value > 0
            THEN cpep.value ELSE NULL 
        END), 0)
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
    )
    *
    CASE cpei_tipo.value
        WHEN 1606 THEN 2
        WHEN 1607 THEN 3
        WHEN 1608 THEN 4
        WHEN 1609 THEN 2
        WHEN 1700 THEN 2
        WHEN 1701 THEN 4
        ELSE 1
    END                                     AS price,

    (
        COALESCE(MAX(CASE 
            WHEN (
                cpev_simple.value LIKE '%Distancia%'
             OR cpev_simple.value LIKE '%Distância%'
             OR cpev_simple.value LIKE '%Modalidade%'
            )
             AND pi_filho.final_price > 0
            THEN pi_filho.final_price ELSE NULL 
        END), 0)
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
    )
    *
    CASE cpei_tipo.value
        WHEN 1606 THEN 2
        WHEN 1607 THEN 3
        WHEN 1608 THEN 4
        WHEN 1609 THEN 2
        WHEN 1700 THEN 2
        WHEN 1701 THEN 4
        ELSE 1
    END                                     AS special_price

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

LEFT JOIN catalog_product_index_price pi_filho
       ON pi_filho.entity_id = cpeos.product_id
      AND pi_filho.website_id = 1
      AND pi_filho.customer_group_id = 0

JOIN catalog_product_entity_event_lot_price lote
       ON lote.entity_id = cpev1.value
      AND lote.lot_id = (
            SELECT lot_id
            FROM catalog_product_entity_event_lot_price
            WHERE entity_id = cpev1.value
            ORDER BY record_id DESC
            LIMIT 1
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
    cpei_tipo.value,
    lote.lot_name,
    lote.lot_value,
    lote.lot_sell_ends

ORDER BY
    cpev1.value,
    special_price
"""


@router.get("/kits", response_model=List[KitRow])
def get_kits_with_config(
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("admin_kit_config", "pode_visualizar")),
):
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
    for kp in all_kit_produtos:
        kit_name = (kp.kit or "").strip()
        cost = sum(float(i.valor_unitario or 0) for i in items_by_kit.get(kp.id, []))
        cadastro_kit_costs.setdefault(kp.cadastro_id, {})[kit_name] = cost

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

        mult_sugerido = int(row_dict.get("multiplicador") or 1)
        price_raw = float(row_dict["price"]) if row_dict.get("price") is not None else None
        special_price_raw = float(row_dict["special_price"]) if row_dict.get("special_price") is not None else None

        price_base = (price_raw / mult_sugerido) if price_raw is not None and mult_sugerido > 0 else price_raw
        special_price_base = (special_price_raw / mult_sugerido) if special_price_raw is not None and mult_sugerido > 0 else special_price_raw

        cfg = config_map.get(bundle_id)
        multiplicador = cfg.multiplicador if cfg else mult_sugerido
        is_configured = cfg is not None
        is_kit_basico = cfg.is_kit_basico if cfg else False
        tipo_kit = cfg.tipo_kit if cfg else None

        custo_cadastro = _get_custo_for_event(row_dict.get("id_evento"), tipo_kit)
        custo_kit_val = float(cfg.custo_kit) if cfg and cfg.custo_kit is not None else None

        price_final = (price_base * multiplicador) if price_base is not None else None
        special_price_final = (special_price_base * multiplicador) if special_price_base is not None else None

        kits.append(KitRow(
            id_evento=str(row_dict.get("id_evento")) if row_dict.get("id_evento") is not None else None,
            nome_evento=row_dict.get("nome_evento"),
            bundle_entity_id=bundle_id,
            nome_kit=row_dict.get("nome_kit"),
            tipo_kit=tipo_kit,
            tipo_categoria=row_dict.get("tipo_categoria"),
            lote_atual=row_dict.get("lote_atual"),
            multiplicador_sugerido=mult_sugerido,
            multiplicador=multiplicador,
            price_base=price_base,
            special_price_base=special_price_base,
            price=price_final,
            special_price=special_price_final,
            is_configured=is_configured,
            is_kit_basico=is_kit_basico,
            custo_cadastro=custo_cadastro,
            custo_kit=custo_kit_val,
            ativo_categoria=cfg.ativo_categoria if cfg else None,
        ))

    return kits


@router.post("/{bundle_entity_id}", response_model=KitConfigResponse)
def upsert_kit_config(
    bundle_entity_id: int,
    body: KitConfigUpsert,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("admin_kit_config", "pode_editar")),
):
    from .marketing import clear_ticket_atual_cache
    from ...core.cache import eventos_list_cache, event_detail_cache

    if body.is_kit_basico and body.id_evento is not None:
        db.query(KitConfig).filter(
            KitConfig.id_evento == body.id_evento,
            KitConfig.bundle_entity_id != bundle_entity_id,
            KitConfig.is_kit_basico == True,
        ).update({"is_kit_basico": False})

    existing = db.query(KitConfig).filter(KitConfig.bundle_entity_id == bundle_entity_id).first()
    try:
        if existing:
            existing.multiplicador = body.multiplicador
            existing.is_kit_basico = body.is_kit_basico
            if body.id_evento is not None:
                existing.id_evento = body.id_evento
            existing.tipo_kit = body.tipo_kit
            if body.custo_kit is not None:
                existing.custo_kit = body.custo_kit
            existing.ativo_categoria = body.ativo_categoria or None
            db.commit()
            db.refresh(existing)
            clear_ticket_atual_cache()
            eventos_list_cache.invalidate_all()
            event_detail_cache.invalidate()
            return existing

        new_config = KitConfig(
            bundle_entity_id=bundle_entity_id,
            multiplicador=body.multiplicador,
            is_kit_basico=body.is_kit_basico,
            id_evento=body.id_evento,
            tipo_kit=body.tipo_kit,
            custo_kit=body.custo_kit,
            ativo_categoria=body.ativo_categoria or None,
        )
        db.add(new_config)
        db.commit()
        db.refresh(new_config)
        clear_ticket_atual_cache()
        eventos_list_cache.invalidate_all()
        event_detail_cache.invalidate()
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
