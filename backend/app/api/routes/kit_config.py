from fastapi import APIRouter, Depends, HTTPException, Response
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
import threading as _threading


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


def _normalize_special_price(price, special_price):
    """Regra B (acordada com usuário, mai/2026):
    o campo `special_price` só deve aparecer quando representa uma promoção
    REAL — isto é, quando for estritamente menor que `price`. Quando o
    fallback do SQL traz special_price >= price (caso típico: kit sem
    EAV special_price cujo MIN(lot_value) acaba >= preço do componente),
    semanticamente NÃO existe promoção, então retornamos None.
    Aplicar este filtro UMA VEZ na leitura (cache/snapshot/live) evita
    espalhar a regra por múltiplos pontos de construção do KitRow.
    """
    if special_price is None or price is None:
        return special_price
    try:
        if float(special_price) >= float(price):
            return None
    except (TypeError, ValueError):
        return special_price
    return special_price


_kits_cache: dict = {"data": None, "ts": 0.0}
_KITS_TTL = 120


def _build_local_fallback_kits(db: Session) -> List[KitRow]:
    all_configs = db.query(KitConfig).filter(KitConfig.ignorado == False).all()
    sku_maps = db.query(SkuMapping).filter(
        SkuMapping.fonte == 'MAGENTO',
        SkuMapping.ativo == True,
    ).all()
    id_evento_to_nome: dict = {}
    for sm in sku_maps:
        if sm.id_externo and sm.nome_evento:
            id_evento_to_nome[int(sm.id_externo)] = sm.nome_evento
    kits = []
    for cfg in all_configs:
        id_ev = cfg.id_evento
        nome_ev = id_evento_to_nome.get(id_ev) if id_ev else None
        kits.append(KitRow(
            id_evento=str(id_ev) if id_ev else None,
            nome_evento=nome_ev,
            bundle_entity_id=cfg.bundle_entity_id,
            nome_kit=cfg.kit_nome,
            tipo_kit=cfg.tipo_kit,
            tipo_categoria=None,
            lote_atual=None,
            multiplicador_sugerido=cfg.multiplicador,
            multiplicador=cfg.multiplicador,
            price_base=None,
            special_price_base=None,
            price=None,
            special_price=None,
            is_configured=True,
            is_kit_basico=cfg.is_kit_basico,
            is_promo_principal=cfg.is_promo_principal,
            custo_cadastro=None,
            custo_kit=float(cfg.custo_kit) if cfg.custo_kit is not None else None,
            ativo_categoria=cfg.ativo_categoria,
            cenario_ciclismo=cfg.cenario_ciclismo,
            status_kit=None,
            fonte="local",
            ignorado=cfg.ignorado,
        ))
    return sorted(kits, key=lambda k: (k.nome_evento or '', k.nome_kit or ''))

_unconfigured_cache: dict = {"data": None, "ts": 0.0}
_UNCONFIGURED_TTL = 300  # 5 minutes

router = APIRouter(prefix="/api/kit-config", tags=["Kit Config"])


