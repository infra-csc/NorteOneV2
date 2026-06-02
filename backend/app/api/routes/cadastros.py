from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, selectinload
from typing import List, Optional
from datetime import datetime, date
from decimal import Decimal
import threading
import time as _time
import logging

from app.core.database import get_db
from ...core.security import get_current_user, require_permission, require_admin, is_user_admin
from ...models.perfil_acesso import PerfilPermissaoCampo

logger = logging.getLogger(__name__)

_list_cache: dict = {"data": None, "json": None, "ts": 0.0}
_list_cache_lock = threading.Lock()
_LIST_CACHE_TTL = 300
_LIST_CACHE_LIMIT = 1000
_opcoes_cache: dict = {"circuitos": None, "localizacoes": None, "ts": 0.0}
_opcoes_cache_lock = threading.Lock()
_OPCOES_CACHE_TTL = 300


def _invalidate_list_cache():
    with _list_cache_lock:
        _list_cache["data"] = None
        _list_cache["json"] = None
        _list_cache["ts"] = 0.0


def _invalidate_opcoes_cache(kind: str | None = None):
    with _opcoes_cache_lock:
        if kind:
            _opcoes_cache[kind] = None
        else:
            _opcoes_cache["circuitos"] = None
            _opcoes_cache["localizacoes"] = None
        _opcoes_cache["ts"] = 0.0


def warm_list_cache(db: Session):
    """Pré-aquece o cache da listagem de cadastros durante o startup."""
    import logging as _logging
    _log = _logging.getLogger(__name__)
    try:
        t0 = _time.time()
        cadastros = (
            db.query(CadastroEvento)
            .filter(CadastroEvento.deleted_at.is_(None))
            .order_by(CadastroEvento.id.desc())
            .limit(_LIST_CACHE_LIMIT)
            .all()
        )
        items = [db_to_list_response(c) for c in cadastros]
        from fastapi.encoders import jsonable_encoder
        json_data = jsonable_encoder(items)
        with _list_cache_lock:
            _list_cache["data"] = items
            _list_cache["json"] = json_data
            _list_cache["ts"] = _time.time()
        _log.warning(f"[CadastrosCache] Pré-aquecido: {len(items)} eventos em {_time.time()-t0:.2f}s (json pré-serializado)")
    except Exception as e:
        _log.error(f"[CadastrosCache] Falha no pré-aquecimento: {e}")


from app.models.cadastro_evento import (
    CadastroEvento, CadastroCortesia, CadastroTaxa,
    CadastroKitProduto, CadastroKitProdutoItem,
    CadastroMerchan, CadastroMerchanItem,
    CadastroFaixaPrecoSite, CadastroFaixaPrecoGrupos,
    CircuitoProduto, Localizacao
)
from app.models.dimensoes import DimProjeto
from app.schemas.cadastro_evento import (
    CadastroEventoCreate, CadastroEventoUpdate, CadastroEventoResponse,
    InfoGeral, AtletasData, RetiradaKit, FaixasPrecoByKit,
    CortesiaItemResponse, TaxaItemResponse, KitProdutoResponse, ProdutoItemResponse,
    MerchanKitResponse, MerchanProdutoItemResponse,
    FaixaPrecoItemBase, CircuitoProdutoSchema, LocalizacaoSchema, AppaiData,
    CiclismoCenariosData
)

router = APIRouter(prefix="/cadastros", tags=["Cadastros"], dependencies=[Depends(get_current_user)])

_CADASTRO_EAGER = [
    selectinload(CadastroEvento.cortesias),
    selectinload(CadastroEvento.taxas),
    selectinload(CadastroEvento.kit_produtos).selectinload(CadastroKitProduto.produtos),
    selectinload(CadastroEvento.merchan_kits).selectinload(CadastroMerchan.itens),
    selectinload(CadastroEvento.faixas_preco_site),
    selectinload(CadastroEvento.faixas_preco_grupos),
]

_EVENT_FIELD_KEYS = [
    "info_geral",
    "retirada_kit",
    "atletas",
    "cortesias",
    "kit_produto",
    "merchan",
    "faixas_preco_site",
    "faixas_preco_grupos",
    "taxas",
]

_INFO_GERAL_UPDATE_FIELDS = [
    "projeto_id",
    "nome",
    "circuito_produto",
    "localizacao_evento",
    "ano_evento",
    "imagem_kv",
    "status",
    "modalidade",
    "sku",
    "produto",
    "tipo_evento",
    "lei",
    "capacidade_maxima",
    "cidade",
    "estado",
    "gratuito",
    "info_geral",
]

_EVENT_FIELD_UPDATE_ATTRS = {
    "info_geral": _INFO_GERAL_UPDATE_FIELDS,
    "retirada_kit": ["retirada_kit"],
    "atletas": ["atletas"],
    "cortesias": ["cortesias"],
    "kit_produto": ["kit_produto"],
    "merchan": ["merchan"],
    "faixas_preco_site": ["faixas_preco_site"],
    "faixas_preco_grupos": ["faixas_preco_grupos"],
    "taxas": ["taxas"],
}


def _event_field_permissions(db: Session, user, permission_attr: str) -> dict:
    if is_user_admin(user):
        return {field: True for field in _EVENT_FIELD_KEYS}
    if not getattr(user, "perfil_acesso_id", None):
        return {field: False for field in _EVENT_FIELD_KEYS}

    # Eventos keeps the historical UI behavior: fields are allowed unless a
    # profile-specific row explicitly denies them.
    perms = {field: True for field in _EVENT_FIELD_KEYS}
    rows = db.query(PerfilPermissaoCampo).filter(
        PerfilPermissaoCampo.perfil_acesso_id == user.perfil_acesso_id,
        PerfilPermissaoCampo.entidade == "eventos",
        PerfilPermissaoCampo.campo.in_(_EVENT_FIELD_KEYS),
    ).all()
    for row in rows:
        perms[row.campo] = bool(getattr(row, permission_attr, False))
    return perms


def _has_event_view_restrictions(db: Session, user) -> bool:
    return not all(_event_field_permissions(db, user, "pode_visualizar").values())


