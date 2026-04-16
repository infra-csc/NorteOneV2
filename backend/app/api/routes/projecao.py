from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func as sqlfunc, extract
from typing import List, Optional
from datetime import datetime
import logging

from ...core.database import get_db
from ...core.security import get_current_user, is_user_admin, require_permission
from ...models.projecao import AreaProjecao, AreaProjecaoUsuario, ProjecaoInscritos, ProjecaoInscritosHistorico
from ...models.cadastro_evento import CadastroEvento
from ...models.user import Usuario
from ...models.vendas_snapshot import VendasDiariaSnapshot
from ...models.dimensoes import SkuMapping, EventoGrupo
from ...schemas.projecao import (
    AreaProjecaoResponse, AreaProjecaoDetailResponse, AreaProjecaoUsuarioResponse,
    AreaProjecaoUsuarioBulk,
    ProjecaoInscritosCreate, ProjecaoInscritosUpdate, ProjecaoInscritosResponse,
    HistoricoResponse,
    ConsolidadoEventoResponse, ConsolidadoAreaItem,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projecao", tags=["Projeção de Inscritos"])

PROJECAO_PERMISSION = "projecao_inscritos"


def _get_user_area_ids(db: Session, user_id: int) -> set:
    rows = db.query(AreaProjecaoUsuario.area_projecao_id).filter(
        AreaProjecaoUsuario.usuario_id == user_id
    ).all()
    return {r[0] for r in rows}


def _check_area_permission(db: Session, user, area_projecao_id: int):
    if is_user_admin(user):
        return
    allowed = _get_user_area_ids(db, user.id)
    if area_projecao_id not in allowed:
        raise HTTPException(status_code=403, detail="Você não tem permissão para editar projeções desta área")


def _record_history(db: Session, projecao_id: int, acao: str, usuario_id: int,
                    campo: str = None, anterior: str = None, novo: str = None):
    hist = ProjecaoInscritosHistorico(
        projecao_id=projecao_id,
        acao=acao,
        campo_alterado=campo,
        valor_anterior=anterior,
        valor_novo=novo,
        usuario_id=usuario_id,
    )
    db.add(hist)


@router.get("/areas", response_model=List[AreaProjecaoResponse])
def list_areas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_visualizar")),
):
    return db.query(AreaProjecao).filter(AreaProjecao.ativo == True).order_by(AreaProjecao.nome).all()


@router.get("/areas/detail", response_model=List[AreaProjecaoDetailResponse])
def list_areas_detail(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_editar")),
):
    if not is_user_admin(current_user):
        raise HTTPException(status_code=403, detail="Apenas administradores podem ver detalhes de atribuições")

    areas = (
        db.query(AreaProjecao)
        .filter(AreaProjecao.ativo == True)
        .options(joinedload(AreaProjecao.usuarios).joinedload(AreaProjecaoUsuario.usuario))
        .order_by(AreaProjecao.nome)
        .all()
    )
    result = []
    for area in areas:
        usuarios_list = []
        for au in area.usuarios:
            usuarios_list.append(AreaProjecaoUsuarioResponse(
                id=au.id,
                area_projecao_id=au.area_projecao_id,
                usuario_id=au.usuario_id,
                usuario_nome=au.usuario.nome if au.usuario else None,
                usuario_email=au.usuario.email if au.usuario else None,
                created_at=au.created_at,
            ))
        result.append(AreaProjecaoDetailResponse(
            id=area.id,
            nome=area.nome,
            ativo=area.ativo,
            created_at=area.created_at,
            usuarios=usuarios_list,
        ))
    return result


@router.post("/areas/atribuir")
def atribuir_usuarios_area(
    data: AreaProjecaoUsuarioBulk,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_editar")),
):
    if not is_user_admin(current_user):
        raise HTTPException(status_code=403, detail="Apenas administradores podem gerenciar atribuições")

    area = db.query(AreaProjecao).filter(AreaProjecao.id == data.area_projecao_id).first()
    if not area:
        raise HTTPException(status_code=404, detail="Área não encontrada")

    db.query(AreaProjecaoUsuario).filter(
        AreaProjecaoUsuario.area_projecao_id == data.area_projecao_id
    ).delete()

    for uid in data.usuario_ids:
        db.add(AreaProjecaoUsuario(area_projecao_id=data.area_projecao_id, usuario_id=uid))

    db.commit()
    return {"message": f"Atribuições atualizadas para a área '{area.nome}'"}


