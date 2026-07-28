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
import secrets
import threading
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import and_, func, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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
    CortesiaSolicitacaoCupomCreate,
    CortesiaSolicitacaoResponse,
    CupomCodigoItem,
    EventoSaldoResponse,
    SaldoAreaItem,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cortesia-solicitacao", tags=["Solicitação de Cortesias"])

# Módulo próprio de permissão (Perfil de Acesso): visualizar/criar solicitações
# é o fluxo do responsável de área; editar é reservado a quem gera os cupons.
CORTESIA_SOLICITACAO_PERMISSION = "cortesia_solicitacao"

_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "uploads", "cortesia_solicitacao")
_ALLOWED_EXTENSOES = {".xlsx", ".xls", ".csv"}
_MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15MB

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


# Geração automática de código de cupom (task #174): sigla da área + SKU do
# evento + sufixo aleatório, todos os códigos com o mesmo tamanho total fixo.
# Alfabeto sem 0/O/1/I/L para não confundir na hora de digitar/conferir.
# Sigla vai até 10 caracteres e o SKU do evento varia hoje entre 8 e 10 —
# o total precisa cobrir o pior caso (10+10=20) mais um sufixo com entropia
# mínima, senão combinações longas estourariam o tamanho fixo dos demais.
_CODIGO_CUPOM_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODIGO_CUPOM_TAMANHO_TOTAL = 26
_CODIGO_CUPOM_SUFIXO_MIN = 6
_CODIGO_CUPOM_BASE_MAXIMA = _CODIGO_CUPOM_TAMANHO_TOTAL - _CODIGO_CUPOM_SUFIXO_MIN
_CODIGO_CUPOM_MAX_TENTATIVAS = 30
_CODIGO_CUPOM_INDICE_UNICO = "ux_cortesia_cupom_codigo_codigo"


def _codigo_cupom_existe(db: Session, codigo: str) -> bool:
    return db.query(CortesiaCupomCodigo.id).filter(func.upper(CortesiaCupomCodigo.codigo) == codigo).first() is not None


def _verificar_espaco_cupom(db: Session, base: str, quantidade: int) -> None:
    """Pré-vôo: verifica se há espaço suficiente no alfabeto de sufixos para
    gerar *quantidade* novos códigos únicos com este base (sigla+SKU).

    Levanta HTTP 400 claro em dois cenários:
    - Espaço totalmente esgotado: não há combinações restantes o suficiente.
    - Espaço quase esgotado (>90% já utilizado): evita que a geração falhe
      silenciosamente no loop de tentativas quando a densidade é alta.

    Não bloqueia para bases com espaço amplo (caso normal); só age quando o
    sufixo é mínimo (_CODIGO_CUPOM_SUFIXO_MIN) e a densidade está elevada.
    """
    sufixo_len = max(_CODIGO_CUPOM_SUFIXO_MIN, _CODIGO_CUPOM_TAMANHO_TOTAL - len(base))
    total_combinacoes = len(_CODIGO_CUPOM_ALPHABET) ** sufixo_len

    # Comprimento exato que todos os códigos gerados para este base terão.
    comprimento_codigo = len(base) + sufixo_len

    # Conta os códigos ocupados por este base em dois grupos:
    #
    # 1. Linhas com base preenchida (coluna adicionada + backfill): match
    #    exato na coluna base — sem ambiguidade de prefixo entre bases distintas.
    #
    # 2. Linhas legadas com base IS NULL (geradas antes da coluna existir e
    #    que a migração de backfill não conseguiu preencher — e.g. sigla ou SKU
    #    ausentes no momento da migração): fallback via comprimento exato +
    #    prefixo escapado.  Pode sobre-contar ligeiramente quando bases distintas
    #    compartilham prefixo (e.g. "AB" vs "ABC"), mas erra do lado conservador
    #    correto — impede falsos negativos na guarda de esgotamento.
    base_escaped = base.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    ja_usados = (
        db.query(func.count(CortesiaCupomCodigo.id))
        .filter(
            or_(
                CortesiaCupomCodigo.base == base,
                and_(
                    CortesiaCupomCodigo.base.is_(None),
                    func.length(CortesiaCupomCodigo.codigo) == comprimento_codigo,
                    func.upper(CortesiaCupomCodigo.codigo).like(
                        f"{base_escaped}%", escape="\\"
                    ),
                ),
            )
        )
        .scalar()
    ) or 0

    espaco_restante = total_combinacoes - ja_usados

    if quantidade > espaco_restante:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Não há combinações únicas suficientes para gerar {quantidade} cupons com "
                f"a base '{base}' (sigla+SKU). "
                f"Espaço total: {total_combinacoes:,} combinações; "
                f"já utilizadas: {ja_usados:,}; disponíveis: {max(0, espaco_restante):,}. "
                "Ajuste a sigla da área ou o SKU do evento para ampliar o espaço disponível."
            ),
        )

    # Limiar de segurança: nega a geração quando mais de 90 % do espaço já foi
    # consumido, pois a taxa de colisões sobe rapidamente e tornaria o loop de
    # tentativas por código quase certo de falhar.
    if total_combinacoes > 0 and (ja_usados + quantidade) > total_combinacoes * 0.9:
        pct_usado = ja_usados / total_combinacoes * 100
        raise HTTPException(
            status_code=400,
            detail=(
                f"O espaço de códigos para a base '{base}' (sigla+SKU) está quase esgotado: "
                f"{ja_usados:,} de {total_combinacoes:,} combinações já utilizadas "
                f"({pct_usado:.1f}%). Gerar mais {quantidade} cupom(ns) ultrapassaria "
                "o limite de segurança de 90 % de ocupação. "
                "Ajuste a sigla da área ou o SKU do evento para ampliar o espaço disponível."
            ),
        )