def _empty_event_field_value(field: str):
    if field == "info_geral":
        return InfoGeral()
    if field == "retirada_kit":
        return RetiradaKit()
    if field == "atletas":
        return AtletasData()
    if field in {"faixas_preco_site", "faixas_preco_grupos"}:
        return FaixasPrecoByKit()
    return []


def _filter_event_response_by_permissions(payload: dict, view_permissions: dict) -> dict:
    filtered = payload.copy()
    for field, allowed in view_permissions.items():
        if not allowed:
            filtered[field] = _empty_event_field_value(field)
    return filtered


def _strip_forbidden_update_fields(data: CadastroEventoUpdate, edit_permissions: dict) -> None:
    for field, allowed in edit_permissions.items():
        if allowed:
            continue
        for attr in _EVENT_FIELD_UPDATE_ATTRS[field]:
            if hasattr(data, attr):
                setattr(data, attr, None)


def _strip_forbidden_create_fields(data: CadastroEventoCreate, edit_permissions: dict) -> None:
    if not edit_permissions.get("info_geral", False):
        raise HTTPException(
            status_code=403,
            detail="Permissao insuficiente para criar evento sem acesso de edicao a Info Geral",
        )
    if not edit_permissions.get("retirada_kit", False):
        data.retirada_kit = RetiradaKit()
    if not edit_permissions.get("atletas", False):
        data.atletas = AtletasData()
    if not edit_permissions.get("cortesias", False):
        data.cortesias = []
    if not edit_permissions.get("kit_produto", False):
        data.kit_produto = []
    if not edit_permissions.get("merchan", False):
        data.merchan = []
    if not edit_permissions.get("faixas_preco_site", False):
        data.faixas_preco_site = FaixasPrecoByKit()
    if not edit_permissions.get("faixas_preco_grupos", False):
        data.faixas_preco_grupos = FaixasPrecoByKit()
    if not edit_permissions.get("taxas", False):
        data.taxas = []


def _update_projeto_fields(projeto: DimProjeto, cadastro: CadastroEvento):
    """Atualiza campos do dim_projeto a partir do cadastro."""
    projeto.produto = cadastro.produto or projeto.produto
    projeto.modalidade = cadastro.modalidade or projeto.modalidade
    projeto.tipo_evento = cadastro.tipo_evento or projeto.tipo_evento
    projeto.evento = cadastro.nome
    projeto.lei = cadastro.lei or projeto.lei
    projeto.status = cadastro.status or projeto.status
    projeto.capacidade_maxima = cadastro.capacidade_maxima
    projeto.imagem_kv = cadastro.imagem_kv
    if cadastro.data_evento:
        projeto.data_evento = cadastro.data_evento
    if cadastro.local:
        projeto.local_evento = cadastro.local
    if cadastro.cidade:
        projeto.cidade = cadastro.cidade
    elif cadastro.localizacao_evento and not projeto.cidade:
        projeto.cidade = cadastro.localizacao_evento
    if cadastro.estado:
        projeto.estado = cadastro.estado


def _sync_dim_projeto(db: Session, cadastro: CadastroEvento):
    """Sincroniza os dados do cadastro com a tabela dim_projeto para manter compatibilidade."""
    if not cadastro.sku or not cadastro.nome:
        return

    if cadastro.projeto_id:
        projeto = db.query(DimProjeto).filter(DimProjeto.id == cadastro.projeto_id).first()
        if projeto and projeto.codigo == cadastro.sku:
            _update_projeto_fields(projeto, cadastro)
            db.flush()
            return
        cadastro.projeto_id = None

    existing = db.query(DimProjeto).filter(DimProjeto.codigo == cadastro.sku).first()
    if existing:
        _update_projeto_fields(existing, cadastro)
        cadastro.projeto_id = existing.id
        db.flush()
    else:
        if cadastro.data_evento:
            novo_projeto = DimProjeto(
                codigo=cadastro.sku,
                produto=cadastro.produto or '',
                modalidade=cadastro.modalidade or 'Corrida',
                tipo_evento=cadastro.tipo_evento or 'Próprio',
                evento=cadastro.nome,
                lei=cadastro.lei or '',
                status=cadastro.status or 'Em andamento',
                data_evento=cadastro.data_evento,
                local_evento=cadastro.local or '',
                capacidade_maxima=cadastro.capacidade_maxima,
                imagem_kv=cadastro.imagem_kv,
                cidade=cadastro.cidade or cadastro.localizacao_evento or '',
                estado=cadastro.estado or ''
            )
            db.add(novo_projeto)
            db.flush()
            cadastro.projeto_id = novo_projeto.id
            db.flush()


