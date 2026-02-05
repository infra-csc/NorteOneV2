from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.models.dimensoes import SkuMapping
from app.schemas.dimensoes import SkuMappingCreate, SkuMappingUpdate, SkuMappingResponse
from app.core.security import get_current_user
from app.models.user import Usuario

router = APIRouter(prefix="/api/admin/sku-mappings", tags=["SKU Mappings"])


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