@router.get("/minhas-areas")
def minhas_areas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_visualizar")),
):
    if is_user_admin(current_user):
        areas = db.query(AreaProjecao).filter(AreaProjecao.ativo == True).all()
        return [{"id": a.id, "nome": a.nome} for a in areas]

    area_ids = _get_user_area_ids(db, current_user.id)
    areas = db.query(AreaProjecao).filter(
        AreaProjecao.id.in_(area_ids),
        AreaProjecao.ativo == True
    ).all()
    return [{"id": a.id, "nome": a.nome} for a in areas]


@router.get("/", response_model=List[ProjecaoInscritosResponse])
def list_projecoes(
    mes: Optional[int] = Query(None, ge=1, le=12),
    tipo_evento: Optional[str] = Query(None),
    area_projecao_id: Optional[int] = Query(None),
    evento_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_visualizar")),
):
    query = (
        db.query(ProjecaoInscritos)
        .join(CadastroEvento, ProjecaoInscritos.evento_id == CadastroEvento.id)
        .join(AreaProjecao, ProjecaoInscritos.area_projecao_id == AreaProjecao.id)
        .options(
            joinedload(ProjecaoInscritos.evento),
            joinedload(ProjecaoInscritos.area_projecao),
            joinedload(ProjecaoInscritos.criador),
            joinedload(ProjecaoInscritos.editor),
        )
    )

    if mes:
        query = query.filter(extract("month", CadastroEvento.data_evento) == mes)
    if tipo_evento:
        query = query.filter(CadastroEvento.tipo_evento == tipo_evento)
    if area_projecao_id:
        query = query.filter(ProjecaoInscritos.area_projecao_id == area_projecao_id)
    if evento_id:
        query = query.filter(ProjecaoInscritos.evento_id == evento_id)

    query = query.filter(
        CadastroEvento.deleted_at.is_(None),
        ProjecaoInscritos.deleted_at.is_(None),
    )
    projecoes = query.order_by(CadastroEvento.data_evento.desc(), AreaProjecao.nome).all()

    user_areas = None
    if not is_user_admin(current_user):
        user_areas = _get_user_area_ids(db, current_user.id)

    result = []
    for p in projecoes:
        if user_areas is not None and p.area_projecao_id not in user_areas:
            continue
        result.append(ProjecaoInscritosResponse(
            id=p.id,
            evento_id=p.evento_id,
            evento_nome=p.evento.nome if p.evento else None,
            evento_data=p.evento.data_evento.isoformat() if p.evento and p.evento.data_evento else None,
            evento_tipo=p.evento.tipo_evento if p.evento else None,
            evento_modalidade=p.evento.modalidade if p.evento else None,
            area_projecao_id=p.area_projecao_id,
            area_projecao_nome=p.area_projecao.nome if p.area_projecao else None,
            quantidade=p.quantidade,
            created_by=p.created_by,
            created_by_nome=p.criador.nome if p.criador else None,
            updated_by=p.updated_by,
            updated_by_nome=p.editor.nome if p.editor else None,
            created_at=p.created_at,
            updated_at=p.updated_at,
        ))
    return result