def db_to_response(cadastro: CadastroEvento) -> dict:
    """Converte modelo do banco para formato de resposta"""
    info_geral = InfoGeral(
        data=cadastro.data_evento.isoformat() if cadastro.data_evento else "",
        horario_largada=cadastro.horario_largada or "",
        local=cadastro.local or "",
        distancias=cadastro.distancias or [],
        dias_encerramento_inscricao=cadastro.dias_encerramento_inscricao if cadastro.dias_encerramento_inscricao is not None else 2
    )
    
    atletas = AtletasData(
        site={"pago": cadastro.atletas_site_pago or 0, "tkt_medio": float(cadastro.atletas_site_tkt_medio or 0)},
        grupos={"pago": cadastro.atletas_grupos_pago or 0, "tkt_medio": float(cadastro.atletas_grupos_tkt_medio or 0)},
        cortesia=cadastro.atletas_cortesia or 0,
        appai=AppaiData(pago=cadastro.atletas_appai_pago or 0, tkt_medio=float(cadastro.atletas_appai_tkt_medio or 0)),
        ciclismo=CiclismoCenariosData(
            participacao_pago=cadastro.ciclismo_participacao_pago or 0,
            sem_bike_pago=cadastro.ciclismo_sem_bike_pago or 0,
            sem_bike_tkt_medio=float(cadastro.ciclismo_sem_bike_tkt_medio or 0),
            com_bike_pago=cadastro.ciclismo_com_bike_pago or 0,
            com_bike_tkt_medio=float(cadastro.ciclismo_com_bike_tkt_medio or 0),
        )
    )
    
    retirada_kit = RetiradaKit(
        local=cadastro.retirada_kit_local or "",
        data_horario=cadastro.retirada_kit_data_horario.isoformat() if cadastro.retirada_kit_data_horario else ""
    )
    
    cortesias = [
        CortesiaItemResponse(id=c.id, cliente=c.cliente, quantidade=c.quantidade)
        for c in cadastro.cortesias
    ]
    
    taxas = [
        TaxaItemResponse(
            id=t.id,
            valor_unitario=t.valor_unitario or Decimal("0"),
            percentual_inscricao=t.percentual_inscricao or Decimal("0"),
            validado=t.validado,
            data_validacao=t.data_validacao.isoformat() if t.data_validacao else None
        )
        for t in cadastro.taxas
    ]
    
    kit_produto = [
        KitProdutoResponse(
            id=kp.id,
            kit=kp.kit or "",
            ativo_categoria=kp.ativo_categoria,
            produtos=[
                ProdutoItemResponse(id=p.id, nome=p.nome, valor_unitario=p.valor_unitario or Decimal("0"))
                for p in kp.produtos
            ]
        )
        for kp in cadastro.kit_produtos
    ]

    merchan = [
        MerchanKitResponse(
            id=mk.id,
            kit=mk.kit or "",
            itens=[
                MerchanProdutoItemResponse(id=it.id, nome=it.nome, valor_venda=it.valor_venda or Decimal("0"))
                for it in mk.itens
            ]
        )
        for mk in cadastro.merchan_kits
    ]

    faixas_site_basico = [
        FaixaPrecoItemBase(faixa=f.faixa, qtd=f.qtd, tkt_medio=f.tkt_medio or Decimal("0"), total=f.total or Decimal("0"))
        for f in cadastro.faixas_preco_site if f.tipo_kit == "kit_basico"
    ]
    faixas_site_participacao = [
        FaixaPrecoItemBase(faixa=f.faixa, qtd=f.qtd, tkt_medio=f.tkt_medio or Decimal("0"), total=f.total or Decimal("0"))
        for f in cadastro.faixas_preco_site if f.tipo_kit == "kit_participacao"
    ]
    faixas_site_sem_bike = [
        FaixaPrecoItemBase(faixa=f.faixa, qtd=f.qtd, tkt_medio=f.tkt_medio or Decimal("0"), total=f.total or Decimal("0"))
        for f in cadastro.faixas_preco_site if f.tipo_kit == "kit_sem_bike"
    ]
    faixas_site_com_bike = [
        FaixaPrecoItemBase(faixa=f.faixa, qtd=f.qtd, tkt_medio=f.tkt_medio or Decimal("0"), total=f.total or Decimal("0"))
        for f in cadastro.faixas_preco_site if f.tipo_kit == "kit_com_bike"
    ]
    
    faixas_grupos_basico = [
        FaixaPrecoItemBase(faixa=f.faixa, qtd=f.qtd, tkt_medio=f.tkt_medio or Decimal("0"), total=f.total or Decimal("0"))
        for f in cadastro.faixas_preco_grupos if f.tipo_kit == "kit_basico"
    ]
    faixas_grupos_participacao = [
        FaixaPrecoItemBase(faixa=f.faixa, qtd=f.qtd, tkt_medio=f.tkt_medio or Decimal("0"), total=f.total or Decimal("0"))
        for f in cadastro.faixas_preco_grupos if f.tipo_kit == "kit_participacao"
    ]
    faixas_grupos_sem_bike = [
        FaixaPrecoItemBase(faixa=f.faixa, qtd=f.qtd, tkt_medio=f.tkt_medio or Decimal("0"), total=f.total or Decimal("0"))
        for f in cadastro.faixas_preco_grupos if f.tipo_kit == "kit_sem_bike"
    ]
    faixas_grupos_com_bike = [
        FaixaPrecoItemBase(faixa=f.faixa, qtd=f.qtd, tkt_medio=f.tkt_medio or Decimal("0"), total=f.total or Decimal("0"))
        for f in cadastro.faixas_preco_grupos if f.tipo_kit == "kit_com_bike"
    ]
    
    return {
        "id": cadastro.id,
        "projeto_id": cadastro.projeto_id,
        "nome": cadastro.nome,
        "id_evento_magento": cadastro.id_evento_magento,
        "circuito_produto": cadastro.circuito_produto or None,
        "localizacao_evento": cadastro.localizacao_evento or None,
        "ano_evento": cadastro.ano_evento or None,
        "imagem_kv": cadastro.imagem_kv or "",
        "status": cadastro.status or "Em andamento",
        "modalidade": cadastro.modalidade or "Corrida",
        "sku": cadastro.sku or None,
        "produto": cadastro.produto or None,
        "tipo_evento": cadastro.tipo_evento or None,
        "lei": cadastro.lei or None,
        "capacidade_maxima": cadastro.capacidade_maxima or None,
        "cidade": cadastro.cidade or None,
        "estado": cadastro.estado or None,
        "info_geral": info_geral,
        "atletas": atletas,
        "cortesias": cortesias,
        "taxas": taxas,
        "retirada_kit": retirada_kit,
        "kit_produto": kit_produto,
        "merchan": merchan,
        "faixas_preco_site": FaixasPrecoByKit(kit_basico=faixas_site_basico, kit_participacao=faixas_site_participacao, kit_sem_bike=faixas_site_sem_bike, kit_com_bike=faixas_site_com_bike),
        "faixas_preco_grupos": FaixasPrecoByKit(kit_basico=faixas_grupos_basico, kit_participacao=faixas_grupos_participacao, kit_sem_bike=faixas_grupos_sem_bike, kit_com_bike=faixas_grupos_com_bike),
        "created_at": cadastro.created_at,
        "updated_at": cadastro.updated_at
    }


