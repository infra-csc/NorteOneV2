from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import extract
from sqlalchemy.exc import IntegrityError
from datetime import timedelta
from typing import List, Optional
from datetime import datetime
from zoneinfo import ZoneInfo
import logging
import csv
import io

from ...core.database import get_db
from ...core.security import get_current_user, is_user_admin, require_permission
from ...models.projecao import (
    AreaProjecao, AreaProjecaoUsuario, ProjecaoInscritos,
    ProjecaoInscritosHistorico, ProjecaoInscritosCliente, ProjecaoCutoffRule,
)
from ...models.cadastro_evento import CadastroEvento
from ...models.user import Usuario
from ...models.dimensoes import SkuMapping, EventoGrupo
from ...schemas.projecao import (
    AreaProjecaoCreate, AreaProjecaoResponse, AreaProjecaoDetailResponse, AreaProjecaoUsuarioResponse,
    AreaProjecaoUsuarioBulk,
    ProjecaoInscritosCreate, ProjecaoInscritosUpdate, ProjecaoInscritosResponse,
    ClienteProjecaoResponse,
    HistoricoResponse,
    ConsolidadoEventoResponse, ConsolidadoAreaItem,
    CutoffRuleCreate, CutoffRuleUpdate, CutoffRuleResponse,
    PendenciaItem, PendenciasResponse, AreaPendenteItem,
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


@router.post("/areas", response_model=AreaProjecaoResponse)
def create_area(
    data: AreaProjecaoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_editar")),
):
    if not is_user_admin(current_user):
        raise HTTPException(status_code=403, detail="Apenas administradores podem criar áreas")
    nome = data.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome da área não pode ser vazio")
    existing = db.query(AreaProjecao).filter(AreaProjecao.nome == nome).first()
    if existing:
        raise HTTPException(status_code=400, detail="Já existe uma área com este nome")
    area = AreaProjecao(nome=nome)
    db.add(area)
    db.commit()
    db.refresh(area)
    return area


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
    mes: Optional[str] = Query(None),
    tipo_evento: Optional[str] = Query(None),
    modalidade: Optional[str] = Query(None),
    area_projecao_id: Optional[str] = Query(None),
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
            joinedload(ProjecaoInscritos.travador),
            joinedload(ProjecaoInscritos.clientes),
        )
    )

    if mes:
        mes_list = [int(m) for m in mes.split(',') if m.strip().isdigit()]
        if mes_list:
            query = query.filter(extract("month", CadastroEvento.data_evento).in_(mes_list))
    if tipo_evento:
        tipos = [t.strip() for t in tipo_evento.split(',') if t.strip()]
        if tipos:
            query = query.filter(CadastroEvento.tipo_evento.in_(tipos))
    if modalidade:
        mods = [m.strip() for m in modalidade.split(',') if m.strip()]
        if mods:
            query = query.filter(CadastroEvento.modalidade.in_(mods))
    if area_projecao_id:
        area_ids = [int(a) for a in area_projecao_id.split(',') if a.strip().isdigit()]
        if area_ids:
            query = query.filter(ProjecaoInscritos.area_projecao_id.in_(area_ids))
    if evento_id:
        query = query.filter(ProjecaoInscritos.evento_id == evento_id)

    query = query.filter(
        CadastroEvento.deleted_at.is_(None),
        ProjecaoInscritos.deleted_at.is_(None),
    )
    projecoes = query.order_by(CadastroEvento.data_evento.desc(), AreaProjecao.nome).all()

    result = []
    for p in projecoes:
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
            clientes=[ClienteProjecaoResponse(
                id=c.id, projecao_id=c.projecao_id, nome_cliente=c.nome_cliente,
                quantidade=c.quantidade, created_at=c.created_at,
            ) for c in p.clientes],
            created_by=p.created_by,
            created_by_nome=p.criador.nome if p.criador else None,
            updated_by=p.updated_by,
            updated_by_nome=p.editor.nome if p.editor else None,
            locked_at=p.locked_at,
            locked_by_nome=p.travador.nome if p.travador else None,
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

    clientes_salvos = []
    if data.clientes:
        for c in data.clientes:
            cliente = ProjecaoInscritosCliente(
                projecao_id=projecao.id,
                nome_cliente=c.nome_cliente.strip(),
                quantidade=c.quantidade,
            )
            db.add(cliente)
            clientes_salvos.append(cliente)

    _record_history(db, projecao.id, "CRIACAO", current_user.id,
                    campo="quantidade", novo=str(data.quantidade))
    for c in clientes_salvos:
        _record_history(db, projecao.id, "CRIACAO", current_user.id,
                        campo="Cliente adicionado",
                        anterior=None, novo=f"{c.nome_cliente} ({c.quantidade})")
    db.commit()
    db.refresh(projecao)
    for c in clientes_salvos:
        db.refresh(c)

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
        clientes=[ClienteProjecaoResponse(
            id=c.id, projecao_id=c.projecao_id, nome_cliente=c.nome_cliente,
            quantidade=c.quantidade, created_at=c.created_at,
        ) for c in clientes_salvos],
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
        joinedload(ProjecaoInscritos.clientes),
    ).filter(
        ProjecaoInscritos.id == projecao_id,
        ProjecaoInscritos.deleted_at.is_(None),
    ).first()
    if not projecao:
        raise HTTPException(status_code=404, detail="Projeção não encontrada")

    if projecao.locked_at is not None:
        raise HTTPException(status_code=423, detail="Esta projeção está travada e não pode ser editada")

    _check_area_permission(db, current_user, projecao.area_projecao_id)

    old_qtd = projecao.quantidade
    if data.quantidade != old_qtd:
        _record_history(db, projecao.id, "EDICAO", current_user.id,
                        campo="quantidade", anterior=str(old_qtd), novo=str(data.quantidade))
        projecao.quantidade = data.quantidade
        projecao.updated_by = current_user.id

    if data.clientes is not None:
        old_clientes = {c.nome_cliente: c.quantidade for c in projecao.clientes}
        new_clientes = {c.nome_cliente.strip(): c.quantidade for c in data.clientes}

        old_names = set(old_clientes.keys())
        new_names = set(new_clientes.keys())

        for nome in old_names - new_names:
            _record_history(db, projecao.id, "EDICAO", current_user.id,
                            campo="Cliente removido",
                            anterior=f"{nome} ({old_clientes[nome]})", novo=None)

        for nome in new_names - old_names:
            _record_history(db, projecao.id, "EDICAO", current_user.id,
                            campo="Cliente adicionado",
                            anterior=None, novo=f"{nome} ({new_clientes[nome]})")

        for nome in old_names & new_names:
            if old_clientes[nome] != new_clientes[nome]:
                _record_history(db, projecao.id, "EDICAO", current_user.id,
                                campo=f"Cliente: {nome}",
                                anterior=str(old_clientes[nome]), novo=str(new_clientes[nome]))

        db.query(ProjecaoInscritosCliente).filter(
            ProjecaoInscritosCliente.projecao_id == projecao.id
        ).delete()
        for c in data.clientes:
            db.add(ProjecaoInscritosCliente(
                projecao_id=projecao.id,
                nome_cliente=c.nome_cliente.strip(),
                quantidade=c.quantidade,
            ))
        if not projecao.updated_by:
            projecao.updated_by = current_user.id

    db.commit()
    db.refresh(projecao)

    clientes_atuais = db.query(ProjecaoInscritosCliente).filter(
        ProjecaoInscritosCliente.projecao_id == projecao.id
    ).all()

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
        clientes=[ClienteProjecaoResponse(
            id=c.id, projecao_id=c.projecao_id, nome_cliente=c.nome_cliente,
            quantidade=c.quantidade, created_at=c.created_at,
        ) for c in clientes_atuais],
        created_by=projecao.created_by,
        created_by_nome=projecao.criador.nome if projecao.criador else None,
        updated_by=projecao.updated_by,
        updated_by_nome=editor.nome if editor else None,
        locked_at=projecao.locked_at,
        locked_by_nome=projecao.travador.nome if projecao.travador else None,
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

    if projecao.locked_at is not None:
        raise HTTPException(status_code=423, detail="Esta projeção está travada e não pode ser removida")

    _check_area_permission(db, current_user, projecao.area_projecao_id)

    _record_history(db, projecao.id, "DELECAO", current_user.id,
                    campo="quantidade", anterior=str(projecao.quantidade), novo=None)

    projecao.deleted_at = datetime.now(ZoneInfo('America/Sao_Paulo')).replace(tzinfo=None)
    projecao.updated_by = current_user.id
    db.commit()
    return {"message": "Projeção removida"}


