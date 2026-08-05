"""Solicitação de Cortesias — tela nova e independente da tela atual de
Cortesias (proxy do app externo). Os responsáveis de cada área "abrem um
chamado" pedindo cortesias para um evento (cupom a gerar manualmente depois,
ou planilha do cliente com a lista de participantes), respeitando como
trava a quantidade total projetada da área (projecao_inscritos.quantidade).

Sem etapa de aprovação: a validação do saldo já é suficiente para registrar
a solicitação. Um usuário com uma permissão distinta (pode_editar do mesmo
módulo) marca solicitações de cupom como geradas, preenchendo o código.
"""

import csv
import io
import logging
import os
import re
import threading
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from ...core.database import get_db
from ...core.security import is_user_admin, require_permission
from ...models.cadastro_evento import CadastroEvento
from ...models.cortesia_solicitacao import (
    STATUS_GERADO,
    STATUS_SOLICITADO,
    TIPO_CUPOM,
    TIPO_PLANILHA,
    CortesiaSolicitacao,
    CortesiaCupomCodigo,
    _now_brasilia,
)
from ...models.projecao import AreaProjecao, AreaProjecaoUsuario, ProjecaoInscritos
from ...models.user import Usuario
from ...schemas.cortesia_solicitacao import (
    CortesiaCupomColarRequest,
    CortesiaSolicitacaoCupomCreate,
    CortesiaSolicitacaoResponse,
    CupomCodigoItem,
    EventoFilaOpcao,
    EventoSaldoResponse,
    ImportarCupomLinhaResultado,
    ImportarCupomResumo,
    SaldoAreaItem,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cortesia-solicitacao", tags=["Solicitação de Cortesias"])

# Módulo próprio de permissão (Perfil de Acesso): visualizar/criar solicitações
# é o fluxo do responsável de área; editar é reservado a quem gera os cupons.
CORTESIA_SOLICITACAO_PERMISSION = "cortesia_solicitacao"

# Sem um evento_id explícito, cupons já gerados há mais de
# _FILA_GERADOS_JANELA_DIAS dias saem da fila padrão — do contrário ela
# cresce sem limite conforme os anos de eventos se acumulam. Pendentes nunca
# entram nessa janela (ver fila_geracao_cupons): é fila de trabalho, um
# pedido esquecido não pode sumir. Selecionar um evento no filtro busca o
# histórico completo (sem a janela) daquele evento, para localizar/exportar
# cupons mais antigos.
_FILA_GERADOS_JANELA_DIAS = 90

_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "uploads", "cortesia_solicitacao")
_ALLOWED_EXTENSOES = {".xlsx", ".xls", ".csv"}
_MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15MB

# Importação em lote de códigos de cupom (task #244) é sempre um arquivo de
# texto simples e pequeno (um código por linha) — 5MB já é folga generosa.
_MAX_IMPORT_TXT_BYTES = 5 * 1024 * 1024

# Um código de cupom por linha é o formato canônico salvo em codigo_cupom,
# mas aceitamos colar/importar separado por vírgula ou ponto e vírgula
# também — tanto no salvamento quanto na leitura de dados antigos.
_CODIGO_CUPOM_SPLIT_RE = re.compile(r"[\r\n,;]+")

# ---------------------------------------------------------------------------
# Per-(evento_id, area_projecao_id) in-process mutex for planilha uploads.
#
# Two requests arriving before either has committed could both pass a plain
# SELECT duplicate check (there is nothing to lock yet — the row does not
# exist).  Holding this threading.Lock for the full insert critical-section
# serialises concurrent in-process requests so the second one always sees the
# first record in the database before deciding to proceed.
#
# For multi-process / distributed deployments the route also acquires a
# PostgreSQL transaction-scoped advisory lock so the guarantee holds across
# workers (pg_advisory_xact_lock is silently skipped on SQLite / other
# backends).
# ---------------------------------------------------------------------------
_PLANILHA_LOCKS: dict[tuple[int, int], threading.Lock] = {}
_PLANILHA_LOCKS_META = threading.Lock()


def _get_planilha_upload_lock(evento_id: int, area_projecao_id: int) -> threading.Lock:
    """Return (and lazily create) the threading.Lock for this (evento, área)."""
    key = (evento_id, area_projecao_id)
    with _PLANILHA_LOCKS_META:
        if key not in _PLANILHA_LOCKS:
            _PLANILHA_LOCKS[key] = threading.Lock()
        return _PLANILHA_LOCKS[key]


def _planilha_advisory_lock_params(evento_id: int, area_projecao_id: int) -> tuple[int, int]:
    """Return the two 32-bit signed integers used as PostgreSQL advisory-lock
    keys for a planilha upload of (evento_id, area_projecao_id).

    PostgreSQL's ``pg_advisory_xact_lock(key1 int, key2 int)`` accepts two
    plain integers, so we pass the IDs directly — no hashing, deterministic
    and identical in every Python process for the same input.

    IDs are masked to the int32 range to satisfy PG's type requirement; IDs
    above 2**31-1 fold into the negative half, which is still a stable unique
    value as long as both callers use the same formula.
    """
    def _to_int32(n: int) -> int:
        n = n & 0xFFFFFFFF
        return n if n < 0x80000000 else n - 0x100000000

    return _to_int32(evento_id), _to_int32(area_projecao_id)


def _parse_codigos_cupom(texto: str | None) -> list[str]:
    if not texto:
        return []
    return [c.strip() for c in _CODIGO_CUPOM_SPLIT_RE.split(texto) if c.strip()]


# Os códigos de cupom não são mais gerados pelo app (task #242) — são criados
# manualmente no Magento e colados na solicitação. O índice único abaixo
# continua garantindo que nenhum código colado se repita entre solicitações.
_CODIGO_CUPOM_INDICE_UNICO = "ux_cortesia_cupom_codigo_codigo"


def _codigo_cupom_existe(db: Session, codigo: str) -> bool:
    """Confere duplicidade contra os códigos já salvos, case-insensitive
    (``codigo`` já deve chegar uppercased do chamador)."""
    return db.query(CortesiaCupomCodigo.id).filter(func.upper(CortesiaCupomCodigo.codigo) == codigo).first() is not None