def db_to_list_response(cadastro: CadastroEvento) -> dict:
    """Versão leve de db_to_response para listagem — sem relacionamentos aninhados."""
    info_geral = InfoGeral(
        data=cadastro.data_evento.isoformat() if cadastro.data_evento else "",
        horario_largada=cadastro.horario_largada or "",
        local=cadastro.local or "",
        distancias=cadastro.distancias or [],
        dias_encerramento_inscricao=cadastro.dias_encerramento_inscricao if cadastro.dias_encerramento_inscricao is not None else 2
    )
    atletas = AtletasData(
        site={"pago": cadastro.atletas_site_pago or 0, "tkt_medio": float(cadastro.atletas_site_tkt_medio or 0)},
        grupos={"pago": cadastro.atletas_grupos_pago or 0, "tkt_medio": float(cadastro.atletas_grupos_tkt_medio or 0)},
        cortesia=cadastro.atletas_cortesia or 0,
        appai=AppaiData(pago=cadastro.atletas_appai_pago or 0, tkt_medio=float(cadastro.atletas_appai_tkt_medio or 0)),
        ciclismo=CiclismoCenariosData(
            participacao_pago=cadastro.ciclismo_participacao_pago or 0,
            sem_bike_pago=cadastro.ciclismo_sem_bike_pago or 0,
            sem_bike_tkt_medio=float(cadastro.ciclismo_sem_bike_tkt_medio or 0),
            com_bike_pago=cadastro.ciclismo_com_bike_pago or 0,
            com_bike_tkt_medio=float(cadastro.ciclismo_com_bike_tkt_medio or 0),
        )
    )
    retirada_kit = RetiradaKit(
        local=cadastro.retirada_kit_local or "",
        data_horario=cadastro.retirada_kit_data_horario.isoformat() if cadastro.retirada_kit_data_horario else ""
    )
    return {
        "id": cadastro.id,
        "projeto_id": cadastro.projeto_id,
        "nome": cadastro.nome,
        "id_evento_magento": cadastro.id_evento_magento,
        "circuito_produto": cadastro.circuito_produto or None,
        "localizacao_evento": cadastro.localizacao_evento or None,
        "ano_evento": cadastro.ano_evento or None,
        "imagem_kv": cadastro.imagem_kv or "",
        "status": cadastro.status or "Em andamento",
        "modalidade": cadastro.modalidade or "Corrida",
        "sku": cadastro.sku or None,
        "produto": cadastro.produto or None,
        "tipo_evento": cadastro.tipo_evento or None,
        "lei": cadastro.lei or None,
        "capacidade_maxima": cadastro.capacidade_maxima or None,
        "cidade": cadastro.cidade or None,
        "estado": cadastro.estado or None,
        "info_geral": info_geral,
        "atletas": atletas,
        "cortesias": [],
        "taxas": [],
        "retirada_kit": retirada_kit,
        "kit_produto": [],
        "merchan": [],
        "faixas_preco_site": FaixasPrecoByKit(kit_basico=[], kit_participacao=[]),
        "faixas_preco_grupos": FaixasPrecoByKit(kit_basico=[], kit_participacao=[]),
        "created_at": cadastro.created_at,
        "updated_at": cadastro.updated_at
    }


@router.get("/")
def listar_cadastros(
    skip: int = 0,
    limit: int = 1000,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(require_permission("eventos", "pode_visualizar"))
):
    """Lista todos os cadastros de eventos ativos (não deletados) — resposta leve sem relacionamentos."""
    t0 = _time.time()
    try:
        from app.services.event_status_service import auto_concluir_eventos_passados
        if auto_concluir_eventos_passados(db) > 0:
            _invalidate_list_cache()
    except Exception as _auto_err:
        logger.error(f"[CadastrosCache] auto-conclusão de eventos falhou (não bloqueante): {_auto_err}")
    if not status and skip == 0:
        with _list_cache_lock:
            cached_json = _list_cache.get("json")
            cached_data = _list_cache["data"]
            age = _time.time() - _list_cache["ts"]
        restricted_view = _has_event_view_restrictions(db, current_user)
        if cached_json is not None and age < _LIST_CACHE_TTL and not restricted_view:
            logger.warning(f"[CadastrosCache] HIT: {len(cached_data)} eventos em {_time.time()-t0:.4f}s (age={age:.0f}s)")
            return JSONResponse(content=cached_json[:limit])
        if cached_data is not None and age < _LIST_CACHE_TTL:
            logger.warning(f"[CadastrosCache] HIT(raw): {len(cached_data)} eventos em {_time.time()-t0:.4f}s")
            items = cached_data[:limit]
            if restricted_view:
                view_permissions = _event_field_permissions(db, current_user, "pode_visualizar")
                return [_filter_event_response_by_permissions(item, view_permissions) for item in items]
            return items

    logger.warning(f"[CadastrosCache] MISS — consultando banco (status={status}, skip={skip})")
    query = db.query(CadastroEvento).filter(CadastroEvento.deleted_at.is_(None))

    if status:
        query = query.filter(CadastroEvento.status == status)

    cadastros = query.order_by(CadastroEvento.id.desc()).offset(skip).limit(limit).all()
    items = [db_to_list_response(c) for c in cadastros]
    logger.warning(f"[CadastrosCache] DB query: {len(items)} eventos em {_time.time()-t0:.4f}s")

    if not status and skip == 0:
        from fastapi.encoders import jsonable_encoder
        json_data = jsonable_encoder(items)
        with _list_cache_lock:
            _list_cache["data"] = items
            _list_cache["json"] = json_data
            _list_cache["ts"] = _time.time()

    if _has_event_view_restrictions(db, current_user):
        view_permissions = _event_field_permissions(db, current_user, "pode_visualizar")
        return [_filter_event_response_by_permissions(item, view_permissions) for item in items]
    return items


@router.get("/lixeira/itens")
def listar_lixeira(db: Session = Depends(get_db), current_user=Depends(require_permission("eventos", "pode_visualizar"))):
    """Lista cadastros deletados (lixeira) — últimos 30 dias"""
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(days=30)
    cadastros = (
        db.query(CadastroEvento)
        .options(*_CADASTRO_EAGER)
        .filter(CadastroEvento.deleted_at.isnot(None))
        .filter(CadastroEvento.deleted_at >= cutoff)
        .order_by(CadastroEvento.deleted_at.desc())
        .all()
    )
    view_permissions = _event_field_permissions(db, current_user, "pode_visualizar")
    return [
        {
            **_filter_event_response_by_permissions(db_to_response(c), view_permissions),
            "deleted_at": c.deleted_at.isoformat() if c.deleted_at else None,
        }
        for c in cadastros
    ]