@router.post("/evento/{evento_id}/toggle-lock")
def toggle_lock_evento(
    evento_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_editar")),
):
    evento = db.query(CadastroEvento).filter(
        CadastroEvento.id == evento_id,
        CadastroEvento.deleted_at.is_(None),
    ).first()
    if not evento:
        raise HTTPException(status_code=404, detail="Evento não encontrado")

    projecoes = db.query(ProjecaoInscritos).options(
        joinedload(ProjecaoInscritos.travador),
    ).filter(
        ProjecaoInscritos.evento_id == evento_id,
        ProjecaoInscritos.deleted_at.is_(None),
    ).all()

    if not projecoes:
        raise HTTPException(status_code=404, detail="Nenhuma projeção encontrada para este evento")

    all_locked = all(p.locked_at is not None for p in projecoes)

    if all_locked:
        if not is_user_admin(current_user):
            raise HTTPException(status_code=403, detail="Apenas administradores podem destravar projeções")
        for p in projecoes:
            p.locked_at = None
            p.locked_by = None
            _record_history(db, p.id, "DESTRAVAMENTO", current_user.id,
                            campo="travamento", anterior="Travado", novo="Destravado")
        db.commit()
        return {"action": "unlocked", "count": len(projecoes)}
    else:
        now = datetime.now(ZoneInfo('America/Sao_Paulo')).replace(tzinfo=None)
        locked_count = 0
        for p in projecoes:
            if p.locked_at is None:
                if not is_user_admin(current_user):
                    allowed = _get_user_area_ids(db, current_user.id)
                    if p.area_projecao_id not in allowed:
                        continue
                p.locked_at = now
                p.locked_by = current_user.id
                _record_history(db, p.id, "TRAVAMENTO", current_user.id,
                                campo="travamento", anterior="Editável", novo="Travado")
                locked_count += 1
        db.commit()
        return {"action": "locked", "count": locked_count}


