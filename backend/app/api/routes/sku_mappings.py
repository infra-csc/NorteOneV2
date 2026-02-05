from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from pydantic import BaseModel
from app.core.database import get_db
from app.models.dimensoes import SkuMapping
from app.schemas.dimensoes import SkuMappingCreate, SkuMappingUpdate, SkuMappingResponse
from app.core.security import get_current_user
from app.models.user import Usuario
import app.core.database as db_module
from concurrent.futures import ThreadPoolExecutor
import asyncio
from functools import partial
import logging
import re

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/sku-mappings", tags=["SKU Mappings"])


class EventoExterno(BaseModel):
    id_evento: str
    nome_evento: str
    sku_original: Optional[str] = None
    data_evento: Optional[str] = None
    fonte: str
    ano: int


class EventoSugerido(BaseModel):
    id_evento: str
    nome_evento: str
    sku_original: Optional[str] = None
    data_evento: Optional[str] = None
    fonte: str
    ano: int
    sku_sugerido: Optional[str] = None
    evento_grupo_sugerido: Optional[str] = None
    match_origem: Optional[str] = None  # "nome" ou "sku"


class DescobertaEventosResponse(BaseModel):
    status: str
    ano: int
    total_ativo: int
    total_magento: int
    eventos_sugeridos: List[EventoSugerido]
    eventos_sem_match: List[EventoExterno]


def normalize_nome_evento(nome: str) -> str:
    """Normaliza o nome do evento para matching."""
    if not nome:
        return ""
    nome = nome.lower().strip()
    nome = re.sub(r'\s+', ' ', nome)
    nome = re.sub(r'20\d{2}', '', nome)
    nome = re.sub(r'\d+[ªº°]?\s*etapa', '', nome)
    nome = re.sub(r'etapa\s*\d+', '', nome)
    nome = nome.strip()
    return nome


def normalize_sku_for_match(sku: str) -> str:
    """Normaliza SKU removendo o ano para matching cross-year."""
    if not sku or len(sku) < 5:
        return ""
    base = sku[:3] + sku[5:] if len(sku) >= 6 else sku
    return base.upper()