def _get_user_area_ids(db: Session, user_id: int) -> set:
    rows = db.query(AreaProjecaoUsuario.area_projecao_id).filter(
        AreaProjecaoUsuario.usuario_id == user_id
    ).all()
    return {r[0] for r in rows}


def _check_area_permission(db: Session, user: Usuario, area_projecao_id: int):
    if is_user_admin(user):
        return
    allowed = _get_user_area_ids(db, user.id)
    if area_projecao_id not in allowed:
        raise HTTPException(status_code=403, detail="Você não tem permissão para solicitar cortesias desta área")


def _calcular_saldo(db: Session, evento_id: int, area_projecao_id: int) -> tuple[int, int, int]:
    projetado = int(
        db.query(func.coalesce(func.sum(ProjecaoInscritos.quantidade), 0))
        .filter(
            ProjecaoInscritos.evento_id == evento_id,
            ProjecaoInscritos.area_projecao_id == area_projecao_id,
            ProjecaoInscritos.deleted_at.is_(None),
        )
        .scalar() or 0
    )
    solicitado = int(
        db.query(func.coalesce(func.sum(CortesiaSolicitacao.quantidade), 0))
        .filter(
            CortesiaSolicitacao.evento_id == evento_id,
            CortesiaSolicitacao.area_projecao_id == area_projecao_id,
            CortesiaSolicitacao.deleted_at.is_(None),
        )
        .scalar() or 0
    )
    return projetado, solicitado, projetado - solicitado


def _calcular_saldos_bulk(
    db: Session, evento_ids: list[int], area_ids: list[int]
) -> dict[tuple[int, int], tuple[int, int, int]]:
    """Versão em lote de `_calcular_saldo`: calcula o saldo de TODAS as
    combinações evento×área com apenas 2 consultas agregadas (uma soma de
    projetado, uma de solicitado, ambas agrupadas por evento e área), em vez
    de 2 consultas para CADA combinação individual. Usada pelas rotas de
    leitura (`/eventos` e `/saldo`), que precisam do saldo de muitos eventos
    e/ou áreas de uma vez — o cálculo ponto-a-ponto usado na validação de
    escrita (`_calcular_saldo`) continua igual, pois lá é sempre uma única
    combinação por requisição.

    Combinações sem nenhuma linha em nenhuma das duas tabelas simplesmente
    não aparecem no dict retornado; quem chamar deve tratar o "não encontrado"
    como (0, 0, 0), igual ao COALESCE(SUM(...), 0) da versão ponto-a-ponto.
    """
    if not evento_ids or not area_ids:
        return {}

    projetado_map: dict[tuple[int, int], int] = {
        (evento_id, area_projecao_id): int(total or 0)
        for evento_id, area_projecao_id, total in (
            db.query(
                ProjecaoInscritos.evento_id,
                ProjecaoInscritos.area_projecao_id,
                func.sum(ProjecaoInscritos.quantidade),
            )
            .filter(
                ProjecaoInscritos.evento_id.in_(evento_ids),
                ProjecaoInscritos.area_projecao_id.in_(area_ids),
                ProjecaoInscritos.deleted_at.is_(None),
            )
            .group_by(ProjecaoInscritos.evento_id, ProjecaoInscritos.area_projecao_id)
            .all()
        )
    }

    solicitado_map: dict[tuple[int, int], int] = {
        (evento_id, area_projecao_id): int(total or 0)
        for evento_id, area_projecao_id, total in (
            db.query(
                CortesiaSolicitacao.evento_id,
                CortesiaSolicitacao.area_projecao_id,
                func.sum(CortesiaSolicitacao.quantidade),
            )
            .filter(
                CortesiaSolicitacao.evento_id.in_(evento_ids),
                CortesiaSolicitacao.area_projecao_id.in_(area_ids),
                CortesiaSolicitacao.deleted_at.is_(None),
            )
            .group_by(CortesiaSolicitacao.evento_id, CortesiaSolicitacao.area_projecao_id)
            .all()
        )
    }

    saldos: dict[tuple[int, int], tuple[int, int, int]] = {}
    for key in set(projetado_map) | set(solicitado_map):
        projetado = projetado_map.get(key, 0)
        solicitado = solicitado_map.get(key, 0)
        saldos[key] = (projetado, solicitado, projetado - solicitado)
    return saldos


def _serialize(sol: CortesiaSolicitacao) -> CortesiaSolicitacaoResponse:
    codigos_detalhes = [
        CupomCodigoItem(
            id=c.id,
            codigo=c.codigo,
            usado=c.usado,
            usado_em=c.usado_em,
            usado_por_nome=c.usuario_uso.nome if c.usuario_uso else None,
        )
        for c in (sol.codigos or [])
    ]
    # codigo_cupom_lista: prefer per-code child rows when available, else parse blob
    if codigos_detalhes:
        codigo_cupom_lista = [c.codigo for c in codigos_detalhes]
    else:
        codigo_cupom_lista = _parse_codigos_cupom(sol.codigo_cupom)
    return CortesiaSolicitacaoResponse(
        id=sol.id,
        evento_id=sol.evento_id,
        evento_nome=sol.evento.nome if sol.evento else None,
        evento_data=sol.evento.data_evento.isoformat() if sol.evento and sol.evento.data_evento else None,
        area_projecao_id=sol.area_projecao_id,
        area_projecao_nome=sol.area_projecao.nome if sol.area_projecao else None,
        tipo=sol.tipo,
        quantidade=sol.quantidade,
        status=sol.status,
        observacao=sol.observacao,
        codigo_cupom=sol.codigo_cupom,
        codigo_cupom_lista=codigo_cupom_lista,
        codigos_detalhes=codigos_detalhes,
        gerado_por_nome=sol.gerador.nome if sol.gerador else None,
        gerado_em=sol.gerado_em,
        nome_arquivo=sol.nome_arquivo,
        quantidade_linhas=sol.quantidade_linhas,
        solicitado_por_nome=sol.solicitante.nome if sol.solicitante else None,
        created_at=sol.created_at,
        updated_at=sol.updated_at,
    )


