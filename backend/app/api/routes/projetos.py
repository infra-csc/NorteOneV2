from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import List, Optional
from ...core.database import get_db
from ...core.security import get_current_user, require_permission
from ...models.dimensoes import DimProjeto
from ...models.fatos import FatoAtletasCanais, FatoAtletasMetricas
from ...models.user import Usuario
from ...schemas.dimensoes import ProjetoCreate, ProjetoUpdate, ProjetoResponse, ProjetoComAtletasResponse

router = APIRouter(prefix="/projetos", tags=["Projetos/Eventos"])


@router.get("/", response_model=List[ProjetoResponse])
def list_projetos(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    modalidade: Optional[str] = None,
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


@router.get("/com-atletas", response_model=List[ProjetoComAtletasResponse])
def list_projetos_com_atletas(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = Query(None, description="Filtrar por status: EM_ANDAMENTO, CONCLUIDO, CANCELADO"),
    modalidade: Optional[str] = Query(None, description="Filtrar por modalidade"),
    tipo_evento: Optional[str] = Query(None, description="Filtrar por tipo de evento"),
    lei: Optional[str] = Query(None, description="Filtrar por lei de incentivo"),
    cidade: Optional[str] = Query(None, description="Filtrar por cidade"),
    estado: Optional[str] = Query(None, description="Filtrar por estado"),
    ano: Optional[int] = Query(None, description="Filtrar por ano do evento"),
    busca: Optional[str] = Query(None, description="Buscar por código ou nome do evento"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Lista projetos com quantidade de atletas por canal (SITE e GRUPOS) do cenário REALIZADO,
    e totais de atletas ORCADO e PROJETADO.
    """

    subq_site = db.query(
        FatoAtletasCanais.projeto_id,
        func.coalesce(func.sum(FatoAtletasCanais.qtd_atletas), 0).label('qtd_site')
    ).filter(
        FatoAtletasCanais.canal == 'SITE',
        FatoAtletasCanais.cenario == 'REALIZADO'
    ).group_by(FatoAtletasCanais.projeto_id).subquery()

    subq_grupo = db.query(
        FatoAtletasCanais.projeto_id,
        func.coalesce(func.sum(FatoAtletasCanais.qtd_atletas), 0).label('qtd_grupo')
    ).filter(
        FatoAtletasCanais.canal == 'GRUPOS',
        FatoAtletasCanais.cenario == 'REALIZADO'
    ).group_by(FatoAtletasCanais.projeto_id).subquery()

    subq_orcado = db.query(
        FatoAtletasCanais.projeto_id,
        func.coalesce(func.sum(FatoAtletasCanais.qtd_atletas), 0).label('qtd_orcado')
    ).filter(
        FatoAtletasCanais.cenario == 'ORCADO'
    ).group_by(FatoAtletasCanais.projeto_id).subquery()

    subq_projetado = db.query(
        FatoAtletasCanais.projeto_id,
        func.coalesce(func.sum(FatoAtletasCanais.qtd_atletas), 0).label('qtd_projetado')
    ).filter(
        FatoAtletasCanais.cenario == 'PROJETADO'
    ).group_by(FatoAtletasCanais.projeto_id).subquery()

    query = db.query(
        DimProjeto,
        func.coalesce(subq_site.c.qtd_site, 0).label('atletas_site'),
        func.coalesce(subq_grupo.c.qtd_grupo, 0).label('atletas_grupo'),
        func.coalesce(subq_orcado.c.qtd_orcado, 0).label('qtd_atletas_orcado'),
        func.coalesce(subq_projetado.c.qtd_projetado, 0).label('qtd_atletas_projetado')
    ).outerjoin(
        subq_site, DimProjeto.id == subq_site.c.projeto_id
    ).outerjoin(
        subq_grupo, DimProjeto.id == subq_grupo.c.projeto_id
    ).outerjoin(
        subq_orcado, DimProjeto.id == subq_orcado.c.projeto_id
    ).outerjoin(
        subq_projetado, DimProjeto.id == subq_projetado.c.projeto_id
    )

    if status:
        query = query.filter(DimProjeto.status == status)
    if modalidade:
        query = query.filter(DimProjeto.modalidade == modalidade)
    if tipo_evento:
        query = query.filter(DimProjeto.tipo_evento == tipo_evento)
    if lei:
        query = query.filter(DimProjeto.lei == lei)
    if cidade:
        query = query.filter(DimProjeto.cidade.ilike(f'%{cidade}%'))
    if estado:
        query = query.filter(DimProjeto.estado == estado)
    if ano:
        query = query.filter(func.extract('year', DimProjeto.data_evento) == ano)
    if busca:
        query = query.filter(
            or_(
                DimProjeto.codigo.ilike(f'%{busca}%'),
                DimProjeto.evento.ilike(f'%{busca}%'),
                DimProjeto.produto.ilike(f'%{busca}%')
            )
        )

    query = query.order_by(DimProjeto.data_evento.desc())

    results = query.offset(skip).limit(limit).all()

    projetos_com_atletas = []
    for projeto, atletas_site, atletas_grupo, qtd_orcado, qtd_projetado in results:
        atletas_total = int(atletas_site or 0) + int(atletas_grupo or 0)

        projeto_dict = {
            "id": projeto.id,
            "codigo": projeto.codigo,
            "produto": projeto.produto,
            "modalidade": projeto.modalidade,
            "tipo_evento": projeto.tipo_evento,
            "evento": projeto.evento,
            "lei": projeto.lei,
            "cliente": projeto.cliente,
            "status": projeto.status,
            "data_evento": projeto.data_evento,
            "local_evento": projeto.local_evento,
            "cidade": projeto.cidade,
            "estado": projeto.estado,
            "capacidade_maxima": projeto.capacidade_maxima,
            "etapa": projeto.etapa,
            "imagem_kv": getattr(projeto, 'imagem_kv', None),
            "created_at": projeto.created_at,
            "atletas_total": atletas_total,
            "atletas_site": int(atletas_site or 0),
            "atletas_grupo": int(atletas_grupo or 0),
            "qtd_atletas_orcado": int(qtd_orcado or 0),
            "qtd_atletas_projetado": int(qtd_projetado or 0)
        }
        projetos_com_atletas.append(projeto_dict)

    return projetos_com_atletas


@router.get("/skus-disponiveis")
def get_skus_disponiveis(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
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
    current_user: Usuario = Depends(get_current_user)
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
    current_user: Usuario = Depends(get_current_user)
):
    projeto = db.query(DimProjeto).filter(DimProjeto.id == projeto_id).first()
    if not projeto:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    return projeto


@router.get("/{projeto_id}/com-atletas")
def get_projeto_com_atletas(
    projeto_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Retorna um projeto específico com dados de atletas por canal.
    """
    projeto = db.query(DimProjeto).filter(DimProjeto.id == projeto_id).first()
    if not projeto:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    atletas_canais = db.query(
        FatoAtletasCanais.canal,
        func.sum(FatoAtletasCanais.qtd_atletas).label('total')
    ).filter(
        FatoAtletasCanais.projeto_id == projeto_id,
        FatoAtletasCanais.cenario == 'REALIZADO'
    ).group_by(FatoAtletasCanais.canal).all()

    atletas_site = 0
    atletas_grupo = 0

    for canal, total in atletas_canais:
        if canal == 'SITE':
            atletas_site = int(total or 0)
        elif canal == 'GRUPOS':
            atletas_grupo = int(total or 0)

    return {
        "id": projeto.id,
        "codigo": projeto.codigo,
        "produto": projeto.produto,
        "modalidade": projeto.modalidade,
        "tipo_evento": projeto.tipo_evento,
        "evento": projeto.evento,
        "lei": projeto.lei,
        "cliente": projeto.cliente,
        "status": projeto.status,
        "data_evento": projeto.data_evento,
        "local_evento": projeto.local_evento,
        "cidade": projeto.cidade,
        "estado": projeto.estado,
        "capacidade_maxima": projeto.capacidade_maxima,
        "etapa": projeto.etapa,
        "imagem_kv": getattr(projeto, 'imagem_kv', None),
        "created_at": projeto.created_at,
        "atletas_total": atletas_site + atletas_grupo,
        "atletas_site": atletas_site,
        "atletas_grupo": atletas_grupo
    }


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