@router.get("/diag-special-price")
def diag_special_price(
    bundle_id: Optional[int] = None,
    nome_like: Optional[str] = None,
    current_user=Depends(require_permission("admin_kit_config", "pode_visualizar")),
):
    """Diagnóstico do special_price de um bundle no Magento.

    Devolve o valor que cada nível do COALESCE da query principal está
    retornando, para identificar por que o special_price exibido está zerado
    ou diferente do esperado.

    Uso:
      GET /api/kit-config/diag-special-price?bundle_id=12345
      GET /api/kit-config/diag-special-price?nome_like=Promocional 50 OFF

    Quando `nome_like` é informado, busca bundles cujo nome contém o termo
    (até 20 resultados) e devolve o diagnóstico de cada um.
    """
    if not bundle_id and not nome_like:
        raise HTTPException(400, "Informe bundle_id OU nome_like")

    if db_module.engine_magento is None:
        raise HTTPException(503, "engine_magento indisponível")

    from app.core.db_retry import magento_run

    def _work(conn):
        results = []
        if bundle_id:
            target_ids = [int(bundle_id)]
        else:
            rows = conn.execute(text("""
                SELECT cpe.entity_id, cpev_name.value AS nome_kit, cpev1.value AS id_evento
                FROM catalog_product_entity cpe
                JOIN catalog_product_entity_varchar cpev_name
                      ON cpev_name.entity_id = cpe.entity_id AND cpev_name.attribute_id = 73
                LEFT JOIN catalog_product_entity_varchar cpev1
                      ON cpev1.entity_id = cpe.entity_id AND cpev1.attribute_id = 321
                WHERE cpe.type_id = 'bundle'
                  AND cpev_name.value LIKE :like
                LIMIT 5
            """), {"like": f"%{nome_like}%"}).fetchall()
            target_ids = [int(r[0]) for r in rows]
            if not target_ids:
                return {"matches": [], "msg": "Nenhum bundle bate com nome_like"}

        for eid in target_ids:
            # Nome do kit e id_evento
            meta = conn.execute(text("""
                SELECT
                    (SELECT value FROM catalog_product_entity_varchar
                     WHERE entity_id = :eid AND attribute_id = 73 LIMIT 1) AS nome_kit,
                    (SELECT value FROM catalog_product_entity_varchar
                     WHERE entity_id = :eid AND attribute_id = 321 LIMIT 1) AS id_evento
            """), {"eid": eid}).fetchone()

            # Nível 1: EAV special_price (todos os scopes, valor bruto)
            eav_sp = conn.execute(text("""
                SELECT cped.store_id, cped.value
                FROM catalog_product_entity_decimal cped
                JOIN eav_attribute ea ON ea.attribute_id = cped.attribute_id
                     AND ea.attribute_code = 'special_price'
                WHERE cped.entity_id = :eid
                ORDER BY cped.store_id
            """), {"eid": eid}).fetchall()
            # Nível 1 (filtrado): o que a query atual usa (value > 0, LIMIT 1)
            eav_sp_picked = conn.execute(text("""
                SELECT cped_sp.value
                FROM catalog_product_entity_decimal cped_sp
                JOIN eav_attribute ea_sp
                      ON ea_sp.attribute_id   = cped_sp.attribute_id
                     AND ea_sp.attribute_code = 'special_price'
                WHERE cped_sp.entity_id = :eid
                  AND cped_sp.value > 0
                LIMIT 1
            """), {"eid": eid}).fetchone()

            # EAV price
            eav_price = conn.execute(text("""
                SELECT cped.store_id, cped.value
                FROM catalog_product_entity_decimal cped
                JOIN eav_attribute ea ON ea.attribute_id = cped.attribute_id
                     AND ea.attribute_code = 'price'
                WHERE cped.entity_id = :eid
                ORDER BY cped.store_id
            """), {"eid": eid}).fetchall()

            # Nível 2: lotes do próprio bundle
            lotes_bundle = conn.execute(text("""
                SELECT lot_value, lot_sell_ends, lot_name
                FROM catalog_product_entity_event_lot_price
                WHERE entity_id = :eid
                ORDER BY lot_value
            """), {"eid": eid}).fetchall()
            lvl2 = conn.execute(text("""
                SELECT MIN(lot_value)
                FROM catalog_product_entity_event_lot_price
                WHERE entity_id = :eid
                  AND lot_value > 0
                  AND (lot_sell_ends IS NULL OR lot_sell_ends >= NOW())
            """), {"eid": eid}).fetchone()

            # Nível 3a: lotes ativos do EVENTO (via cpev1)
            id_evento = meta[1] if meta else None
            lotes_evento = []
            min_lote_evento = None
            if id_evento:
                try:
                    id_evento_int = int(id_evento)
                    lotes_evento = conn.execute(text("""
                        SELECT lot_value, lot_sell_ends, lot_name
                        FROM catalog_product_entity_event_lot_price
                        WHERE entity_id = :eid
                          AND lot_value > 0
                        ORDER BY lot_value
                        LIMIT 10
                    """), {"eid": id_evento_int}).fetchall()
                    r = conn.execute(text("""
                        SELECT MIN(lot_value)
                        FROM catalog_product_entity_event_lot_price
                        WHERE entity_id = :eid
                          AND lot_value > 0
                          AND (lot_sell_ends IS NULL OR lot_sell_ends >= NOW())
                    """), {"eid": id_evento_int}).fetchone()
                    min_lote_evento = float(r[0]) if r and r[0] is not None else None
                except (ValueError, TypeError):
                    pass

            # Nível 4: index_price (mesmo filtro da query real: min_price > 0)
            idx = conn.execute(text("""
                SELECT MIN(min_price), MIN(final_price), MIN(price)
                FROM catalog_product_index_price
                WHERE entity_id = :eid
                  AND min_price > 0
            """), {"eid": eid}).fetchone()
            lvl4 = float(idx[0]) if idx and idx[0] is not None else None

            # Addon do kit (para nível 3): MAX(preço componente não-Distância/Modalidade/etc).
            # Replica a mesma blacklist da MAGENTO_KITS_QUERY.
            addon_row = conn.execute(text("""
                SELECT COALESCE(MAX(CASE
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
                END), 0) AS addon
                FROM catalog_product_bundle_selection cpbs
                JOIN catalog_product_entity cpe_simple
                      ON cpe_simple.entity_id = cpbs.product_id
                LEFT JOIN catalog_product_entity_decimal cpep
                      ON cpep.entity_id = cpe_simple.entity_id
                     AND cpep.attribute_id = (SELECT attribute_id FROM eav_attribute
                                              WHERE attribute_code='price' AND entity_type_id=4 LIMIT 1)
                LEFT JOIN catalog_product_entity_varchar cpev_simple
                      ON cpev_simple.entity_id = cpe_simple.entity_id
                     AND cpev_simple.attribute_id = 73
                WHERE cpbs.parent_product_id = :eid
            """), {"eid": eid}).fetchone()
            addon_val = float(addon_row[0]) if addon_row and addon_row[0] is not None else 0.0

            # Status do bundle
            status = conn.execute(text("""
                SELECT cpei.value
                FROM catalog_product_entity_int cpei
                JOIN eav_attribute ea ON ea.attribute_id = cpei.attribute_id
                     AND ea.attribute_code = 'status'
                WHERE cpei.entity_id = :eid
                ORDER BY cpei.store_id
            """), {"eid": eid}).fetchall()

            # Resolver qual nível ganha (replica fielmente a COALESCE da MAGENTO_KITS_QUERY)
            lvl1_val = float(eav_sp_picked[0]) if eav_sp_picked and eav_sp_picked[0] is not None else None
            lvl2_val = float(lvl2[0]) if lvl2 and lvl2[0] is not None else None
            # Fallback 3 só ativa quando bundle NÃO tem lotes próprios
            lvl3_val = None
            if not lotes_bundle:
                # Mesma fórmula da query real: COALESCE(min_lote_evento,0) + COALESCE(addon,0)
                lvl3_val = (min_lote_evento or 0.0) + addon_val
            winner = None
            if lvl1_val is not None:
                winner = ("nivel_1_eav_special_price", lvl1_val)
            elif lvl2_val is not None:
                winner = ("nivel_2_min_lote_bundle", lvl2_val)
            elif lvl3_val is not None:
                # ATENÇÃO: COALESCE retorna o primeiro NÃO-NULL — soma 0+0 = 0 é NÃO-NULL,
                # então mesmo quando ambos zeram a query real retorna 0 e bloqueia o nível 4.
                # Este é potencialmente o bug do "R$ 0,00".
                winner = ("nivel_3_min_lote_evento + addon", lvl3_val)
            elif lvl4 is not None:
                winner = ("nivel_4_index_price", lvl4)
            else:
                winner = ("NENHUM — retornaria NULL", None)

            results.append({
                "bundle_entity_id": eid,
                "nome_kit": meta[0] if meta else None,
                "id_evento": id_evento,
                "status_eav": [(s[0], int(s[1])) for s in status],
                "nivel_1_eav_special_price": {
                    "todos_scopes": [(s[0], float(s[1]) if s[1] is not None else None) for s in eav_sp],
                    "valor_escolhido_pela_query": lvl1_val,
                },
                "eav_price_todos_scopes": [(s[0], float(s[1]) if s[1] is not None else None) for s in eav_price],
                "nivel_2_lotes_bundle": {
                    "todos": [{"valor": float(l[0]), "sell_ends": str(l[1]) if l[1] else None, "name": l[2]} for l in lotes_bundle],
                    "min_ativo_query": lvl2_val,
                },
                "nivel_3_lotes_evento_mais_addon": {
                    "id_evento_usado": id_evento,
                    "amostra_lotes_evento": [{"valor": float(l[0]), "sell_ends": str(l[1]) if l[1] else None, "name": l[2]} for l in lotes_evento],
                    "min_lote_evento_ativo": min_lote_evento,
                    "addon_max_componente": addon_val,
                    "soma_que_query_retornaria": lvl3_val,
                    "fallback_so_ativa_se": "lotes_bundle estiver vazio",
                },
                "nivel_4_index_price": {
                    "min_price": float(idx[0]) if idx and idx[0] is not None else None,
                    "final_price": float(idx[1]) if idx and idx[1] is not None else None,
                    "valor_usado_query": lvl4,
                },
                "VENCEDOR_DA_COALESCE": {
                    "nivel": winner[0],
                    "valor_retornado": winner[1],
                },
            })
        return {"matches": results, "total": len(results)}

    try:
        return magento_run(_work, label="kit_config:diag-special-price", profile="request")
    except Exception:
        logger.exception("diag-special-price failed")
        raise HTTPException(500, "Diagnóstico falhou — ver logs do servidor")