@router.get("/lixeira", response_model=List[ProjecaoInscritosResponse])
def list_lixeira(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_visualizar")),
):
    if not is_user_admin(current_user):
        raise HTTPException(status_code=403, detail="Apenas administradores podem acessar a lixeira")

    projecoes = (
        db.query(ProjecaoInscritos)
        .join(CadastroEvento, ProjecaoInscritos.evento_id == CadastroEvento.id)
        .join(AreaProjecao, ProjecaoInscritos.area_projecao_id == AreaProjecao.id)
        .options(
            joinedload(ProjecaoInscritos.evento),
            joinedload(ProjecaoInscritos.area_projecao),
            joinedload(ProjecaoInscritos.criador),
            joinedload(ProjecaoInscritos.editor),
        )
        .filter(ProjecaoInscritos.deleted_at.isnot(None))
        .order_by(ProjecaoInscritos.deleted_at.desc())
        .all()
    )

    result = []
    for p in projecoes:
        deleted_by_nome = None
        if p.updated_by:
            deleter = db.query(Usuario).filter(Usuario.id == p.updated_by).first()
            deleted_by_nome = deleter.nome if deleter else None

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
            deleted_at=p.deleted_at,
            deleted_by_nome=deleted_by_nome,
        ))
    return result


@router.post("/lixeira/{projecao_id}/restaurar")
def restaurar_projecao(
    projecao_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_editar")),
):
    if not is_user_admin(current_user):
        raise HTTPException(status_code=403, detail="Apenas administradores podem restaurar projeções")

    projecao = db.query(ProjecaoInscritos).filter(
        ProjecaoInscritos.id == projecao_id,
        ProjecaoInscritos.deleted_at.isnot(None),
    ).first()
    if not projecao:
        raise HTTPException(status_code=404, detail="Projeção não encontrada na lixeira")

    existing_active = db.query(ProjecaoInscritos).filter(
        ProjecaoInscritos.evento_id == projecao.evento_id,
        ProjecaoInscritos.area_projecao_id == projecao.area_projecao_id,
        ProjecaoInscritos.deleted_at.is_(None),
        ProjecaoInscritos.id != projecao.id,
    ).first()
    if existing_active:
        raise HTTPException(
            status_code=409,
            detail="Já existe uma projeção ativa para este evento e área. Exclua-a antes de restaurar."
        )

    projecao.deleted_at = None
    projecao.updated_by = current_user.id

    _record_history(db, projecao.id, "RESTAURACAO", current_user.id,
                    campo="quantidade", novo=str(projecao.quantidade))
    db.commit()
    return {"message": "Projeção restaurada com sucesso"}


