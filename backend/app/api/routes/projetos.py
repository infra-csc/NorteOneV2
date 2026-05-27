from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
import threading
import time as _time
from ...core.database import get_db
from ...core.security import get_current_user, require_permission
from ...models.dimensoes import DimProjeto
from ...models.user import Usuario
from ...schemas.dimensoes import ProjetoCreate, ProjetoUpdate, ProjetoResponse

router = APIRouter(prefix="/projetos", tags=["Projetos/Eventos"])
_FILTROS_CACHE_TTL = 300
_filtros_cache = {"data": None, "ts": 0.0}
_filtros_cache_lock = threading.Lock()


def _invalidate_filtros_cache():
    with _filtros_cache_lock:
        _filtros_cache["data"] = None
        _filtros_cache["ts"] = 0.0


@router.get("/", response_model=List[ProjetoResponse])
def list_projetos(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    modalidade: Optional[str] = None,
    tipo_evento: Optional[str] = None,
    lei: Optional[str] = None,
    ano: Optional[int] = None,
    busca: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("eventos", "pode_visualizar"))
):
    query = db.query(DimProjeto)
    if status:
        query = query.filter(DimProjeto.status == status)
    if modalidade:
        query = query.filter(DimProjeto.modalidade == modalidade)
    if tipo_evento:
        query = query.filter(DimProjeto.tipo_evento == tipo_evento)
    if lei:
        query = query.filter(DimProjeto.lei == lei)
    if ano:
        from datetime import date
        query = query.filter(
            DimProjeto.data_evento >= date(int(ano), 1, 1),
            DimProjeto.data_evento < date(int(ano) + 1, 1, 1),
        )
    if busca:
        q = f"%{busca.strip()}%"
        query = query.filter(
            (DimProjeto.evento.ilike(q)) |
            (DimProjeto.codigo.ilike(q)) |
            (DimProjeto.cidade.ilike(q)) |
            (DimProjeto.local_evento.ilike(q))
        )
    projetos = query.offset(skip).limit(limit).all()
    return projetos


@router.get("/skus-disponiveis")
def get_skus_disponiveis(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("eventos", "pode_visualizar"))
):
    """Retorna SKUs disponíveis dos mapeamentos para seleção no cadastro de projetos."""
    from ...models.dimensoes import SkuMapping
    mappings = db.query(
        SkuMapping.sku, SkuMapping.nome_evento, SkuMapping.evento_grupo, SkuMapping.ano, SkuMapping.fonte
    ).filter(
        SkuMapping.ativo == True
    ).order_by(SkuMapping.evento_grupo, SkuMapping.ano.desc()).all()
    
    return [
        {
            "sku": m.sku,
            "nome_evento": m.nome_evento,
            "evento_grupo": m.evento_grupo,
            "ano": m.ano,
            "fonte": m.fonte
        }
        for m in mappings
    ]


@router.get("/filtros")
def get_filtros_disponiveis(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("eventos", "pode_visualizar"))
):
    """
    Retorna os valores disponíveis para os filtros.
    """
    now = _time.time()
    with _filtros_cache_lock:
        cached = _filtros_cache["data"]
        if cached is not None and (now - _filtros_cache["ts"]) < _FILTROS_CACHE_TTL:
            return cached

    rows = db.query(
        DimProjeto.modalidade,
        DimProjeto.tipo_evento,
        DimProjeto.lei,
        DimProjeto.estado,
        DimProjeto.cidade,
        DimProjeto.data_evento,
    ).all()

    result = {
        "modalidades": sorted({row.modalidade for row in rows if row.modalidade}),
        "tipos_evento": sorted({row.tipo_evento for row in rows if row.tipo_evento}),
        "leis": sorted({row.lei for row in rows if row.lei}),
        "estados": sorted({row.estado for row in rows if row.estado}),
        "cidades": sorted({row.cidade for row in rows if row.cidade}),
        "anos": sorted({row.data_evento.year for row in rows if row.data_evento}, reverse=True),
        "status": ["EM_ANDAMENTO", "CONCLUIDO", "CANCELADO"]
    }
    with _filtros_cache_lock:
        _filtros_cache["data"] = result
        _filtros_cache["ts"] = now
    return result


@router.post("/", response_model=ProjetoResponse)
def create_projeto(
    projeto: ProjetoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("eventos", "pode_criar"))
):
    existing = db.query(DimProjeto).filter(DimProjeto.codigo == projeto.codigo).first()
    if existing:
        raise HTTPException(status_code=400, detail="Código já existe")

    db_projeto = DimProjeto(**projeto.model_dump())
    db.add(db_projeto)
    db.commit()
    db.refresh(db_projeto)
    _invalidate_filtros_cache()
    return db_projeto


@router.get("/{projeto_id}", response_model=ProjetoResponse)
def get_projeto(
    projeto_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("eventos", "pode_visualizar"))
):
    projeto = db.query(DimProjeto).filter(DimProjeto.id == projeto_id).first()
    if not projeto:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    return projeto


@router.put("/{projeto_id}", response_model=ProjetoResponse)
def update_projeto(
    projeto_id: int,
    projeto_update: ProjetoUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("eventos", "pode_editar"))
):
    projeto = db.query(DimProjeto).filter(DimProjeto.id == projeto_id).first()
    if not projeto:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    for field, value in projeto_update.model_dump(exclude_unset=True).items():
        setattr(projeto, field, value)

    db.commit()
    db.refresh(projeto)
    _invalidate_filtros_cache()
    return projeto


@router.delete("/{projeto_id}")
def delete_projeto(
    projeto_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("eventos", "pode_deletar"))
):
    projeto = db.query(DimProjeto).filter(DimProjeto.id == projeto_id).first()
    if not projeto:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    setattr(projeto, 'status', 'CANCELADO')
    db.commit()
    _invalidate_filtros_cache()
    return {"message": "Projeto cancelado"}