MAGENTO_KITS_QUERY = """
SELECT /*+ MAX_EXECUTION_TIME(60000) */
    cpev1.value                             AS id_evento,
    cpev_kit.value                          AS nome_evento,
    cpe_parent.entity_id                    AS bundle_entity_id,
    cpev_kit_name.value                     AS nome_kit,
    eaov_tipo.value                         AS tipo_categoria,

    -- price (De/strikethrough): MAX(componente Distância/Modalidade) + MAX(componente addon não-blacklisted).
    -- A primeira parcela é COALESCE para 0: em bundles cujo componente "distância"
    -- não usa a nomenclatura padrão (ex.: "BPC26SP1MB-5Km" em vez de "Distancia-5Km"),
    -- a branch "distância" retorna NULL e, sem o COALESCE, `NULL + addon` zerava todo
    -- o preço. Com COALESCE, a branch "addon" naturalmente acaba pegando o próprio
    -- componente principal (preço da inscrição) e o resultado bate com o valor base
    -- do bundle. NULLIF(...,0) garante que bundles totalmente sem preço retornem
    -- NULL em vez de 0 (mantém semântica histórica).
    NULLIF(
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
        END), 0),
        0
    )                                       AS price,

    -- lote_atual: nome do lote corrente (por bundle → fallback por evento)
    COALESCE(lote_b.lot_name, lote_e.lot_name) AS lote_atual,

    -- current_price: preço do lote corrente — usado pelo ticket_atual no ISC dashboard.
    -- MAX(record_id) garante o lote mais recente (já resolvido via joins lote_b/lote_e).
    COALESCE(lote_b.lot_value, lote_e.lot_value) AS current_price,

    -- special_price: preço promocional/entrada do kit.
    -- Fonte canônica: catalog_product_index_price.min_price do BUNDLE PAI,
    -- que já reflete as catalog price rules ativas (promoções vigentes do
    -- Magento). É o valor "de entrada" exibido na vitrine.
    -- Fallback (kit inativo): bundles inativos não entram no index do
    -- Magento, então pi_pai.min_price vem NULL. Nesse caso somamos o
    -- final_price dos componentes simples a partir do index dos filhos
    -- (pi_filho): MAX(componente Distância/Modalidade) + MAX(addon não
    -- blacklisted). Espelha a mesma decomposição usada no `price`.
    COALESCE(
        pi_pai.min_price,
        NULLIF(
            -- COALESCE na 1ª parcela (igual ao `price`): bundles cujo
            -- componente "distância" foge da nomenclatura padrão (ex.:
            -- "BPC26SP1MB-5Km") não entram nessa branch; sem o COALESCE,
            -- NULL + addon zeraria todo o special_price. NULLIF(...,0) final
            -- devolve NULL (em vez de R$ 0,00) quando o kit inativo não tem
            -- nenhum componente priceado.
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
            END), 0),
            0
        )
    )                                           AS special_price,

    -- pi_pai_min_price: valor bruto do índice do bundle pai, antes de qualquer
    -- normalização. Quando disponível, é a fonte autoritativa do preço atual
    -- (reflete catalog price rules ativas). Exposto separadamente de special_price
    -- para que a Regra B (>= price) seja aplicada APENAS ao fallback (soma de
    -- componentes), nunca ao valor do índice em si.
    pi_pai.min_price                            AS pi_pai_min_price,

    CASE cpei_status.value
        WHEN 1 THEN 'ativo'
        WHEN 2 THEN 'inativo'
    END                                     AS status_kit

FROM catalog_product_entity cpe_parent

-- Pré-computa attribute_ids de tipo_categoria e status em um único scan de eav_attribute
CROSS JOIN (
    SELECT
        MAX(CASE WHEN attribute_code = 'tipo_categoria' THEN attribute_id END) AS tipo_cat_id,
        MAX(CASE WHEN attribute_code = 'status'         THEN attribute_id END) AS status_id
    FROM eav_attribute
    WHERE attribute_code IN ('tipo_categoria', 'status')
      AND entity_type_id = (
          SELECT entity_type_id FROM eav_entity_type
          WHERE entity_type_code = 'catalog_product'
      )
) attrs

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

-- tipo_categoria: attribute_id pré-computado (sem subquery correlacionada por linha)
LEFT JOIN catalog_product_entity_int cpei_tipo
       ON cpei_tipo.entity_id    = cpe_parent.entity_id
      AND cpei_tipo.attribute_id = attrs.tipo_cat_id

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

-- Index price dos componentes simples (fallback p/ kits inativos no special_price)
LEFT JOIN catalog_product_index_price pi_filho
       ON pi_filho.entity_id = cpeos.product_id
      AND pi_filho.website_id = 1
      AND pi_filho.customer_group_id = 0

-- Index price do bundle pai: min_price já reflete catalog price rules ativas
LEFT JOIN catalog_product_index_price pi_pai
       ON pi_pai.entity_id = cpe_parent.entity_id
      AND pi_pai.website_id = 1
      AND pi_pai.customer_group_id = 0

-- Lote keyed pelo bundle entity_id (preço específico por kit; prioridade)
-- MAX(record_id) garante exatamente 1 linha por bundle; sem múltiplas rows por lot_id.
LEFT JOIN catalog_product_entity_event_lot_price lote_b
       ON lote_b.entity_id = cpe_parent.entity_id
      AND lote_b.record_id = (
              SELECT MAX(record_id)
              FROM catalog_product_entity_event_lot_price
              WHERE entity_id = cpe_parent.entity_id
          )

-- Lote keyed pelo event entity_id (fallback; padrão original)
-- MAX(record_id) garante exatamente 1 linha por evento; sem múltiplas rows por lot_id.
LEFT JOIN catalog_product_entity_event_lot_price lote_e
       ON lote_e.entity_id = cpev1.value
      AND lote_e.record_id = (
              SELECT MAX(record_id)
              FROM catalog_product_entity_event_lot_price
              WHERE entity_id = cpev1.value
          )

-- status do bundle: attribute_id pré-computado
LEFT JOIN catalog_product_entity_int cpei_status
       ON cpei_status.entity_id    = cpe_parent.entity_id
      AND cpei_status.attribute_id = attrs.status_id

WHERE cpe_parent.type_id = 'bundle'
  AND cped_date.value >= DATE_FORMAT(CURDATE(), '%Y-01-01')
  AND cped_date.value <  DATE_FORMAT(CURDATE(), '%Y-01-01') + INTERVAL 1 YEAR

GROUP BY
    cpev1.value,
    cpev_kit.value,
    cpe_parent.entity_id,
    cpev_kit_name.value,
    eaov_tipo.value,
    pi_pai.min_price

ORDER BY
    cpev1.value,
    COALESCE(lote_b.lot_value, lote_e.lot_value)
"""


