from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from typing import List
from app.core.database import get_db
from app.core.security import get_current_user, require_permission
from app.models.kit_config import KitConfig
from app.schemas.kit_config import KitConfigUpsert, KitRow, KitConfigResponse
import app.core.database as db_module
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/kit-config", tags=["Kit Config"])

MAGENTO_KITS_QUERY = """
SELECT
    cpev1.value                         AS id_evento,
    cpev_kit.value                      AS nome_evento,
    cpe_parent.entity_id                AS bundle_entity_id,
    cpev_kit_name.value                 AS nome_kit,
    lote.lot_name                       AS lote_atual,
    lote.lot_value                      AS preco_lote,
    lote.lot_sell_ends                  AS lote_termina_em,

    COALESCE(MAX(CASE 
        WHEN cpep.value NOT IN (14.50)
         AND cpev_simple.value NOT LIKE '%Distancia%'
         AND cpev_simple.value NOT LIKE '%Distância%'
        THEN cpep.value 
        ELSE NULL 
    END), 0)                            AS preco_adicional_kit,

    CASE
        WHEN MAX(CASE 
            WHEN cpep.value NOT IN (14.50)
             AND cpev_simple.value NOT LIKE '%Distancia%'
             AND cpev_simple.value NOT LIKE '%Distância%'
            THEN cpep.value ELSE NULL 
        END) IS NOT NULL
        THEN lote.lot_value + MAX(CASE 
            WHEN cpep.value NOT IN (14.50)
             AND cpev_simple.value NOT LIKE '%Distancia%'
             AND cpev_simple.value NOT LIKE '%Distância%'
            THEN cpep.value ELSE NULL 
        END)
        ELSE MAX(CASE 
            WHEN (cpev_simple.value LIKE '%Distancia%' OR cpev_simple.value LIKE '%Distância%')
             AND cpep.value > 0
            THEN cpep.value ELSE NULL 
        END)
    END                                 AS ticket_base,

    GROUP_CONCAT(DISTINCT CASE 
        WHEN (cpev_simple.value LIKE '%Distancia%' OR cpev_simple.value LIKE '%Distância%')
        THEN cpev_simple.value 
        ELSE NULL 
    END ORDER BY cpev_simple.value SEPARATOR ' | ') AS distancias

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
  AND YEAR(cped_date.value) = YEAR(CURDATE())

GROUP BY
    cpev1.value,
    cpev_kit.value,
    cpe_parent.entity_id,
    cpev_kit_name.value,
    lote.lot_name,
    lote.lot_value,
    lote.lot_sell_ends

ORDER BY
    cpev1.value,
    ticket_base
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

    kits: List[KitRow] = []
    for row in magento_rows:
        row_dict = dict(zip(columns, row))
        bundle_id = int(row_dict["bundle_entity_id"])
        ticket_base = float(row_dict["ticket_base"]) if row_dict.get("ticket_base") is not None else None

        cfg = config_map.get(bundle_id)
        multiplicador = cfg.multiplicador if cfg else 1
        is_configured = cfg is not None
        is_kit_basico = cfg.is_kit_basico if cfg else False

        ticket_final = (ticket_base * multiplicador) if ticket_base is not None else None

        lote_termina = row_dict.get("lote_termina_em")
        if lote_termina is not None:
            lote_termina = str(lote_termina)

        kits.append(KitRow(
            id_evento=str(row_dict.get("id_evento")) if row_dict.get("id_evento") is not None else None,
            nome_evento=row_dict.get("nome_evento"),
            bundle_entity_id=bundle_id,
            nome_kit=row_dict.get("nome_kit"),
            lote_atual=row_dict.get("lote_atual"),
            preco_lote=float(row_dict["preco_lote"]) if row_dict.get("preco_lote") is not None else None,
            lote_termina_em=lote_termina,
            preco_adicional_kit=float(row_dict["preco_adicional_kit"]) if row_dict.get("preco_adicional_kit") is not None else None,
            ticket_base=ticket_base,
            distancias=row_dict.get("distancias"),
            multiplicador=multiplicador,
            ticket_final=ticket_final,
            is_configured=is_configured,
            is_kit_basico=is_kit_basico,
        ))

    return kits


@router.post("/{bundle_entity_id}", response_model=KitConfigResponse)
def upsert_kit_config(
    bundle_entity_id: int,
    body: KitConfigUpsert,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("admin_kit_config", "pode_editar")),
):
    from .marketing import clear_ticket_atual_cache, clear_sku_id_evento_bridge_cache

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
            db.commit()
            db.refresh(existing)
            clear_ticket_atual_cache()
            clear_sku_id_evento_bridge_cache()
            return existing

        new_config = KitConfig(
            bundle_entity_id=bundle_entity_id,
            multiplicador=body.multiplicador,
            is_kit_basico=body.is_kit_basico,
            id_evento=body.id_evento,
        )
        db.add(new_config)
        db.commit()
        db.refresh(new_config)
        clear_ticket_atual_cache()
        clear_sku_id_evento_bridge_cache()
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
