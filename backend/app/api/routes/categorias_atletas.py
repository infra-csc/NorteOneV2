from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import threading
import time as _time
from ...core.database import get_db
from ...core.security import get_current_user, require_permission
from ...models.dimensoes import DimCategoriaAtleta
from ...models.user import Usuario
from ...schemas.dimensoes import CategoriaAtletaCreate, CategoriaAtletaUpdate, CategoriaAtletaResponse

router = APIRouter(prefix="/categorias-atletas", tags=["Categorias de Atletas"])
_CATEGORIAS_CACHE_TTL = 300
_categorias_cache: dict = {}
_categorias_cache_lock = threading.Lock()


def _invalidate_categorias_cache():
    with _categorias_cache_lock:
        _categorias_cache.clear()

@router.get("/", response_model=List[CategoriaAtletaResponse])
def list_categorias(
    skip: int = 0,
    limit: int = 100,
    modalidade: str = None,
    genero: str = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("categorias_atletas", "pode_visualizar"))
):
    now = _time.time()
    cache_key = (skip, limit, modalidade or "", genero or "")
    with _categorias_cache_lock:
        cached = _categorias_cache.get(cache_key)
        if cached and (now - cached["ts"]) < _CATEGORIAS_CACHE_TTL:
            return cached["data"]
    query = db.query(DimCategoriaAtleta).filter(DimCategoriaAtleta.ativo == True)
    if modalidade:
        query = query.filter(DimCategoriaAtleta.modalidade == modalidade)
    if genero:
        query = query.filter(DimCategoriaAtleta.genero == genero)
    categorias = query.offset(skip).limit(limit).all()
    with _categorias_cache_lock:
        _categorias_cache[cache_key] = {"data": categorias, "ts": now}
    return categorias

@router.post("/", response_model=CategoriaAtletaResponse)
def create_categoria(
    categoria: CategoriaAtletaCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("categorias_atletas", "pode_criar"))
):
    existing = db.query(DimCategoriaAtleta).filter(DimCategoriaAtleta.codigo == categoria.codigo).first()
    if existing:
        raise HTTPException(status_code=400, detail="Código já existe")
    
    db_categoria = DimCategoriaAtleta(**categoria.model_dump())
    db.add(db_categoria)
    db.commit()
    db.refresh(db_categoria)
    _invalidate_categorias_cache()
    return db_categoria

@router.get("/{categoria_id}", response_model=CategoriaAtletaResponse)
def get_categoria(
    categoria_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("categorias_atletas", "pode_visualizar"))
):
    categoria = db.query(DimCategoriaAtleta).filter(DimCategoriaAtleta.id == categoria_id).first()
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    return categoria

@router.put("/{categoria_id}", response_model=CategoriaAtletaResponse)
def update_categoria(
    categoria_id: int,
    categoria_update: CategoriaAtletaUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("categorias_atletas", "pode_editar"))
):
    categoria = db.query(DimCategoriaAtleta).filter(DimCategoriaAtleta.id == categoria_id).first()
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    
    for field, value in categoria_update.model_dump(exclude_unset=True).items():
        setattr(categoria, field, value)
    
    db.commit()
    db.refresh(categoria)
    _invalidate_categorias_cache()
    return categoria

@router.delete("/{categoria_id}")
def delete_categoria(
    categoria_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("categorias_atletas", "pode_deletar"))
):
    categoria = db.query(DimCategoriaAtleta).filter(DimCategoriaAtleta.id == categoria_id).first()
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    
    categoria.ativo = False
    db.commit()
    _invalidate_categorias_cache()
    return {"message": "Categoria desativada"}
