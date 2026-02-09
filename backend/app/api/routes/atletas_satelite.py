from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from ...core.database import get_db
from ...core.security import get_current_user, require_roles
from ...models.fatos import FatoAtletasMetricas, FatoAtletasCanais, FatoAtletasKits, FatoAtletasCustos
from ...models.dimensoes import DimProjeto
from ...models.user import Usuario
from ...schemas.fatos import (
    AtletasMetricasCreate, AtletasMetricasUpdate, AtletasMetricasResponse,
    AtletasCanaisCreate, AtletasCanaisUpdate, AtletasCanaisResponse,
    AtletasKitsCreate, AtletasKitsUpdate, AtletasKitsResponse,
    AtletasCustosCreate, AtletasCustosUpdate, AtletasCustosResponse
)

router = APIRouter(prefix="/atletas-satelite", tags=["Atletas Satélite"])


# === METRICAS (principal) ===
@router.get("/metricas/", response_model=List[AtletasMetricasResponse])
def list_metricas(
    projeto_id: Optional[int] = Query(None, description="Filtrar por projeto"),
    cenario: Optional[str] = Query(None, description="Filtrar por cenário: ORCADO, PROJETADO, REALIZADO"),
    categoria_atleta_id: Optional[int] = Query(None, description="Filtrar por categoria de atleta"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    query = db.query(FatoAtletasMetricas)
    
    if projeto_id:
        query = query.filter(FatoAtletasMetricas.projeto_id == projeto_id)
    if cenario:
        query = query.filter(FatoAtletasMetricas.cenario == cenario)
    if categoria_atleta_id:
        query = query.filter(FatoAtletasMetricas.categoria_atleta_id == categoria_atleta_id)
    
    return query.all()


@router.post("/metricas/", response_model=AtletasMetricasResponse)
def create_metrica(
    data: AtletasMetricasCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN", "ANALISTA", "GESTOR"]))
):
    projeto = db.query(DimProjeto).filter(DimProjeto.id == data.projeto_id).first()
    if not projeto:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    
    db_item = FatoAtletasMetricas(**data.model_dump(), created_by=current_user.id)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


@router.put("/metricas/{item_id}", response_model=AtletasMetricasResponse)
def update_metrica(
    item_id: int,
    data: AtletasMetricasUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN", "ANALISTA", "GESTOR"]))
):
    item = db.query(FatoAtletasMetricas).filter(FatoAtletasMetricas.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    
    db.commit()
    db.refresh(item)
    return item


@router.delete("/metricas/{item_id}")
def delete_metrica(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN"]))
):
    item = db.query(FatoAtletasMetricas).filter(FatoAtletasMetricas.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    
    db.delete(item)
    db.commit()
    return {"message": "Registro excluído"}


@router.post("/metricas/bulk", response_model=List[AtletasMetricasResponse])
def create_metricas_bulk(
    data: List[AtletasMetricasCreate],
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN", "ANALISTA", "GESTOR"]))
):
    items = [FatoAtletasMetricas(**item.model_dump(), created_by=current_user.id) for item in data]
    db.add_all(items)
    db.commit()
    for item in items:
        db.refresh(item)
    return items


# === CANAIS ===
@router.get("/canais/", response_model=List[AtletasCanaisResponse])
def list_canais(
    projeto_id: Optional[int] = Query(None, description="Filtrar por projeto"),
    canal: Optional[str] = Query(None, description="Filtrar por canal: SITE, GRUPOS, APPAI"),
    cenario: Optional[str] = Query(None, description="Filtrar por cenário: ORCADO, PROJETADO, REALIZADO"),
    categoria_atleta_id: Optional[int] = Query(None, description="Filtrar por categoria de atleta"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    query = db.query(FatoAtletasCanais)
    
    if projeto_id:
        query = query.filter(FatoAtletasCanais.projeto_id == projeto_id)
    if canal:
        query = query.filter(FatoAtletasCanais.canal == canal)
    if cenario:
        query = query.filter(FatoAtletasCanais.cenario == cenario)
    if categoria_atleta_id:
        query = query.filter(FatoAtletasCanais.categoria_atleta_id == categoria_atleta_id)
    
    return query.all()


@router.post("/canais/", response_model=AtletasCanaisResponse)
def create_canal(
    data: AtletasCanaisCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN", "ANALISTA", "GESTOR"]))
):
    projeto = db.query(DimProjeto).filter(DimProjeto.id == data.projeto_id).first()
    if not projeto:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    
    db_item = FatoAtletasCanais(**data.model_dump(), created_by=current_user.id)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


@router.put("/canais/{item_id}", response_model=AtletasCanaisResponse)
def update_canal(
    item_id: int,
    data: AtletasCanaisUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN", "ANALISTA", "GESTOR"]))
):
    item = db.query(FatoAtletasCanais).filter(FatoAtletasCanais.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    
    db.commit()
    db.refresh(item)
    return item


@router.delete("/canais/{item_id}")
def delete_canal(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN"]))
):
    item = db.query(FatoAtletasCanais).filter(FatoAtletasCanais.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    
    db.delete(item)
    db.commit()
    return {"message": "Registro excluído"}


# === KITS ===
@router.get("/kits/", response_model=List[AtletasKitsResponse])
def list_kits(
    projeto_id: Optional[int] = Query(None, description="Filtrar por projeto"),
    tipo_kit: Optional[str] = Query(None, description="Filtrar por tipo de kit: VIP, PLUS, SUPER, PRODUTO"),
    cenario: Optional[str] = Query(None, description="Filtrar por cenário: ORCADO, PROJETADO, REALIZADO"),
    categoria_atleta_id: Optional[int] = Query(None, description="Filtrar por categoria de atleta"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    query = db.query(FatoAtletasKits)
    
    if projeto_id:
        query = query.filter(FatoAtletasKits.projeto_id == projeto_id)
    if tipo_kit:
        query = query.filter(FatoAtletasKits.tipo_kit == tipo_kit)
    if cenario:
        query = query.filter(FatoAtletasKits.cenario == cenario)
    if categoria_atleta_id:
        query = query.filter(FatoAtletasKits.categoria_atleta_id == categoria_atleta_id)
    
    return query.all()


@router.post("/kits/", response_model=AtletasKitsResponse)
def create_kit(
    data: AtletasKitsCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN", "ANALISTA", "GESTOR"]))
):
    projeto = db.query(DimProjeto).filter(DimProjeto.id == data.projeto_id).first()
    if not projeto:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    
    db_item = FatoAtletasKits(**data.model_dump(), created_by=current_user.id)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


@router.put("/kits/{item_id}", response_model=AtletasKitsResponse)
def update_kit(
    item_id: int,
    data: AtletasKitsUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN", "ANALISTA", "GESTOR"]))
):
    item = db.query(FatoAtletasKits).filter(FatoAtletasKits.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    
    db.commit()
    db.refresh(item)
    return item


@router.delete("/kits/{item_id}")
def delete_kit(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN"]))
):
    item = db.query(FatoAtletasKits).filter(FatoAtletasKits.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    
    db.delete(item)
    db.commit()
    return {"message": "Registro excluído"}


# === CUSTOS ===
@router.get("/custos/", response_model=List[AtletasCustosResponse])
def list_custos(
    projeto_id: Optional[int] = Query(None, description="Filtrar por projeto"),
    tipo_custo: Optional[str] = Query(None, description="Filtrar por tipo de custo"),
    cenario: Optional[str] = Query(None, description="Filtrar por cenário: ORCADO, PROJETADO, REALIZADO"),
    categoria_atleta_id: Optional[int] = Query(None, description="Filtrar por categoria de atleta"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    query = db.query(FatoAtletasCustos)
    
    if projeto_id:
        query = query.filter(FatoAtletasCustos.projeto_id == projeto_id)
    if tipo_custo:
        query = query.filter(FatoAtletasCustos.tipo_custo == tipo_custo)
    if cenario:
        query = query.filter(FatoAtletasCustos.cenario == cenario)
    if categoria_atleta_id:
        query = query.filter(FatoAtletasCustos.categoria_atleta_id == categoria_atleta_id)
    
    return query.all()


@router.post("/custos/", response_model=AtletasCustosResponse)
def create_custo(
    data: AtletasCustosCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN", "ANALISTA", "GESTOR"]))
):
    projeto = db.query(DimProjeto).filter(DimProjeto.id == data.projeto_id).first()
    if not projeto:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    
    db_item = FatoAtletasCustos(**data.model_dump(), created_by=current_user.id)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


@router.put("/custos/{item_id}", response_model=AtletasCustosResponse)
def update_custo(
    item_id: int,
    data: AtletasCustosUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN", "ANALISTA", "GESTOR"]))
):
    item = db.query(FatoAtletasCustos).filter(FatoAtletasCustos.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    
    db.commit()
    db.refresh(item)
    return item


@router.delete("/custos/{item_id}")
def delete_custo(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN"]))
):
    item = db.query(FatoAtletasCustos).filter(FatoAtletasCustos.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    
    db.delete(item)
    db.commit()
    return {"message": "Registro excluído"}


# === BULK OPERATIONS ===
@router.post("/canais/bulk", response_model=List[AtletasCanaisResponse])
def create_canais_bulk(
    data: List[AtletasCanaisCreate],
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN", "ANALISTA", "GESTOR"]))
):
    items = [FatoAtletasCanais(**item.model_dump(), created_by=current_user.id) for item in data]
    db.add_all(items)
    db.commit()
    for item in items:
        db.refresh(item)
    return items


@router.post("/kits/bulk", response_model=List[AtletasKitsResponse])
def create_kits_bulk(
    data: List[AtletasKitsCreate],
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN", "ANALISTA", "GESTOR"]))
):
    items = [FatoAtletasKits(**item.model_dump(), created_by=current_user.id) for item in data]
    db.add_all(items)
    db.commit()
    for item in items:
        db.refresh(item)
    return items


@router.post("/custos/bulk", response_model=List[AtletasCustosResponse])
def create_custos_bulk(
    data: List[AtletasCustosCreate],
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["ADMIN", "ANALISTA", "GESTOR"]))
):
    items = [FatoAtletasCustos(**item.model_dump(), created_by=current_user.id) for item in data]
    db.add_all(items)
    db.commit()
    for item in items:
        db.refresh(item)
    return items
