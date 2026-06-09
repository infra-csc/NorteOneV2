from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import extract, text
from sqlalchemy.exc import IntegrityError
from datetime import timedelta
from typing import List, Optional
from datetime import datetime
from zoneinfo import ZoneInfo
import logging
import re
import csv
import io
import threading
import time as _time

from ...core.database import get_db
from ...core.security import get_current_user, is_user_admin, require_permission
from ...models.projecao import (
    AreaProjecao, AreaProjecaoUsuario, ProjecaoInscritos,
    ProjecaoInscritosHistorico, ProjecaoInscritosCliente, ProjecaoInscritosKit, ProjecaoCutoffRule,
    ProjecaoCutoffEventoArea, ProjecaoAutoLockConfig,
    ProjecaoCorteConfig, ProjecaoCorteSnapshot, ProjecaoKitCorteSnapshot,
    KIT_CAMISETA_AVULSA_ORIGEM,
)
from ...models.cadastro_evento import CadastroEvento
from ...models.user import Usuario
from ...models.dimensoes import SkuMapping, EventoGrupo
from ...schemas.projecao import (
    AreaProjecaoCreate, AreaProjecaoResponse, AreaProjecaoDetailResponse, AreaProjecaoUsuarioResponse,
    AreaProjecaoUsuarioBulk,
    ProjecaoInscritosCreate, ProjecaoInscritosUpdate, ProjecaoInscritosResponse,
    ClienteProjecaoResponse, KitProjecaoResponse, KitProjecaoItem,
    HistoricoResponse,
    ConsolidadoEventoResponse, ConsolidadoAreaItem, CamisetaAvulsaInfoResponse,
    CutoffRuleCreate, CutoffRuleUpdate, CutoffRuleResponse,
    PendenciaItem, PendenciasResponse, AreaPendenteItem,
    AreaCutoffCustomizadoToggle, CutoffEventoAreaUpsert, CutoffEventoAreaResponse,
    AutoLockConfigUpdate, AutoLockConfigResponse,
    CorteConfigUpdate, CorteConfigResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projecao", tags=["Projeção de Inscritos"])

PROJECAO_PERMISSION = "projecao_inscritos"


def _normalize_kit_nome(nome: str) -> str:
    """Normaliza nome de kit p/ comparação: sem acentos, minúsculo,
    espaços internos colapsados. Evita drift no cálculo de camisetas."""
    if not nome:
        return ""
    import unicodedata
    s = unicodedata.normalize("NFKD", nome)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


_AREAS_CACHE_TTL = 300
_areas_cache = {"data": None, "ts": 0.0}
_areas_cache_lock = threading.Lock()
_CUTOFF_RULES_CACHE_TTL = 300
_cutoff_rules_cache: dict = {}
_cutoff_rules_cache_lock = threading.Lock()
_USER_AREA_IDS_CACHE_TTL = 300
_user_area_ids_cache: dict[int, dict] = {}
_user_area_ids_cache_lock = threading.Lock()


def _invalidate_areas_cache():
    with _areas_cache_lock:
        _areas_cache["data"] = None
        _areas_cache["ts"] = 0.0


def _invalidate_cutoff_rules_cache():
    with _cutoff_rules_cache_lock:
        _cutoff_rules_cache.clear()


def _invalidate_user_area_ids_cache():
    with _user_area_ids_cache_lock:
        _user_area_ids_cache.clear()


def _get_user_area_ids(db: Session, user_id: int) -> set:
    now = _time.time()
    with _user_area_ids_cache_lock:
        cached = _user_area_ids_cache.get(user_id)
        if cached and (now - cached["ts"]) < _USER_AREA_IDS_CACHE_TTL:
            return cached["data"]
    rows = db.query(AreaProjecaoUsuario.area_projecao_id).filter(
        AreaProjecaoUsuario.usuario_id == user_id
    ).all()
    area_ids = {r[0] for r in rows}
    with _user_area_ids_cache_lock:
        _user_area_ids_cache[user_id] = {"data": area_ids, "ts": now}
    return area_ids


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
    now = _time.time()
    with _areas_cache_lock:
        cached = _areas_cache["data"]
        if cached is not None and (now - _areas_cache["ts"]) < _AREAS_CACHE_TTL:
            return cached
    rows = db.query(AreaProjecao).filter(AreaProjecao.ativo == True).order_by(AreaProjecao.nome).all()
    with _areas_cache_lock:
        _areas_cache["data"] = rows
        _areas_cache["ts"] = now
    return rows


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
        .options(selectinload(AreaProjecao.usuarios).joinedload(AreaProjecaoUsuario.usuario))
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
            usa_cutoff_customizado=area.usa_cutoff_customizado,
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
    _invalidate_areas_cache()
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
    _invalidate_user_area_ids_cache()
    return {"message": f"Atribuições atualizadas para a área '{area.nome}'"}


@router.get("/minhas-areas")
def minhas_areas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_visualizar")),
):
    if is_user_admin(current_user):
        areas = db.query(AreaProjecao).filter(AreaProjecao.ativo == True).all()
        return [{"id": a.id, "nome": a.nome, "usa_cutoff_customizado": a.usa_cutoff_customizado} for a in areas]

    area_ids = _get_user_area_ids(db, current_user.id)
    areas = db.query(AreaProjecao).filter(
        AreaProjecao.id.in_(area_ids),
        AreaProjecao.ativo == True
    ).all()
    return [{"id": a.id, "nome": a.nome, "usa_cutoff_customizado": a.usa_cutoff_customizado} for a in areas]


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
            selectinload(ProjecaoInscritos.clientes),
            selectinload(ProjecaoInscritos.kits),
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
            kits=[KitProjecaoResponse(
                id=k.id, projecao_id=k.projecao_id, nome_kit=k.nome_kit,
                quantidade=k.quantidade, created_at=k.created_at,
            ) for k in p.kits],
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


def _get_auto_lock_config(db: Session) -> Optional[ProjecaoAutoLockConfig]:
    return db.query(ProjecaoAutoLockConfig).first()