# ---------------------------------------------------------------------------
# Singleflight + TTL para MAGENTO_KITS_QUERY.
# A query é a 2ª mais cara do sistema (joins múltiplos em catalog_product_*,
# 4 subqueries correlacionadas no special_price, 25+ NOT LIKE) e é disparada
# por 3 endpoints distintos (POST /kits/refresh, GET /eventos/{id}, modal
# de margem). Como NÃO tem parâmetros (varre todos os kits), uma única
# entrada em cache serve todos os chamadores. TTL=60s: estrutura de kits
# muda raramente (lotes/preços só são editados pontualmente). Singleflight
# evita 3 queries paralelas no Magento quando vários endpoints disparam ao
# mesmo tempo (ex.: detalhe de evento + modal de margem).
# Não muda lógica: cada chamador segue recebendo (rows, columns) tupla
# idêntica ao que o conn.execute() retornaria.
# ---------------------------------------------------------------------------
_MK_SF_LOCK = _threading.Lock()
# Voo em curso: dict com {"event": Event, "rows": list|None, "cols": list|None, "exc": BaseException|None}.
# Cada chamada concorrente que pega o MESMO _MK_SF_FLIGHT espera o mesmo Event e lê o resultado
# DESSE voo (não de voos antigos). Quando o voo termina, _MK_SF_FLIGHT é zerado mas o dict
# permanece acessível via referência local dos followers — assim mesmo após timeout, eles leem
# apenas o resultado do voo que aguardaram, nunca estado global stale.
_MK_SF_FLIGHT: dict | None = None
# Último resultado VÁLIDO (rows não-vazio) — só este é usado como cache hit.
# Erros NUNCA poluem o cache; ficam isolados no flight dict e só atingem participantes daquele voo.
_MK_SF_LAST_GOOD: dict = {"ts": 0.0, "rows": None, "cols": None}
_MK_SF_TTL = 60.0


def _fetch_magento_kits_cached(label: str):
    """Executa MAGENTO_KITS_QUERY com singleflight + cache TTL.

    Retorna (rows, columns) — mesmo formato que conn.execute(...).fetchall() +
    conn.execute(...).keys(). Propaga exceções APENAS aos participantes do voo
    corrente (líder + followers que esperaram seu Event). Follower que sofreu
    timeout (120s sem set()) NÃO vira leader e NÃO lê estado global stale:
    executa query direta isoladamente e loga warning. Resultados vazios NÃO
    são cacheados como válidos — falha parcial do Magento não vira "OK"
    pelos próximos 60s.
    """
    from app.core.db_retry import magento_run
    global _MK_SF_FLIGHT
    now = _time.time()
    with _MK_SF_LOCK:
        # Cache hit: somente last-good (rows não-vazio) dentro do TTL.
        if (_MK_SF_LAST_GOOD["rows"]
                and (now - _MK_SF_LAST_GOOD["ts"]) < _MK_SF_TTL):
            return _MK_SF_LAST_GOOD["rows"], _MK_SF_LAST_GOOD["cols"]
        if _MK_SF_FLIGHT is not None:
            flight = _MK_SF_FLIGHT
            leader = False
        else:
            flight = {
                "event": _threading.Event(),
                "rows": None,
                "cols": None,
                "exc": None,
            }
            _MK_SF_FLIGHT = flight
            leader = True

    if not leader:
        flight["event"].wait(timeout=120.0)
        if flight["event"].is_set():
            # Leu APENAS o resultado deste voo (referência local), nunca estado global stale.
            if flight["exc"] is not None:
                raise flight["exc"]
            return flight["rows"], flight["cols"]
        # Timeout sem set(): leader desapareceu. Cai para retry direto SEM ler flight.
        # Não vira novo leader (risco de stampede); apenas executa sua própria query.
        # Logamos para diagnóstico — é cenário raro de processo emperrado.
        logger.warning(
            "[KitConfig] singleflight follower timeout (120s) — leader não publicou; "
            "executando query direta sem cache"
        )
        # Limpeza defensiva: se o flight órfão ainda é o ativo (compare-by-identity),
        # libera para que o próximo caller possa se eleger leader normalmente em vez
        # de também esperar 120s em loop.
        with _MK_SF_LOCK:
            if _MK_SF_FLIGHT is flight:
                _MK_SF_FLIGHT = None

    rows = None
    cols = None
    exc_caught = None
    try:
        def _kits_work(conn):
            result = conn.execute(text(MAGENTO_KITS_QUERY))
            return result.fetchall(), list(result.keys())
        rows, cols = magento_run(_kits_work, label=label, profile="request")
    except BaseException as e:
        exc_caught = e
    finally:
        if leader:
            with _MK_SF_LOCK:
                flight["rows"] = rows
                flight["cols"] = cols
                flight["exc"] = exc_caught
                # Atualiza last-good APENAS com resultado não-vazio sem erro.
                # Resultado vazio (Magento respondeu mas sem linhas) é tratado como
                # falha parcial — preserva o last_good anterior em vez de promover [].
                if exc_caught is None and rows:
                    _MK_SF_LAST_GOOD["ts"] = _time.time()
                    _MK_SF_LAST_GOOD["rows"] = rows
                    _MK_SF_LAST_GOOD["cols"] = cols
                _MK_SF_FLIGHT = None
            flight["event"].set()
    if exc_caught is not None:
        raise exc_caught
    return rows, cols


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
# True quando a última execução de fetch_ativo_kits_indexed conseguiu falar com
# o engine_ssh sem exceção (independente de quantas linhas voltaram). Usado
# por _build_kit_rows_internal para decidir se a fonte Ativo deve participar
# da remoção de linhas no snapshot.
_ativo_kits_last_ok: bool = False