def _gerar_codigo_cupom_unico(db: Session, base: str, ja_gerados: list[str]) -> str:
    """Gera um código único (contra o histórico já persistido + os já
    reservados nesta mesma chamada). Levanta HTTPException 500 clara se
    esgotar as tentativas — nunca retorna um código sem checar unicidade."""
    sufixo_len = max(_CODIGO_CUPOM_SUFIXO_MIN, _CODIGO_CUPOM_TAMANHO_TOTAL - len(base))
    for _ in range(_CODIGO_CUPOM_MAX_TENTATIVAS):
        sufixo = "".join(secrets.choice(_CODIGO_CUPOM_ALPHABET) for _ in range(sufixo_len))
        candidato = f"{base}{sufixo}"
        if candidato in ja_gerados:
            continue
        if not _codigo_cupom_existe(db, candidato):
            return candidato
    raise HTTPException(status_code=500, detail="Não foi possível gerar um código de cupom único. Tente novamente.")


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

    result = []
    for ev in eventos:
        area_items = []
        for area in areas:
            projetado, solicitado, saldo = _calcular_saldo(db, ev.id, area.id)
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
    result = []
    for area in areas:
        projetado, solicitado, saldo = _calcular_saldo(db, evento_id, area.id)
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
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(CORTESIA_SOLICITACAO_PERMISSION, "pode_editar")),
):
    """Fila dedicada de quem gera os cupons: todas as solicitações do tipo
    cupom, sem recorte por área — a mesma regra de acesso que já vale hoje
    para marcar uma solicitação como gerada (pode_editar do módulo, não
    depende de vínculo com a área). O frontend separa pendentes x gerados."""
    rows = (
        db.query(CortesiaSolicitacao)
        .filter(
            CortesiaSolicitacao.tipo == TIPO_CUPOM,
            CortesiaSolicitacao.deleted_at.is_(None),
        )
        .order_by(CortesiaSolicitacao.created_at.desc())
        .all()
    )
    return [_serialize(r) for r in rows]


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