@router.post("/{cadastro_id}/restaurar")
def restaurar_cadastro(cadastro_id: int, db: Session = Depends(get_db), current_user=Depends(require_permission('eventos', 'pode_editar'))):
    """Restaura um cadastro da lixeira"""
    cadastro = db.query(CadastroEvento).filter(CadastroEvento.id == cadastro_id).first()
    if not cadastro:
        raise HTTPException(status_code=404, detail="Cadastro não encontrado")
    if cadastro.deleted_at is None:
        raise HTTPException(status_code=400, detail="Cadastro não está na lixeira")
    cadastro.deleted_at = None
    db.commit()
    _invalidate_list_cache()
    return {"message": "Cadastro restaurado com sucesso"}


@router.get("/{cadastro_id}", response_model=CadastroEventoResponse)
def obter_cadastro(cadastro_id: int, db: Session = Depends(get_db), current_user=Depends(require_permission("eventos", "pode_visualizar"))):
    """Obtém um cadastro específico (não deletado)"""
    cadastro = (
        db.query(CadastroEvento)
        .options(*_CADASTRO_EAGER)
        .filter(CadastroEvento.id == cadastro_id, CadastroEvento.deleted_at.is_(None))
        .first()
    )
    
    if not cadastro:
        raise HTTPException(status_code=404, detail="Cadastro não encontrado")
    
    view_permissions = _event_field_permissions(db, current_user, "pode_visualizar")
    return _filter_event_response_by_permissions(db_to_response(cadastro), view_permissions)


@router.post("/", response_model=CadastroEventoResponse)
def criar_cadastro(data: CadastroEventoCreate, db: Session = Depends(get_db), current_user=Depends(require_permission('eventos', 'pode_editar'))):
    """Cria um novo cadastro de evento"""
    edit_permissions = _event_field_permissions(db, current_user, "pode_editar")
    _strip_forbidden_create_fields(data, edit_permissions)

    
    if data.sku and data.sku.strip():
        existing_sku = db.query(CadastroEvento).filter(
            CadastroEvento.sku == data.sku.strip(),
            CadastroEvento.deleted_at.is_(None)
        ).first()
        if existing_sku:
            raise HTTPException(
                status_code=409,
                detail=f"O SKU '{data.sku}' já está em uso pelo evento '{existing_sku.nome}'."
            )
    
    data_evento = None
    if data.info_geral.data:
        try:
            data_evento = date.fromisoformat(data.info_geral.data)
        except (ValueError, TypeError):
            pass
    
    retirada_dt = None
    if data.retirada_kit.data_horario:
        try:
            retirada_dt = datetime.fromisoformat(data.retirada_kit.data_horario)
        except (ValueError, TypeError):
            pass
    
    cadastro = CadastroEvento(
        projeto_id=data.projeto_id,
        nome=data.nome,
        circuito_produto=data.circuito_produto,
        localizacao_evento=data.localizacao_evento,
        ano_evento=data.ano_evento,
        imagem_kv=data.imagem_kv,
        status=data.status,
        modalidade=data.modalidade,
        sku=data.sku.strip() if data.sku else data.sku,
        produto=data.produto,
        tipo_evento=data.tipo_evento,
        lei=data.lei,
        capacidade_maxima=data.capacidade_maxima,
        cidade=data.cidade,
        estado=data.estado,
        gratuito=data.gratuito,
        data_evento=data_evento,
        horario_largada=data.info_geral.horario_largada,
        local=data.info_geral.local,
        distancias=data.info_geral.distancias,
        dias_encerramento_inscricao=data.info_geral.dias_encerramento_inscricao,
        atletas_site_pago=data.atletas.site.get("pago", 0),
        atletas_site_tkt_medio=Decimal(str(data.atletas.site.get("tkt_medio", 0))),
        atletas_grupos_pago=data.atletas.grupos.get("pago", 0),
        atletas_grupos_tkt_medio=Decimal(str(data.atletas.grupos.get("tkt_medio", 0))),
        atletas_cortesia=data.atletas.cortesia,
        atletas_appai_pago=data.atletas.appai.pago if data.atletas.appai else 0,
        atletas_appai_tkt_medio=Decimal(str(data.atletas.appai.tkt_medio)) if data.atletas.appai else Decimal("0"),
        ciclismo_participacao_pago=data.atletas.ciclismo.participacao_pago if data.atletas.ciclismo else 0,
        ciclismo_sem_bike_pago=data.atletas.ciclismo.sem_bike_pago if data.atletas.ciclismo else 0,
        ciclismo_sem_bike_tkt_medio=Decimal(str(data.atletas.ciclismo.sem_bike_tkt_medio)) if data.atletas.ciclismo else Decimal("0"),
        ciclismo_com_bike_pago=data.atletas.ciclismo.com_bike_pago if data.atletas.ciclismo else 0,
        ciclismo_com_bike_tkt_medio=Decimal(str(data.atletas.ciclismo.com_bike_tkt_medio)) if data.atletas.ciclismo else Decimal("0"),
        retirada_kit_local=data.retirada_kit.local,
        retirada_kit_data_horario=retirada_dt
    )
    
    if data.modalidade and data.modalidade.lower() == 'ciclismo' and data.atletas.ciclismo:
        cic = data.atletas.ciclismo
        agg_pago = cic.participacao_pago + cic.sem_bike_pago + cic.com_bike_pago
        agg_tkt = (Decimal(str(cic.sem_bike_pago * cic.sem_bike_tkt_medio + cic.com_bike_pago * cic.com_bike_tkt_medio)) / Decimal(str(agg_pago))) if agg_pago > 0 else Decimal("0")
        cadastro.atletas_site_pago = agg_pago
        cadastro.atletas_site_tkt_medio = round(agg_tkt, 2)
        cadastro.atletas_appai_pago = 0
        cadastro.atletas_appai_tkt_medio = Decimal("0")

    db.add(cadastro)
    db.flush()
    
    _sync_dim_projeto(db, cadastro)
    
    for cortesia in data.cortesias:
        db.add(CadastroCortesia(
            cadastro_id=cadastro.id,
            cliente=cortesia.cliente,
            quantidade=cortesia.quantidade
        ))
    
    for taxa in data.taxas:
        data_validacao = None
        if taxa.data_validacao:
            try:
                data_validacao = date.fromisoformat(taxa.data_validacao)
            except (ValueError, TypeError):
                pass
        
        db.add(CadastroTaxa(
            cadastro_id=cadastro.id,
            valor_unitario=taxa.valor_unitario,
            percentual_inscricao=taxa.percentual_inscricao,
            validado=taxa.validado,
            data_validacao=data_validacao
        ))
    
    for kit in data.kit_produto:
        kit_obj = CadastroKitProduto(
            cadastro_id=cadastro.id,
            kit=kit.kit,
            ativo_categoria=kit.ativo_categoria
        )
        db.add(kit_obj)
        db.flush()
        
        for produto in kit.produtos:
            db.add(CadastroKitProdutoItem(
                kit_produto_id=kit_obj.id,
                nome=produto.nome,
                valor_unitario=produto.valor_unitario
            ))

    for mk in data.merchan:
        mk_obj = CadastroMerchan(
            cadastro_id=cadastro.id,
            kit=mk.kit
        )
        db.add(mk_obj)
        db.flush()
        for item in mk.itens:
            db.add(CadastroMerchanItem(
                merchan_id=mk_obj.id,
                nome=item.nome,
                valor_venda=item.valor_venda
            ))

    for tipo_kit_key in ["kit_basico", "kit_participacao", "kit_sem_bike", "kit_com_bike"]:
        for faixa in getattr(data.faixas_preco_site, tipo_kit_key, []):
            db.add(CadastroFaixaPrecoSite(
                cadastro_id=cadastro.id,
                tipo_kit=tipo_kit_key,
                faixa=faixa.faixa,
                qtd=faixa.qtd,
                tkt_medio=faixa.tkt_medio,
                total=faixa.total
            ))

    for tipo_kit_key in ["kit_basico", "kit_participacao", "kit_sem_bike", "kit_com_bike"]:
        for faixa in getattr(data.faixas_preco_grupos, tipo_kit_key, []):
            db.add(CadastroFaixaPrecoGrupos(
                cadastro_id=cadastro.id,
                tipo_kit=tipo_kit_key,
                faixa=faixa.faixa,
                qtd=faixa.qtd,
                tkt_medio=faixa.tkt_medio,
                total=faixa.total
            ))
    
    db.commit()
    db.refresh(cadastro)
    _invalidate_list_cache()
    view_permissions = _event_field_permissions(db, current_user, "pode_visualizar")
    return _filter_event_response_by_permissions(db_to_response(cadastro), view_permissions)