def _check_auto_lock(db: Session, evento: CadastroEvento, current_user: Usuario):
    """Rejeita a operação se o evento está dentro do período de trava automática (não-admins)."""
    if is_user_admin(current_user):
        return
    config = _get_auto_lock_config(db)
    if not config or not config.ativo:
        return
    if not evento.data_evento:
        return
    now = datetime.now(ZoneInfo('America/Sao_Paulo'))
    dias = (evento.data_evento - now.date()).days
    hora_str = getattr(config, 'hora_trava', None) or "00:00"
    if dias < config.dias_antes_evento:
        locked = True
    elif dias == config.dias_antes_evento:
        # No dia exato D-N a trava só vale a partir do horário configurado (BRT).
        try:
            hh, mm = (int(x) for x in hora_str.split(':'))
            gatilho = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        except (ValueError, TypeError):
            # Valor persistido inválido (edição manual/legado) → trava o dia inteiro.
            gatilho = now.replace(hour=0, minute=0, second=0, microsecond=0)
        locked = now >= gatilho
    else:
        locked = False
    if locked:
        raise HTTPException(
            status_code=423,
            detail=f"Este evento está dentro do período de trava automática (D-{config.dias_antes_evento} às {hora_str}). Não é possível criar, editar ou excluir projeções.",
        )


def _validate_distribuicao_sums(quantidade: int, clientes, kits):
    """Garante que a soma das distribuições por cliente e/ou kit bate com a quantidade total."""
    if clientes:
        soma_c = sum(c.quantidade for c in clientes)
        if soma_c != quantidade:
            raise HTTPException(
                status_code=400,
                detail=f"A soma das quantidades por cliente ({soma_c}) deve ser igual à quantidade total ({quantidade}).",
            )
    if kits:
        soma_k = sum(k.quantidade for k in kits)
        if soma_k != quantidade:
            raise HTTPException(
                status_code=400,
                detail=f"A soma das quantidades por Kit ({soma_k}) deve ser igual à quantidade total ({quantidade}).",
            )


def _camiseta_avulsa_info(db: Session, evento_id: int, area_projecao_id: int) -> tuple[bool, int]:
    """Retorna (corte1_congelado, piso) para o kit 'Kit Completo - Sem camiseta'
    de um (evento, área). corte1_congelado = Corte 1 do evento já congelado.
    piso = valor desse kit capturado no Corte 1 (0 se não houver captura)."""
    snap = db.query(ProjecaoCorteSnapshot).filter(
        ProjecaoCorteSnapshot.evento_id == evento_id
    ).first()
    corte1_congelado = bool(snap and snap.congelado_corte_1_em is not None and snap.valor_corte_1 is not None)
    piso = 0
    if corte1_congelado:
        ks = db.query(ProjecaoKitCorteSnapshot).filter(
            ProjecaoKitCorteSnapshot.evento_id == evento_id,
            ProjecaoKitCorteSnapshot.area_projecao_id == area_projecao_id,
            ProjecaoKitCorteSnapshot.nome_kit == KIT_CAMISETA_AVULSA_ORIGEM,
        ).first()
        piso = int(ks.valor_corte_1) if ks and ks.valor_corte_1 is not None else 0
    return corte1_congelado, piso


def _validate_camiseta_avulsa_piso(db: Session, evento_id: int, area_projecao_id: int, kits):
    """Após o Corte 1, 'Kit Completo - Sem camiseta' vira 'Camiseta avulsa' e não
    pode ser reduzida abaixo do valor congelado no Corte 1 (só pode aumentar).

    O piso é obrigatório: quando o Corte 1 está congelado e há piso > 0, a
    'Camiseta avulsa' tem que estar presente com quantidade >= piso. Isso impede
    o bypass de simplesmente desligar a distribuição por kit (kits vazio) ou
    omitir o kit para "zerar" o valor congelado."""
    corte1_congelado, piso = _camiseta_avulsa_info(db, evento_id, area_projecao_id)
    if not corte1_congelado or piso <= 0:
        return
    qtd_camiseta = None
    for k in (kits or []):
        if k.nome_kit.strip() == KIT_CAMISETA_AVULSA_ORIGEM:
            qtd_camiseta = k.quantidade
            break
    if qtd_camiseta is None or qtd_camiseta < piso:
        raise HTTPException(
            status_code=400,
            detail=f"A 'Camiseta avulsa' não pode ser menor que {piso} (valor congelado no Corte 1). Só é possível aumentar.",
        )


def _is_pk_violation(exc: IntegrityError) -> bool:
    """Detecta UniqueViolation no PK (sequence dessincronizada)."""
    msg = str(getattr(exc, "orig", exc)).lower()
    return "duplicate key" in msg and "_pkey" in msg


def _resync_projecao_sequences(db: Session):
    """Realinha (monotônico) as sequences das tabelas de projeção com o MAX(id)."""
    for tabela in (
        "projecao_inscritos",
        "projecao_inscritos_historico",
        "projecao_inscritos_cliente",
        "projecao_inscritos_kit",
    ):
        db.execute(text("""
            SELECT setval(
                pg_get_serial_sequence(:tabela, 'id'),
                GREATEST(
                    (SELECT last_value FROM pg_sequences WHERE schemaname = 'public' AND sequencename = :tabela || '_id_seq'),
                    (SELECT COALESCE(MAX(id), 1) FROM """ + tabela + """)
                ),
                true
            )
        """), {"tabela": tabela})
    db.commit()


@router.post("/", response_model=ProjecaoInscritosResponse)
def create_projecao(
    data: ProjecaoInscritosCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_criar")),
):
    _check_area_permission(db, current_user, data.area_projecao_id)

    if data.quantidade is None or data.quantidade <= 0:
        raise HTTPException(status_code=400, detail="Quantidade deve ser maior que zero.")

    _validate_distribuicao_sums(data.quantidade, data.clientes, data.kits)
    _validate_camiseta_avulsa_piso(db, data.evento_id, data.area_projecao_id, data.kits)

    evento = db.query(CadastroEvento).filter(CadastroEvento.id == data.evento_id, CadastroEvento.deleted_at.is_(None)).first()
    if not evento:
        raise HTTPException(status_code=404, detail="Evento não encontrado")

    _check_auto_lock(db, evento, current_user)

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

    def _build_and_commit():
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

        kits_salvos = []
        if data.kits:
            for k in data.kits:
                kit = ProjecaoInscritosKit(
                    projecao_id=projecao.id,
                    nome_kit=k.nome_kit.strip(),
                    quantidade=k.quantidade,
                )
                db.add(kit)
                kits_salvos.append(kit)

        _record_history(db, projecao.id, "CRIACAO", current_user.id,
                        campo="quantidade", novo=str(data.quantidade))
        for c in clientes_salvos:
            _record_history(db, projecao.id, "CRIACAO", current_user.id,
                            campo="Cliente adicionado",
                            anterior=None, novo=f"{c.nome_cliente} ({c.quantidade})")
        for k in kits_salvos:
            _record_history(db, projecao.id, "CRIACAO", current_user.id,
                            campo="Kit adicionado",
                            anterior=None, novo=f"{k.nome_kit} ({k.quantidade})")
        db.commit()
        invalidate_consolidado_cache()
        return projecao, clientes_salvos, kits_salvos

    try:
        projecao, clientes_salvos, kits_salvos = _build_and_commit()
    except IntegrityError as exc:
        # Auto-cura: sequence de id dessincronizada (PK duplicada) — realinha e tenta 1x.
        db.rollback()
        if not _is_pk_violation(exc):
            raise
        logger.warning("[ProjecaoCreate] PK collision detectada — realinhando sequence e tentando novamente")
        _resync_projecao_sequences(db)
        try:
            projecao, clientes_salvos, kits_salvos = _build_and_commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=500, detail="Erro ao criar projeção")

    db.refresh(projecao)
    for c in clientes_salvos:
        db.refresh(c)
    for k in kits_salvos:
        db.refresh(k)

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
        kits=[KitProjecaoResponse(
            id=k.id, projecao_id=k.projecao_id, nome_kit=k.nome_kit,
            quantidade=k.quantidade, created_at=k.created_at,
        ) for k in kits_salvos],
        created_by=projecao.created_by,
        created_by_nome=current_user.nome,
        updated_by=projecao.updated_by,
        updated_by_nome=None,
        created_at=projecao.created_at,
        updated_at=projecao.updated_at,
    )


