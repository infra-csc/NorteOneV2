from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import extract, text, func, or_
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
    ProjecaoCorteDistSnapshot, ProjecaoNotifLog,
    KIT_CAMISETA_AVULSA_ORIGEM,
)
from ...models.cadastro_evento import CadastroEvento
from ...models.user import Usuario
from ...models.dimensoes import SkuMapping, EventoGrupo
from ...schemas.projecao import (
    AreaProjecaoCreate, AreaProjecaoResponse, AreaProjecaoDetailResponse, AreaProjecaoUsuarioResponse,
    AreaProjecaoUsuarioBulk,
    ProjecaoInscritosCreate, ProjecaoInscritosUpdate, ProjecaoInscritosResponse,
    ClienteProjecaoResponse, KitProjecaoResponse, KitProjecaoItem, ClienteProjecaoItem,
    HistoricoResponse,
    ConsolidadoEventoResponse, ConsolidadoAreaItem, CamisetaAvulsaInfoResponse,
    CorteDistAreaResponse,
    CutoffRuleCreate, CutoffRuleUpdate, CutoffRuleResponse,
    PendenciaItem, PendenciasResponse, AreaPendenteItem,
    AreaCutoffCustomizadoToggle, CutoffEventoAreaUpsert, CutoffEventoAreaResponse,
    AutoLockConfigUpdate, AutoLockConfigResponse,
    CorteConfigUpdate, CorteConfigResponse, AlertaConfigUpdate,
    NotifConfigUpdate,
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


def _check_corte_congelado(db: Session, evento_id: int, current_user: Usuario):
    """Rejeita criação de novas projeções para não-admins quando o Corte 1 (ou Corte 2)
    do evento já foi congelado e não foi reaberto manualmente."""
    if is_user_admin(current_user):
        return
    snap = db.query(ProjecaoCorteSnapshot).filter(
        ProjecaoCorteSnapshot.evento_id == evento_id
    ).first()
    if not snap:
        return
    corte1_congelado = (snap.congelado_corte_1_em is not None or snap.valor_corte_1 is not None)
    corte2_congelado = (snap.congelado_corte_2_em is not None or snap.valor_corte_2 is not None)
    if corte2_congelado and not snap.reaberto_manual_corte_2:
        em = snap.congelado_corte_2_em
        data_str = em.strftime('%d/%m/%Y às %H:%M') if em else 'data desconhecida'
        raise HTTPException(
            status_code=423,
            detail=f"O Corte 2 deste evento foi congelado em {data_str}. Não é possível adicionar novas projeções.",
        )
    if corte1_congelado and not snap.reaberto_manual_corte_1:
        em = snap.congelado_corte_1_em
        data_str = em.strftime('%d/%m/%Y às %H:%M') if em else 'data desconhecida'
        raise HTTPException(
            status_code=423,
            detail=f"O Corte 1 deste evento foi congelado em {data_str}. Não é possível adicionar novas projeções.",
        )


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
    """Retorna (corte1_congelado, teto) para o kit 'Kit Completo - Sem camiseta'
    de um (evento, área). corte1_congelado = Corte 1 do evento já congelado.
    teto = valor desse kit capturado no Corte 1 (0 se não houver captura)."""
    snap = db.query(ProjecaoCorteSnapshot).filter(
        ProjecaoCorteSnapshot.evento_id == evento_id
    ).first()
    corte1_congelado = bool(snap and snap.congelado_corte_1_em is not None and snap.valor_corte_1 is not None)
    teto = 0
    if corte1_congelado:
        ks = db.query(ProjecaoKitCorteSnapshot).filter(
            ProjecaoKitCorteSnapshot.evento_id == evento_id,
            ProjecaoKitCorteSnapshot.area_projecao_id == area_projecao_id,
            ProjecaoKitCorteSnapshot.nome_kit == KIT_CAMISETA_AVULSA_ORIGEM,
        ).first()
        if ks and ks.valor_corte_1 is not None:
            teto = int(ks.valor_corte_1)
        else:
            # Fallback (apenas leitura) para eventos congelados ANTES do teto ser
            # capturado corretamente (ex.: recongelados manualmente por um caminho
            # antigo que não gravava o kit snapshot). Sem captura, usa o valor
            # atual já salvo da "Camiseta avulsa" como teto, garantindo a regra de
            # "só diminui" a partir do estado atual. Caminhos novos de congelamento
            # sempre gravam o snapshot, então este fallback só atinge dados legados.
            teto = int(
                db.query(func.coalesce(func.sum(ProjecaoInscritosKit.quantidade), 0))
                .join(ProjecaoInscritos, ProjecaoInscritosKit.projecao_id == ProjecaoInscritos.id)
                .filter(
                    ProjecaoInscritos.evento_id == evento_id,
                    ProjecaoInscritos.area_projecao_id == area_projecao_id,
                    ProjecaoInscritos.deleted_at.is_(None),
                    ProjecaoInscritosKit.nome_kit == KIT_CAMISETA_AVULSA_ORIGEM,
                )
                .scalar() or 0
            )
    return corte1_congelado, teto


def _validate_camiseta_avulsa_teto(db: Session, evento_id: int, area_projecao_id: int, kits):
    """Após o Corte 1, 'Kit Completo - Sem camiseta' vira 'Camiseta avulsa' e não
    pode ser aumentada acima do valor congelado no Corte 1 (só pode diminuir).

    O teto é um limite máximo: quando o Corte 1 está congelado e há teto > 0, a
    'Camiseta avulsa', se presente, não pode ter quantidade > teto. Omitir o kit
    ou zerá-lo é permitido (é uma redução, dentro do teto)."""
    corte1_congelado, teto = _camiseta_avulsa_info(db, evento_id, area_projecao_id)
    if not corte1_congelado or teto <= 0:
        return
    qtd_camiseta = None
    for k in (kits or []):
        if k.nome_kit.strip() == KIT_CAMISETA_AVULSA_ORIGEM:
            qtd_camiseta = k.quantidade
            break
    if qtd_camiseta is not None and qtd_camiseta > teto:
        raise HTTPException(
            status_code=400,
            detail=f"A 'Camiseta avulsa' não pode ser maior que {teto} (valor congelado no Corte 1). Só é possível diminuir.",
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
    _validate_camiseta_avulsa_teto(db, data.evento_id, data.area_projecao_id, data.kits)

    evento = db.query(CadastroEvento).filter(CadastroEvento.id == data.evento_id, CadastroEvento.deleted_at.is_(None)).first()
    if not evento:
        raise HTTPException(status_code=404, detail="Evento não encontrado")

    _check_auto_lock(db, evento, current_user)
    _check_corte_congelado(db, data.evento_id, current_user)

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
        return CorteConfigResponse(dias_corte_1=30, dias_corte_2=7, dias_alerta_envio=30, notif_email_ativo=False, notif_email_hora=8, notif_canal='email', ativo=False)
    editor = db.query(Usuario).filter(Usuario.id == config.updated_by).first() if config.updated_by else None
    return CorteConfigResponse(
        dias_corte_1=config.dias_corte_1,
        dias_corte_2=config.dias_corte_2,
        dias_alerta_envio=config.dias_alerta_envio,
        notif_email_ativo=config.notif_email_ativo,
        notif_email_hora=config.notif_email_hora,
        notif_canal=getattr(config, 'notif_canal', 'email') or 'email',
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
        dias_alerta_envio=config.dias_alerta_envio,
        notif_email_ativo=config.notif_email_ativo,
        notif_email_hora=config.notif_email_hora,
        notif_canal=getattr(config, 'notif_canal', 'email') or 'email',
        ativo=config.ativo,
        updated_by_nome=current_user.nome,
        updated_at=config.updated_at,
    )


@router.put("/alerta-config", response_model=CorteConfigResponse)
def update_alerta_config(
    data: AlertaConfigUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_editar")),
):
    """
    Define o ÚNICO valor de dias do alerta "Ponto de corte" (D-N contado em cima
    da Data de corte Envio do evento). 0 = alerta desligado. Não toca na config
    de congelamento (dias_corte_1/2/ativo).
    """
    if not is_user_admin(current_user):
        raise HTTPException(status_code=403, detail="Apenas administradores podem alterar o alerta de ponto de corte")
    if data.dias_alerta_envio < 0 or data.dias_alerta_envio > 365:
        raise HTTPException(status_code=400, detail="Dias deve estar entre 0 e 365")

    config = _get_corte_config(db)
    if config is None:
        config = ProjecaoCorteConfig(
            dias_alerta_envio=data.dias_alerta_envio,
            updated_by=current_user.id,
        )
        db.add(config)
    else:
        config.dias_alerta_envio = data.dias_alerta_envio
        config.updated_by = current_user.id
    db.commit()
    db.refresh(config)
    return CorteConfigResponse(
        dias_corte_1=config.dias_corte_1,
        dias_corte_2=config.dias_corte_2,
        dias_alerta_envio=config.dias_alerta_envio,
        notif_email_ativo=config.notif_email_ativo,
        notif_email_hora=config.notif_email_hora,
        notif_canal=getattr(config, 'notif_canal', 'email') or 'email',
        ativo=config.ativo,
        updated_by_nome=current_user.nome,
        updated_at=config.updated_at,
    )


_CANAIS_VALIDOS = {'email', 'teams', 'ambos'}


@router.put("/notif-config", response_model=CorteConfigResponse)
def update_notif_config(
    data: NotifConfigUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_editar")),
):
    """
    Ativa/desativa o resumo diário das pendências, define hora (BRT) e canal
    (email | teams | ambos). Apenas administradores. Não toca nas demais configs.
    """
    if not is_user_admin(current_user):
        raise HTTPException(status_code=403, detail="Apenas administradores podem alterar a notificação")
    if data.notif_email_hora < 0 or data.notif_email_hora > 23:
        raise HTTPException(status_code=400, detail="Hora deve estar entre 0 e 23")
    canal = (data.notif_canal or 'email').strip().lower()
    if canal not in _CANAIS_VALIDOS:
        raise HTTPException(status_code=400, detail=f"Canal inválido '{canal}'. Use: email, teams ou ambos")

    config = _get_corte_config(db)
    if config is None:
        config = ProjecaoCorteConfig(
            notif_email_ativo=data.notif_email_ativo,
            notif_email_hora=data.notif_email_hora,
            notif_canal=canal,
            updated_by=current_user.id,
        )
        db.add(config)
    else:
        config.notif_email_ativo = data.notif_email_ativo
        config.notif_email_hora = data.notif_email_hora
        config.notif_canal = canal
        config.updated_by = current_user.id
    db.commit()
    db.refresh(config)
    return CorteConfigResponse(
        dias_corte_1=config.dias_corte_1,
        dias_corte_2=config.dias_corte_2,
        dias_alerta_envio=config.dias_alerta_envio,
        notif_email_ativo=config.notif_email_ativo,
        notif_email_hora=config.notif_email_hora,
        notif_canal=getattr(config, 'notif_canal', 'email') or 'email',
        ativo=config.ativo,
        updated_by_nome=current_user.nome,
        updated_at=config.updated_at,
    )


@router.get("/notif-teams-health")
def notif_teams_health(
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_editar")),
):
    """
    Verifica se as permissões Azure necessárias para envio de Teams DM estão
    configuradas (User.Read.All, Chat.Create, ChatMessage.Send).
    Tenta adquirir token e faz chamadas de dry-run ao Microsoft Graph.
    Retorna { ok, missing_scopes, error }.
    """
    if not is_user_admin(current_user):
        raise HTTPException(status_code=403, detail="Apenas administradores podem verificar as permissões Teams")
    from ...services.projecao_notif_service import check_teams_permissions
    return check_teams_permissions()


@router.post("/notif-test")
def enviar_notif_teste(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_editar")),
):
    """
    Dispara o resumo diário AGORA (force=True), ignorando o toggle e a hora — para
    teste. Envia aos responsáveis das áreas com pendência no dia. Apenas admin.
    """
    if not is_user_admin(current_user):
        raise HTTPException(status_code=403, detail="Apenas administradores podem disparar o teste de e-mail")
    from ...services.projecao_notif_service import enviar_resumo_diario
    resumo = enviar_resumo_diario(db, force=True)
    return resumo


@router.get("/notif-history")
def get_notif_history(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_editar")),
):
    """
    Retorna os últimos N disparos de notificação registrados em projecao_notif_log.
    Apenas administradores.
    """
    import json as _json
    if not is_user_admin(current_user):
        raise HTTPException(status_code=403, detail="Apenas administradores podem consultar o histórico de notificações")

    rows = (
        db.query(ProjecaoNotifLog)
        .order_by(ProjecaoNotifLog.disparado_em.desc())
        .limit(limit)
        .all()
    )

    result = []
    for r in rows:
        try:
            destinatarios = _json.loads(r.destinatarios_json) if r.destinatarios_json else []
        except Exception:
            destinatarios = []
        try:
            erros = _json.loads(r.erros_json) if r.erros_json else []
        except Exception:
            erros = []
        result.append({
            "id": r.id,
            "disparado_em": r.disparado_em.isoformat() if r.disparado_em else None,
            "canal": r.canal,
            "enviados_email": r.enviados_email,
            "enviados_teams": r.enviados_teams,
            "falhas": r.falhas,
            "total_eventos": r.total_eventos,
            "destinatarios": destinatarios,
            "erros": erros,
            "foi_teste": r.foi_teste,
            "usuario_teste_id": r.usuario_teste_id,
        })

    return result


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
        snap.congelado_manual_corte_1 = False
    else:
        snap.valor_corte_2 = None
        snap.congelado_corte_2_em = None
        snap.reaberto_manual_corte_2 = True
        snap.congelado_manual_corte_2 = False
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
        snap.congelado_manual_corte_1 = True
        # Recongelar manual também precisa capturar o teto da "Camiseta avulsa"
        # (mesma lógica do congelamento automático), senão o teto fica zerado e a
        # validação é silenciosamente ignorada.
        from ...services.snapshot_service import (
            capturar_kit_snapshot_corte1,
            capturar_dist_snapshot_corte1,
        )
        capturar_kit_snapshot_corte1(db, evento_id, now)
        capturar_dist_snapshot_corte1(db, evento_id, now)
    else:
        snap.valor_corte_2 = total
        snap.congelado_corte_2_em = now
        snap.reaberto_manual_corte_2 = False
        snap.congelado_manual_corte_2 = True
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
    dsc = _parse_iso_date(data.data_saida_caminhao)

    def _filter_row():
        return db.query(ProjecaoCutoffEventoArea).filter(
            ProjecaoCutoffEventoArea.evento_id == data.evento_id,
            ProjecaoCutoffEventoArea.area_projecao_id == data.area_projecao_id,
        )

    obs1 = (data.observacao_corte_1 or "").strip() or None

    row = _filter_row().first()
    if row is None:
        row = ProjecaoCutoffEventoArea(
            evento_id=data.evento_id,
            area_projecao_id=data.area_projecao_id,
            data_corte_1=d1,
            data_corte_2=d2,
            data_saida_caminhao=dsc,
            observacao_corte_1=obs1,
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
            row.data_saida_caminhao = dsc
            row.observacao_corte_1 = obs1
            row.updated_by = current_user.id
            db.commit()
    else:
        row.data_corte_1 = d1
        row.data_corte_2 = d2
        row.data_saida_caminhao = dsc
        row.observacao_corte_1 = obs1
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
        data_saida_caminhao=row.data_saida_caminhao.isoformat() if row.data_saida_caminhao else None,
        observacao_corte_1=row.observacao_corte_1,
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
    _validate_camiseta_avulsa_teto(db, projecao.evento_id, projecao.area_projecao_id, data.kits)

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
    (Corte 1 congelado) e qual o teto máximo para o par (evento, área)."""
    corte1_congelado, teto = _camiseta_avulsa_info(db, evento_id, area_projecao_id)
    return CamisetaAvulsaInfoResponse(corte1_congelado=corte1_congelado, teto=teto)


@router.get("/corte1-distribuicao", response_model=CorteDistAreaResponse)
def get_corte1_distribuicao(
    evento_id: int = Query(...),
    area_projecao_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_visualizar")),
):
    """Distribuição congelada do Corte 1 (quantidade + kits + clientes) para uma
    (evento, área), usada pela coluna de leitura do layout aditivo do Corte 2.

    Serve a foto real quando existe; senão (eventos que já estavam no Corte 2
    antes da foto passar a ser gravada) aproxima com os valores AO VIVO atuais e
    marca `fonte='aproximado'`."""
    import json as _json
    corte_snap = db.query(ProjecaoCorteSnapshot).filter(
        ProjecaoCorteSnapshot.evento_id == evento_id
    ).first()
    # Fase aditiva ("Corte 2"): começa assim que o Corte 1 está CONGELADO — é a
    # janela em que se acumulam adições sobre a foto do Corte 1. Reabrir o Corte 1
    # limpa valor_corte_1/congelado_corte_1_em, então volta ao layout normal.
    em_corte2 = bool(corte_snap is not None and (
        corte_snap.valor_corte_1 is not None or corte_snap.congelado_corte_1_em is not None
    ))
    snap = db.query(ProjecaoCorteDistSnapshot).filter(
        ProjecaoCorteDistSnapshot.evento_id == evento_id,
        ProjecaoCorteDistSnapshot.area_projecao_id == area_projecao_id,
    ).first()

    # Self-heal da foto do Corte 1: eventos congelados ANTES da captura do
    # snapshot de distribuição passar a existir (ou por qualquer caminho que a
    # tenha pulado) ficam em Corte 2 sem a foto. Sem ela, o fallback "aproximado"
    # abaixo usa os valores AO VIVO como baseline do Corte 1 — e como o ao vivo
    # se move a cada save, o acréscimo do Corte 2 é absorvido no baseline e some
    # ao reabrir o modal. Captura a foto AGORA (uma única vez) a partir do estado
    # atual, congelando o baseline para que os acréscimos passem a persistir.
    if em_corte2 and snap is None:
        from ...services.snapshot_service import capturar_dist_snapshot_corte1
        ts = corte_snap.congelado_corte_1_em or datetime.now(ZoneInfo('America/Sao_Paulo')).replace(tzinfo=None)
        try:
            # only_missing: preenche só a lacuna desta área; NUNCA regrava as áreas
            # já congeladas com o ao vivo atual (evitaria nova divergência da foto).
            capturar_dist_snapshot_corte1(db, evento_id, ts, only_missing=True)
            db.commit()
        except IntegrityError:
            # Outra requisição concorrente capturou a foto primeiro — relê.
            db.rollback()
        snap = db.query(ProjecaoCorteDistSnapshot).filter(
            ProjecaoCorteDistSnapshot.evento_id == evento_id,
            ProjecaoCorteDistSnapshot.area_projecao_id == area_projecao_id,
        ).first()

    if snap is not None:
        try:
            kits_raw = _json.loads(snap.kits_json) if snap.kits_json else []
        except (ValueError, TypeError):
            kits_raw = []
        try:
            clientes_raw = _json.loads(snap.clientes_json) if snap.clientes_json else []
        except (ValueError, TypeError):
            clientes_raw = []
        return CorteDistAreaResponse(
            evento_id=evento_id,
            area_projecao_id=area_projecao_id,
            quantidade=int(snap.quantidade or 0),
            kits=[KitProjecaoItem(nome_kit=k.get("nome_kit", ""), quantidade=int(k.get("quantidade", 0) or 0)) for k in kits_raw],
            clientes=[ClienteProjecaoItem(nome_cliente=c.get("nome_cliente", ""), quantidade=int(c.get("quantidade", 0) or 0)) for c in clientes_raw],
            fonte="snapshot",
            congelado_em=snap.congelado_em,
            em_corte2=em_corte2,
        )

    # Fallback (aproximado): usa os valores ao vivo atuais como se fossem o Corte 1.
    proj = db.query(ProjecaoInscritos).filter(
        ProjecaoInscritos.evento_id == evento_id,
        ProjecaoInscritos.area_projecao_id == area_projecao_id,
        ProjecaoInscritos.deleted_at.is_(None),
    ).first()
    if proj is None:
        return CorteDistAreaResponse(
            evento_id=evento_id,
            area_projecao_id=area_projecao_id,
            quantidade=0,
            kits=[],
            clientes=[],
            fonte="aproximado",
            em_corte2=em_corte2,
        )
    qtd_aprox = int(proj.quantidade or 0)
    kits_aprox = [KitProjecaoItem(nome_kit=k.nome_kit, quantidade=int(k.quantidade or 0)) for k in proj.kits]
    # Mesma regra do congelamento: sem distribuição por kit, a quantidade vai toda
    # para o "Kit Básico" (mantém um baseline de kit no layout aditivo do Corte 2).
    if not kits_aprox and qtd_aprox > 0:
        kits_aprox = [KitProjecaoItem(nome_kit="Kit Básico", quantidade=qtd_aprox)]
    return CorteDistAreaResponse(
        evento_id=evento_id,
        area_projecao_id=area_projecao_id,
        quantidade=qtd_aprox,
        kits=kits_aprox,
        clientes=[ClienteProjecaoItem(nome_cliente=c.nome_cliente, quantidade=int(c.quantidade or 0)) for c in proj.clientes],
        fonte="aproximado",
        em_corte2=em_corte2,
    )


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

    def _swr_refresh():
        from ...core.database import SessionLocal
        _db = SessionLocal()
        try:
            # Congelamento ao vivo em background (não bloqueia a requisição síncrona)
            from ...services.snapshot_service import congelar_cortes_para_eventos
            try:
                _t0 = _time.time()
                congelar_cortes_para_eventos(_db, evento_ids=None)
                _dt = _time.time() - _t0
                if _dt > 1.0:
                    logger.info(f"[Consolidado] congelamento ao vivo em background: {_dt:.2f}s")
            except Exception as _e:
                logger.warning(f"[Consolidado] congelamento ao vivo background falhou: {_e}")
                _db.rollback()
            fresh = _compute_consolidado(_db, mes, tipo_evento, modalidade, area_projecao_id, evento_id)
            projecao_consolidado_cache.set(cache_key, fresh)
        finally:
            _db.close()

    if not force_refresh:
        cached, _is_stale = projecao_consolidado_cache.get_or_revalidate(cache_key, refresh_fn=_swr_refresh)
        if cached is not None:
            return cached

    # Cache miss ou force_refresh: roda o congelamento ao vivo antes de computar,
    # igual ao _swr_refresh. Caso típico: cache foi invalidado ao salvar data_corte_1
    # e a próxima requisição chega aqui sem nenhum valor em cache para ficar stale.
    from ...services.snapshot_service import congelar_cortes_para_eventos as _freeze
    try:
        _freeze(db, evento_ids=None)
    except Exception as _e:
        logger.warning(f"[Consolidado] congelamento ao vivo (cache miss) falhou: {_e}")
        db.rollback()

    result = _compute_consolidado(db, mes, tipo_evento, modalidade, area_projecao_id, evento_id)
    projecao_consolidado_cache.set(cache_key, result)
    return result


def _aplicar_delta_desc(itens: list, attr: str, delta: int) -> None:
    """Aplica `delta` (variação total desejada) sobre o atributo `attr` de `itens`,
    sem nunca gerar valores negativos.

    Positivo: soma tudo no maior item (cresce sem limite superior). Negativo:
    remove em cascata começando pelos maiores, respeitando o piso 0 de cada item.
    A soma converge exatamente para o alvo desde que `abs(delta)` (quando negativo)
    não exceda a soma atual dos itens — invariante garantida pelos chamadores, já
    que a redução pedida é `soma_atual - valor_corte_1 <= soma_atual`.
    """
    if not itens or delta == 0:
        return
    ordenados = sorted(itens, key=lambda it: getattr(it, attr), reverse=True)
    if delta > 0:
        setattr(ordenados[0], attr, getattr(ordenados[0], attr) + delta)
        return
    rem = -delta
    for it in ordenados:
        if rem <= 0:
            break
        v = getattr(it, attr)
        take = min(v, rem)
        if take:
            setattr(it, attr, v - take)
            rem -= take


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

    # Config de cortes (single-row) + snapshots congelados por evento
    corte_config = _get_corte_config(db)
    corte_dias_1 = corte_config.dias_corte_1 if corte_config else None
    corte_dias_2 = corte_config.dias_corte_2 if corte_config else None
    corte_ativo = bool(corte_config.ativo) if corte_config else False
    corte_snaps = db.query(ProjecaoCorteSnapshot).filter(
        ProjecaoCorteSnapshot.evento_id.in_(evento_ids)
    ).all()
    snaps_by_evento = {s.evento_id: s for s in corte_snaps}

    # Teto da "Camiseta avulsa" por (evento, área) — valor de "Kit Completo -
    # Sem camiseta" congelado no Corte 1. Usado para exibir a comparação
    # Corte 1 → atual na visão consolidada.
    teto_by_evento_area: dict[tuple, int] = {}
    for ks in db.query(ProjecaoKitCorteSnapshot).filter(
        ProjecaoKitCorteSnapshot.evento_id.in_(evento_ids),
        ProjecaoKitCorteSnapshot.nome_kit == KIT_CAMISETA_AVULSA_ORIGEM,
    ).all():
        teto_by_evento_area[(ks.evento_id, ks.area_projecao_id)] = int(ks.valor_corte_1 or 0)

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

    # Distribuição congelada do Corte 1 (Projeção Convicta) por (evento, área).
    # Batch único (evita N+1). kits_json guarda a foto por kit. Quando não há foto
    # para um par, o consumidor cai no fallback ao vivo (aproximado).
    import json as _json_dist
    dist_by_evento_area: dict[tuple, ProjecaoCorteDistSnapshot] = {}
    for ds in db.query(ProjecaoCorteDistSnapshot).filter(
        ProjecaoCorteDistSnapshot.evento_id.in_(evento_ids)
    ).all():
        dist_by_evento_area[(ds.evento_id, ds.area_projecao_id)] = ds

    # "Saída caminhão" (data_saida_caminhao) por evento — mesma regra: se houver
    # mais de uma área preenchida, usa a data mais antiga.
    saida_caminhao_by_evento: dict[int, str] = {}
    for (ev_id, dsc) in db.query(
        ProjecaoCutoffEventoArea.evento_id, ProjecaoCutoffEventoArea.data_saida_caminhao
    ).filter(
        ProjecaoCutoffEventoArea.evento_id.in_(evento_ids),
        ProjecaoCutoffEventoArea.data_saida_caminhao.isnot(None),
    ).all():
        atual = saida_caminhao_by_evento.get(ev_id)
        iso = dsc.isoformat()
        if atual is None or iso < atual:
            saida_caminhao_by_evento[ev_id] = iso

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
            # Sem distribuição por kit: a quantidade total entra no "Kit Básico"
            # (mesma regra do congelamento do Corte 1 e da leitura aditiva).
            if not kits_items and (p.quantidade or 0) > 0:
                kits_items = [KitProjecaoItem(nome_kit="Kit Básico", quantidade=p.quantidade)]
            # Teto só é não-nulo quando o Corte 1 do evento está congelado — é
            # esse estado (e não a existência da linha de snapshot) que dispara o
            # rename para "Camiseta avulsa". Sem linha capturada, teto = 0.
            snap_ev = snaps_by_evento.get(evento.id)
            corte1_congelado_ev = bool(
                snap_ev and snap_ev.congelado_corte_1_em is not None and snap_ev.valor_corte_1 is not None
            )
            teto_area = (
                teto_by_evento_area.get((evento.id, p.area_projecao_id), 0)
                if corte1_congelado_ev else None
            )
            # Projeção Convicta (Corte 1): usa a foto congelada por área/kit quando
            # existe; senão espelha o ao vivo (mesma lógica de get_corte1_distribuicao).
            dist_snap = dist_by_evento_area.get((evento.id, p.area_projecao_id))
            if dist_snap is not None:
                try:
                    conv_raw = _json_dist.loads(dist_snap.kits_json) if dist_snap.kits_json else []
                except (ValueError, TypeError):
                    conv_raw = []
                convicta_kits = [
                    KitProjecaoItem(
                        nome_kit=k.get("nome_kit", ""),
                        quantidade=int(k.get("quantidade", 0) or 0),
                    )
                    for k in sorted(conv_raw, key=lambda k: int(k.get("quantidade", 0) or 0), reverse=True)
                ]
                convicta_quantidade = int(dist_snap.quantidade or 0)
                if not convicta_kits and convicta_quantidade > 0:
                    convicta_kits = [KitProjecaoItem(nome_kit="Kit Básico", quantidade=convicta_quantidade)]
            else:
                convicta_kits = [
                    KitProjecaoItem(nome_kit=ki.nome_kit, quantidade=ki.quantidade)
                    for ki in kits_items
                ]
                convicta_quantidade = p.quantidade
            projecoes_items.append(ConsolidadoAreaItem(
                area_projecao_id=p.area_projecao_id,
                area_projecao_nome=nome_area,
                quantidade=p.quantidade,
                kits=kits_items,
                convicta_quantidade=convicta_quantidade,
                convicta_kits=convicta_kits,
                camiseta_avulsa_teto=teto_area,
            ))
            total_projecoes += p.quantidade
            if nome_area.strip().lower() == "site":
                projecao_site += p.quantidade
            for k in p.kits:
                if _normalize_kit_nome(k.nome_kit) == "inscricao participacao":
                    inscricao_participacao += k.quantidade

        # Reconciliação da Projeção Convicta com o total congelado.
        # `valor_corte_1` é a fonte canônica do Corte 1 (congelado uma única vez no
        # instante do corte). As fotos por área podem ter divergido desse total:
        #   - edições feitas DEPOIS do congelamento que o self-heal recapturou ao
        #     vivo sob o carimbo antigo (deriva nos snapshots existentes); ou
        #   - áreas sem foto, que caem no fallback ao vivo (soma segue o ao vivo).
        # Quando o Corte 1 está congelado, ajusta a soma das áreas para bater
        # exatamente com `valor_corte_1`, lançando a diferença na maior área (e no
        # seu maior kit) — caso típico em que a área que mais cresceu pós-corte
        # absorveu a deriva. Mantém cabeçalho (Convicta) e detalhe por área coesos.
        snap_recon = snaps_by_evento.get(evento.id)
        if snap_recon and snap_recon.valor_corte_1 is not None and projecoes_items:
            conv_total = sum(it.convicta_quantidade for it in projecoes_items)
            delta = int(snap_recon.valor_corte_1) - conv_total
            if delta != 0:
                ordenadas = sorted(
                    projecoes_items, key=lambda it: it.convicta_quantidade, reverse=True
                )
                if delta > 0:
                    # Falta para o alvo: soma na maior área (e no seu maior kit).
                    alvo = ordenadas[0]
                    alvo.convicta_quantidade += delta
                    _aplicar_delta_desc(alvo.convicta_kits, "quantidade", delta)
                else:
                    # Excesso sobre o alvo: remove em cascata das maiores áreas,
                    # espelhando a mesma remoção nos kits de cada área tocada para
                    # manter `convicta_kits` somando `convicta_quantidade`.
                    rem = -delta
                    for it in ordenadas:
                        if rem <= 0:
                            break
                        take = min(it.convicta_quantidade, rem)
                        if take:
                            it.convicta_quantidade -= take
                            _aplicar_delta_desc(it.convicta_kits, "quantidade", -take)
                            rem -= take

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
            data_saida_caminhao=saida_caminhao_by_evento.get(evento.id),
            reaberto_manual_corte_1=bool(snap.reaberto_manual_corte_1) if snap else False,
            reaberto_manual_corte_2=bool(snap.reaberto_manual_corte_2) if snap else False,
            # Fase aditiva ("Corte 2"): mesma regra (OR) que get_corte1_distribuicao
            # usa como fonte autoritativa — começa assim que o Corte 1 foi congelado.
            em_corte2=bool(
                snap and (snap.valor_corte_1 is not None or snap.congelado_corte_1_em is not None)
            ),
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


@router.get("/cutoff-envio-map")
def get_cutoff_envio_map(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_visualizar")),
):
    """
    Mapa leve {evento_id: "YYYY-MM-DD"} com a "Data de corte Envio" (a MAIS
    ANTIGA `data_corte_1` entre as áreas) de cada evento. Usado pelo frontend
    da Projeção de Inscritos para ancorar os marcadores de ponto de corte na
    Data de corte Envio sem depender da aba/consolidado estar carregado —
    mesma âncora que `/projecao/pendencias` usa no backend.
    """
    rows = (
        db.query(
            ProjecaoCutoffEventoArea.evento_id,
            func.min(ProjecaoCutoffEventoArea.data_corte_1),
        )
        .filter(ProjecaoCutoffEventoArea.data_corte_1.isnot(None))
        .group_by(ProjecaoCutoffEventoArea.evento_id)
        .all()
    )
    return {str(eid): dt.isoformat() for eid, dt in rows if dt is not None}


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
    Retorna eventos em status 'Em andamento' que cruzaram o ponto de corte e
    ainda não têm projeção registrada para alguma das áreas que o usuário tem
    permissão de editar.

    Existe um ÚNICO valor de dias (`projecao_corte_config.dias_alerta_envio`),
    contado SEMPRE em cima da "Data de corte Envio" do evento (`data_corte_1`, a
    MAIS ANTIGA entre as áreas — mesma âncora do congelamento do Corte 1). O
    alerta dispara no dia exato em que `today == data_corte_envio - N`, para
    TODAS as áreas que o usuário pode editar.

    Eventos SEM Data de corte Envio cadastrada NÃO geram alerta (sem fallback
    pela data do evento). Admins enxergam pendências de TODAS as áreas.
    """
    today = datetime.now(ZoneInfo("America/Sao_Paulo")).date()

    # Valor único de dias do alerta. 0 (ou config inexistente) = desligado.
    config = _get_corte_config(db)
    n = config.dias_alerta_envio if config else 30
    if not n or n <= 0:
        return PendenciasResponse(total_eventos=0, total_areas=0, pendencias=[])

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

    all_areas_ids = {a.id for a in areas_user}
    areas_nome_by_id = {a.id: a.nome for a in areas_user}

    # "Data de corte Envio" por evento = a MAIS ANTIGA entre as áreas (mesma
    # âncora usada pelo congelamento do Corte 1, para alerta e freeze baterem).
    cesb_rows = (
        db.query(
            ProjecaoCutoffEventoArea.evento_id,
            func.min(ProjecaoCutoffEventoArea.data_corte_1),
        )
        .filter(ProjecaoCutoffEventoArea.data_corte_1.isnot(None))
        .group_by(ProjecaoCutoffEventoArea.evento_id)
        .all()
    )
    corte_envio_by_evento = {eid: dt for eid, dt in cesb_rows}

    # Dispara somente quando hoje == data_envio - N (sem fallback por data do evento).
    trigger = {eid: dt for eid, dt in corte_envio_by_evento.items() if (dt - today).days == n}
    if not trigger:
        return PendenciasResponse(total_eventos=0, total_areas=0, pendencias=[])

    evs = (
        db.query(CadastroEvento)
        .filter(
            CadastroEvento.id.in_(list(trigger.keys())),
            CadastroEvento.deleted_at.is_(None),
            CadastroEvento.status == 'Em andamento',
        )
        .all()
    )
    if not evs:
        return PendenciasResponse(total_eventos=0, total_areas=0, pendencias=[])

    # Projeções já registradas para os eventos candidatos
    evento_ids = {ev.id for ev in evs}
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

    pendencias = []
    for ev in evs:
        ref_date = trigger[ev.id]
        faltando = [
            AreaPendenteItem(
                area_projecao_id=aid,
                area_projecao_nome=areas_nome_by_id[aid],
            )
            for aid in all_areas_ids
            if (ev.id, aid) not in existentes
        ]
        if not faltando:
            continue
        faltando.sort(key=lambda x: x.area_projecao_nome)
        dias_ate = (ev.data_evento - today).days if ev.data_evento else 0
        pendencias.append(PendenciaItem(
            evento_id=ev.id,
            evento_nome=ev.nome,
            evento_data=ev.data_evento.isoformat() if ev.data_evento else None,
            dias_ate_evento=dias_ate,
            cutoff_dias=n,
            cutoff_nome=f"D-{n}",
            cutoff_customizado=True,
            cutoff_data=ref_date.isoformat(),
            areas_pendentes=faltando,
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

@router.get("/diagnostico-pos-corte")
def get_diagnostico_pos_corte(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_visualizar")),
):
    """Admin: lista projeções criadas pós-Corte 1 congelado que não têm
    ProjecaoCorteDistSnapshot — ou seja, não foram contabilizadas no valor_corte_1.
    Cada item reporta o evento, a área, a quantidade e o valor_corte_1 atual."""
    if not is_user_admin(current_user):
        raise HTTPException(status_code=403, detail="Apenas administradores podem visualizar este diagnóstico")

    frozen_snaps = db.query(ProjecaoCorteSnapshot).filter(
        or_(
            ProjecaoCorteSnapshot.valor_corte_1.isnot(None),
            ProjecaoCorteSnapshot.congelado_corte_1_em.isnot(None),
        )
    ).all()
    if not frozen_snaps:
        return []

    snap_by_evento = {s.evento_id: s for s in frozen_snaps}
    frozen_evento_ids = list(snap_by_evento.keys())

    projecoes = (
        db.query(ProjecaoInscritos)
        .options(selectinload(ProjecaoInscritos.kits), selectinload(ProjecaoInscritos.clientes))
        .filter(
            ProjecaoInscritos.evento_id.in_(frozen_evento_ids),
            ProjecaoInscritos.deleted_at.is_(None),
        )
        .all()
    )
    if not projecoes:
        return []

    dist_snaps = db.query(ProjecaoCorteDistSnapshot).filter(
        ProjecaoCorteDistSnapshot.evento_id.in_(frozen_evento_ids),
    ).all()
    snapped_keys = {(d.evento_id, d.area_projecao_id) for d in dist_snaps}

    orphans = [p for p in projecoes if (p.evento_id, p.area_projecao_id) not in snapped_keys]
    if not orphans:
        return []

    ev_ids = list({o.evento_id for o in orphans})
    area_ids = list({o.area_projecao_id for o in orphans})
    eventos = {e.id: e for e in db.query(CadastroEvento).filter(CadastroEvento.id.in_(ev_ids)).all()}
    areas = {a.id: a for a in db.query(AreaProjecao).filter(AreaProjecao.id.in_(area_ids)).all()}

    result = []
    for o in orphans:
        ev = eventos.get(o.evento_id)
        area = areas.get(o.area_projecao_id)
        snap = snap_by_evento.get(o.evento_id)
        result.append({
            "projecao_id": o.id,
            "evento_id": o.evento_id,
            "evento_nome": ev.nome if ev else str(o.evento_id),
            "area_projecao_id": o.area_projecao_id,
            "area_nome": area.nome if area else str(o.area_projecao_id),
            "quantidade": int(o.quantidade or 0),
            "valor_corte_1_atual": snap.valor_corte_1 if snap else None,
            "congelado_em": snap.congelado_corte_1_em.isoformat() if snap and snap.congelado_corte_1_em else None,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        })
    return result


@router.post("/diagnostico-pos-corte/backfill")
def backfill_pos_corte(
    evento_id: int = Query(...),
    area_projecao_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(PROJECAO_PERMISSION, "pode_editar")),
):
    """Admin: inclui uma área órfã no snapshot do Corte 1 (backfill).

    Cria a ProjecaoCorteDistSnapshot ausente e incrementa valor_corte_1 com a
    quantidade dessa área, corrigindo a discrepância silenciosa no consolidado."""
    if not is_user_admin(current_user):
        raise HTTPException(status_code=403, detail="Apenas administradores podem executar o backfill")

    corte_snap = db.query(ProjecaoCorteSnapshot).filter(
        ProjecaoCorteSnapshot.evento_id == evento_id
    ).first()
    if not corte_snap or (corte_snap.valor_corte_1 is None and corte_snap.congelado_corte_1_em is None):
        raise HTTPException(status_code=400, detail="Corte 1 não está congelado para este evento")

    existing_dist = db.query(ProjecaoCorteDistSnapshot).filter(
        ProjecaoCorteDistSnapshot.evento_id == evento_id,
        ProjecaoCorteDistSnapshot.area_projecao_id == area_projecao_id,
    ).first()
    if existing_dist:
        raise HTTPException(status_code=409, detail="Esta área já tem snapshot de distribuição")

    proj = (
        db.query(ProjecaoInscritos)
        .options(selectinload(ProjecaoInscritos.kits), selectinload(ProjecaoInscritos.clientes))
        .filter(
            ProjecaoInscritos.evento_id == evento_id,
            ProjecaoInscritos.area_projecao_id == area_projecao_id,
            ProjecaoInscritos.deleted_at.is_(None),
        )
        .first()
    )
    if not proj:
        raise HTTPException(status_code=404, detail="Projeção não encontrada ou já excluída")

    import json as _json
    qtd = int(proj.quantidade or 0)
    kits = [{"nome_kit": k.nome_kit, "quantidade": int(k.quantidade or 0)} for k in proj.kits]
    clientes = [{"nome_cliente": c.nome_cliente, "quantidade": int(c.quantidade or 0)} for c in proj.clientes]
    if not kits and qtd > 0:
        kits = [{"nome_kit": "Kit Básico", "quantidade": qtd}]

    now = datetime.now(ZoneInfo('America/Sao_Paulo')).replace(tzinfo=None)
    ts = corte_snap.congelado_corte_1_em or now

    dist = ProjecaoCorteDistSnapshot(
        evento_id=evento_id,
        area_projecao_id=area_projecao_id,
        quantidade=qtd,
        kits_json=_json.dumps(kits, ensure_ascii=False),
        clientes_json=_json.dumps(clientes, ensure_ascii=False),
        congelado_em=ts,
    )
    db.add(dist)

    if corte_snap.valor_corte_1 is not None:
        corte_snap.valor_corte_1 = int(corte_snap.valor_corte_1 or 0) + qtd
    else:
        corte_snap.valor_corte_1 = qtd

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Conflito ao criar snapshot — tente novamente")

    invalidate_consolidado_cache()
    logger.info(
        "[DiagnosticoPosCorte] backfill evento_id=%s area_projecao_id=%s qtd=%s novo_valor_corte_1=%s by=%s",
        evento_id, area_projecao_id, qtd, corte_snap.valor_corte_1, current_user.id,
    )
    return {
        "status": "ok",
        "evento_id": evento_id,
        "area_projecao_id": area_projecao_id,
        "quantidade_adicionada": qtd,
        "novo_valor_corte_1": corte_snap.valor_corte_1,
    }


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
            data_saida_caminhao=r.data_saida_caminhao.isoformat() if r.data_saida_caminhao else None,
            observacao_corte_1=r.observacao_corte_1,
            updated_by=r.updated_by,
            updated_by_nome=r.editor.nome if r.editor else None,
            updated_at=r.updated_at,
        ))
    return result