def fetch_ativo_kits_indexed(force_refresh: bool = False, return_status: bool = False):
    """Wrapper retrocompatível: por padrão retorna apenas o índice (dict).
    Quando ``return_status=True``, retorna ``(index, ok)`` — onde ``ok``
    reflete **estritamente esta chamada** (capturado como variável local
    pelo impl, sem ler nenhuma global compartilhada). Em concorrência
    entre threads, isso impede que outra execução de Ativo
    bem-sucedida/falha contamine o flag desta execução.
    """
    idx, ok = _fetch_ativo_kits_indexed_impl(force_refresh=force_refresh)
    if return_status:
        return idx, ok
    return idx


def _fetch_ativo_kits_indexed_impl(force_refresh: bool = False):
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
        # Cache hit: tratamos como sucesso (dados válidos disponíveis nesta
        # execução, mesmo que tenham vindo de uma chamada anterior).
        return _ativo_kits_cache["data"], True

    # As tabelas sa_evento/sa_combo/sa_modalidade* ficam no banco "0_transfer"
    # acessado via SSH tunnel (mesma conexão usada por fetch_eventos_ativo).
    # ``ok_local`` é variável da execução atual — nunca lida de global.
    global _ativo_kits_last_ok
    ok_local = False
    if db_module.engine_ssh is None:
        logger.info("[KitConfig] engine_ssh não configurado; pulando ATIVO_KITS_QUERY")
        _ativo_kits_last_ok = False
        return {}, False

    try:
        with db_module.engine_ssh.connect() as conn:
            result = conn.execute(text(ATIVO_KITS_QUERY))
            rows = result.fetchall()
            columns = list(result.keys())
        ok_local = True
    except Exception as e:
        logger.error(f"[KitConfig] Erro ao buscar kits do Ativo: {e}")
        _ativo_kits_last_ok = False
        return {}, False
    _ativo_kits_last_ok = True

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
    return indexed, ok_local


@router.get("/kits", response_model=List[KitRow])
def get_kits_with_config(
    response: Response,
    db: Session = Depends(get_db),
    force_refresh: bool = False,
    current_user=Depends(require_permission("admin_kit_config", "pode_visualizar")),
):
    """Tela /admin/kit-config.

    Caminho rápido: lê do snapshot persistido (kit_mapping_snapshot) e
    aplica overlay de KitConfig em tempo real. Caminho lento (fallback):
    quando o snapshot está vazio OU quando force_refresh=true, roda
    Magento+Ativo ao vivo. Para sincronizar diff sem segurar a request,
    prefira POST /kits/refresh.
    """
    from app.services.kit_snapshot_service import read_kit_snapshot, snapshot_is_stale

    if not force_refresh:
        snapshot_dicts = read_kit_snapshot(db)
        if snapshot_dicts is not None:
            rows = _apply_overlay_to_snapshot(db, snapshot_dicts)
            response.headers["X-Kit-Source"] = "snapshot"
            # Sinaliza ao frontend se o snapshot está velho o suficiente para
            # disparar um refresh automático em segundo plano (SWR). A leitura
            # continua instantânea — o rebuild pesado roda só quando stale.
            response.headers["X-Kit-Stale"] = "true" if snapshot_is_stale(db) else "false"
            return rows

    rows, magento_ok, ativo_ok = _build_kit_rows_internal(db, force_refresh=force_refresh)
    response.headers["X-Kit-Source"] = (
        "live" if (magento_ok or ativo_ok) else "local-fallback"
    )
    # Regra B (resposta apenas): esconde special_price/special_price_base quando >= price.
    # Exceção: quando pi_pai_min_price está disponível, é a fonte autoritativa do índice
    # do Magento e NÃO passa pelo filtro >= price (o índice reflete o preço real atual,
    # que pode ser superior ao campo `price` baseado em EAV).
    # NÃO aplicada dentro de _build_kit_rows_internal porque a mesma função alimenta
    # rebuild_kit_snapshot, que deve persistir valores raw vindos de Magento/Ativo.
    for r in rows:
        if r.pi_pai_min_price and r.pi_pai_min_price > 0:
            r.special_price = r.pi_pai_min_price
            r.special_price_base = r.pi_pai_min_price
        else:
            r.special_price = _normalize_special_price(r.price, r.special_price)
            r.special_price_base = _normalize_special_price(r.price_base, r.special_price_base)
    return rows


@router.post("/kits/refresh")
def refresh_kit_snapshot(
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("admin_kit_config", "pode_editar")),
):
    """Reconstrói o snapshot do Mapeamento de Kits e devolve o diff
    (novos / alterados / sem mudança / removidos). Linhas de uma fonte
    indisponível ficam preservadas (não somem em instabilidade temporária).
    """
    from app.services.kit_snapshot_service import rebuild_kit_snapshot
    result = rebuild_kit_snapshot(db)
    _kits_cache["data"] = None
    _kits_cache["ts"] = 0.0
    _unconfigured_cache["data"] = None
    _unconfigured_cache["ts"] = 0.0
    return result


