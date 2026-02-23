from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
from ...core.database import get_db
from ...core.security import get_current_user, require_admin
from ...models.cadastro_evento import DistanciaOpcao
from ...models.user import Usuario

router = APIRouter(prefix="/distancias", tags=["Distâncias"])


class DistanciaResponse(BaseModel):
    id: int
    nome: str
    ativo: bool
    ordem: int

    class Config:
        from_attributes = True


class DistanciaCreate(BaseModel):
    nome: str


@router.get("/", response_model=List[DistanciaResponse])
def list_distancias(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    return db.query(DistanciaOpcao).filter(
        DistanciaOpcao.ativo == True
    ).order_by(DistanciaOpcao.ordem, DistanciaOpcao.nome).all()


@router.post("/", response_model=DistanciaResponse, status_code=201)
def create_distancia(
    data: DistanciaCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin())
):
    nome = data.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")

    existing = db.query(DistanciaOpcao).filter(DistanciaOpcao.nome == nome).first()
    if existing:
        if not existing.ativo:
            existing.ativo = True
            db.commit()
            db.refresh(existing)
            return existing
        raise HTTPException(status_code=400, detail="Distância já existe")

    max_ordem = db.query(DistanciaOpcao).count()
    distancia = DistanciaOpcao(nome=nome, ordem=max_ordem)
    db.add(distancia)
    db.commit()
    db.refresh(distancia)
    return distancia


@router.delete("/{distancia_id}")
def delete_distancia(
    distancia_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin())
):
    distancia = db.query(DistanciaOpcao).filter(DistanciaOpcao.id == distancia_id).first()
    if not distancia:
        raise HTTPException(status_code=404, detail="Distância não encontrada")
    distancia.ativo = False
    db.commit()
    return {"message": "Distância removida com sucesso"}