@router.put("/{cadastro_id}", response_model=CadastroEventoResponse)
def atualizar_cadastro(cadastro_id: int, data: CadastroEventoUpdate, db: Session = Depends(get_db), current_user=Depends(require_permission('eventos', 'pode_editar'))):
    """Atualiza um cadastro existente"""
    cadastro = db.query(CadastroEvento).filter(CadastroEvento.id == cadastro_id).first()
    
    if not cadastro:
        raise HTTPException(status_code=404, detail="Cadastro não encontrado")
    
    edit_permissions = _event_field_permissions(db, current_user, "pode_editar")
    _strip_forbidden_update_fields(data, edit_permissions)

    if data.sku is not None and data.sku.strip():
        sku_trimmed = data.sku.strip()
        existing_sku = db.query(CadastroEvento).filter(
            CadastroEvento.sku == sku_trimmed,
            CadastroEvento.id != cadastro_id
        ).first()
        if existing_sku:
            raise HTTPException(
                status_code=409,
                detail=f"O SKU '{sku_trimmed}' já está em uso pelo evento '{existing_sku.nome}'."
            )
    
    if data.projeto_id is not None:
        cadastro.projeto_id = data.projeto_id
    if data.nome is not None:
        cadastro.nome = data.nome
    if data.circuito_produto is not None:
        cadastro.circuito_produto = data.circuito_produto
    if data.localizacao_evento is not None:
        cadastro.localizacao_evento = data.localizacao_evento
    if data.ano_evento is not None:
        cadastro.ano_evento = data.ano_evento
    if data.imagem_kv is not None:
        cadastro.imagem_kv = data.imagem_kv
    if data.status is not None:
        cadastro.status = data.status
    if data.modalidade is not None:
        cadastro.modalidade = data.modalidade
    if data.sku is not None:
        cadastro.sku = data.sku.strip()
    if data.produto is not None:
        cadastro.produto = data.produto
    if data.tipo_evento is not None:
        cadastro.tipo_evento = data.tipo_evento
    if data.lei is not None:
        cadastro.lei = data.lei
    if data.capacidade_maxima is not None:
        cadastro.capacidade_maxima = data.capacidade_maxima
    if data.cidade is not None:
        cadastro.cidade = data.cidade
    if data.estado is not None:
        cadastro.estado = data.estado
    if data.gratuito is not None:
        cadastro.gratuito = data.gratuito
    
    if data.info_geral is not None:
        if data.info_geral.data:
            try:
                cadastro.data_evento = date.fromisoformat(data.info_geral.data)
            except (ValueError, TypeError):
                pass
        cadastro.horario_largada = data.info_geral.horario_largada
        cadastro.local = data.info_geral.local
        cadastro.distancias = data.info_geral.distancias
        if data.info_geral.dias_encerramento_inscricao is not None:
            cadastro.dias_encerramento_inscricao = data.info_geral.dias_encerramento_inscricao
    
    if data.atletas is not None:
        cadastro.atletas_site_pago = data.atletas.site.get("pago", 0)
        cadastro.atletas_site_tkt_medio = Decimal(str(data.atletas.site.get("tkt_medio", 0)))
        cadastro.atletas_grupos_pago = data.atletas.grupos.get("pago", 0)
        cadastro.atletas_grupos_tkt_medio = Decimal(str(data.atletas.grupos.get("tkt_medio", 0)))
        cadastro.atletas_cortesia = data.atletas.cortesia
        if data.atletas.appai:
            cadastro.atletas_appai_pago = data.atletas.appai.pago
            cadastro.atletas_appai_tkt_medio = Decimal(str(data.atletas.appai.tkt_medio))
        effective_modalidade = (data.modalidade or cadastro.modalidade or '').lower()
        if effective_modalidade == 'ciclismo' and data.atletas.ciclismo:
            cadastro.ciclismo_participacao_pago = data.atletas.ciclismo.participacao_pago
            cadastro.ciclismo_sem_bike_pago = data.atletas.ciclismo.sem_bike_pago
            cadastro.ciclismo_sem_bike_tkt_medio = Decimal(str(data.atletas.ciclismo.sem_bike_tkt_medio))
            cadastro.ciclismo_com_bike_pago = data.atletas.ciclismo.com_bike_pago
            cadastro.ciclismo_com_bike_tkt_medio = Decimal(str(data.atletas.ciclismo.com_bike_tkt_medio))
            cic = data.atletas.ciclismo
            agg_pago = cic.participacao_pago + cic.sem_bike_pago + cic.com_bike_pago
            agg_tkt = (Decimal(str(cic.sem_bike_pago * cic.sem_bike_tkt_medio + cic.com_bike_pago * cic.com_bike_tkt_medio)) / Decimal(str(agg_pago))) if agg_pago > 0 else Decimal("0")
            cadastro.atletas_site_pago = agg_pago
            cadastro.atletas_site_tkt_medio = round(agg_tkt, 2)
            cadastro.atletas_appai_pago = 0
            cadastro.atletas_appai_tkt_medio = Decimal("0")
    
    if data.retirada_kit is not None:
        cadastro.retirada_kit_local = data.retirada_kit.local
        if data.retirada_kit.data_horario:
            try:
                cadastro.retirada_kit_data_horario = datetime.fromisoformat(data.retirada_kit.data_horario)
            except (ValueError, TypeError):
                pass
    
    if data.cortesias is not None and len(data.cortesias) > 0:
        for c in cadastro.cortesias:
            db.delete(c)
        for cortesia in data.cortesias:
            db.add(CadastroCortesia(
                cadastro_id=cadastro.id,
                cliente=cortesia.cliente,
                quantidade=cortesia.quantidade
            ))

    if data.taxas is not None and len(data.taxas) > 0:
        for t in cadastro.taxas:
            db.delete(t)
        for taxa in data.taxas:
            data_validacao = None
            if taxa.data_validacao:
                try:
                    data_validacao = date.fromisoformat(taxa.data_validacao)
                except (ValueError, TypeError):
                    pass
            db.add(CadastroTaxa(
                cadastro_id=cadastro.id,
                valor_unitario=taxa.valor_unitario,
                percentual_inscricao=taxa.percentual_inscricao,
                validado=taxa.validado,
                data_validacao=data_validacao
            ))

    if data.kit_produto is not None and len(data.kit_produto) > 0:
        for kp in cadastro.kit_produtos:
            db.delete(kp)
        db.flush()
        for kit in data.kit_produto:
            kit_obj = CadastroKitProduto(
                cadastro_id=cadastro.id,
                kit=kit.kit,
                ativo_categoria=kit.ativo_categoria
            )
            db.add(kit_obj)
            db.flush()
            for produto in kit.produtos:
                db.add(CadastroKitProdutoItem(
                    kit_produto_id=kit_obj.id,
                    nome=produto.nome,
                    valor_unitario=produto.valor_unitario
                ))

    if data.merchan is not None and len(data.merchan) > 0:
        for mk in cadastro.merchan_kits:
            db.delete(mk)
        db.flush()
        for mk in data.merchan:
            mk_obj = CadastroMerchan(
                cadastro_id=cadastro.id,
                kit=mk.kit
            )
            db.add(mk_obj)
            db.flush()
            for item in mk.itens:
                db.add(CadastroMerchanItem(
                    merchan_id=mk_obj.id,
                    nome=item.nome,
                    valor_venda=item.valor_venda
                ))

    _all_kit_types = ["kit_basico", "kit_participacao", "kit_sem_bike", "kit_com_bike"]
    _faixas_site_tem_dados = data.faixas_preco_site is not None and any(
        len(getattr(data.faixas_preco_site, k, [])) > 0 for k in _all_kit_types
    )
    if _faixas_site_tem_dados:
        for f in cadastro.faixas_preco_site:
            db.delete(f)
        for tipo_kit_key in _all_kit_types:
            for faixa in getattr(data.faixas_preco_site, tipo_kit_key, []):
                db.add(CadastroFaixaPrecoSite(
                    cadastro_id=cadastro.id,
                    tipo_kit=tipo_kit_key,
                    faixa=faixa.faixa,
                    qtd=faixa.qtd,
                    tkt_medio=faixa.tkt_medio,
                    total=faixa.total
                ))

    _faixas_grupos_tem_dados = data.faixas_preco_grupos is not None and any(
        len(getattr(data.faixas_preco_grupos, k, [])) > 0 for k in _all_kit_types
    )
    if _faixas_grupos_tem_dados:
        for f in cadastro.faixas_preco_grupos:
            db.delete(f)
        for tipo_kit_key in _all_kit_types:
            for faixa in getattr(data.faixas_preco_grupos, tipo_kit_key, []):
                db.add(CadastroFaixaPrecoGrupos(
                    cadastro_id=cadastro.id,
                    tipo_kit=tipo_kit_key,
                    faixa=faixa.faixa,
                    qtd=faixa.qtd,
                    tkt_medio=faixa.tkt_medio,
                    total=faixa.total
                ))
    
    _sync_dim_projeto(db, cadastro)
    
    db.commit()
    db.refresh(cadastro)
    
    if cadastro.projeto_id:
        try:
            from app.api.routes.marketing import invalidate_cadastro_caches
            invalidate_cadastro_caches(cadastro.projeto_id)
        except Exception:
            pass
    _invalidate_list_cache()
    view_permissions = _event_field_permissions(db, current_user, "pode_visualizar")
    return _filter_event_response_by_permissions(db_to_response(cadastro), view_permissions)