def _apply_overlay_to_snapshot(db: Session, snapshot_dicts: list) -> List[KitRow]:
    """Converte linhas do snapshot em KitRow aplicando overlay dinâmico
    (KitConfig + CadastroKitProduto). Preserva paridade com o caminho
    legado: calcula ``custo_cadastro`` por evento+tipo_kit e usa
    ``kp.ativo_categoria`` como fallback quando não há KitConfig.

    Toda a leitura é local (Postgres) — barata, e necessária para que
    edições do usuário em KitConfig/CadastroKitProduto apareçam
    imediatamente sem esperar um novo rebuild do snapshot.
    """
    all_configs = db.query(KitConfig).all()
    config_map = {c.bundle_entity_id: c for c in all_configs}

    # Overlay context — espelha exatamente o caminho legado.
    all_sku_maps_magento = db.query(SkuMapping).filter(
        SkuMapping.fonte == 'MAGENTO',
        SkuMapping.ativo == True,
    ).all()
    externo_to_sku_mag: dict = {sm.id_externo: (sm.sku or "").upper().strip()
                                for sm in all_sku_maps_magento if sm.id_externo}
    all_sku_maps_ativo = db.query(SkuMapping).filter(
        SkuMapping.fonte == 'ATIVO',
        SkuMapping.ativo == True,
    ).all()
    externo_to_sku_ativo: dict = {sm.id_externo: (sm.sku or "").upper().strip()
                                  for sm in all_sku_maps_ativo if sm.id_externo}

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

    cadastro_kit_costs: dict = {}
    cadastro_kit_ativo_cat: dict = {}  # (cadastro_id, kit_normalizado) → ativo_categoria
    for kp in all_kit_produtos:
        kit_name = (kp.kit or "").strip()
        cost = sum(float(i.valor_unitario or 0) for i in items_by_kit.get(kp.id, []))
        cadastro_kit_costs.setdefault(kp.cadastro_id, {})[kit_name] = cost
        # também indexa por nome normalizado (paridade com path Ativo do legado).
        cadastro_kit_costs.setdefault(kp.cadastro_id, {}).setdefault(
            _normalize_kit_name(kit_name), cost
        )
        if kp.ativo_categoria:
            cadastro_kit_ativo_cat[(kp.cadastro_id, _normalize_kit_name(kit_name))] = kp.ativo_categoria

    def _custo_for(fonte: str, id_evento_raw, tipo_kit: str | None, nome_kit: str | None):
        """Custo do kit por evento. Magento usa id_externo→sku→projeto→cadastro.
        Ativo usa SkuMapping ATIVO com o mesmo encadeamento."""
        if not id_evento_raw:
            return None, None
        try:
            id_externo = int(id_evento_raw)
        except (ValueError, TypeError):
            return None, None
        sku = (externo_to_sku_mag if (fonte or "").lower() == "magento" else externo_to_sku_ativo).get(id_externo)
        if not sku:
            return None, None
        projeto_id = sku_to_projeto_id.get(sku)
        if not projeto_id:
            return None, None
        cadastro_id = projeto_to_cadastro_id.get(projeto_id)
        if not cadastro_id:
            return None, None
        costs_by_kit = cadastro_kit_costs.get(cadastro_id, {})
        kit_key_norm = _normalize_kit_name(nome_kit or "")
        # Prefere bater por tipo_kit; cai pra nome_kit normalizado (path Ativo).
        cost = None
        if tipo_kit:
            cost = costs_by_kit.get(tipo_kit) or costs_by_kit.get(_normalize_kit_name(tipo_kit))
        if cost is None and kit_key_norm:
            cost = costs_by_kit.get(kit_key_norm)
        ativo_cat = cadastro_kit_ativo_cat.get((cadastro_id, kit_key_norm))
        return (float(cost) if cost else None), ativo_cat

    rows: List[KitRow] = []
    for d in snapshot_dicts:
        beid = int(d["bundle_entity_id"])
        cfg = config_map.get(beid)
        is_configured = cfg is not None
        custo_cadastro, kp_ativo_cat = _custo_for(
            d.get("fonte") or "", d.get("id_evento"),
            cfg.tipo_kit if cfg else None, d.get("nome_kit"),
        )
        # Regra B no read do snapshot: se pi_pai_min_price disponível, é
        # fonte autoritativa do índice Magento — usa diretamente sem >= price.
        # Caso contrário, aplica normalização ao special_price raw do snapshot.
        _pi_sp = d.get("pi_pai_min_price")
        _sp_norm = (
            _pi_sp
            if (_pi_sp and float(_pi_sp) > 0)
            else _normalize_special_price(d.get("price"), d.get("special_price"))
        )
        rows.append(KitRow(
            id_evento=d.get("id_evento"),
            nome_evento=d.get("nome_evento"),
            bundle_entity_id=beid,
            nome_kit=d.get("nome_kit"),
            tipo_kit=cfg.tipo_kit if cfg else None,
            tipo_categoria=d.get("tipo_categoria"),
            lote_atual=d.get("lote_atual"),
            multiplicador_sugerido=1,
            multiplicador=cfg.multiplicador if cfg else 1,
            price_base=d.get("price"),
            special_price_base=_sp_norm,
            price=d.get("price"),
            special_price=_sp_norm,
            # Nota: snapshot armazena raw; aplica Regra B só na resposta.
            # Aqui é leitura do snapshot já persistido → normaliza no read.
            is_configured=is_configured,
            is_kit_basico=cfg.is_kit_basico if cfg else False,
            is_promo_principal=cfg.is_promo_principal if cfg else False,
            custo_cadastro=custo_cadastro,
            custo_kit=(float(cfg.custo_kit) if (cfg and cfg.custo_kit is not None) else None),
            ativo_categoria=(cfg.ativo_categoria if cfg else None) or kp_ativo_cat,
            status_kit=d.get("status_kit"),
            fonte=d.get("fonte"),
            cenario_ciclismo=cfg.cenario_ciclismo if cfg else None,
            ignorado=cfg.ignorado if cfg else False,
        ))
    return rows


