from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from ...core.database import get_db
from ...core.security import get_current_user, require_permission
from ...models.dimensoes import DimProjeto
from ...models.user import Usuario
from ...schemas.dimensoes import ProjetoCreate, ProjetoUpdate, ProjetoResponse

router = APIRouter(prefix="/projetos", tags=["Projetos/Eventos"])


@router.get("/", response_model=List[ProjetoResponse])
def list_projetos(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    modalidade: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission("eventos", "pode_visualizar"))
):
    query = db.query(DimProjeto)
    if status:
        query = query.filter(DimProjeto.status == status)
    if modalidade:
        query = query.filter(DimProjeto.modalidade == modalidade)
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
    modalidades = db.query(DimProjeto.modalidade).distinct().all()
    tipos_evento = db.query(DimProjeto.tipo_evento).distinct().all()
    leis = db.query(DimProjeto.lei).distinct().all()
    estados = db.query(DimProjeto.estado).filter(DimProjeto.estado.isnot(None)).distinct().all()
    cidades = db.query(DimProjeto.cidade).filter(DimProjeto.cidade.isnot(None)).distinct().all()
    anos = db.query(func.extract('year', DimProjeto.data_evento).label('ano')).distinct().order_by(func.extract('year', DimProjeto.data_evento).desc()).all()

    return {
        "modalidades": [mod[0] for mod in modalidades if mod[0]],
        "tipos_evento": [tipo[0] for tipo in tipos_evento if tipo[0]],
        "leis": [lei_item[0] for lei_item in leis if lei_item[0]],
        "estados": [est[0] for est in estados if est[0]],
        "cidades": [cid[0] for cid in cidades if cid[0]],
        "anos": [int(ano_item[0]) for ano_item in anos if ano_item[0]],
        "status": ["EM_ANDAMENTO", "CONCLUIDO", "CANCELADO"]
    }


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
    return {"message": "Projeto cancelado"}