@router.delete("/lixeira/{projecao_id}/permanente")
def delete_permanente(
    projecao_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_deletar")),
):
    if not is_user_admin(current_user):
        raise HTTPException(status_code=403, detail="Apenas administradores podem excluir permanentemente")

    projecao = db.query(ProjecaoInscritos).filter(
        ProjecaoInscritos.id == projecao_id,
        ProjecaoInscritos.deleted_at.isnot(None),
    ).first()
    if not projecao:
        raise HTTPException(status_code=404, detail="Projeção não encontrada na lixeira")

    db.query(ProjecaoInscritosHistorico).filter(
        ProjecaoInscritosHistorico.projecao_id == projecao_id
    ).delete()
    db.delete(projecao)
    db.commit()
    return {"message": "Projeção excluída permanentemente"}


@router.get("/exportar")
def exportar_projecoes(
    mes: Optional[str] = Query(None),
    tipo_evento: Optional[str] = Query(None),
    modalidade: Optional[str] = Query(None),
    area_projecao_id: Optional[str] = Query(None),
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
            joinedload(ProjecaoInscritos.clientes),
        )
        .filter(
            CadastroEvento.deleted_at.is_(None),
            ProjecaoInscritos.deleted_at.is_(None),
        )
    )

    if mes:
        mes_list = [int(m) for m in mes.split(',') if m.strip().isdigit()]
        if mes_list:
            query = query.filter(extract("month", CadastroEvento.data_evento).in_(mes_list))
    if tipo_evento:
        tipos = [t.strip() for t in tipo_evento.split(',') if t.strip()]
        if tipos:
            query = query.filter(CadastroEvento.tipo_evento.in_(tipos))
    if modalidade:
        mods = [m.strip() for m in modalidade.split(',') if m.strip()]
        if mods:
            query = query.filter(CadastroEvento.modalidade.in_(mods))
    if area_projecao_id:
        area_ids = [int(a) for a in area_projecao_id.split(',') if a.strip().isdigit()]
        if area_ids:
            query = query.filter(ProjecaoInscritos.area_projecao_id.in_(area_ids))

    projecoes = query.order_by(CadastroEvento.data_evento.desc(), AreaProjecao.nome).all()

    def _sanitize_csv(val: str) -> str:
        if val and val[0] in ('=', '+', '-', '@', '\t', '\r'):
            return "'" + val
        return val

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow([
        'Evento', 'Data Evento', 'Tipo', 'Modalidade',
        'Área', 'Quantidade Total', 'Cliente', 'Qtd Cliente',
        'Criado por', 'Data Criação', 'Editado por', 'Data Edição',
    ])

    for p in projecoes:
        base = [
            _sanitize_csv(p.evento.nome if p.evento else ''),
            p.evento.data_evento.strftime('%d/%m/%Y') if p.evento and p.evento.data_evento else '',
            _sanitize_csv(p.evento.tipo_evento if p.evento else ''),
            _sanitize_csv(p.evento.modalidade if p.evento else ''),
            _sanitize_csv(p.area_projecao.nome if p.area_projecao else ''),
            p.quantidade,
        ]
        tail = [
            _sanitize_csv(p.criador.nome if p.criador else ''),
            p.created_at.strftime('%d/%m/%Y %H:%M') if p.created_at else '',
            _sanitize_csv(p.editor.nome if p.editor else ''),
            p.updated_at.strftime('%d/%m/%Y %H:%M') if p.updated_at else '',
        ]
        if p.clientes:
            for c in p.clientes:
                writer.writerow(base + [_sanitize_csv(c.nome_cliente), c.quantidade] + tail)
        else:
            writer.writerow(base + ['', ''] + tail)

    output.seek(0)
    bom = '\ufeff'
    content = bom + output.getvalue()

    return StreamingResponse(
        io.BytesIO(content.encode('utf-8-sig')),
        media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename=projecao_inscritos.csv'},
    )