@router.post("/", response_model=ProjecaoInscritosResponse)
def create_projecao(
    data: ProjecaoInscritosCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_criar")),
):
    _check_area_permission(db, current_user, data.area_projecao_id)

    evento = db.query(CadastroEvento).filter(CadastroEvento.id == data.evento_id, CadastroEvento.deleted_at.is_(None)).first()
    if not evento:
        raise HTTPException(status_code=404, detail="Evento não encontrado")

    area = db.query(AreaProjecao).filter(AreaProjecao.id == data.area_projecao_id, AreaProjecao.ativo == True).first()
    if not area:
        raise HTTPException(status_code=404, detail="Área de projeção não encontrada")

    existing_active = db.query(ProjecaoInscritos).filter(
        ProjecaoInscritos.evento_id == data.evento_id,
        ProjecaoInscritos.area_projecao_id == data.area_projecao_id,
        ProjecaoInscritos.deleted_at.is_(None),
    ).first()
    if existing_active:
        raise HTTPException(status_code=409, detail="Já existe uma projeção para este evento e área")

    projecao = ProjecaoInscritos(
        evento_id=data.evento_id,
        area_projecao_id=data.area_projecao_id,
        quantidade=data.quantidade,
        created_by=current_user.id,
    )
    db.add(projecao)
    db.flush()

    _record_history(db, projecao.id, "CRIACAO", current_user.id,
                    campo="quantidade", novo=str(data.quantidade))
    db.commit()
    db.refresh(projecao)

    return ProjecaoInscritosResponse(
        id=projecao.id,
        evento_id=projecao.evento_id,
        evento_nome=evento.nome,
        evento_data=evento.data_evento.isoformat() if evento.data_evento else None,
        evento_tipo=evento.tipo_evento,
        evento_modalidade=evento.modalidade,
        area_projecao_id=projecao.area_projecao_id,
        area_projecao_nome=area.nome,
        quantidade=projecao.quantidade,
        created_by=projecao.created_by,
        created_by_nome=current_user.nome,
        updated_by=projecao.updated_by,
        updated_by_nome=None,
        created_at=projecao.created_at,
        updated_at=projecao.updated_at,
    )


@router.put("/{projecao_id}", response_model=ProjecaoInscritosResponse)
def update_projecao(
    projecao_id: int,
    data: ProjecaoInscritosUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_editar")),
):
    projecao = db.query(ProjecaoInscritos).options(
        joinedload(ProjecaoInscritos.evento),
        joinedload(ProjecaoInscritos.area_projecao),
        joinedload(ProjecaoInscritos.criador),
    ).filter(
        ProjecaoInscritos.id == projecao_id,
        ProjecaoInscritos.deleted_at.is_(None),
    ).first()
    if not projecao:
        raise HTTPException(status_code=404, detail="Projeção não encontrada")

    _check_area_permission(db, current_user, projecao.area_projecao_id)

    old_qtd = projecao.quantidade
    if data.quantidade != old_qtd:
        _record_history(db, projecao.id, "EDICAO", current_user.id,
                        campo="quantidade", anterior=str(old_qtd), novo=str(data.quantidade))
        projecao.quantidade = data.quantidade
        projecao.updated_by = current_user.id

    db.commit()
    db.refresh(projecao)

    editor = db.query(Usuario).filter(Usuario.id == projecao.updated_by).first() if projecao.updated_by else None

    return ProjecaoInscritosResponse(
        id=projecao.id,
        evento_id=projecao.evento_id,
        evento_nome=projecao.evento.nome if projecao.evento else None,
        evento_data=projecao.evento.data_evento.isoformat() if projecao.evento and projecao.evento.data_evento else None,
        evento_tipo=projecao.evento.tipo_evento if projecao.evento else None,
        evento_modalidade=projecao.evento.modalidade if projecao.evento else None,
        area_projecao_id=projecao.area_projecao_id,
        area_projecao_nome=projecao.area_projecao.nome if projecao.area_projecao else None,
        quantidade=projecao.quantidade,
        created_by=projecao.created_by,
        created_by_nome=projecao.criador.nome if projecao.criador else None,
        updated_by=projecao.updated_by,
        updated_by_nome=editor.nome if editor else None,
        created_at=projecao.created_at,
        updated_at=projecao.updated_at,
    )


