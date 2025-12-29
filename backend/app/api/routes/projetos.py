from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ...core.database import get_db
from ...core.security import get_current_user, require_roles
from ...models.dimensoes import DimProjeto
from ...models.user import Usuario
from ...schemas.dimensoes import ProjetoCreate, ProjetoUpdate, ProjetoResponse

router = APIRouter(prefix="/projetos", tags=["Projetos/Eventos"])

@router.get("/", response_model=List[ProjetoResponse])
async def list_projetos(
    skip: int = 0,
    limit: int = 100,
    status: str = None,
    modalidade: str = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    query = db.query(DimProjeto)
    if status:
        query = query.filter(DimProjeto.status == status)
    if modalidade:
        query = query.filter(DimProjeto.modalidade == modalidade)
    projetos = query.offset(skip).limit(limit).all()
    return projetos

@router.post("/", response_model=ProjetoResponse)
async def create_projeto(
    projeto: ProjetoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN", "ANALISTA", "GESTOR"]))
):
    existing = db.query(DimProjeto).filter(DimProjeto.codigo == projeto.codigo).first()
    if existing:
        raise HTTPException(status_code=400, detail="Código já existe")
    
    db_projeto = DimProjeto(**projeto.model_dump())
    db.add(db_projeto)
    db.commit()
    db.refresh(db_projeto)
    return db_projeto

@router.get("/{projeto_id}", response_model=ProjetoResponse)
async def get_projeto(
    projeto_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    projeto = db.query(DimProjeto).filter(DimProjeto.id == projeto_id).first()
    if not projeto:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    return projeto

@router.put("/{projeto_id}", response_model=ProjetoResponse)
async def update_projeto(
    projeto_id: int,
    projeto_update: ProjetoUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN", "ANALISTA", "GESTOR"]))
):
    projeto = db.query(DimProjeto).filter(DimProjeto.id == projeto_id).first()
    if not projeto:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    
    for field, value in projeto_update.model_dump(exclude_unset=True).items():
        setattr(projeto, field, value)
    
    db.commit()
    db.refresh(projeto)
    return projeto

@router.delete("/{projeto_id}")
async def delete_projeto(
    projeto_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN"]))
):
    projeto = db.query(DimProjeto).filter(DimProjeto.id == projeto_id).first()
    if not projeto:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    
    projeto.status = "CANCELADO"
    db.commit()
    return {"message": "Projeto cancelado"}