@router.get("/eventos", response_model=list[EventoSaldoResponse])
def list_eventos_saldo(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(CORTESIA_SOLICITACAO_PERMISSION, "pode_visualizar")),
):
    """Eventos futuros com o saldo (projetado - solicitado) por área.

    Admins veem todas as áreas ativas; demais usuários só as áreas às quais
    estão vinculados (mesma tabela area_projecao_usuario da tela de Projeção).
    """
    hoje = date.today()
    eventos = (
        db.query(CadastroEvento)
        .filter(
            CadastroEvento.deleted_at.is_(None),
            CadastroEvento.data_evento.isnot(None),
            CadastroEvento.data_evento >= hoje,
        )
        .order_by(CadastroEvento.data_evento.asc(), CadastroEvento.nome.asc())
        .all()
    )
    if not eventos:
        return []

    if is_user_admin(current_user):
        areas = db.query(AreaProjecao).filter(AreaProjecao.ativo == True).order_by(AreaProjecao.nome).all()
    else:
        area_ids = _get_user_area_ids(db, current_user.id)
        areas = (
            db.query(AreaProjecao)
            .filter(AreaProjecao.id.in_(area_ids), AreaProjecao.ativo == True)
            .order_by(AreaProjecao.nome)
            .all()
        )
    if not areas:
        return []

    saldos = _calcular_saldos_bulk(db, [ev.id for ev in eventos], [area.id for area in areas])

    result = []
    for ev in eventos:
        area_items = []
        for area in areas:
            projetado, solicitado, saldo = saldos.get((ev.id, area.id), (0, 0, 0))
            if projetado == 0 and solicitado == 0:
                continue
            area_items.append(SaldoAreaItem(
                area_projecao_id=area.id,
                area_projecao_nome=area.nome,
                projetado=projetado,
                solicitado=solicitado,
                saldo=saldo,
                area_sigla=(area.sigla or "").strip() or None,
            ))
        if not area_items:
            continue
        result.append(EventoSaldoResponse(
            evento_id=ev.id,
            evento_nome=ev.nome,
            evento_data=ev.data_evento.isoformat() if ev.data_evento else None,
            evento_sku=(ev.sku or "").strip() or None,
            areas=area_items,
        ))
    return result


@router.get("/saldo", response_model=list[SaldoAreaItem])
def get_saldo_evento(
    evento_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(CORTESIA_SOLICITACAO_PERMISSION, "pode_visualizar")),
):
    if is_user_admin(current_user):
        areas = db.query(AreaProjecao).filter(AreaProjecao.ativo == True).order_by(AreaProjecao.nome).all()
    else:
        area_ids = _get_user_area_ids(db, current_user.id)
        areas = (
            db.query(AreaProjecao)
            .filter(AreaProjecao.id.in_(area_ids), AreaProjecao.ativo == True)
            .order_by(AreaProjecao.nome)
            .all()
        )
    saldos = _calcular_saldos_bulk(db, [evento_id], [area.id for area in areas])
    result = []
    for area in areas:
        projetado, solicitado, saldo = saldos.get((evento_id, area.id), (0, 0, 0))
        result.append(SaldoAreaItem(
            area_projecao_id=area.id,
            area_projecao_nome=area.nome,
            projetado=projetado,
            solicitado=solicitado,
            saldo=saldo,
            area_sigla=(area.sigla or "").strip() or None,
        ))
    return result


@router.get("/", response_model=list[CortesiaSolicitacaoResponse])
def list_solicitacoes(
    evento_id: int = Query(None),
    area_projecao_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(CORTESIA_SOLICITACAO_PERMISSION, "pode_visualizar")),
):
    query = db.query(CortesiaSolicitacao).filter(CortesiaSolicitacao.deleted_at.is_(None))
    if evento_id:
        query = query.filter(CortesiaSolicitacao.evento_id == evento_id)
    if area_projecao_id:
        query = query.filter(CortesiaSolicitacao.area_projecao_id == area_projecao_id)
    if not is_user_admin(current_user):
        area_ids = _get_user_area_ids(db, current_user.id)
        query = query.filter(CortesiaSolicitacao.area_projecao_id.in_(area_ids))
    rows = query.order_by(CortesiaSolicitacao.created_at.desc()).all()
    return [_serialize(r) for r in rows]


@router.get("/fila-geracao", response_model=list[CortesiaSolicitacaoResponse])
def fila_geracao_cupons(
    evento_id: int = Query(None, description="Se informado, ignora a janela padrão e retorna o histórico completo de gerados deste evento."),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(CORTESIA_SOLICITACAO_PERMISSION, "pode_editar")),
):
    """Fila dedicada de quem gera os cupons: todas as solicitações do tipo
    cupom, sem recorte por área — a mesma regra de acesso que já vale hoje
    para marcar uma solicitação como gerada (pode_editar do módulo, não
    depende de vínculo com a área). O frontend separa pendentes x gerados.

    Pendentes: sempre completos, nunca filtrados por evento nem pela janela
    — é fila de trabalho, um pedido esquecido não pode sumir da lista.
    Gerados: por padrão limitados aos últimos _FILA_GERADOS_JANELA_DIAS dias
    (por gerado_em) e a um teto de segurança; passar evento_id troca para o
    histórico completo daquele evento, sem janela nem teto."""
    base = (
        db.query(CortesiaSolicitacao)
        .options(
            joinedload(CortesiaSolicitacao.evento),
            joinedload(CortesiaSolicitacao.area_projecao),
            joinedload(CortesiaSolicitacao.solicitante),
            joinedload(CortesiaSolicitacao.gerador),
            joinedload(CortesiaSolicitacao.codigos).joinedload(CortesiaCupomCodigo.usuario_uso),
        )
        .filter(
            CortesiaSolicitacao.tipo == TIPO_CUPOM,
            CortesiaSolicitacao.deleted_at.is_(None),
        )
    )

    pendentes = (
        base.filter(CortesiaSolicitacao.status == STATUS_SOLICITADO)
        .order_by(CortesiaSolicitacao.created_at.desc())
        .all()
    )

    gerados_query = base.filter(CortesiaSolicitacao.status == STATUS_GERADO)
    if evento_id:
        gerados = (
            gerados_query
            .filter(CortesiaSolicitacao.evento_id == evento_id)
            .order_by(CortesiaSolicitacao.gerado_em.desc())
            .all()
        )
    else:
        limite = datetime.now(ZoneInfo('America/Sao_Paulo')).replace(tzinfo=None) - timedelta(days=_FILA_GERADOS_JANELA_DIAS)
        gerados = (
            gerados_query
            .filter(CortesiaSolicitacao.gerado_em >= limite)
            .order_by(CortesiaSolicitacao.gerado_em.desc())
            .limit(1000)
            .all()
        )

    return [_serialize(r) for r in pendentes + gerados]


