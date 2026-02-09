from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import Usuario
from app.models.tarefas import Tarefa, StatusTarefa as ModelStatusTarefa, PrioridadeTarefa as ModelPrioridadeTarefa
from app.schemas.tarefas import TarefaCreate, TarefaUpdate, TarefaResponse, StatusTarefa, PrioridadeTarefa

router = APIRouter(prefix="/tarefas", tags=["Tarefas"])


@router.get("/", response_model=List[TarefaResponse])
def list_tarefas(
    status: Optional[StatusTarefa] = None,
    prioridade: Optional[PrioridadeTarefa] = None,
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
    
    tarefas = query.order_by(Tarefa.data_vencimento.asc().nullsfirst()).all()
    return tarefas


@router.get("/pendentes", response_model=List[TarefaResponse])
def list_tarefas_pendentes(
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
    ).order_by(Tarefa.data_vencimento.asc().nullsfirst()).all()
    return tarefas


@router.get("/hoje", response_model=List[TarefaResponse])
def list_tarefas_hoje(
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
    ).order_by(Tarefa.data_vencimento.asc()).all()
    return tarefas


@router.get("/delegadas", response_model=List[TarefaResponse])
def list_tarefas_delegadas(
    status: Optional[StatusTarefa] = None,
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
    
    tarefas = query.order_by(Tarefa.created_at.desc()).all()
    return tarefas


@router.get("/resumo")
def get_resumo_tarefas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    from sqlalchemy import or_, and_
    
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
    
    total = db.query(Tarefa).filter(minhas_tarefas_filter).count()
    pendentes = db.query(Tarefa).filter(
        minhas_tarefas_filter,
        Tarefa.status == ModelStatusTarefa.PENDENTE
    ).count()
    em_andamento = db.query(Tarefa).filter(
        minhas_tarefas_filter,
        Tarefa.status == ModelStatusTarefa.EM_ANDAMENTO
    ).count()
    concluidas = db.query(Tarefa).filter(
        minhas_tarefas_filter,
        Tarefa.status == ModelStatusTarefa.CONCLUIDA
    ).count()
    
    hoje = datetime.now().date()
    vencendo_hoje = db.query(Tarefa).filter(
        minhas_tarefas_filter,
        Tarefa.data_vencimento >= hoje,
        Tarefa.data_vencimento < hoje + timedelta(days=1),
        Tarefa.status.in_([ModelStatusTarefa.PENDENTE, ModelStatusTarefa.EM_ANDAMENTO])
    ).count()
    
    atrasadas = db.query(Tarefa).filter(
        minhas_tarefas_filter,
        Tarefa.data_vencimento < hoje,
        Tarefa.status.in_([ModelStatusTarefa.PENDENTE, ModelStatusTarefa.EM_ANDAMENTO])
    ).count()
    
    delegadas_total = db.query(Tarefa).filter(delegadas_filter).count()
    delegadas_pendentes = db.query(Tarefa).filter(
        delegadas_filter,
        Tarefa.status.in_([ModelStatusTarefa.PENDENTE, ModelStatusTarefa.EM_ANDAMENTO])
    ).count()
    
    return {
        "total": total,
        "pendentes": pendentes,
        "em_andamento": em_andamento,
        "concluidas": concluidas,
        "vencendo_hoje": vencendo_hoje,
        "atrasadas": atrasadas,
        "delegadas_total": delegadas_total,
        "delegadas_pendentes": delegadas_pendentes
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