def _parse_iso_date(value: Optional[str]):
    if value is None or value == "":
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Data inválida: {value} (use YYYY-MM-DD)")


# ============================================================
# TRAVA AUTOMÁTICA (Auto-Lock)
# ============================================================

@router.get("/auto-lock-config", response_model=AutoLockConfigResponse)
def get_auto_lock_config(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_visualizar")),
):
    config = _get_auto_lock_config(db)
    if config is None:
        return AutoLockConfigResponse(dias_antes_evento=0, hora_trava="00:00", ativo=False)
    editor = db.query(Usuario).filter(Usuario.id == config.updated_by).first() if config.updated_by else None
    return AutoLockConfigResponse(
        dias_antes_evento=config.dias_antes_evento,
        hora_trava=getattr(config, 'hora_trava', None) or "00:00",
        ativo=config.ativo,
        updated_by_nome=editor.nome if editor else None,
        updated_at=config.updated_at,
    )


@router.put("/auto-lock-config", response_model=AutoLockConfigResponse)
def update_auto_lock_config(
    data: AutoLockConfigUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_editar")),
):
    if not is_user_admin(current_user):
        raise HTTPException(status_code=403, detail="Apenas administradores podem alterar a trava automática")
    if data.dias_antes_evento < 0 or data.dias_antes_evento > 365:
        raise HTTPException(status_code=400, detail="Dias deve estar entre 0 e 365")

    hora_trava = (data.hora_trava or "00:00").strip()
    m = re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", hora_trava)
    if not m:
        raise HTTPException(status_code=400, detail="Horário deve estar no formato HH:MM (00:00 a 23:59)")

    config = _get_auto_lock_config(db)
    if config is None:
        config = ProjecaoAutoLockConfig(
            dias_antes_evento=data.dias_antes_evento,
            hora_trava=hora_trava,
            ativo=data.ativo,
            updated_by=current_user.id,
        )
        db.add(config)
    else:
        config.dias_antes_evento = data.dias_antes_evento
        config.hora_trava = hora_trava
        config.ativo = data.ativo
        config.updated_by = current_user.id
    db.commit()
    db.refresh(config)
    return AutoLockConfigResponse(
        dias_antes_evento=config.dias_antes_evento,
        hora_trava=getattr(config, 'hora_trava', None) or "00:00",
        ativo=config.ativo,
        updated_by_nome=current_user.nome,
        updated_at=config.updated_at,
    )


# ============================================================
# CORTES DE PROJEÇÃO (congelamento por evento: envio / convicta)
# ============================================================

def _compute_total_projecoes(db: Session, evento_id: int) -> int:
    """Soma das quantidades de todas as áreas ativas (não-deletadas) do evento.

    Mesma base que `get_consolidado` usa em `total_projecoes` — é o número
    exibido nos dois cards de corte.
    """
    rows = db.query(ProjecaoInscritos.quantidade).filter(
        ProjecaoInscritos.evento_id == evento_id,
        ProjecaoInscritos.deleted_at.is_(None),
    ).all()
    return sum(int(q or 0) for (q,) in rows)


def _get_corte_config(db: Session) -> Optional[ProjecaoCorteConfig]:
    return db.query(ProjecaoCorteConfig).first()


@router.get("/corte-config", response_model=CorteConfigResponse)
def get_corte_config(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_visualizar")),
):
    config = _get_corte_config(db)
    if config is None:
        # Defaults sugeridos (ainda inativo até admin salvar).
        return CorteConfigResponse(dias_corte_1=30, dias_corte_2=7, ativo=False)
    editor = db.query(Usuario).filter(Usuario.id == config.updated_by).first() if config.updated_by else None
    return CorteConfigResponse(
        dias_corte_1=config.dias_corte_1,
        dias_corte_2=config.dias_corte_2,
        ativo=config.ativo,
        updated_by_nome=editor.nome if editor else None,
        updated_at=config.updated_at,
    )


@router.put("/corte-config", response_model=CorteConfigResponse)
def update_corte_config(
    data: CorteConfigUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_editar")),
):
    if not is_user_admin(current_user):
        raise HTTPException(status_code=403, detail="Apenas administradores podem alterar os cortes de projeção")
    for label, val in (("Corte 1", data.dias_corte_1), ("Corte 2", data.dias_corte_2)):
        if val < 0 or val > 365:
            raise HTTPException(status_code=400, detail=f"{label}: dias deve estar entre 0 e 365")

    config = _get_corte_config(db)
    if config is None:
        config = ProjecaoCorteConfig(
            dias_corte_1=data.dias_corte_1,
            dias_corte_2=data.dias_corte_2,
            ativo=data.ativo,
            updated_by=current_user.id,
        )
        db.add(config)
    else:
        config.dias_corte_1 = data.dias_corte_1
        config.dias_corte_2 = data.dias_corte_2
        config.ativo = data.ativo
        config.updated_by = current_user.id
    db.commit()
    db.refresh(config)
    invalidate_consolidado_cache()
    return CorteConfigResponse(
        dias_corte_1=config.dias_corte_1,
        dias_corte_2=config.dias_corte_2,
        ativo=config.ativo,
        updated_by_nome=current_user.nome,
        updated_at=config.updated_at,
    )


def _get_or_create_corte_snapshot(db: Session, evento_id: int) -> ProjecaoCorteSnapshot:
    snap = db.query(ProjecaoCorteSnapshot).filter(ProjecaoCorteSnapshot.evento_id == evento_id).first()
    if snap is None:
        snap = ProjecaoCorteSnapshot(evento_id=evento_id)
        db.add(snap)
        db.flush()
    return snap