@router.get("/fila-geracao/eventos", response_model=list[EventoFilaOpcao])
def listar_eventos_fila_geracao(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(CORTESIA_SOLICITACAO_PERMISSION, "pode_editar")),
):
    """Eventos com pelo menos um cupom já gerado — alimenta o filtro que
    busca além da janela padrão da fila. Cresce com o número de eventos
    distintos, não com o total de solicitações, então continua rápido mesmo
    com anos de histórico acumulado."""
    rows = (
        db.query(
            CadastroEvento.id,
            CadastroEvento.nome,
            CadastroEvento.data_evento,
        )
        .join(CortesiaSolicitacao, CortesiaSolicitacao.evento_id == CadastroEvento.id)
        .filter(
            CortesiaSolicitacao.tipo == TIPO_CUPOM,
            CortesiaSolicitacao.status == STATUS_GERADO,
            CortesiaSolicitacao.deleted_at.is_(None),
            CadastroEvento.deleted_at.is_(None),
        )
        .distinct()
        .order_by(CadastroEvento.data_evento.desc().nullslast(), CadastroEvento.nome.asc())
        .all()
    )
    return [
        EventoFilaOpcao(
            evento_id=r.id,
            evento_nome=r.nome,
            evento_data=r.data_evento.isoformat() if r.data_evento else None,
        )
        for r in rows
    ]


@router.post("/cupom", response_model=CortesiaSolicitacaoResponse)
def criar_solicitacao_cupom(
    data: CortesiaSolicitacaoCupomCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(CORTESIA_SOLICITACAO_PERMISSION, "pode_criar")),
):
    if data.quantidade <= 0:
        raise HTTPException(status_code=400, detail="A quantidade solicitada deve ser maior que zero")

    evento = db.query(CadastroEvento).filter(CadastroEvento.id == data.evento_id, CadastroEvento.deleted_at.is_(None)).first()
    if not evento:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    area = db.query(AreaProjecao).filter(AreaProjecao.id == data.area_projecao_id).first()
    if not area:
        raise HTTPException(status_code=404, detail="Área não encontrada")

    _check_area_permission(db, current_user, data.area_projecao_id)

    _, _, saldo = _calcular_saldo(db, data.evento_id, data.area_projecao_id)
    if data.quantidade > saldo:
        raise HTTPException(
            status_code=400,
            detail=f"Quantidade solicitada ({data.quantidade}) maior que o saldo disponível ({saldo}) para esta área.",
        )

    sol = CortesiaSolicitacao(
        evento_id=data.evento_id,
        area_projecao_id=data.area_projecao_id,
        tipo=TIPO_CUPOM,
        quantidade=data.quantidade,
        status=STATUS_SOLICITADO,
        observacao=(data.observacao or "").strip() or None,
        solicitado_por=current_user.id,
    )
    db.add(sol)
    db.commit()
    db.refresh(sol)
    return _serialize(sol)


def _contar_linhas_planilha(nome_arquivo: str, conteudo: bytes) -> int | None:
    """Tenta inferir a quantidade de linhas de dados (exclui cabeçalho).
    Falha silenciosamente (retorna None) — nunca bloqueia o upload."""
    try:
        ext = os.path.splitext(nome_arquivo)[1].lower()
        if ext == ".csv":
            texto = conteudo.decode("utf-8-sig", errors="ignore")
            linhas = list(csv.reader(io.StringIO(texto)))
            linhas = [l for l in linhas if any((c or "").strip() for c in l)]
            return max(0, len(linhas) - 1)
        if ext in (".xlsx", ".xls"):
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
            ws = wb.active
            total = 0
            for row in ws.iter_rows(values_only=True):
                if any(c is not None and str(c).strip() for c in row):
                    total += 1
            wb.close()
            return max(0, total - 1)
    except Exception as e:
        logger.warning("Não foi possível contar linhas da planilha %s: %s", nome_arquivo, e)
    return None