@router.post("/resync-projetos")
def resync_dim_projetos(db: Session = Depends(get_db), current_user=Depends(require_admin())):
    """Re-sincroniza todos os cadastro_evento com dim_projeto, corrigindo links incorretos."""
    cadastros = db.query(CadastroEvento).all()
    fixed = 0
    created = 0
    for cad in cadastros:
        if not cad.sku or not cad.nome:
            continue
        old_pid = cad.projeto_id
        if cad.projeto_id:
            proj = db.query(DimProjeto).filter(DimProjeto.id == cad.projeto_id).first()
            if proj and proj.codigo == cad.sku:
                continue
            cad.projeto_id = None
        existing = db.query(DimProjeto).filter(DimProjeto.codigo == cad.sku).first()
        if existing:
            _update_projeto_fields(existing, cad)
            cad.projeto_id = existing.id
            if old_pid != existing.id:
                fixed += 1
        elif cad.data_evento:
            novo = DimProjeto(
                codigo=cad.sku,
                produto=cad.produto or '',
                modalidade=cad.modalidade or 'Corrida',
                tipo_evento=cad.tipo_evento or 'Próprio',
                evento=cad.nome,
                lei=cad.lei or '',
                status=cad.status or 'Em andamento',
                data_evento=cad.data_evento,
                local_evento=cad.local or '',
                capacidade_maxima=cad.capacidade_maxima,
                imagem_kv=cad.imagem_kv
            )
            db.add(novo)
            db.flush()
            cad.projeto_id = novo.id
            created += 1
    db.commit()
    return {"message": f"Re-sync completo. {fixed} links corrigidos, {created} projetos criados."}