@router.post("/{solicitacao_id}/gerar", response_model=CortesiaSolicitacaoResponse)
def gerar_cupom(
    solicitacao_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(CORTESIA_SOLICITACAO_PERMISSION, "pode_editar")),
):
    """Gera automaticamente os códigos de cupom desta solicitação — um por
    unidade solicitada — no padrão SIGLA da área + SKU do evento + sufixo
    aleatório. Falha com mensagem clara se a área ainda não tem sigla
    cadastrada ou se o evento não tem SKU (nada de fallback silencioso)."""
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
    if sol.tipo != TIPO_CUPOM:
        raise HTTPException(status_code=400, detail="Somente solicitações do tipo cupom podem ser marcadas como geradas")
    if sol.status == STATUS_GERADO:
        raise HTTPException(status_code=400, detail="Esta solicitação já foi marcada como gerada")

    area = db.query(AreaProjecao).filter(AreaProjecao.id == sol.area_projecao_id).first()
    sigla = (area.sigla or "").strip().upper() if area else ""
    if not sigla:
        nome_area = area.nome if area else "desta solicitação"
        raise HTTPException(
            status_code=400,
            detail=f"A área '{nome_area}' ainda não tem uma sigla configurada. Configure a sigla em Configurações › Áreas e Usuários antes de gerar os cupons.",
        )

    evento = db.query(CadastroEvento).filter(CadastroEvento.id == sol.evento_id).first()
    sku = (evento.sku or "").strip().upper() if evento else ""
    if not sku:
        raise HTTPException(status_code=400, detail="O evento desta solicitação não tem um SKU cadastrado. Cadastre o SKU do evento antes de gerar os cupons.")

    base = f"{sigla}{sku}"
    if len(base) > _CODIGO_CUPOM_BASE_MAXIMA:
        raise HTTPException(
            status_code=400,
            detail=(
                f"A sigla '{sigla}' combinada com o SKU '{sku}' do evento soma "
                f"{len(base)} caracteres, acima do limite de {_CODIGO_CUPOM_BASE_MAXIMA} "
                "necessário para manter todos os códigos de cupom com o mesmo tamanho. "
                "Ajuste a sigla da área para algo mais curto e tente novamente."
            ),
        )
    quantidade = max(1, sol.quantidade or 1)

    # Pré-vôo: garante que há espaço suficiente no alfabeto de sufixos antes
    # de iniciar qualquer tentativa de geração (HTTP 400 explícito se não há).
    _verificar_espaco_cupom(db, base, quantidade)

    # Retry no nível da transação: mesmo com a checagem prévia de unicidade,
    # uma colisão real só é detectada pelo índice único no commit — nesse
    # caso descarta tudo e gera de novo (memory: delete-insert-child-race).
    for tentativa in range(3):
        codigos: list[str] = []
        for _ in range(quantidade):
            codigos.append(_gerar_codigo_cupom_unico(db, base, codigos))

        # Normaliza para um código por linha, mesmo formato usado pelo fluxo
        # legado — mantém leitura/exportação consistentes.
        sol.codigo_cupom = "\n".join(codigos)
        sol.status = STATUS_GERADO
        sol.gerado_por = current_user.id
        sol.gerado_em = _now_brasilia()

        for codigo in codigos:
            db.add(CortesiaCupomCodigo(solicitacao_id=sol.id, codigo=codigo, base=base))

        try:
            db.commit()
            break
        except IntegrityError as exc:
            db.rollback()
            # Só trata como colisão de código (retry vale a pena) quando o
            # próprio índice único de código é o que rejeitou; qualquer outra
            # violação de integridade é um erro real e não deve ser mascarado
            # como "conflito ao gerar código".
            if _CODIGO_CUPOM_INDICE_UNICO not in str(getattr(exc, "orig", exc)):
                raise HTTPException(status_code=500, detail="Erro inesperado ao salvar os códigos de cupom gerados.") from exc
            if tentativa == 2:
                raise HTTPException(status_code=409, detail="Conflito ao gerar códigos únicos de cupom. Tente novamente.")
            continue

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
    regra de acesso e mesmo recorte (sem filtro de área) da fila de geração."""
    query = db.query(CortesiaSolicitacao).filter(
        CortesiaSolicitacao.tipo == TIPO_CUPOM,
        CortesiaSolicitacao.status == STATUS_GERADO,
        CortesiaSolicitacao.deleted_at.is_(None),
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