@router.post("/planilha", response_model=CortesiaSolicitacaoResponse)
async def criar_solicitacao_planilha(
    evento_id: int = Form(...),
    area_projecao_id: int = Form(...),
    quantidade: int = Form(...),
    observacao: str = Form(None),
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(CORTESIA_SOLICITACAO_PERMISSION, "pode_criar")),
):
    if quantidade <= 0:
        raise HTTPException(status_code=400, detail="A quantidade solicitada deve ser maior que zero")

    evento = db.query(CadastroEvento).filter(CadastroEvento.id == evento_id, CadastroEvento.deleted_at.is_(None)).first()
    if not evento:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    area = db.query(AreaProjecao).filter(AreaProjecao.id == area_projecao_id).first()
    if not area:
        raise HTTPException(status_code=404, detail="Área não encontrada")

    _check_area_permission(db, current_user, area_projecao_id)

    _, _, saldo = _calcular_saldo(db, evento_id, area_projecao_id)
    if quantidade > saldo:
        raise HTTPException(
            status_code=400,
            detail=f"Quantidade informada ({quantidade}) maior que o saldo disponível ({saldo}) para esta área.",
        )

    # ------------------------------------------------------------------
    # Double-submit guard (two layers):
    #
    # 1. threading.Lock — serialises concurrent in-process requests.  Two
    #    requests arriving before either inserts cannot both pass a plain
    #    SELECT check (nothing to lock yet).  Holding the lock for the full
    #    critical section means the second request always observes the first
    #    row in the DB before deciding to proceed.
    #
    # 2. PostgreSQL advisory lock — extends the same guarantee across worker
    #    processes on multi-process deployments.  Silently skipped on SQLite
    #    and other non-PG backends (the threading lock is enough there).
    # ------------------------------------------------------------------
    _upload_lock = _get_planilha_upload_lock(evento_id, area_projecao_id)
    if not _upload_lock.acquire(timeout=10):
        raise HTTPException(
            status_code=409,
            detail="Outro envio para este evento e área está em andamento. Tente novamente em instantes.",
        )
    caminho_completo: str | None = None
    try:
        # Advisory lock for multi-process safety (PostgreSQL only).
        # Uses the two-argument form pg_advisory_xact_lock(key1 int, key2 int)
        # so the keys are the raw IDs — deterministic and identical across
        # every Python process with no hashing.
        try:
            _k1, _k2 = _planilha_advisory_lock_params(evento_id, area_projecao_id)
            db.execute(text("SELECT pg_advisory_xact_lock(:k1, :k2)"), {"k1": _k1, "k2": _k2})
        except Exception:
            pass  # SQLite / non-PG backend — threading lock is sufficient

        # DB-level dedup check: belt-and-suspenders for requests that arrive
        # after the in-process lock has already been released by the first
        # upload but still within the 30-second window.
        recent_cutoff = _now_brasilia() - timedelta(seconds=30)
        duplicate = (
            db.query(CortesiaSolicitacao.id)
            .filter(
                CortesiaSolicitacao.evento_id == evento_id,
                CortesiaSolicitacao.area_projecao_id == area_projecao_id,
                CortesiaSolicitacao.tipo == TIPO_PLANILHA,
                CortesiaSolicitacao.deleted_at.is_(None),
                CortesiaSolicitacao.created_at >= recent_cutoff,
            )
            .first()
        )
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Uma planilha para este evento e área já foi enviada nos últimos 30 segundos. "
                    "Aguarde antes de tentar novamente."
                ),
            )

        nome_original = arquivo.filename or "planilha"
        ext = os.path.splitext(nome_original)[1].lower()
        if ext not in _ALLOWED_EXTENSOES:
            raise HTTPException(
                status_code=400,
                detail="Formato de arquivo não suportado. Envie um arquivo .xlsx, .xls ou .csv.",
            )

        conteudo = await arquivo.read()
        if len(conteudo) > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=400, detail="Arquivo maior que o limite de 15MB.")
        if not conteudo:
            raise HTTPException(status_code=400, detail="Arquivo vazio.")

        os.makedirs(_UPLOAD_DIR, exist_ok=True)
        nome_salvo = f"{uuid.uuid4().hex}{ext}"
        caminho_completo = os.path.join(_UPLOAD_DIR, nome_salvo)
        with open(caminho_completo, "wb") as f:
            f.write(conteudo)

        quantidade_linhas = _contar_linhas_planilha(nome_original, conteudo)

        sol = CortesiaSolicitacao(
            evento_id=evento_id,
            area_projecao_id=area_projecao_id,
            tipo=TIPO_PLANILHA,
            quantidade=quantidade,
            status=STATUS_SOLICITADO,
            observacao=(observacao or "").strip() or None,
            nome_arquivo=nome_original,
            caminho_arquivo=nome_salvo,
            quantidade_linhas=quantidade_linhas,
            solicitado_por=current_user.id,
        )
        db.add(sol)
        try:
            db.commit()
        except Exception:
            # DB insert failed — roll back and remove the file already written
            # to avoid leaving an orphan on disk.
            db.rollback()
            try:
                if caminho_completo:
                    os.remove(caminho_completo)
            except OSError:
                pass
            raise
    finally:
        _upload_lock.release()

    db.refresh(sol)
    return _serialize(sol)


def _aplicar_codigos_cupom(
    db: Session,
    sol: CortesiaSolicitacao,
    codigos_brutos: list[str] | None,
    current_user: Usuario,
) -> None:
    """Valida e grava o(s) código(s) de cupom numa solicitação pendente.

    Compartilhado pelo paste individual (``gerar_cupom``, task #242) e pela
    importação em lote via .txt (``importar_cupons``, task #244) — nunca deve
    haver duas cópias dessa regra, ou os dois caminhos divergem com o tempo.

    Não faz commit: quem chama decide o escopo da transação (uma solicitação
    por commit no paste individual; um commit por grupo evento+área,
    independente dos demais, na importação em lote). Lança ``HTTPException``
    com o motivo da rejeição; nada é persistido quando ela é lançada."""
    if sol.tipo != TIPO_CUPOM:
        raise HTTPException(status_code=400, detail="Somente solicitações do tipo cupom podem ser marcadas como geradas")
    if sol.status == STATUS_GERADO:
        raise HTTPException(status_code=400, detail="Esta solicitação já foi marcada como gerada")

    codigos = [c.strip() for c in (codigos_brutos or []) if c and c.strip()]
    if not codigos:
        raise HTTPException(status_code=400, detail="Informe ao menos um código de cupom gerado no Magento.")

    quantidade = max(1, sol.quantidade or 1)
    if len(codigos) != quantidade:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Esta solicitação pediu {quantidade} cortesia(s), mas {len(codigos)} código(s) "
                f"foram informados. Informe exatamente {quantidade} código(s)."
            ),
        )

    codigo_longo_demais = next((c for c in codigos if len(c) > 300), None)
    if codigo_longo_demais:
        raise HTTPException(
            status_code=400,
            detail=f"O código '{codigo_longo_demais[:40]}...' passa do limite de 300 caracteres.",
        )

    # Duplicidade dentro do próprio envio, case-insensitive.
    vistos: set[str] = set()
    for codigo in codigos:
        chave = codigo.upper()
        if chave in vistos:
            raise HTTPException(status_code=400, detail=f"O código '{codigo}' foi informado mais de uma vez.")
        vistos.add(chave)

    # Duplicidade contra códigos já salvos em qualquer outra solicitação.
    for codigo in codigos:
        if _codigo_cupom_existe(db, codigo.upper()):
            raise HTTPException(status_code=400, detail=f"O código '{codigo}' já está em uso em outra solicitação.")

    sol.codigo_cupom = "\n".join(codigos)
    sol.status = STATUS_GERADO
    sol.gerado_por = current_user.id
    sol.gerado_em = _now_brasilia()

    for codigo in codigos:
        db.add(CortesiaCupomCodigo(solicitacao_id=sol.id, codigo=codigo))


