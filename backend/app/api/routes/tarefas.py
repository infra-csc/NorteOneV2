from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import Usuario
from app.models.tarefas import Tarefa, StatusTarefa as ModelStatusTarefa
from app.schemas.tarefas import TarefaCreate, TarefaUpdate, TarefaResponse, StatusTarefa, PrioridadeTarefa

router = APIRouter(prefix="/tarefas", tags=["Tarefas"])


@router.get("/", response_model=List[TarefaResponse])
def list_tarefas(
    status: Optional[StatusTarefa] = None,
    prioridade: Optional[PrioridadeTarefa] = None,
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    from sqlalchemy import or_, and_
    query = db.query(Tarefa).filter(
        or_(
            Tarefa.responsavel_id == current_user.id,
            and_(
                Tarefa.usuario_id == current_user.id,
                Tarefa.responsavel_id.is_(None)
            )
        )
    )
    
    if status:
        query = query.filter(Tarefa.status == status)
    if prioridade:
        query = query.filter(Tarefa.prioridade == prioridade)
    
    tarefas = query.order_by(Tarefa.data_vencimento.asc().nullsfirst()).limit(limit).all()
    return tarefas


@router.get("/pendentes", response_model=List[TarefaResponse])
def list_tarefas_pendentes(
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    from sqlalchemy import or_, and_
    tarefas = db.query(Tarefa).filter(
        or_(
            Tarefa.responsavel_id == current_user.id,
            and_(
                Tarefa.usuario_id == current_user.id,
                Tarefa.responsavel_id.is_(None)
            )
        ),
        Tarefa.status.in_([ModelStatusTarefa.PENDENTE, ModelStatusTarefa.EM_ANDAMENTO])
    ).order_by(Tarefa.data_vencimento.asc().nullsfirst()).limit(limit).all()
    return tarefas


@router.get("/hoje", response_model=List[TarefaResponse])
def list_tarefas_hoje(
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    from sqlalchemy import or_, and_
    hoje = datetime.now().date()
    amanha = hoje + timedelta(days=1)
    
    tarefas = db.query(Tarefa).filter(
        or_(
            Tarefa.responsavel_id == current_user.id,
            and_(
                Tarefa.usuario_id == current_user.id,
                Tarefa.responsavel_id.is_(None)
            )
        ),
        Tarefa.data_vencimento >= hoje,
        Tarefa.data_vencimento < amanha,
        Tarefa.status.in_([ModelStatusTarefa.PENDENTE, ModelStatusTarefa.EM_ANDAMENTO])
    ).order_by(Tarefa.data_vencimento.asc()).limit(limit).all()
    return tarefas


@router.get("/delegadas", response_model=List[TarefaResponse])
def list_tarefas_delegadas(
    status: Optional[StatusTarefa] = None,
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    from sqlalchemy import and_
    query = db.query(Tarefa).filter(
        and_(
            Tarefa.usuario_id == current_user.id,
            Tarefa.responsavel_id.isnot(None),
            Tarefa.responsavel_id != current_user.id
        )
    )
    
    if status:
        query = query.filter(Tarefa.status == status)
    
    tarefas = query.order_by(Tarefa.created_at.desc()).limit(limit).all()
    return tarefas


@router.get("/resumo")
def get_resumo_tarefas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    from sqlalchemy import or_, and_, func as sa_func, case
    
    minhas_tarefas_filter = or_(
        Tarefa.responsavel_id == current_user.id,
        and_(
            Tarefa.usuario_id == current_user.id,
            Tarefa.responsavel_id.is_(None)
        )
    )
    
    delegadas_filter = and_(
        Tarefa.usuario_id == current_user.id,
        Tarefa.responsavel_id.isnot(None),
        Tarefa.responsavel_id != current_user.id
    )
    
    hoje = datetime.now().date()
    amanha = hoje + timedelta(days=1)
    status_ativos = [ModelStatusTarefa.PENDENTE, ModelStatusTarefa.EM_ANDAMENTO]

    minhas_counts = db.query(
        sa_func.count(Tarefa.id).label("total"),
        sa_func.sum(case((Tarefa.status == ModelStatusTarefa.PENDENTE, 1), else_=0)).label("pendentes"),
        sa_func.sum(case((Tarefa.status == ModelStatusTarefa.EM_ANDAMENTO, 1), else_=0)).label("em_andamento"),
        sa_func.sum(case((Tarefa.status == ModelStatusTarefa.CONCLUIDA, 1), else_=0)).label("concluidas"),
        sa_func.sum(case((
            and_(
                Tarefa.data_vencimento >= hoje,
                Tarefa.data_vencimento < amanha,
                Tarefa.status.in_(status_ativos),
            ),
            1
        ), else_=0)).label("vencendo_hoje"),
        sa_func.sum(case((
            and_(
                Tarefa.data_vencimento < hoje,
                Tarefa.status.in_(status_ativos),
            ),
            1
        ), else_=0)).label("atrasadas"),
    ).filter(minhas_tarefas_filter).one()

    delegadas_counts = db.query(
        sa_func.count(Tarefa.id).label("total"),
        sa_func.sum(case((Tarefa.status.in_(status_ativos), 1), else_=0)).label("pendentes"),
    ).filter(delegadas_filter).one()
    
    return {
        "total": int(minhas_counts.total or 0),
        "pendentes": int(minhas_counts.pendentes or 0),
        "em_andamento": int(minhas_counts.em_andamento or 0),
        "concluidas": int(minhas_counts.concluidas or 0),
        "vencendo_hoje": int(minhas_counts.vencendo_hoje or 0),
        "atrasadas": int(minhas_counts.atrasadas or 0),
        "delegadas_total": int(delegadas_counts.total or 0),
        "delegadas_pendentes": int(delegadas_counts.pendentes or 0)
    }


@router.get("/{tarefa_id}", response_model=TarefaResponse)
def get_tarefa(
    tarefa_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    from sqlalchemy import or_
    tarefa = db.query(Tarefa).filter(
        Tarefa.id == tarefa_id,
        or_(
            Tarefa.usuario_id == current_user.id,
            Tarefa.responsavel_id == current_user.id
        )
    ).first()
    
    if not tarefa:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    
    return tarefa


@router.post("/", response_model=TarefaResponse)
def create_tarefa(
    tarefa: TarefaCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    responsavel_id = tarefa.responsavel_id
    if responsavel_id:
        responsavel = db.query(Usuario).filter(Usuario.id == responsavel_id).first()
        if not responsavel:
            raise HTTPException(status_code=400, detail="Responsável não encontrado")
    
    db_tarefa = Tarefa(
        titulo=tarefa.titulo,
        descricao=tarefa.descricao,
        data_vencimento=tarefa.data_vencimento,
        hora_lembrete=tarefa.hora_lembrete,
        prioridade=tarefa.prioridade,
        criado_por_nori=tarefa.criado_por_nori,
        usuario_id=current_user.id,
        responsavel_id=responsavel_id,
        dados_analise=tarefa.dados_analise
    )
    
    db.add(db_tarefa)
    db.commit()
    db.refresh(db_tarefa)
    
    return db_tarefa


@router.put("/{tarefa_id}", response_model=TarefaResponse)
def update_tarefa(
    tarefa_id: int,
    tarefa: TarefaUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    from sqlalchemy import or_
    db_tarefa = db.query(Tarefa).filter(
        Tarefa.id == tarefa_id,
        or_(
            Tarefa.usuario_id == current_user.id,
            Tarefa.responsavel_id == current_user.id
        )
    ).first()
    
    if not db_tarefa:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    
    update_data = tarefa.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_tarefa, key, value)
    
    db.commit()
    db.refresh(db_tarefa)
    
    return db_tarefa


@router.put("/{tarefa_id}/concluir", response_model=TarefaResponse)
def concluir_tarefa(
    tarefa_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    from sqlalchemy import or_
    db_tarefa = db.query(Tarefa).filter(
        Tarefa.id == tarefa_id,
        or_(
            Tarefa.usuario_id == current_user.id,
            Tarefa.responsavel_id == current_user.id
        )
    ).first()
    
    if not db_tarefa:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    
    db_tarefa.status = ModelStatusTarefa.CONCLUIDA
    db.commit()
    db.refresh(db_tarefa)
    
    return db_tarefa


@router.delete("/{tarefa_id}")
def delete_tarefa(
    tarefa_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    from sqlalchemy import or_
    db_tarefa = db.query(Tarefa).filter(
        Tarefa.id == tarefa_id,
        or_(
            Tarefa.usuario_id == current_user.id,
            Tarefa.responsavel_id == current_user.id
        )
    ).first()
    
    if not db_tarefa:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    
    db.delete(db_tarefa)
    db.commit()
    
    return {"message": "Tarefa excluída com sucesso"}
