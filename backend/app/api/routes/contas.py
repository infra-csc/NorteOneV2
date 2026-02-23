from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ...core.database import get_db
from ...core.security import get_current_user, require_permission
from ...models.dimensoes import DimConta
from ...models.user import Usuario
from ...schemas.dimensoes import ContaCreate, ContaUpdate, ContaResponse

router = APIRouter(prefix="/contas", tags=["Contas Contábeis"])

@router.get("/", response_model=List[ContaResponse])
def list_contas(
    skip: int = 0,
    limit: int = 100,
    tipo: str = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    query = db.query(DimConta).filter(DimConta.ativo == True)
    if tipo:
        query = query.filter(DimConta.tipo == tipo)
    contas = query.offset(skip).limit(limit).all()
    return contas

@router.post("/", response_model=ContaResponse)
def create_conta(
    conta: ContaCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_contas", "pode_criar"))
):
    existing = db.query(DimConta).filter(DimConta.codigo == conta.codigo).first()
    if existing:
        raise HTTPException(status_code=400, detail="Código já existe")
    
    db_conta = DimConta(**conta.model_dump())
    db.add(db_conta)
    db.commit()
    db.refresh(db_conta)
    return db_conta

@router.get("/{conta_id}", response_model=ContaResponse)
def get_conta(
    conta_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    conta = db.query(DimConta).filter(DimConta.id == conta_id).first()
    if not conta:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    return conta

@router.put("/{conta_id}", response_model=ContaResponse)
def update_conta(
    conta_id: int,
    conta_update: ContaUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_contas", "pode_editar"))
):
    conta = db.query(DimConta).filter(DimConta.id == conta_id).first()
    if not conta:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    
    for field, value in conta_update.model_dump(exclude_unset=True).items():
        setattr(conta, field, value)
    
    db.commit()
    db.refresh(conta)
    return conta

@router.delete("/{conta_id}")
def delete_conta(
    conta_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("admin_contas", "pode_deletar"))
):
    conta = db.query(DimConta).filter(DimConta.id == conta_id).first()
    if not conta:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    
    conta.ativo = False
    db.commit()
    return {"message": "Conta desativada"}