def _commit_codigos_cupom(db: Session) -> None:
    """Faz o commit do que ``_aplicar_codigos_cupom`` preparou, traduzindo um
    IntegrityError do índice único de código para HTTP 409 amigável.

    Extraído junto com ``_aplicar_codigos_cupom`` para que o paste individual
    e a importação em lote tratem a mesma corrida (dois caminhos gravando o
    mesmo código) de forma idêntica."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # Só trata como conflito de unicidade (mensagem amigável) quando o
        # próprio índice único de código é o que rejeitou; qualquer outra
        # violação de integridade é um erro real e não deve ser mascarada
        # (memory: delete-insert-child-race).
        if _CODIGO_CUPOM_INDICE_UNICO not in str(getattr(exc, "orig", exc)):
            raise HTTPException(status_code=500, detail="Erro inesperado ao salvar os códigos de cupom.") from exc
        raise HTTPException(
            status_code=409,
            detail="Um dos códigos já foi salvo por outra solicitação nesse meio tempo. Confira e tente novamente.",
        )


@router.post("/{solicitacao_id}/gerar", response_model=CortesiaSolicitacaoResponse)
def gerar_cupom(
    solicitacao_id: int,
    payload: CortesiaCupomColarRequest,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(CORTESIA_SOLICITACAO_PERMISSION, "pode_editar")),
):
    """Registra o(s) código(s) de cupom já gerados manualmente no Magento
    para esta solicitação — o app não gera mais código sozinho, só valida e
    salva o que foi colado (nada de fallback silencioso em duplicidade)."""
    sol = (
        db.query(CortesiaSolicitacao)
        .filter(
            CortesiaSolicitacao.id == solicitacao_id,
            CortesiaSolicitacao.deleted_at.is_(None),
        )
        .with_for_update()
        .first()
    )
    if not sol:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")

    _aplicar_codigos_cupom(db, sol, payload.codigos, current_user)
    _commit_codigos_cupom(db)

    db.refresh(sol)
    return _serialize(sol)


@router.patch("/{solicitacao_id}/codigos/{codigo_id}/toggle-usado", response_model=CupomCodigoItem)
def toggle_codigo_usado(
    solicitacao_id: int,
    codigo_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(CORTESIA_SOLICITACAO_PERMISSION, "pode_editar")),
):
    """Alterna o status de uso de um código individual (usado ↔ não usado).
    Restrito a quem tem permissão de edição do módulo (mesmo papel que gera cupons)."""
    sol = db.query(CortesiaSolicitacao).filter(
        CortesiaSolicitacao.id == solicitacao_id,
        CortesiaSolicitacao.deleted_at.is_(None),
    ).first()
    if not sol:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")

    codigo = db.query(CortesiaCupomCodigo).filter(
        CortesiaCupomCodigo.id == codigo_id,
        CortesiaCupomCodigo.solicitacao_id == solicitacao_id,
    ).first()
    if not codigo:
        raise HTTPException(status_code=404, detail="Código não encontrado")

    from datetime import datetime
    from zoneinfo import ZoneInfo
    agora = datetime.now(ZoneInfo('America/Sao_Paulo')).replace(tzinfo=None)

    if codigo.usado:
        codigo.usado = False
        codigo.usado_em = None
        codigo.usado_por = None
    else:
        codigo.usado = True
        codigo.usado_em = agora
        codigo.usado_por = current_user.id

    db.commit()
    db.refresh(codigo)
    return CupomCodigoItem(
        id=codigo.id,
        codigo=codigo.codigo,
        usado=codigo.usado,
        usado_em=codigo.usado_em,
        usado_por_nome=codigo.usuario_uso.nome if codigo.usuario_uso else None,
    )


@router.get("/exportar-cupons")
def exportar_cupons(
    evento_id: int = Query(None),
    area_projecao_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(CORTESIA_SOLICITACAO_PERMISSION, "pode_editar")),
):
    """CSV com um código de cupom por linha, dos lotes já gerados — mesma
    regra de acesso e mesmo recorte (sem filtro de área) da fila de geração.
    Sem janela por padrão (ação explícita e pontual, não carregamento de
    tela); use evento_id/area_projecao_id para restringir uma exportação."""
    query = (
        db.query(CortesiaSolicitacao)
        .options(
            joinedload(CortesiaSolicitacao.evento),
            joinedload(CortesiaSolicitacao.area_projecao),
            joinedload(CortesiaSolicitacao.solicitante),
            joinedload(CortesiaSolicitacao.gerador),
        )
        .filter(
            CortesiaSolicitacao.tipo == TIPO_CUPOM,
            CortesiaSolicitacao.status == STATUS_GERADO,
            CortesiaSolicitacao.deleted_at.is_(None),
        )
    )
    if evento_id:
        query = query.filter(CortesiaSolicitacao.evento_id == evento_id)
    if area_projecao_id:
        query = query.filter(CortesiaSolicitacao.area_projecao_id == area_projecao_id)
    rows = query.order_by(CortesiaSolicitacao.gerado_em.desc()).all()

    def _sanitize_csv(val: str) -> str:
        if val and val[0] in ('=', '+', '-', '@', '\t', '\r'):
            return "'" + val
        return val

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow([
        'Evento', 'Data Evento', 'Área', 'Quantidade do Lote', 'Código',
        'Solicitado por', 'Gerado por', 'Gerado em',
    ])
    for sol in rows:
        base = [
            _sanitize_csv(sol.evento.nome if sol.evento else ''),
            sol.evento.data_evento.strftime('%d/%m/%Y') if sol.evento and sol.evento.data_evento else '',
            _sanitize_csv(sol.area_projecao.nome if sol.area_projecao else ''),
            sol.quantidade,
        ]
        tail = [
            _sanitize_csv(sol.solicitante.nome if sol.solicitante else ''),
            _sanitize_csv(sol.gerador.nome if sol.gerador else ''),
            sol.gerado_em.strftime('%d/%m/%Y %H:%M') if sol.gerado_em else '',
        ]
        codigos = _parse_codigos_cupom(sol.codigo_cupom)
        if not codigos:
            writer.writerow(base + [''] + tail)
        else:
            for codigo in codigos:
                writer.writerow(base + [_sanitize_csv(codigo)] + tail)

    output.seek(0)
    bom = '\ufeff'
    content = bom + output.getvalue()

    return StreamingResponse(
        io.BytesIO(content.encode('utf-8-sig')),
        media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename=cupons_gerados.csv'},
    )


def _pendentes_cupom_com_nomes(db: Session) -> list[CortesiaSolicitacao]:
    """Solicitações de cupom ainda pendentes de geração, com evento/área
    pré-carregados — usado tanto pelo modelo de importação quanto pelo
    casamento de linhas na importação em lote."""
    return (
        db.query(CortesiaSolicitacao)
        .options(joinedload(CortesiaSolicitacao.evento), joinedload(CortesiaSolicitacao.area_projecao))
        .filter(
            CortesiaSolicitacao.tipo == TIPO_CUPOM,
            CortesiaSolicitacao.status == STATUS_SOLICITADO,
            CortesiaSolicitacao.deleted_at.is_(None),
        )
        .order_by(CortesiaSolicitacao.evento_id, CortesiaSolicitacao.area_projecao_id, CortesiaSolicitacao.created_at)
        .all()
    )


def _e_cabecalho_importacao(evento_texto: str, area_texto: str, codigo_texto: str) -> bool:
    """Reconhece a linha de cabeçalho pelo conteúdo (EVENTO;AREA;CODIGO,
    case-insensitive/com ou sem acento) — nunca por posição, para que o
    admin possa reordenar ou reenviar o arquivo do modelo sem se preocupar."""
    return (
        evento_texto.strip().lower() == "evento"
        and area_texto.strip().lower() in ("área", "area")
        and codigo_texto.strip().lower() in ("código", "codigo")
    )


@router.get("/importar-cupons/modelo")
def baixar_modelo_importacao_cupons(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(CORTESIA_SOLICITACAO_PERMISSION, "pode_editar")),
):
    """.txt modelo com uma linha por cortesia ainda pendente de geração —
    evento e área já preenchidos exatamente como o importador espera, só
    falta colar o código gerado no Magento no final de cada linha. Elimina
    o maior risco de erro do formato manual: digitar o nome do evento/área
    de um jeito que não bate com o cadastro."""
    pendentes = _pendentes_cupom_com_nomes(db)
    linhas = [
        "# Preencha o código de cupom gerado no Magento no final de cada linha.",
        "# Não altere EVENTO nem AREA — é assim que o importador encontra a solicitação certa.",
        "# Uma linha por cortesia solicitada: quem pediu mais de uma já aparece repetido abaixo.",
        "EVENTO;AREA;CODIGO",
    ]
    if not pendentes:
        linhas.append("# Nenhuma solicitação de cupom pendente de geração no momento.")
    for sol in pendentes:
        evento_nome = sol.evento.nome if sol.evento else f"Evento {sol.evento_id}"
        area_nome = sol.area_projecao.nome if sol.area_projecao else f"Área {sol.area_projecao_id}"
        for _ in range(max(1, sol.quantidade or 1)):
            linhas.append(f"{evento_nome};{area_nome};")
    conteudo = "\n".join(linhas) + "\n"
    return StreamingResponse(
        io.BytesIO(conteudo.encode("utf-8-sig")),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=modelo_importacao_cupons.txt"},
    )


@router.post("/importar-cupons", response_model=ImportarCupomResumo)
async def importar_cupons(
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(CORTESIA_SOLICITACAO_PERMISSION, "pode_editar")),
):
    """Importa em lote códigos de cupom já gerados manualmente no Magento
    (task #244): cada linha do .txt traz EVENTO;AREA;CODIGO e é aplicada à
    solicitação pendente correspondente, reaproveitando a mesma validação e
    gravação do paste individual (_aplicar_codigos_cupom, task #242) — os
    dois caminhos nunca podem divergir.

    Cada grupo de linhas com o mesmo evento+área é resolvido e salvo de forma
    independente: um grupo com problema (solicitação não encontrada, ambígua,
    código repetido, quantidade errada, etc.) não impede os demais grupos do
    arquivo de serem aplicados. Dentro de um grupo continua valendo a regra
    tudo-ou-nada do paste manual — uma solicitação nunca é parcialmente
    atendida."""
    nome_original = arquivo.filename or "cupons.txt"
    if os.path.splitext(nome_original)[1].lower() != ".txt":
        raise HTTPException(status_code=400, detail="Envie um arquivo .txt.")

    conteudo = await arquivo.read()
    if not conteudo:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")
    if len(conteudo) > _MAX_IMPORT_TXT_BYTES:
        raise HTTPException(status_code=400, detail="Arquivo maior que o limite de 5MB.")
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Não foi possível ler o arquivo como texto UTF-8. Salve novamente como .txt (UTF-8) e reenvie.",
        )

    resultados: list[ImportarCupomLinhaResultado] = []
    entradas: list[dict] = []
    ignorados = 0
    for idx, bruta in enumerate(texto.splitlines(), start=1):
        linha = bruta.strip()
        if not linha or linha.startswith("#"):
            continue
        partes = linha.split(";")
        if len(partes) != 3:
            resultados.append(ImportarCupomLinhaResultado(
                linha=idx, texto=linha, aplicado=False,
                mensagem="Formato inválido — cada linha precisa ter EVENTO;AREA;CODIGO.",
            ))
            continue
        evento_texto, area_texto, codigo = (p.strip() for p in partes)
        if _e_cabecalho_importacao(evento_texto, area_texto, codigo):
            ignorados += 1
            continue
        if not codigo:
            # Linha do modelo baixado ainda sem o código preenchido — não é
            # erro, só não há nada a aplicar ainda.
            ignorados += 1
            continue
        if not evento_texto or not area_texto:
            resultados.append(ImportarCupomLinhaResultado(
                linha=idx, texto=linha, aplicado=False,
                mensagem="Formato inválido — EVENTO e AREA não podem ficar em branco.",
            ))
            continue
        if len(codigo) > 300:
            resultados.append(ImportarCupomLinhaResultado(
                linha=idx, texto=linha, aplicado=False,
                mensagem="O código passa do limite de 300 caracteres.",
            ))
            continue
        entradas.append({
            "linha": idx, "texto": linha,
            "evento_texto": evento_texto, "area_texto": area_texto, "codigo": codigo,
        })

    if not entradas:
        if resultados:
            return ImportarCupomResumo(
                total=len(resultados), aplicados=0, rejeitados=len(resultados),
                ignorados=ignorados, resultados=resultados,
            )
        raise HTTPException(
            status_code=400,
            detail="Nenhum código encontrado no arquivo. Preencha ao menos uma linha com EVENTO;AREA;CODIGO.",
        )

    # Duplicidade de código dentro do próprio arquivo, mesmo entre grupos
    # diferentes — nunca aplicar o mesmo código em duas solicitações. Fica
    # mais claro apontar as linhas exatas aqui do que deixar cair no check
    # genérico "já em uso em outra solicitação" lá na frente, que também
    # cobriria (com mensagem mais vaga) um código reciclado de outro upload.
    por_codigo: dict[str, list[dict]] = {}
    for entrada in entradas:
        por_codigo.setdefault(entrada["codigo"].upper(), []).append(entrada)
    entradas_validas: list[dict] = []
    for ocorrencias in por_codigo.values():
        if len(ocorrencias) > 1:
            numeros = ", ".join(str(o["linha"]) for o in ocorrencias)
            for o in ocorrencias:
                resultados.append(ImportarCupomLinhaResultado(
                    linha=o["linha"], texto=o["texto"], aplicado=False,
                    mensagem=f"Código repetido no arquivo (linhas {numeros}) — corrija e reenvie.",
                ))
        else:
            entradas_validas.append(ocorrencias[0])

    # Agrupar por (evento, área) normalizado — cada grupo deve corresponder a
    # no máximo uma solicitação pendente (ambiguidade é rejeitada, nunca
    # distribuída automaticamente entre múltiplas).
    grupos: dict[tuple[str, str], list[dict]] = {}
    for entrada in entradas_validas:
        grupo_chave = (entrada["evento_texto"].lower(), entrada["area_texto"].lower())
        grupos.setdefault(grupo_chave, []).append(entrada)

    mapa_pendentes: dict[tuple[str, str], list[int]] = {}
    for sol in _pendentes_cupom_com_nomes(db):
        chave = (
            (sol.evento.nome if sol.evento else "").strip().lower(),
            (sol.area_projecao.nome if sol.area_projecao else "").strip().lower(),
        )
        mapa_pendentes.setdefault(chave, []).append(sol.id)

    for grupo_chave, linhas_grupo in grupos.items():
        evento_label = linhas_grupo[0]["evento_texto"]
        area_label = linhas_grupo[0]["area_texto"]
        candidatos_ids = mapa_pendentes.get(grupo_chave, [])

        if not candidatos_ids:
            motivo = f"Nenhuma solicitação pendente encontrada para evento '{evento_label}' e área '{area_label}'."
            for item in linhas_grupo:
                resultados.append(ImportarCupomLinhaResultado(linha=item["linha"], texto=item["texto"], aplicado=False, mensagem=motivo))
            continue

        if len(candidatos_ids) > 1:
            motivo = (
                f"Existem {len(candidatos_ids)} solicitações pendentes para evento '{evento_label}' e área '{area_label}' "
                "— ambíguo para importar em lote. Aplique pela fila individualmente (\"Marcar gerado\")."
            )
            for item in linhas_grupo:
                resultados.append(ImportarCupomLinhaResultado(linha=item["linha"], texto=item["texto"], aplicado=False, mensagem=motivo))
            continue

        sol = (
            db.query(CortesiaSolicitacao)
            .filter(CortesiaSolicitacao.id == candidatos_ids[0], CortesiaSolicitacao.deleted_at.is_(None))
            .with_for_update()
            .first()
        )
        if not sol or sol.status == STATUS_GERADO:
            motivo = "Esta solicitação foi gerada ou cancelada por outra ação enquanto o arquivo era processado."
            for item in linhas_grupo:
                resultados.append(ImportarCupomLinhaResultado(linha=item["linha"], texto=item["texto"], aplicado=False, mensagem=motivo))
            continue

        codigos_ordenados = [item["codigo"] for item in sorted(linhas_grupo, key=lambda item: item["linha"])]
        try:
            _aplicar_codigos_cupom(db, sol, codigos_ordenados, current_user)
            _commit_codigos_cupom(db)
        except HTTPException as exc:
            db.rollback()
            motivo = exc.detail if isinstance(exc.detail, str) else "Não foi possível aplicar estes códigos."
            for item in linhas_grupo:
                resultados.append(ImportarCupomLinhaResultado(linha=item["linha"], texto=item["texto"], aplicado=False, mensagem=motivo))
            continue

        db.refresh(sol)
        motivo = f"Aplicado à solicitação de {evento_label} — {area_label} (#{sol.id})."
        for item in linhas_grupo:
            resultados.append(ImportarCupomLinhaResultado(linha=item["linha"], texto=item["texto"], aplicado=True, mensagem=motivo))

    resultados.sort(key=lambda r: r.linha)
    aplicados = sum(1 for r in resultados if r.aplicado)
    rejeitados = sum(1 for r in resultados if not r.aplicado)
    return ImportarCupomResumo(
        total=len(resultados), aplicados=aplicados, rejeitados=rejeitados,
        ignorados=ignorados, resultados=resultados,
    )


@router.delete("/{solicitacao_id}")
def cancelar_solicitacao(
    solicitacao_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(CORTESIA_SOLICITACAO_PERMISSION, "pode_deletar")),
):
    sol = db.query(CortesiaSolicitacao).filter(
        CortesiaSolicitacao.id == solicitacao_id,
        CortesiaSolicitacao.deleted_at.is_(None),
    ).first()
    if not sol:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")

    _check_area_permission(db, current_user, sol.area_projecao_id)

    from datetime import datetime
    from zoneinfo import ZoneInfo
    sol.deleted_at = datetime.now(ZoneInfo('America/Sao_Paulo')).replace(tzinfo=None)
    sol.deleted_by = current_user.id
    db.commit()
    return {"message": "Solicitação cancelada. O saldo da área foi liberado."}


@router.get("/{solicitacao_id}/arquivo")
def baixar_arquivo(
    solicitacao_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(CORTESIA_SOLICITACAO_PERMISSION, "pode_visualizar")),
):
    sol = db.query(CortesiaSolicitacao).filter(CortesiaSolicitacao.id == solicitacao_id).first()
    if not sol or not sol.caminho_arquivo:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    if not is_user_admin(current_user):
        area_ids = _get_user_area_ids(db, current_user.id)
        if sol.area_projecao_id not in area_ids:
            raise HTTPException(status_code=403, detail="Você não tem permissão para acessar este arquivo")

    caminho_completo = os.path.join(_UPLOAD_DIR, sol.caminho_arquivo)
    if not os.path.isfile(caminho_completo):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado no armazenamento")

    return FileResponse(
        caminho_completo,
        filename=sol.nome_arquivo or sol.caminho_arquivo,
        media_type="application/octet-stream",
    )