@router.get("/consolidado", response_model=List[ConsolidadoEventoResponse])
def get_consolidado(
    mes: Optional[str] = Query(None),
    tipo_evento: Optional[str] = Query(None),
    modalidade: Optional[str] = Query(None),
    area_projecao_id: Optional[str] = Query(None),
    evento_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_visualizar")),
):
    query = db.query(CadastroEvento).filter(CadastroEvento.deleted_at.is_(None))
    if mes:
        mes_list = [int(m) for m in mes.split(',') if m.strip().isdigit()]
        if mes_list:
            query = query.filter(extract("month", CadastroEvento.data_evento).in_(mes_list))
    if tipo_evento:
        tipos = [t.strip() for t in tipo_evento.split(',') if t.strip()]
        if tipos:
            query = query.filter(CadastroEvento.tipo_evento.in_(tipos))
    if modalidade:
        mods = [m.strip() for m in modalidade.split(',') if m.strip()]
        if mods:
            query = query.filter(CadastroEvento.modalidade.in_(mods))
    if evento_id:
        query = query.filter(CadastroEvento.id == evento_id)

    eventos = query.order_by(CadastroEvento.data_evento.desc()).all()

    sku_to_grupo = {}
    all_mappings = db.query(SkuMapping).filter(SkuMapping.ativo == True).all()
    for m in all_mappings:
        if m.evento_grupo and m.sku:
            sku_to_grupo[m.sku.upper().strip()] = m.evento_grupo

    from ...services.snapshot_service import get_isc_totals_from_snapshot
    current_year = datetime.now().year
    isc_totals = get_isc_totals_from_snapshot(db, current_year)

    result = []
    for evento in eventos:
        proj_query = db.query(ProjecaoInscritos).options(
            joinedload(ProjecaoInscritos.area_projecao)
        ).filter(
            ProjecaoInscritos.evento_id == evento.id,
            ProjecaoInscritos.deleted_at.is_(None),
        )
        if area_projecao_id:
            area_ids = [int(a) for a in area_projecao_id.split(',') if a.strip().isdigit()]
            if area_ids:
                proj_query = proj_query.filter(ProjecaoInscritos.area_projecao_id.in_(area_ids))
        projecoes = proj_query.all()

        if not projecoes:
            continue

        inscritos_reais = 0
        if evento.sku:
            grupo_nome = sku_to_grupo.get(evento.sku.upper().strip())
            if grupo_nome and grupo_nome in isc_totals:
                inscritos_reais = isc_totals[grupo_nome].get("qtd_site", 0)

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


