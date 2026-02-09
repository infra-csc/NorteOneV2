from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ...core.database import get_db
from ...core.security import get_current_user, require_roles
from ...models.dimensoes import DimCentroCusto
from ...models.user import Usuario
from ...schemas.dimensoes import CentroCustoCreate, CentroCustoUpdate, CentroCustoResponse

router = APIRouter(prefix="/centros-custo", tags=["Centros de Custo"])

@router.get("/", response_model=List[CentroCustoResponse])
def list_centros_custo(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    centros = db.query(DimCentroCusto).filter(DimCentroCusto.ativo == True).offset(skip).limit(limit).all()
    return centros

@router.post("/", response_model=CentroCustoResponse)
def create_centro_custo(
    centro: CentroCustoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN", "ANALISTA"]))
):
    existing = db.query(DimCentroCusto).filter(DimCentroCusto.codigo == centro.codigo).first()
    if existing:
        raise HTTPException(status_code=400, detail="Código já existe")
    
    db_centro = DimCentroCusto(**centro.model_dump())
    db.add(db_centro)
    db.commit()
    db.refresh(db_centro)
    return db_centro

@router.get("/{centro_id}", response_model=CentroCustoResponse)
def get_centro_custo(
    centro_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    centro = db.query(DimCentroCusto).filter(DimCentroCusto.id == centro_id).first()
    if not centro:
        raise HTTPException(status_code=404, detail="Centro de custo não encontrado")
    return centro

@router.put("/{centro_id}", response_model=CentroCustoResponse)
def update_centro_custo(
    centro_id: int,
    centro_update: CentroCustoUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN", "ANALISTA"]))
):
    centro = db.query(DimCentroCusto).filter(DimCentroCusto.id == centro_id).first()
    if not centro:
        raise HTTPException(status_code=404, detail="Centro de custo não encontrado")
    
    for field, value in centro_update.model_dump(exclude_unset=True).items():
        setattr(centro, field, value)
    
    db.commit()
    db.refresh(centro)
    return centro

@router.delete("/{centro_id}")
def delete_centro_custo(
    centro_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN"]))
):
    centro = db.query(DimCentroCusto).filter(DimCentroCusto.id == centro_id).first()
    if not centro:
        raise HTTPException(status_code=404, detail="Centro de custo não encontrado")
    
    centro.ativo = False
    db.commit()
    return {"message": "Centro de custo desativado"}