@router.post("/eventos/{evento_id}/corte/{corte}/reabrir")
def reabrir_corte(
    evento_id: int,
    corte: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_editar")),
):
    """Admin: apaga o valor congelado de um corte (volta a acompanhar ao vivo)."""
    if not is_user_admin(current_user):
        raise HTTPException(status_code=403, detail="Apenas administradores podem reabrir cortes")
    if corte not in (1, 2):
        raise HTTPException(status_code=400, detail="Corte deve ser 1 ou 2")
    snap = db.query(ProjecaoCorteSnapshot).filter(ProjecaoCorteSnapshot.evento_id == evento_id).first()
    if snap is None:
        return {"status": "ok", "corte": corte, "congelado": False}
    if corte == 1:
        snap.valor_corte_1 = None
        snap.congelado_corte_1_em = None
        snap.reaberto_manual_corte_1 = True
    else:
        snap.valor_corte_2 = None
        snap.congelado_corte_2_em = None
        snap.reaberto_manual_corte_2 = True
    db.commit()
    invalidate_consolidado_cache()
    return {"status": "ok", "corte": corte, "congelado": False}


@router.post("/eventos/{evento_id}/corte/{corte}/recongelar")
def recongelar_corte(
    evento_id: int,
    corte: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_editar")),
):
    """Admin: regrava o valor do corte com o total de projeção atual."""
    if not is_user_admin(current_user):
        raise HTTPException(status_code=403, detail="Apenas administradores podem recongelar cortes")
    if corte not in (1, 2):
        raise HTTPException(status_code=400, detail="Corte deve ser 1 ou 2")
    evento = db.query(CadastroEvento).filter(CadastroEvento.id == evento_id, CadastroEvento.deleted_at.is_(None)).first()
    if not evento:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    total = _compute_total_projecoes(db, evento_id)
    snap = _get_or_create_corte_snapshot(db, evento_id)
    now = datetime.now(ZoneInfo('America/Sao_Paulo')).replace(tzinfo=None)
    if corte == 1:
        snap.valor_corte_1 = total
        snap.congelado_corte_1_em = now
        snap.reaberto_manual_corte_1 = False
    else:
        snap.valor_corte_2 = total
        snap.congelado_corte_2_em = now
        snap.reaberto_manual_corte_2 = False
    db.commit()
    invalidate_consolidado_cache()
    return {"status": "ok", "corte": corte, "congelado": True, "valor": total}