@router.get("/{projecao_id}/historico", response_model=List[HistoricoResponse])
def get_historico(
    projecao_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_visualizar")),
):
    projecao = db.query(ProjecaoInscritos).filter(ProjecaoInscritos.id == projecao_id).first()
    if not projecao:
        raise HTTPException(status_code=404, detail="Projeção não encontrada")

    _check_area_permission(db, current_user, projecao.area_projecao_id)

    historicos = (
        db.query(ProjecaoInscritosHistorico)
        .options(joinedload(ProjecaoInscritosHistorico.usuario))
        .filter(ProjecaoInscritosHistorico.projecao_id == projecao_id)
        .order_by(ProjecaoInscritosHistorico.created_at.desc())
        .all()
    )
    return [
        HistoricoResponse(
            id=h.id,
            projecao_id=h.projecao_id,
            acao=h.acao,
            campo_alterado=h.campo_alterado,
            valor_anterior=h.valor_anterior,
            valor_novo=h.valor_novo,
            usuario_id=h.usuario_id,
            usuario_nome=h.usuario.nome if h.usuario else None,
            created_at=h.created_at,
        )
        for h in historicos
    ]


@router.delete("/{projecao_id}")
def delete_projecao(
    projecao_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_deletar")),
):
    projecao = db.query(ProjecaoInscritos).filter(
        ProjecaoInscritos.id == projecao_id,
        ProjecaoInscritos.deleted_at.is_(None),
    ).first()
    if not projecao:
        raise HTTPException(status_code=404, detail="Projeção não encontrada")

    _check_area_permission(db, current_user, projecao.area_projecao_id)

    _record_history(db, projecao.id, "DELECAO", current_user.id,
                    campo="quantidade", anterior=str(projecao.quantidade), novo=None)

    projecao.deleted_at = datetime.utcnow()
    projecao.updated_by = current_user.id
    db.commit()
    return {"message": "Projeção removida"}


@router.get("/consolidado", response_model=List[ConsolidadoEventoResponse])
def get_consolidado(
    mes: Optional[int] = Query(None, ge=1, le=12),
    tipo_evento: Optional[str] = Query(None),
    evento_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_visualizar")),
):
    query = db.query(CadastroEvento).filter(CadastroEvento.deleted_at.is_(None))
    if mes:
        query = query.filter(extract("month", CadastroEvento.data_evento) == mes)
    if tipo_evento:
        query = query.filter(CadastroEvento.tipo_evento == tipo_evento)
    if evento_id:
        query = query.filter(CadastroEvento.id == evento_id)

    eventos = query.order_by(CadastroEvento.data_evento.desc()).all()

    sku_to_grupo = {}
    all_mappings = db.query(SkuMapping).filter(SkuMapping.ativo == True).all()
    for m in all_mappings:
        if m.evento_grupo and m.sku:
            sku_to_grupo[m.sku.upper().strip()] = m.evento_grupo

    result = []
    for evento in eventos:
        projecoes = db.query(ProjecaoInscritos).options(
            joinedload(ProjecaoInscritos.area_projecao)
        ).filter(
            ProjecaoInscritos.evento_id == evento.id,
            ProjecaoInscritos.deleted_at.is_(None),
        ).all()

        if not projecoes:
            continue

        inscritos_reais = 0
        if evento.sku:
            grupo_nome = sku_to_grupo.get(evento.sku.upper().strip())
            if grupo_nome:
                total = db.query(sqlfunc.sum(VendasDiariaSnapshot.quantidade)).filter(
                    VendasDiariaSnapshot.evento_grupo == grupo_nome
                ).scalar()
                inscritos_reais = total or 0

        projecoes_items = []
        total_projecoes = 0
        for p in projecoes:
            projecoes_items.append(ConsolidadoAreaItem(
                area_projecao_id=p.area_projecao_id,
                area_projecao_nome=p.area_projecao.nome if p.area_projecao else "N/A",
                quantidade=p.quantidade,
            ))
            total_projecoes += p.quantidade

        result.append(ConsolidadoEventoResponse(
            evento_id=evento.id,
            evento_nome=evento.nome,
            evento_data=evento.data_evento.isoformat() if evento.data_evento else None,
            inscritos_reais=inscritos_reais,
            projecoes=projecoes_items,
            total_projecoes=total_projecoes,
            total_geral=inscritos_reais + total_projecoes,
        ))

    return result