def _build_kit_rows_internal(db: Session, force_refresh: bool = False,
                             local_fallback_allowed: bool = True):
    """Caminho legado (lento): consulta Magento + Ativo ao vivo e devolve
    (rows, magento_ok, ativo_ok). Usado pelo POST /kits/refresh para
    popular o snapshot e como fallback do GET /kits quando o snapshot
    ainda não existe.

    Quando ``local_fallback_allowed=False`` (caller é o rebuild do
    snapshot), uma falha do Magento devolve ([], False, ativo_ok) em vez
    do fallback local — para o snapshot NUNCA persistir linhas que não
    vieram de Magento/Ativo. As flags refletem APENAS esta execução
    (Ativo é checado via ``return_status=True`` para evitar acoplamento
    com chamadas paralelas de outros módulos como ``marketing.py``).
    """
    now = _time.time()
    if not force_refresh and _kits_cache["data"] is not None and (now - _kits_cache["ts"]) < _KITS_TTL:
        logger.info(f"[KitConfig] Returning cached kit list (age={now - _kits_cache['ts']:.0f}s)")
        return _kits_cache["data"], True, True

    magento_ok = False
    if db_module.engine_magento is None:
        if not local_fallback_allowed:
            logger.warning("[KitConfig] engine_magento indisponível — rebuild abortado (sem fallback local)")
            return [], False, False
        if _kits_cache["data"] is not None:
            logger.warning("[KitConfig] engine_magento indisponível — retornando cache stale")
            return _kits_cache["data"], False, False
        logger.warning("[KitConfig] engine_magento indisponível — retornando fallback local (sem preços)")
        fallback = _build_local_fallback_kits(db)
        return fallback, False, False

    from app.core.db_retry import MagentoEngineUnavailable

    try:
        magento_rows, columns = _fetch_magento_kits_cached(label="kit_config:list-magento")
        magento_ok = True
    except MagentoEngineUnavailable:
        if not local_fallback_allowed:
            logger.warning("[KitConfig] Magento indisponível — rebuild abortado (sem fallback local)")
            return [], False, False
        if _kits_cache["data"] is not None:
            logger.warning("[KitConfig] Magento indisponível — retornando cache stale")
            return _kits_cache["data"], False, False
        logger.warning("[KitConfig] Magento indisponível — retornando fallback local (sem preços)")
        fallback = _build_local_fallback_kits(db)
        return fallback, False, False
    except Exception as e:
        logger.error(f"Erro ao buscar kits do Magento: {e}")
        if not local_fallback_allowed:
            logger.warning("[KitConfig] Erro no Magento — rebuild abortado (sem fallback local)")
            return [], False, False
        if _kits_cache["data"] is not None:
            logger.warning("[KitConfig] Erro no Magento — retornando cache stale")
            return _kits_cache["data"], False, False
        logger.warning("[KitConfig] Erro Magento — retornando fallback local (sem preços)")
        fallback = _build_local_fallback_kits(db)
        return fallback, False, False

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
        pi_pai_min_price_raw = float(row_dict["pi_pai_min_price"]) if row_dict.get("pi_pai_min_price") is not None else None

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
            pi_pai_min_price=pi_pai_min_price_raw,
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
    ativo_kits_index, ativo_ok_local = fetch_ativo_kits_indexed(force_refresh=force_refresh, return_status=True)

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
    return kits, magento_ok, ativo_ok_local


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
            SELECT /*+ MAX_EXECUTION_TIME(45000) */
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


def _invalidate_detalhe_snapshot_for_grupos(
    db: Session,
    grupos: list[str],
) -> int:
    """Apaga DetalheEventosSnapshot persistido e invalida cache em memória do Detalhamento.

    O endpoint de Detalhamento serve do snapshot PostgreSQL como fast path.
    Sem esta invalidação, uma renomeação de tipo_kit em KitConfig continuaria
    exibindo o nome antigo até o snapshot expirar (26 h).
    """
    from ...models.vendas_snapshot import DetalheEventosSnapshot
    from ...services.detalhe_eventos_service import invalidate_cache as _invalidate_detalhe_cache

    if not grupos:
        return 0

    total = 0
    try:
        for grupo in grupos:
            deleted = (
                db.query(DetalheEventosSnapshot)
                .filter(DetalheEventosSnapshot.evento_grupo == grupo)
                .delete(synchronize_session=False)
            )
            total += deleted or 0
        if total:
            db.commit()
            logger.info(
                f"[KitConfig] DetalheEventosSnapshot removido para {grupos} ({total} linha(s))"
            )
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning(f"[KitConfig] Falha ao apagar DetalheEventosSnapshot: {e}")

    for grupo in grupos:
        try:
            _invalidate_detalhe_cache(grupo)
        except Exception as e:
            logger.warning(f"[KitConfig] Falha ao invalidar detalhe_cache para '{grupo}': {e}")

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
    4. Apaga DetalheEventosSnapshot persistido e invalida cache em memória do Detalhamento.
    5. Fallback por DimProjeto quando id_evento bate com um projeto (cobre
       eventos standalone numéricos).
    6. Último recurso: invalidação total do cache em memória (snapshots
       persistidos são deixados intactos para o scheduler atualizar; evita
       apagar tudo por uma operação isolada).

    Retorna True quando a invalidação direcionada (passos 1–4 ou 5) ocorreu.
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
        grupos_uniq = list({g for g, _ in grupo_anos})
        _invalidate_detalhe_snapshot_for_grupos(db, grupos_uniq)
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

    from ...services.detalhe_eventos_service import invalidate_cache as _invalidate_detalhe_cache
    event_detail_cache.invalidate()
    _invalidate_detalhe_cache()
    logger.info(
        f"[KitConfig] Full event_detail invalidation for bundle {bundle_entity_id} (no SKU mapping found)"
    )
    return False


