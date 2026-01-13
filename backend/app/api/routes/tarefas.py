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
async def list_tarefas(
    status: Optional[StatusTarefa] = None,
    prioridade: Optional[PrioridadeTarefa] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    query = db.query(Tarefa).filter(Tarefa.usuario_id == current_user.id)
    
    if status:
        query = query.filter(Tarefa.status == status)
    if prioridade:
        query = query.filter(Tarefa.prioridade == prioridade)
    
    tarefas = query.order_by(Tarefa.data_vencimento.asc().nullsfirst()).all()
    return tarefas


@router.get("/pendentes", response_model=List[TarefaResponse])
async def list_tarefas_pendentes(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    tarefas = db.query(Tarefa).filter(
        Tarefa.usuario_id == current_user.id,
        Tarefa.status.in_([ModelStatusTarefa.PENDENTE, ModelStatusTarefa.EM_ANDAMENTO])
    ).order_by(Tarefa.data_vencimento.asc().nullsfirst()).all()
    return tarefas


@router.get("/hoje", response_model=List[TarefaResponse])
async def list_tarefas_hoje(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    hoje = datetime.now().date()
    amanha = hoje + timedelta(days=1)
    
    tarefas = db.query(Tarefa).filter(
        Tarefa.usuario_id == current_user.id,
        Tarefa.data_vencimento >= hoje,
        Tarefa.data_vencimento < amanha,
        Tarefa.status.in_([ModelStatusTarefa.PENDENTE, ModelStatusTarefa.EM_ANDAMENTO])
    ).order_by(Tarefa.data_vencimento.asc()).all()
    return tarefas


@router.get("/resumo")
async def get_resumo_tarefas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    total = db.query(Tarefa).filter(Tarefa.usuario_id == current_user.id).count()
    pendentes = db.query(Tarefa).filter(
        Tarefa.usuario_id == current_user.id,
        Tarefa.status == ModelStatusTarefa.PENDENTE
    ).count()
    em_andamento = db.query(Tarefa).filter(
        Tarefa.usuario_id == current_user.id,
        Tarefa.status == ModelStatusTarefa.EM_ANDAMENTO
    ).count()
    concluidas = db.query(Tarefa).filter(
        Tarefa.usuario_id == current_user.id,
        Tarefa.status == ModelStatusTarefa.CONCLUIDA
    ).count()
    
    hoje = datetime.now().date()
    vencendo_hoje = db.query(Tarefa).filter(
        Tarefa.usuario_id == current_user.id,
        Tarefa.data_vencimento >= hoje,
        Tarefa.data_vencimento < hoje + timedelta(days=1),
        Tarefa.status.in_([ModelStatusTarefa.PENDENTE, ModelStatusTarefa.EM_ANDAMENTO])
    ).count()
    
    atrasadas = db.query(Tarefa).filter(
        Tarefa.usuario_id == current_user.id,
        Tarefa.data_vencimento < hoje,
        Tarefa.status.in_([ModelStatusTarefa.PENDENTE, ModelStatusTarefa.EM_ANDAMENTO])
    ).count()
    
    return {
        "total": total,
        "pendentes": pendentes,
        "em_andamento": em_andamento,
        "concluidas": concluidas,
        "vencendo_hoje": vencendo_hoje,
        "atrasadas": atrasadas
    }


@router.get("/{tarefa_id}", response_model=TarefaResponse)
async def get_tarefa(
    tarefa_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    tarefa = db.query(Tarefa).filter(
        Tarefa.id == tarefa_id,
        Tarefa.usuario_id == current_user.id
    ).first()
    
    if not tarefa:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    
    return tarefa


@router.post("/", response_model=TarefaResponse)
async def create_tarefa(
    tarefa: TarefaCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    db_tarefa = Tarefa(
        titulo=tarefa.titulo,
        descricao=tarefa.descricao,
        data_vencimento=tarefa.data_vencimento,
        hora_lembrete=tarefa.hora_lembrete,
        prioridade=tarefa.prioridade,
        criado_por_nori=tarefa.criado_por_nori,
        usuario_id=current_user.id
    )
    
    db.add(db_tarefa)
    db.commit()
    db.refresh(db_tarefa)
    
    return db_tarefa


@router.put("/{tarefa_id}", response_model=TarefaResponse)
async def update_tarefa(
    tarefa_id: int,
    tarefa: TarefaUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    db_tarefa = db.query(Tarefa).filter(
        Tarefa.id == tarefa_id,
        Tarefa.usuario_id == current_user.id
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
async def concluir_tarefa(
    tarefa_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    db_tarefa = db.query(Tarefa).filter(
        Tarefa.id == tarefa_id,
        Tarefa.usuario_id == current_user.id
    ).first()
    
    if not db_tarefa:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    
    db_tarefa.status = ModelStatusTarefa.CONCLUIDA
    db.commit()
    db.refresh(db_tarefa)
    
    return db_tarefa


@router.delete("/{tarefa_id}")
async def delete_tarefa(
    tarefa_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    db_tarefa = db.query(Tarefa).filter(
        Tarefa.id == tarefa_id,
        Tarefa.usuario_id == current_user.id
    ).first()
    
    if not db_tarefa:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    
    db.delete(db_tarefa)
    db.commit()
    
    return {"message": "Tarefa excluída com sucesso"}