# ============================================================
# REGRAS DE PONTO DE CORTE (cut-off rules)
# ============================================================

@router.get("/cutoff-rules", response_model=List[CutoffRuleResponse])
def list_cutoff_rules(
    incluir_inativas: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_visualizar")),
):
    query = db.query(ProjecaoCutoffRule)
    if not incluir_inativas:
        query = query.filter(ProjecaoCutoffRule.ativo == True)
    return query.order_by(ProjecaoCutoffRule.dias_antes_evento.desc()).all()


@router.post("/cutoff-rules", response_model=CutoffRuleResponse)
def create_cutoff_rule(
    data: CutoffRuleCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_editar")),
):
    if not is_user_admin(current_user):
        raise HTTPException(status_code=403, detail="Apenas administradores podem criar regras de corte")
    nome = (data.nome or "").strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome da regra não pode ser vazio")
    if data.dias_antes_evento is None or data.dias_antes_evento < 0:
        raise HTTPException(status_code=400, detail="Dias antes do evento deve ser >= 0")
    if data.dias_antes_evento > 365:
        raise HTTPException(status_code=400, detail="Dias antes do evento deve ser <= 365")
    existing = db.query(ProjecaoCutoffRule).filter(
        ProjecaoCutoffRule.dias_antes_evento == data.dias_antes_evento
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Já existe uma regra com esse valor de dias")
    rule = ProjecaoCutoffRule(
        nome=nome,
        dias_antes_evento=data.dias_antes_evento,
        ativo=data.ativo if data.ativo is not None else True,
    )
    db.add(rule)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Já existe uma regra com esse valor de dias")
    db.refresh(rule)
    return rule


@router.put("/cutoff-rules/{rule_id}", response_model=CutoffRuleResponse)
def update_cutoff_rule(
    rule_id: int,
    data: CutoffRuleUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_editar")),
):
    if not is_user_admin(current_user):
        raise HTTPException(status_code=403, detail="Apenas administradores podem editar regras de corte")
    rule = db.query(ProjecaoCutoffRule).filter(ProjecaoCutoffRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Regra não encontrada")

    if data.nome is not None:
        nome = data.nome.strip()
        if not nome:
            raise HTTPException(status_code=400, detail="Nome da regra não pode ser vazio")
        rule.nome = nome
    if data.dias_antes_evento is not None:
        if data.dias_antes_evento < 0 or data.dias_antes_evento > 365:
            raise HTTPException(status_code=400, detail="Dias antes do evento deve estar entre 0 e 365")
        if data.dias_antes_evento != rule.dias_antes_evento:
            conflict = db.query(ProjecaoCutoffRule).filter(
                ProjecaoCutoffRule.dias_antes_evento == data.dias_antes_evento,
                ProjecaoCutoffRule.id != rule_id,
            ).first()
            if conflict:
                raise HTTPException(status_code=400, detail="Já existe uma regra com esse valor de dias")
        rule.dias_antes_evento = data.dias_antes_evento
    if data.ativo is not None:
        rule.ativo = data.ativo

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Já existe uma regra com esse valor de dias")
    db.refresh(rule)
    return rule


@router.delete("/cutoff-rules/{rule_id}")
def delete_cutoff_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_editar")),
):
    if not is_user_admin(current_user):
        raise HTTPException(status_code=403, detail="Apenas administradores podem remover regras de corte")
    rule = db.query(ProjecaoCutoffRule).filter(ProjecaoCutoffRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    db.delete(rule)
    db.commit()
    return {"message": "Regra removida com sucesso"}


# ============================================================
# PENDÊNCIAS — eventos em ponto de corte sem projeção do usuário
# ============================================================

@router.get("/pendencias", response_model=PendenciasResponse)
def get_pendencias(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_visualizar")),
):
    """
    Retorna eventos em status 'Em andamento' que cruzaram algum ponto de corte
    e ainda não têm projeção registrada para alguma das áreas que o usuário
    tem permissão de editar.
    Admins enxergam pendências de TODAS as áreas.
    """
    rules = (
        db.query(ProjecaoCutoffRule)
        .filter(ProjecaoCutoffRule.ativo == True)
        .order_by(ProjecaoCutoffRule.dias_antes_evento.asc())
        .all()
    )
    if not rules:
        return PendenciasResponse(total_eventos=0, total_areas=0, pendencias=[])

    today = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    # Cada regra dispara somente no dia exato (D-N). O conjunto de datas
    # de evento que nos interessa é exatamente {today + N dias} para cada N.
    rule_days = sorted({r.dias_antes_evento for r in rules})
    rule_by_dias = {r.dias_antes_evento: r for r in rules}
    target_dates = [today + timedelta(days=n) for n in rule_days]

    # Áreas em que o usuário pode editar (admin = todas)
    if is_user_admin(current_user):
        areas_user = db.query(AreaProjecao).filter(AreaProjecao.ativo == True).all()
    else:
        area_ids = _get_user_area_ids(db, current_user.id)
        if not area_ids:
            return PendenciasResponse(total_eventos=0, total_areas=0, pendencias=[])
        areas_user = db.query(AreaProjecao).filter(
            AreaProjecao.id.in_(area_ids),
            AreaProjecao.ativo == True,
        ).all()
    if not areas_user:
        return PendenciasResponse(total_eventos=0, total_areas=0, pendencias=[])
    areas_user_ids = {a.id for a in areas_user}
    areas_nome_by_id = {a.id: a.nome for a in areas_user}

    # Eventos candidatos: em andamento e cuja data cai exatamente em
    # algum dos pontos de corte configurados (today + N dias).
    eventos = (
        db.query(CadastroEvento)
        .filter(
            CadastroEvento.deleted_at.is_(None),
            CadastroEvento.status == 'Em andamento',
            CadastroEvento.data_evento.isnot(None),
            CadastroEvento.data_evento.in_(target_dates),
        )
        .all()
    )
    eventos_candidatos = []
    for ev in eventos:
        dias = (ev.data_evento - today).days
        regra_aplicavel = rule_by_dias.get(dias)
        if regra_aplicavel:
            eventos_candidatos.append((ev, dias, regra_aplicavel))

    if not eventos_candidatos:
        return PendenciasResponse(total_eventos=0, total_areas=0, pendencias=[])

    evento_ids = [ev.id for ev, _, _ in eventos_candidatos]
    # Projeções existentes (não deletadas) por (evento, area)
    projs = (
        db.query(ProjecaoInscritos.evento_id, ProjecaoInscritos.area_projecao_id)
        .filter(
            ProjecaoInscritos.evento_id.in_(evento_ids),
            ProjecaoInscritos.area_projecao_id.in_(areas_user_ids),
            ProjecaoInscritos.deleted_at.is_(None),
        )
        .all()
    )
    existentes = {(p.evento_id, p.area_projecao_id) for p in projs}

    pendencias = []
    total_areas = 0
    for ev, dias, regra in eventos_candidatos:
        faltando = []
        for aid in areas_user_ids:
            if (ev.id, aid) not in existentes:
                faltando.append(AreaPendenteItem(
                    area_projecao_id=aid,
                    area_projecao_nome=areas_nome_by_id[aid],
                ))
        if faltando:
            faltando.sort(key=lambda x: x.area_projecao_nome)
            pendencias.append(PendenciaItem(
                evento_id=ev.id,
                evento_nome=ev.nome,
                evento_data=ev.data_evento.isoformat() if ev.data_evento else None,
                dias_ate_evento=dias,
                cutoff_dias=regra.dias_antes_evento,
                cutoff_nome=regra.nome,
                areas_pendentes=faltando,
            ))
            total_areas += len(faltando)

    pendencias.sort(key=lambda p: (p.dias_ate_evento, p.evento_nome))
    return PendenciasResponse(
        total_eventos=len(pendencias),
        total_areas=total_areas,
        pendencias=pendencias,
    )