def _prewarm_ticket_cache_background():
    """Reconstrói o cache do ticket_atual em background após um Salvar.

    Abre uma sessão PG própria (não reutiliza a do request), chama
    _get_ticket_atual_map e fecha. Dessa forma, quando o usuário navegar
    para o evento segundos após salvar, o cache já está quente.
    """
    from .marketing import _get_ticket_atual_map

    def _work():
        if db_module.SessionLocal is None:
            return
        db = db_module.SessionLocal()
        try:
            _get_ticket_atual_map(db)
            logger.info("[KitConfig] Pre-warm ticket_atual cache concluído em background")
        except Exception as e:
            logger.warning(f"[KitConfig] Pre-warm ticket_atual cache falhou: {e}")
        finally:
            db.close()

    t = _threading.Thread(target=_work, daemon=True, name="ticket-prewarm")
    t.start()


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
        from ...services.detalhe_eventos_service import invalidate_cache as _invalidate_detalhe_cache
        event_detail_cache.invalidate()
        _invalidate_detalhe_cache()
        logger.info(f"[KitConfig] Bulk save: full event_detail invalidation ({len(bundle_ids)} bundles, some had no SKU mapping)")
    else:
        for key in invalidated_keys:
            event_detail_cache.invalidate(key)
        logger.info(f"[KitConfig] Bulk save: targeted invalidation of {len(invalidated_keys)} keys")

    if affected_grupo_anos:
        _invalidate_persisted_snapshot_for_grupos(db, sorted(affected_grupo_anos))
        grupos_uniq = list({g for g, _ in affected_grupo_anos})
        _invalidate_detalhe_snapshot_for_grupos(db, grupos_uniq)

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

    # Auto-populate kit_nome from KitMappingSnapshot when not provided by the caller.
    # kit_nome is the raw Magento bundle name used as lookup key in detalhe_eventos_service.
    resolved_kit_nome = body.kit_nome
    if not resolved_kit_nome:
        from app.models.kit_mapping_snapshot import KitMappingSnapshot as _KMS
        snap_row = db.query(_KMS.nome_kit).filter(
            _KMS.bundle_entity_id == bundle_entity_id,
            _KMS.nome_kit.isnot(None),
        ).first()
        if snap_row:
            resolved_kit_nome = snap_row.nome_kit

    try:
        if existing:
            existing.multiplicador = body.multiplicador
            existing.is_kit_basico = body.is_kit_basico
            existing.is_promo_principal = body.is_promo_principal
            if body.id_evento is not None:
                existing.id_evento = body.id_evento
            existing.tipo_kit = body.tipo_kit
            if resolved_kit_nome is not None:
                existing.kit_nome = resolved_kit_nome
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
            _prewarm_ticket_cache_background()
            _invalidate_event_detail_for_bundle(db, bundle_entity_id, body.id_evento)
            return existing

        new_config = KitConfig(
            bundle_entity_id=bundle_entity_id,
            multiplicador=body.multiplicador,
            is_kit_basico=body.is_kit_basico,
            is_promo_principal=body.is_promo_principal,
            id_evento=body.id_evento,
            kit_nome=body.kit_nome,
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
        _prewarm_ticket_cache_background()
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


@router.get("/by-grupo", response_model=List[KitConfigResponse])
def get_kit_configs_by_grupo(
    grupo_nome: str,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("admin_kit_config", "pode_visualizar")),
):
    nome = grupo_nome.strip()

    sku_maps = db.query(SkuMapping).filter(
        SkuMapping.fonte == 'MAGENTO',
        SkuMapping.ativo == True,
        SkuMapping.evento_grupo.ilike(nome),
        SkuMapping.id_externo.isnot(None),
    ).all()

    mev_ids = list({sm.id_externo for sm in sku_maps if sm.id_externo is not None})

    if not mev_ids:
        return []

    configs = (
        db.query(KitConfig)
        .filter(
            KitConfig.id_evento.in_(mev_ids),
            KitConfig.ignorado == False,
        )
        .order_by(
            KitConfig.is_promo_principal.desc(),
            KitConfig.is_kit_basico.desc(),
            KitConfig.kit_nome,
        )
        .all()
    )

    # Enrich with actual Magento price (catalog_product_index_price.min_price).
    # Primary: query leve ao Magento — min_price reflete o preço real atual do bundle.
    # Fallback: receita/qtd do MargemBundleRevSnapshot (média histórica) se Magento indisponível.
    bundle_ids = [cfg.bundle_entity_id for cfg in configs if cfg.bundle_entity_id is not None]
    snap_prices: dict = {}
    if bundle_ids:
        magento_price_ok = False
        if db_module.engine_magento is not None:
            try:
                from app.core.db_retry import magento_run as _magento_run
                ids_csv = ",".join(str(b) for b in bundle_ids)
                _price_sql = f"""
                    SELECT /*+ MAX_EXECUTION_TIME(15000) */
                           entity_id,
                           COALESCE(min_price, price) AS sp_base
                    FROM   catalog_product_index_price
                    WHERE  entity_id IN ({ids_csv})
                      AND  customer_group_id = 0
                      AND  website_id = 1
                """
                def _price_work(conn):
                    r = conn.execute(text(_price_sql))
                    return r.fetchall(), list(r.keys())
                p_rows, p_cols = _magento_run(_price_work, label="by-grupo:prices", profile="request")
                for row in p_rows:
                    d = dict(zip(p_cols, row))
                    sp = d.get("sp_base")
                    if sp is not None and float(sp) > 0:
                        snap_prices[int(d["entity_id"])] = round(float(sp), 2)
                magento_price_ok = True
            except Exception as e:
                logger.warning(f"[by-grupo] Preço Magento indisponível, usando fallback snapshot: {e}")

        if not magento_price_ok:
            try:
                from ...models.vendas_snapshot import MargemBundleRevSnapshot as _MBRS
                snap_rows = db.query(_MBRS).filter(_MBRS.bundle_entity_id.in_(bundle_ids)).all()
                for sr in snap_rows:
                    if sr.qtd_inscricoes and int(sr.qtd_inscricoes) > 0 and sr.receita_liquida:
                        snap_prices[sr.bundle_entity_id] = round(
                            float(sr.receita_liquida) / int(sr.qtd_inscricoes), 2
                        )
            except Exception as e:
                logger.warning(f"[by-grupo] Fallback snapshot também falhou: {e}")

    result = []
    for cfg in configs:
        resp = KitConfigResponse.model_validate(cfg)
        resp.sp_snapshot = snap_prices.get(cfg.bundle_entity_id)
        result.append(resp)
    return result