def fetch_eventos_ativo(ano: int) -> List[Dict]:
    """Busca eventos distintos do Ativo para um ano."""
    query = f"""
    SELECT DISTINCT
        b.id_evento,
        b.ds_evento AS nome_evento,
        b.id_campanha_salesforce AS sku,
        DATE(b.dt_evento) AS data_evento
    FROM sa_evento AS b
    INNER JOIN sa_pedido_evento AS a ON b.id_evento = a.id_evento
    INNER JOIN sa_pedido AS c ON c.id_pedido = a.id_pedido
    WHERE 
        YEAR(b.dt_evento) = {ano}
        AND c.id_pedido_status = 2
    ORDER BY b.dt_evento
    """
    
    try:
        with db_module.mysql_ativo_engine.connect() as connection:
            result = connection.execute(db_module.text(query))
            rows = result.fetchall()
            return [
                {
                    "id_evento": str(row[0]),
                    "nome_evento": row[1] or "",
                    "sku_original": row[2] or "",
                    "data_evento": str(row[3]) if row[3] else None
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(f"Erro ao buscar eventos Ativo: {e}")
        return []


def fetch_eventos_magento(ano: int) -> List[Dict]:
    """Busca eventos distintos do Magento para um ano."""
    query = f"""
    SELECT DISTINCT
        wl.location_id AS id_evento,
        wl.location_name AS nome_evento,
        COALESCE(cpev.value, cpe.sku) AS sku,
        DATE(wl.final_date) AS data_evento
    FROM core_db.walmart_location AS wl
    LEFT JOIN catalog_product_entity AS cpe ON cpe.entity_id = wl.product_id
    LEFT JOIN catalog_product_entity_varchar AS cpev 
        ON cpev.entity_id = cpe.entity_id AND cpev.attribute_id = 97
    WHERE 
        wl.enabled = 1
        AND YEAR(wl.final_date) = {ano}
    ORDER BY wl.final_date
    """
    
    try:
        tunnel = db_module.create_magento_ssh_tunnel()
        if not tunnel:
            logger.error("Não foi possível criar túnel SSH para Magento")
            return []
        
        try:
            tunnel.start()
            local_port = tunnel.local_bind_port
            
            import mysql.connector
            conn = mysql.connector.connect(
                host='127.0.0.1',
                port=local_port,
                user=db_module.MAGENTO_CONFIG['user'],
                password=db_module.MAGENTO_CONFIG['password'],
                database=db_module.MAGENTO_CONFIG['database']
            )
            
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            
            eventos = [
                {
                    "id_evento": str(row[0]),
                    "nome_evento": row[1] or "",
                    "sku_original": row[2] or "",
                    "data_evento": str(row[3]) if row[3] else None
                }
                for row in rows
            ]
            
            cursor.close()
            conn.close()
            return eventos
            
        finally:
            tunnel.stop()
            
    except Exception as e:
        logger.error(f"Erro ao buscar eventos Magento: {e}")
        return []


@router.get("", response_model=List[SkuMappingResponse])
async def list_sku_mappings(
    fonte: Optional[str] = None,
    ano: Optional[int] = None,
    evento_grupo: Optional[str] = None,
    ativo: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    query = db.query(SkuMapping)
    
    if fonte:
        query = query.filter(SkuMapping.fonte == fonte)
    if ano:
        query = query.filter(SkuMapping.ano == ano)
    if evento_grupo:
        query = query.filter(SkuMapping.evento_grupo.ilike(f"%{evento_grupo}%"))
    if ativo is not None:
        query = query.filter(SkuMapping.ativo == ativo)
    
    return query.order_by(SkuMapping.evento_grupo, SkuMapping.ano.desc(), SkuMapping.fonte).all()


@router.get("/grupos", response_model=List[str])
async def list_evento_grupos(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    result = db.query(SkuMapping.evento_grupo).distinct().order_by(SkuMapping.evento_grupo).all()
    return [r[0] for r in result]


@router.get("/anos", response_model=List[int])
async def list_anos(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    result = db.query(SkuMapping.ano).distinct().order_by(SkuMapping.ano.desc()).all()
    return [r[0] for r in result]


@router.get("/{mapping_id}", response_model=SkuMappingResponse)
async def get_sku_mapping(
    mapping_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    mapping = db.query(SkuMapping).filter(SkuMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapeamento não encontrado")
    return mapping


@router.post("", response_model=SkuMappingResponse)
async def create_sku_mapping(
    mapping: SkuMappingCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    existing = db.query(SkuMapping).filter(
        SkuMapping.fonte == mapping.fonte,
        SkuMapping.id_externo == mapping.id_externo,
        SkuMapping.ano == mapping.ano
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Já existe um mapeamento para {mapping.fonte} ID {mapping.id_externo} no ano {mapping.ano}"
        )
    
    db_mapping = SkuMapping(**mapping.model_dump())
    db.add(db_mapping)
    db.commit()
    db.refresh(db_mapping)
    return db_mapping


@router.put("/{mapping_id}", response_model=SkuMappingResponse)
async def update_sku_mapping(
    mapping_id: int,
    mapping: SkuMappingUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    db_mapping = db.query(SkuMapping).filter(SkuMapping.id == mapping_id).first()
    if not db_mapping:
        raise HTTPException(status_code=404, detail="Mapeamento não encontrado")
    
    update_data = mapping.model_dump(exclude_unset=True)
    
    if update_data:
        new_fonte = update_data.get('fonte', db_mapping.fonte)
        new_id_externo = update_data.get('id_externo', db_mapping.id_externo)
        new_ano = update_data.get('ano', db_mapping.ano)
        
        existing = db.query(SkuMapping).filter(
            SkuMapping.fonte == new_fonte,
            SkuMapping.id_externo == new_id_externo,
            SkuMapping.ano == new_ano,
            SkuMapping.id != mapping_id
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Já existe um mapeamento para {new_fonte} ID {new_id_externo} no ano {new_ano}"
            )
    
    for key, value in update_data.items():
        setattr(db_mapping, key, value)
    
    db.commit()
    db.refresh(db_mapping)
    return db_mapping


@router.delete("/{mapping_id}")
async def delete_sku_mapping(
    mapping_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    db_mapping = db.query(SkuMapping).filter(SkuMapping.id == mapping_id).first()
    if not db_mapping:
        raise HTTPException(status_code=404, detail="Mapeamento não encontrado")
    
    db.delete(db_mapping)
    db.commit()
    return {"message": "Mapeamento excluído com sucesso"}


@router.post("/bulk", response_model=List[SkuMappingResponse])
async def bulk_create_sku_mappings(
    mappings: List[SkuMappingCreate],
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    created = []
    for mapping in mappings:
        existing = db.query(SkuMapping).filter(
            SkuMapping.fonte == mapping.fonte,
            SkuMapping.id_externo == mapping.id_externo,
            SkuMapping.ano == mapping.ano
        ).first()
        
        if not existing:
            db_mapping = SkuMapping(**mapping.model_dump())
            db.add(db_mapping)
            created.append(db_mapping)
    
    db.commit()
    for m in created:
        db.refresh(m)
    
    return created


@router.get("/descobrir-eventos", response_model=DescobertaEventosResponse)
async def descobrir_eventos_externos(
    ano: int = Query(2025, description="Ano dos eventos a descobrir"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Descobre eventos de um ano específico nos bancos externos (Ativo e Magento)
    e sugere mapeamentos baseados nos eventos de 2026 já cadastrados.
    """
    executor = ThreadPoolExecutor(max_workers=2)
    loop = asyncio.get_event_loop()
    
    ativo_future = loop.run_in_executor(executor, partial(fetch_eventos_ativo, ano))
    magento_future = loop.run_in_executor(executor, partial(fetch_eventos_magento, ano))
    
    try:
        results = await asyncio.wait_for(
            asyncio.gather(ativo_future, magento_future, return_exceptions=True),
            timeout=120.0
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Timeout ao buscar eventos externos")
    
    eventos_ativo = results[0] if not isinstance(results[0], Exception) else []
    eventos_magento = results[1] if not isinstance(results[1], Exception) else []
    
    mapeamentos_2026 = db.query(SkuMapping).filter(
        SkuMapping.ano == 2026,
        SkuMapping.ativo == True
    ).all()
    
    mapeamentos_existentes = db.query(SkuMapping).filter(
        SkuMapping.ano == ano,
        SkuMapping.ativo == True
    ).all()
    
    ids_ja_mapeados = {
        (m.fonte, str(m.id_externo)) for m in mapeamentos_existentes
    }
    
    nome_to_mapping = {}
    sku_base_to_mapping = {}
    
    for m in mapeamentos_2026:
        nome_norm = normalize_nome_evento(m.nome_evento)
        if nome_norm:
            nome_to_mapping[nome_norm] = m
        
        sku_base = normalize_sku_for_match(m.sku)
        if sku_base:
            sku_base_to_mapping[sku_base] = m
    
    eventos_sugeridos = []
    eventos_sem_match = []
    
    def processar_eventos(eventos: List[Dict], fonte: str):
        for ev in eventos:
            if (fonte, ev["id_evento"]) in ids_ja_mapeados:
                continue
            
            match_encontrado = None
            match_origem = None
            
            nome_norm = normalize_nome_evento(ev["nome_evento"])
            if nome_norm and nome_norm in nome_to_mapping:
                match_encontrado = nome_to_mapping[nome_norm]
                match_origem = "nome"
            
            if not match_encontrado:
                sku_base = normalize_sku_for_match(ev.get("sku_original") or "")
                if sku_base and sku_base in sku_base_to_mapping:
                    match_encontrado = sku_base_to_mapping[sku_base]
                    match_origem = "sku"
            
            if match_encontrado:
                sku_sugerido = match_encontrado.sku[:3] + str(ano)[-2:] + match_encontrado.sku[5:]
                
                eventos_sugeridos.append(EventoSugerido(
                    id_evento=ev["id_evento"],
                    nome_evento=ev["nome_evento"],
                    sku_original=ev.get("sku_original"),
                    data_evento=ev.get("data_evento"),
                    fonte=fonte,
                    ano=ano,
                    sku_sugerido=sku_sugerido,
                    evento_grupo_sugerido=match_encontrado.evento_grupo,
                    match_origem=match_origem
                ))
            else:
                eventos_sem_match.append(EventoExterno(
                    id_evento=ev["id_evento"],
                    nome_evento=ev["nome_evento"],
                    sku_original=ev.get("sku_original"),
                    data_evento=ev.get("data_evento"),
                    fonte=fonte,
                    ano=ano
                ))
    
    processar_eventos(eventos_ativo, "ATIVO")
    processar_eventos(eventos_magento, "MAGENTO")
    
    return DescobertaEventosResponse(
        status="success",
        ano=ano,
        total_ativo=len(eventos_ativo),
        total_magento=len(eventos_magento),
        eventos_sugeridos=eventos_sugeridos,
        eventos_sem_match=eventos_sem_match
    )