@router.delete("/{cadastro_id}")
def deletar_cadastro(cadastro_id: int, db: Session = Depends(get_db), current_user=Depends(require_permission('eventos', 'pode_editar'))):
    """Move um cadastro para a lixeira (soft-delete — recuperável por 30 dias)"""
    cadastro = db.query(CadastroEvento).filter(
        CadastroEvento.id == cadastro_id,
        CadastroEvento.deleted_at.is_(None)
    ).first()
    
    if not cadastro:
        raise HTTPException(status_code=404, detail="Cadastro não encontrado")
    
    cadastro.deleted_at = datetime.utcnow()
    db.commit()
    _invalidate_list_cache()
    return {"message": "Cadastro movido para a lixeira. Você tem 30 dias para restaurá-lo."}


@router.get("/opcoes/circuitos", response_model=List[CircuitoProdutoSchema])
def listar_circuitos(db: Session = Depends(get_db), current_user=Depends(require_permission("eventos", "pode_visualizar"))):
    now = _time.time()
    with _opcoes_cache_lock:
        cached = _opcoes_cache["circuitos"]
        if cached is not None and (now - _opcoes_cache["ts"]) < _OPCOES_CACHE_TTL:
            return cached
    rows = db.query(CircuitoProduto).order_by(CircuitoProduto.nome).all()
    with _opcoes_cache_lock:
        _opcoes_cache["circuitos"] = rows
        _opcoes_cache["ts"] = now
    return rows


@router.post("/opcoes/circuitos", response_model=CircuitoProdutoSchema)
def criar_circuito(data: CircuitoProdutoSchema, db: Session = Depends(get_db), current_user=Depends(require_permission('eventos', 'pode_editar'))):
    existing = db.query(CircuitoProduto).filter(CircuitoProduto.nome == data.nome).first()
    if existing:
        raise HTTPException(status_code=409, detail="Circuito já existe")
    item = CircuitoProduto(nome=data.nome)
    db.add(item)
    db.commit()
    db.refresh(item)
    _invalidate_opcoes_cache("circuitos")
    return item


@router.put("/opcoes/circuitos/{item_id}", response_model=CircuitoProdutoSchema)
def atualizar_circuito(item_id: int, data: CircuitoProdutoSchema, db: Session = Depends(get_db), current_user=Depends(require_permission('eventos', 'pode_editar'))):
    item = db.query(CircuitoProduto).filter(CircuitoProduto.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Circuito não encontrado")
    item.nome = data.nome
    db.commit()
    db.refresh(item)
    _invalidate_opcoes_cache("circuitos")
    return item


@router.delete("/opcoes/circuitos/{item_id}")
def deletar_circuito(item_id: int, db: Session = Depends(get_db), current_user=Depends(require_permission('eventos', 'pode_editar'))):
    item = db.query(CircuitoProduto).filter(CircuitoProduto.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Circuito não encontrado")
    db.delete(item)
    db.commit()
    _invalidate_opcoes_cache("circuitos")
    return {"message": "Circuito deletado"}


@router.get("/opcoes/localizacoes", response_model=List[LocalizacaoSchema])
def listar_localizacoes(db: Session = Depends(get_db), current_user=Depends(require_permission("eventos", "pode_visualizar"))):
    now = _time.time()
    with _opcoes_cache_lock:
        cached = _opcoes_cache["localizacoes"]
        if cached is not None and (now - _opcoes_cache["ts"]) < _OPCOES_CACHE_TTL:
            return cached
    rows = db.query(Localizacao).order_by(Localizacao.nome).all()
    with _opcoes_cache_lock:
        _opcoes_cache["localizacoes"] = rows
        _opcoes_cache["ts"] = now
    return rows


@router.post("/opcoes/localizacoes", response_model=LocalizacaoSchema)
def criar_localizacao(data: LocalizacaoSchema, db: Session = Depends(get_db), current_user=Depends(require_permission('eventos', 'pode_editar'))):
    existing = db.query(Localizacao).filter(Localizacao.nome == data.nome).first()
    if existing:
        raise HTTPException(status_code=409, detail="Localização já existe")
    item = Localizacao(nome=data.nome)
    db.add(item)
    db.commit()
    db.refresh(item)
    _invalidate_opcoes_cache("localizacoes")
    return item


@router.put("/opcoes/localizacoes/{item_id}", response_model=LocalizacaoSchema)
def atualizar_localizacao(item_id: int, data: LocalizacaoSchema, db: Session = Depends(get_db), current_user=Depends(require_permission('eventos', 'pode_editar'))):
    item = db.query(Localizacao).filter(Localizacao.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Localização não encontrada")
    item.nome = data.nome
    db.commit()
    db.refresh(item)
    _invalidate_opcoes_cache("localizacoes")
    return item


@router.delete("/opcoes/localizacoes/{item_id}")
def deletar_localizacao(item_id: int, db: Session = Depends(get_db), current_user=Depends(require_permission('eventos', 'pode_editar'))):
    item = db.query(Localizacao).filter(Localizacao.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Localização não encontrada")
    db.delete(item)
    db.commit()
    _invalidate_opcoes_cache("localizacoes")
    return {"message": "Localização deletada"}