@router.put("/cutoff-evento-area", response_model=CutoffEventoAreaResponse)
def upsert_cutoff_evento_area(
    data: CutoffEventoAreaUpsert,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_editar")),
):
    """Cria ou atualiza as duas datas de corte para um (evento, area)."""
    area = db.query(AreaProjecao).filter(AreaProjecao.id == data.area_projecao_id, AreaProjecao.ativo == True).first()
    if not area:
        raise HTTPException(status_code=404, detail="Área de projeção não encontrada")
    if not area.usa_cutoff_customizado:
        raise HTTPException(status_code=400, detail="Esta área não está habilitada para cortes customizados por evento")

    _check_area_permission(db, current_user, area.id)

    evento = db.query(CadastroEvento).filter(
        CadastroEvento.id == data.evento_id,
        CadastroEvento.deleted_at.is_(None),
    ).first()
    if not evento:
        raise HTTPException(status_code=404, detail="Evento não encontrado")

    d1 = _parse_iso_date(data.data_corte_1)
    d2 = _parse_iso_date(data.data_corte_2)

    def _filter_row():
        return db.query(ProjecaoCutoffEventoArea).filter(
            ProjecaoCutoffEventoArea.evento_id == data.evento_id,
            ProjecaoCutoffEventoArea.area_projecao_id == data.area_projecao_id,
        )

    row = _filter_row().first()
    if row is None:
        row = ProjecaoCutoffEventoArea(
            evento_id=data.evento_id,
            area_projecao_id=data.area_projecao_id,
            data_corte_1=d1,
            data_corte_2=d2,
            created_by=current_user.id,
            updated_by=current_user.id,
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            row = _filter_row().first()
            if row is None:
                raise HTTPException(status_code=500, detail="Falha ao salvar datas de corte")
            row.data_corte_1 = d1
            row.data_corte_2 = d2
            row.updated_by = current_user.id
            db.commit()
    else:
        row.data_corte_1 = d1
        row.data_corte_2 = d2
        row.updated_by = current_user.id
        db.commit()
    db.refresh(row)
    invalidate_consolidado_cache()
    editor = db.query(Usuario).filter(Usuario.id == row.updated_by).first() if row.updated_by else None
    return CutoffEventoAreaResponse(
        id=row.id,
        evento_id=row.evento_id,
        area_projecao_id=row.area_projecao_id,
        area_projecao_nome=area.nome,
        data_corte_1=row.data_corte_1.isoformat() if row.data_corte_1 else None,
        data_corte_2=row.data_corte_2.isoformat() if row.data_corte_2 else None,
        updated_by=row.updated_by,
        updated_by_nome=editor.nome if editor else None,
        updated_at=row.updated_at,
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
        selectinload(ProjecaoInscritos.clientes),
        selectinload(ProjecaoInscritos.kits),
    ).filter(
        ProjecaoInscritos.id == projecao_id,
        ProjecaoInscritos.deleted_at.is_(None),
    ).first()
    if not projecao:
        raise HTTPException(status_code=404, detail="Projeção não encontrada")

    if projecao.locked_at is not None:
        raise HTTPException(status_code=423, detail="Esta projeção está travada e não pode ser editada")

    _check_area_permission(db, current_user, projecao.area_projecao_id)

    if projecao.evento:
        _check_auto_lock(db, projecao.evento, current_user)

    if data.quantidade is None or data.quantidade <= 0:
        raise HTTPException(status_code=400, detail="Quantidade deve ser maior que zero.")

    _validate_distribuicao_sums(data.quantidade, data.clientes, data.kits)
    _validate_camiseta_avulsa_piso(db, projecao.evento_id, projecao.area_projecao_id, data.kits)

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

    if data.kits is not None:
        old_kits = {k.nome_kit: k.quantidade for k in projecao.kits}
        new_kits = {k.nome_kit.strip(): k.quantidade for k in data.kits}

        old_kit_names = set(old_kits.keys())
        new_kit_names = set(new_kits.keys())

        for nome in old_kit_names - new_kit_names:
            _record_history(db, projecao.id, "EDICAO", current_user.id,
                            campo="Kit removido",
                            anterior=f"{nome} ({old_kits[nome]})", novo=None)

        for nome in new_kit_names - old_kit_names:
            _record_history(db, projecao.id, "EDICAO", current_user.id,
                            campo="Kit adicionado",
                            anterior=None, novo=f"{nome} ({new_kits[nome]})")

        for nome in old_kit_names & new_kit_names:
            if old_kits[nome] != new_kits[nome]:
                _record_history(db, projecao.id, "EDICAO", current_user.id,
                                campo=f"Kit: {nome}",
                                anterior=str(old_kits[nome]), novo=str(new_kits[nome]))

        db.query(ProjecaoInscritosKit).filter(
            ProjecaoInscritosKit.projecao_id == projecao.id
        ).delete()
        for k in data.kits:
            db.add(ProjecaoInscritosKit(
                projecao_id=projecao.id,
                nome_kit=k.nome_kit.strip(),
                quantidade=k.quantidade,
            ))
        if not projecao.updated_by:
            projecao.updated_by = current_user.id

    db.commit()
    db.refresh(projecao)
    invalidate_consolidado_cache()

    clientes_atuais = db.query(ProjecaoInscritosCliente).filter(
        ProjecaoInscritosCliente.projecao_id == projecao.id
    ).all()
    kits_atuais = db.query(ProjecaoInscritosKit).filter(
        ProjecaoInscritosKit.projecao_id == projecao.id
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
        kits=[KitProjecaoResponse(
            id=k.id, projecao_id=k.projecao_id, nome_kit=k.nome_kit,
            quantidade=k.quantidade, created_at=k.created_at,
        ) for k in kits_atuais],
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

    projecao_com_evento = db.query(ProjecaoInscritos).options(
        joinedload(ProjecaoInscritos.evento)
    ).filter(ProjecaoInscritos.id == projecao_id).first()
    if projecao_com_evento and projecao_com_evento.evento:
        _check_auto_lock(db, projecao_com_evento.evento, current_user)

    _record_history(db, projecao.id, "DELECAO", current_user.id,
                    campo="quantidade", anterior=str(projecao.quantidade), novo=None)

    projecao.deleted_at = datetime.now(ZoneInfo('America/Sao_Paulo')).replace(tzinfo=None)
    projecao.updated_by = current_user.id
    db.commit()
    invalidate_consolidado_cache()
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
        invalidate_consolidado_cache()
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
        invalidate_consolidado_cache()
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
    invalidate_consolidado_cache()
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
    invalidate_consolidado_cache()
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
            selectinload(ProjecaoInscritos.clientes),
            selectinload(ProjecaoInscritos.kits),
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
        'Área', 'Quantidade Total', 'Kit', 'Qtd Kit', 'Cliente', 'Qtd Cliente',
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
        kits_pares = [(_sanitize_csv(k.nome_kit), k.quantidade) for k in (p.kits or [])] or [('', '')]
        clientes_pares = [(_sanitize_csv(c.nome_cliente), c.quantidade) for c in (p.clientes or [])] or [('', '')]
        max_rows = max(len(kits_pares), len(clientes_pares))
        for i in range(max_rows):
            kit_nome, kit_qtd = kits_pares[i] if i < len(kits_pares) else ('', '')
            cli_nome, cli_qtd = clientes_pares[i] if i < len(clientes_pares) else ('', '')
            writer.writerow(base + [kit_nome, kit_qtd, cli_nome, cli_qtd] + tail)

    output.seek(0)
    bom = '\ufeff'
    content = bom + output.getvalue()

    return StreamingResponse(
        io.BytesIO(content.encode('utf-8-sig')),
        media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename=projecao_inscritos.csv'},
    )


def _consolidado_cache_key(
    mes: Optional[str],
    tipo_evento: Optional[str],
    modalidade: Optional[str],
    area_projecao_id: Optional[str],
    evento_id: Optional[int],
) -> str:
    """Chave estável por combinação de filtros + ano-edição corrente."""
    return "|".join([
        str(datetime.now().year),
        (mes or "").strip(),
        (tipo_evento or "").strip(),
        (modalidade or "").strip(),
        (area_projecao_id or "").strip(),
        str(evento_id) if evento_id is not None else "",
    ])


def invalidate_consolidado_cache():
    """Limpa todas as variações (filtros) do cache da Visão Consolidada.

    Chamado após qualquer mutação que altere projeções ou cortes, garantindo
    que a próxima leitura reflita o estado novo (a recomputação acontece em
    background via SWR nas leituras seguintes)."""
    try:
        from ...core.cache import projecao_consolidado_cache
        projecao_consolidado_cache.invalidate()
    except Exception as _e:
        logger.warning(f"[Consolidado] falha ao invalidar cache: {_e}")


@router.get("/camiseta-avulsa-info", response_model=CamisetaAvulsaInfoResponse)
def get_camiseta_avulsa_info(
    evento_id: int = Query(...),
    area_projecao_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_visualizar")),
):
    """Informa se 'Kit Completo - Sem camiseta' já virou 'Camiseta avulsa'
    (Corte 1 congelado) e qual o piso mínimo para o par (evento, área)."""
    corte1_congelado, piso = _camiseta_avulsa_info(db, evento_id, area_projecao_id)
    return CamisetaAvulsaInfoResponse(corte1_congelado=corte1_congelado, piso=piso)


@router.get("/consolidado", response_model=List[ConsolidadoEventoResponse])
def get_consolidado(
    mes: Optional[str] = Query(None),
    tipo_evento: Optional[str] = Query(None),
    modalidade: Optional[str] = Query(None),
    area_projecao_id: Optional[str] = Query(None),
    evento_id: Optional[int] = Query(None),
    force_refresh: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_visualizar")),
):
    from ...core.cache import projecao_consolidado_cache
    cache_key = _consolidado_cache_key(mes, tipo_evento, modalidade, area_projecao_id, evento_id)

    if not force_refresh:
        def _swr_refresh():
            from ...core.database import SessionLocal
            _db = SessionLocal()
            try:
                fresh = _compute_consolidado(_db, mes, tipo_evento, modalidade, area_projecao_id, evento_id)
                projecao_consolidado_cache.set(cache_key, fresh)
            finally:
                _db.close()

        cached, _is_stale = projecao_consolidado_cache.get_or_revalidate(cache_key, refresh_fn=_swr_refresh)
        if cached is not None:
            return cached

    result = _compute_consolidado(db, mes, tipo_evento, modalidade, area_projecao_id, evento_id)
    projecao_consolidado_cache.set(cache_key, result)
    return result


def _compute_consolidado(
    db: Session,
    mes: Optional[str],
    tipo_evento: Optional[str],
    modalidade: Optional[str],
    area_projecao_id: Optional[str],
    evento_id: Optional[int],
) -> list:
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

    if not eventos:
        return []

    evento_ids = [e.id for e in eventos]

    sku_to_grupo = {}
    all_mappings = db.query(SkuMapping).filter(SkuMapping.ativo == True).all()
    for m in all_mappings:
        if m.evento_grupo and m.sku:
            sku_to_grupo[m.sku.upper().strip()] = m.evento_grupo

    from ...services.snapshot_service import get_isc_totals_from_snapshot
    current_year = datetime.now().year
    isc_totals = get_isc_totals_from_snapshot(db, current_year)

    # Fetch all projections for all events in a single query (avoids N+1)
    proj_query = db.query(ProjecaoInscritos).options(
        joinedload(ProjecaoInscritos.area_projecao),
        selectinload(ProjecaoInscritos.kits),
    ).filter(
        ProjecaoInscritos.evento_id.in_(evento_ids),
        ProjecaoInscritos.deleted_at.is_(None),
    )
    if area_projecao_id:
        area_ids = [int(a) for a in area_projecao_id.split(',') if a.strip().isdigit()]
        if area_ids:
            proj_query = proj_query.filter(ProjecaoInscritos.area_projecao_id.in_(area_ids))
    all_projecoes = proj_query.all()

    # Group projections by evento_id
    projecoes_by_evento: dict[int, list] = {}
    for p in all_projecoes:
        projecoes_by_evento.setdefault(p.evento_id, []).append(p)

    # Congelamento AO VIVO: avalia e congela os cortes atingidos neste exato
    # momento (mesma regra do job noturno, via fonte única em snapshot_service),
    # para que o travamento aconteça assim que a data de corte chega — sem
    # esperar o job da madrugada. Idempotente e seguro: nunca rebaixa valores.
    from ...services.snapshot_service import congelar_cortes_para_eventos
    try:
        congelar_cortes_para_eventos(db, evento_ids=evento_ids)
    except Exception as _e:
        logger.warning(f"[Consolidado] congelamento ao vivo falhou (segue exibindo): {_e}")
        db.rollback()

    # Config de cortes (single-row) + snapshots congelados por evento
    corte_config = _get_corte_config(db)
    corte_dias_1 = corte_config.dias_corte_1 if corte_config else None
    corte_dias_2 = corte_config.dias_corte_2 if corte_config else None
    corte_ativo = bool(corte_config.ativo) if corte_config else False
    corte_snaps = db.query(ProjecaoCorteSnapshot).filter(
        ProjecaoCorteSnapshot.evento_id.in_(evento_ids)
    ).all()
    snaps_by_evento = {s.evento_id: s for s in corte_snaps}

    # Piso da "Camiseta avulsa" por (evento, área) — valor de "Kit Completo -
    # Sem camiseta" congelado no Corte 1. Usado para exibir a comparação
    # Corte 1 → atual na visão consolidada.
    piso_by_evento_area: dict[tuple, int] = {}
    for ks in db.query(ProjecaoKitCorteSnapshot).filter(
        ProjecaoKitCorteSnapshot.evento_id.in_(evento_ids),
        ProjecaoKitCorteSnapshot.nome_kit == KIT_CAMISETA_AVULSA_ORIGEM,
    ).all():
        piso_by_evento_area[(ks.evento_id, ks.area_projecao_id)] = int(ks.valor_corte_1 or 0)

    # "Data de corte Envio" (data_corte_1) por evento — regra principal do Corte 1.
    # Na prática só uma área a preenche; se houver mais de uma, usa a mais antiga.
    data_envio_by_evento: dict[int, str] = {}
    for (ev_id, dc1) in db.query(
        ProjecaoCutoffEventoArea.evento_id, ProjecaoCutoffEventoArea.data_corte_1
    ).filter(
        ProjecaoCutoffEventoArea.evento_id.in_(evento_ids),
        ProjecaoCutoffEventoArea.data_corte_1.isnot(None),
    ).all():
        atual = data_envio_by_evento.get(ev_id)
        iso = dc1.isoformat()
        if atual is None or iso < atual:
            data_envio_by_evento[ev_id] = iso

    result = []
    for evento in eventos:
        projecoes = projecoes_by_evento.get(evento.id)
        if not projecoes:
            continue

        inscritos_reais = 0
        if evento.sku:
            grupo_nome = sku_to_grupo.get(evento.sku.upper().strip())
            if grupo_nome and grupo_nome in isc_totals:
                inscritos_reais = isc_totals[grupo_nome].get("qtd_site", 0)

        projecoes_items = []
        total_projecoes = 0
        projecao_site = 0
        inscricao_participacao = 0
        for p in projecoes:
            nome_area = p.area_projecao.nome if p.area_projecao else "N/A"
            kits_items = [
                KitProjecaoItem(nome_kit=k.nome_kit, quantidade=k.quantidade)
                for k in sorted(p.kits, key=lambda k: k.quantidade, reverse=True)
            ]
            # Piso só é não-nulo quando o Corte 1 do evento está congelado — é
            # esse estado (e não a existência da linha de snapshot) que dispara o
            # rename para "Camiseta avulsa". Sem linha capturada, piso = 0.
            snap_ev = snaps_by_evento.get(evento.id)
            corte1_congelado_ev = bool(
                snap_ev and snap_ev.congelado_corte_1_em is not None and snap_ev.valor_corte_1 is not None
            )
            piso_area = (
                piso_by_evento_area.get((evento.id, p.area_projecao_id), 0)
                if corte1_congelado_ev else None
            )
            projecoes_items.append(ConsolidadoAreaItem(
                area_projecao_id=p.area_projecao_id,
                area_projecao_nome=nome_area,
                quantidade=p.quantidade,
                kits=kits_items,
                camiseta_avulsa_piso=piso_area,
            ))
            total_projecoes += p.quantidade
            if nome_area.strip().lower() == "site":
                projecao_site += p.quantidade
            for k in p.kits:
                if _normalize_kit_nome(k.nome_kit) == "inscricao participacao":
                    inscricao_participacao += k.quantidade

        # Inscritos reais (vindos do site) substituem a parte "Site" da projeção:
        # se ainda não atingiram, a projeção_site cobre o restante;
        # se ultrapassaram, contam como excedente.
        site_efetivo = max(inscritos_reais, projecao_site)
        outras_projecoes = total_projecoes - projecao_site
        total_geral = site_efetivo + outras_projecoes

        snap = snaps_by_evento.get(evento.id)
        result.append(ConsolidadoEventoResponse(
            evento_id=evento.id,
            evento_nome=evento.nome,
            evento_data=evento.data_evento.isoformat() if evento.data_evento else None,
            inscritos_reais=inscritos_reais,
            projecoes=projecoes_items,
            total_projecoes=total_projecoes,
            projecao_site=projecao_site,
            total_geral=total_geral,
            inscricao_participacao=inscricao_participacao,
            projecao_camisetas=total_projecoes - inscricao_participacao,
            corte_dias_1=corte_dias_1,
            corte_dias_2=corte_dias_2,
            corte_ativo=corte_ativo,
            corte_valor_1=snap.valor_corte_1 if snap else None,
            corte_congelado_1_em=snap.congelado_corte_1_em if snap else None,
            corte_valor_2=snap.valor_corte_2 if snap else None,
            corte_congelado_2_em=snap.congelado_corte_2_em if snap else None,
            corte_data_envio=data_envio_by_evento.get(evento.id),
            reaberto_manual_corte_1=bool(snap.reaberto_manual_corte_1) if snap else False,
            reaberto_manual_corte_2=bool(snap.reaberto_manual_corte_2) if snap else False,
        ))

    # Retorna dicts JSON-safe: o resultado é cacheado em memória e persistido no
    # PostgreSQL (CacheEntry) pelo SmartCache; objetos Pydantic não serializam lá.
    return [r.model_dump(mode="json") for r in result]


# ============================================================
# REGRAS DE PONTO DE CORTE (cut-off rules)
# ============================================================

@router.get("/cutoff-rules", response_model=List[CutoffRuleResponse])
def list_cutoff_rules(
    incluir_inativas: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_visualizar")),
):
    now = _time.time()
    cache_key = bool(incluir_inativas)
    with _cutoff_rules_cache_lock:
        cached = _cutoff_rules_cache.get(cache_key)
        if cached and (now - cached["ts"]) < _CUTOFF_RULES_CACHE_TTL:
            return cached["data"]
    query = db.query(ProjecaoCutoffRule)
    if not incluir_inativas:
        query = query.filter(ProjecaoCutoffRule.ativo == True)
    rows = query.order_by(ProjecaoCutoffRule.dias_antes_evento.desc()).all()
    with _cutoff_rules_cache_lock:
        _cutoff_rules_cache[cache_key] = {"data": rows, "ts": now}
    return rows


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
    _invalidate_cutoff_rules_cache()
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
    _invalidate_cutoff_rules_cache()
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
    _invalidate_cutoff_rules_cache()
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

    - Áreas com `usa_cutoff_customizado=False` usam as regras globais D-N
      (`projecao_cutoff_rule`). Trigger no dia exato em que faltam N dias.
    - Áreas com `usa_cutoff_customizado=True` usam datas específicas por
      evento (`projecao_cutoff_evento_area`). Trigger no dia exato em que
      `today == data_corte_1` ou `today == data_corte_2`.

    Admins enxergam pendências de TODAS as áreas.
    """
    today = datetime.now(ZoneInfo("America/Sao_Paulo")).date()

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

    areas_global_ids = {a.id for a in areas_user if not a.usa_cutoff_customizado}
    areas_custom_ids = {a.id for a in areas_user if a.usa_cutoff_customizado}
    areas_nome_by_id = {a.id: a.nome for a in areas_user}

    # Carrega regras de corte uma única vez — usadas pelos dois blocos
    rules = (
        db.query(ProjecaoCutoffRule)
        .filter(ProjecaoCutoffRule.ativo == True)
        .order_by(ProjecaoCutoffRule.dias_antes_evento.asc())
        .all()
    )
    rule_by_dias = {r.dias_antes_evento: r for r in rules}

    # === Bloco 1: regras globais D-N para áreas SEM cutoff customizado ===
    eventos_global = []  # (evento, dias_ate, regra)
    if areas_global_ids and rules:
        target_dates = [today + timedelta(days=n) for n in rule_by_dias.keys()]
        evs = (
            db.query(CadastroEvento)
            .filter(
                CadastroEvento.deleted_at.is_(None),
                CadastroEvento.status == 'Em andamento',
                CadastroEvento.data_evento.isnot(None),
                CadastroEvento.data_evento.in_(target_dates),
            )
            .all()
        )
        for ev in evs:
            dias = (ev.data_evento - today).days
            regra = rule_by_dias.get(dias)
            if regra:
                eventos_global.append((ev, dias, regra))

    # === Bloco 2: cortes customizados por (evento, area) ===
    # Para a Data de corte Envio (data_corte_1), o alerta dispara N dias ANTES
    # da data de corte, onde N vem das regras ativas (mesmo offset do Bloco 1,
    # mas ancorado em data_corte_1 em vez de data_evento).
    cortes_custom = []  # (evento, area_id, idx, cutoff_data, regra_matched)
    if areas_custom_ids and rules:
        custom_rows = (
            db.query(ProjecaoCutoffEventoArea)
            .options(joinedload(ProjecaoCutoffEventoArea.evento))
            .filter(
                ProjecaoCutoffEventoArea.area_projecao_id.in_(areas_custom_ids),
            )
            .all()
        )
        for row in custom_rows:
            ev = row.evento
            if not ev or ev.deleted_at is not None or ev.status != 'Em andamento':
                continue
            if row.data_corte_1:
                for rule in rules:
                    trigger_date = row.data_corte_1 - timedelta(days=rule.dias_antes_evento)
                    if trigger_date == today:
                        cortes_custom.append((ev, row.area_projecao_id, 1, row.data_corte_1, rule))

    if not eventos_global and not cortes_custom:
        return PendenciasResponse(total_eventos=0, total_areas=0, pendencias=[])

    # Buscar projeções existentes para todos os eventos candidatos
    evento_ids = {ev.id for ev, _, _ in eventos_global} | {ev.id for ev, _, _, _, _ in cortes_custom}
    all_areas_ids = areas_global_ids | areas_custom_ids
    projs = (
        db.query(ProjecaoInscritos.evento_id, ProjecaoInscritos.area_projecao_id)
        .filter(
            ProjecaoInscritos.evento_id.in_(evento_ids),
            ProjecaoInscritos.area_projecao_id.in_(all_areas_ids),
            ProjecaoInscritos.deleted_at.is_(None),
        )
        .all()
    )
    existentes = {(p.evento_id, p.area_projecao_id) for p in projs}

    # Agrupa por evento (UM PendenciaItem por evento).
    # Quando o evento tem áreas pendentes tanto globais quanto customizadas,
    # combinamos a lista, marcamos cutoff_customizado=True apenas se TODAS as
    # áreas pendentes forem customizadas (sinaliza UI sem regra D-N).
    # Caso misto, prevalece a metadata global (D-N) e cutoff_data carrega a
    # data customizada para tooltip.
    accum: dict = {}  # evento_id -> {evento, dias, regra, custom_areas, global_areas, custom_data, custom_indices, global_triggered, custom_regra}
    # eventos em que uma regra global D-N disparou hoje, mesmo se todas as áreas
    # globais já tiverem projeção registrada — usado para sinalizar que o evento
    # NÃO é "apenas customizado" (cutoff_customizado=False).
    eventos_com_trigger_global = {ev.id for ev, _, _ in eventos_global}

    for ev, dias, regra in eventos_global:
        faltando_global = [
            AreaPendenteItem(
                area_projecao_id=aid,
                area_projecao_nome=areas_nome_by_id[aid],
            )
            for aid in areas_global_ids
            if (ev.id, aid) not in existentes
        ]
        if not faltando_global:
            continue
        accum.setdefault(ev.id, {
            "evento": ev,
            "dias": dias,
            "regra": regra,
            "global_areas": [],
            "custom_areas": [],
            "custom_data": None,
            "custom_indices": set(),
            "custom_regra": None,
        })
        accum[ev.id]["global_areas"].extend(faltando_global)

    for ev, aid, idx, dt, matched_rule in cortes_custom:
        if (ev.id, aid) in existentes:
            continue
        info = accum.setdefault(ev.id, {
            "evento": ev,
            "dias": (ev.data_evento - today).days if ev.data_evento else 0,
            "regra": None,
            "global_areas": [],
            "custom_areas": [],
            "custom_data": None,
            "custom_indices": set(),
            "custom_regra": None,
        })
        if aid not in {a.area_projecao_id for a in info["custom_areas"]}:
            info["custom_areas"].append(AreaPendenteItem(
                area_projecao_id=aid,
                area_projecao_nome=areas_nome_by_id[aid],
            ))
        info["custom_indices"].add(idx)
        if info["custom_data"] is None:
            info["custom_data"] = dt
        if info["custom_regra"] is None:
            info["custom_regra"] = matched_rule

    pendencias = []
    for eid, info in accum.items():
        ev = info["evento"]
        regra = info["regra"]
        global_areas = info["global_areas"]
        custom_areas = info["custom_areas"]
        all_areas = global_areas + custom_areas
        if not all_areas:
            continue
        # ordenar e deduplicar por id
        seen = set()
        deduped = []
        for a in sorted(all_areas, key=lambda x: x.area_projecao_nome):
            if a.area_projecao_id in seen:
                continue
            seen.add(a.area_projecao_id)
            deduped.append(a)
        only_custom = (
            bool(custom_areas)
            and not global_areas
            and eid not in eventos_com_trigger_global
        )
        custom_regra = info.get("custom_regra")
        if regra is not None:
            cutoff_dias = regra.dias_antes_evento
            cutoff_nome = regra.nome
        elif custom_areas and custom_regra is not None:
            cutoff_dias = custom_regra.dias_antes_evento
            cutoff_nome = custom_regra.nome
        elif custom_areas:
            cutoff_dias = info["dias"]
            cutoff_nome = "Corte Envio"
        else:
            cutoff_dias = info["dias"]
            cutoff_nome = ""
        pendencias.append(PendenciaItem(
            evento_id=ev.id,
            evento_nome=ev.nome,
            evento_data=ev.data_evento.isoformat() if ev.data_evento else None,
            dias_ate_evento=info["dias"],
            cutoff_dias=cutoff_dias,
            cutoff_nome=cutoff_nome,
            cutoff_customizado=only_custom,
            cutoff_data=info["custom_data"].isoformat() if info["custom_data"] else None,
            areas_pendentes=deduped,
        ))

    pendencias.sort(key=lambda p: (p.dias_ate_evento, p.evento_nome))
    total_areas = sum(len(p.areas_pendentes) for p in pendencias)

    return PendenciasResponse(
        total_eventos=len(pendencias),
        total_areas=total_areas,
        pendencias=pendencias,
    )

# ============================================================
# CUTOFF CUSTOMIZADO POR EVENTO + ÁREA
# ============================================================

@router.put("/areas/{area_id}/cutoff-customizado", response_model=AreaProjecaoResponse)
def toggle_area_cutoff_customizado(
    area_id: int,
    data: AreaCutoffCustomizadoToggle,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_editar")),
):
    if not is_user_admin(current_user):
        raise HTTPException(status_code=403, detail="Apenas administradores podem alterar essa configuração")
    area = db.query(AreaProjecao).filter(AreaProjecao.id == area_id).first()
    if not area:
        raise HTTPException(status_code=404, detail="Área não encontrada")
    area.usa_cutoff_customizado = bool(data.ativo)
    db.commit()
    db.refresh(area)
    _invalidate_areas_cache()
    return area


@router.get("/cutoff-evento-area", response_model=List[CutoffEventoAreaResponse])
def list_cutoffs_por_evento(
    evento_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_visualizar")),
):
    """Retorna os cortes customizados de um evento, restritos às áreas que
    o usuário tem permissão de visualizar (admin vê todas)."""
    evento = db.query(CadastroEvento).filter(
        CadastroEvento.id == evento_id,
        CadastroEvento.deleted_at.is_(None),
    ).first()
    if not evento:
        raise HTTPException(status_code=404, detail="Evento não encontrado")

    if is_user_admin(current_user):
        area_ids = None
    else:
        area_ids = _get_user_area_ids(db, current_user.id)
        if not area_ids:
            return []

    q = (
        db.query(ProjecaoCutoffEventoArea)
        .options(
            joinedload(ProjecaoCutoffEventoArea.area),
            joinedload(ProjecaoCutoffEventoArea.editor),
        )
        .filter(ProjecaoCutoffEventoArea.evento_id == evento_id)
    )
    if area_ids is not None:
        q = q.filter(ProjecaoCutoffEventoArea.area_projecao_id.in_(area_ids))
    rows = q.all()
    result = []
    for r in rows:
        result.append(CutoffEventoAreaResponse(
            id=r.id,
            evento_id=r.evento_id,
            area_projecao_id=r.area_projecao_id,
            area_projecao_nome=r.area.nome if r.area else None,
            data_corte_1=r.data_corte_1.isoformat() if r.data_corte_1 else None,
            data_corte_2=r.data_corte_2.isoformat() if r.data_corte_2 else None,
            updated_by=r.updated_by,
            updated_by_nome=r.editor.nome if r.editor else None,
            updated_at=r.updated_at,
        ))
    return result




