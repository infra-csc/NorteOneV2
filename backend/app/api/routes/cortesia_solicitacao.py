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
import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func
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
)
from ...models.projecao import AreaProjecao, AreaProjecaoUsuario, ProjecaoInscritos
from ...models.user import Usuario
from ...schemas.cortesia_solicitacao import (
    CortesiaSolicitacaoCupomCreate,
    CortesiaSolicitacaoGerarUpdate,
    CortesiaSolicitacaoResponse,
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
            ))
        if not area_items:
            continue
        result.append(EventoSaldoResponse(
            evento_id=ev.id,
            evento_nome=ev.nome,
            evento_data=ev.data_evento.isoformat() if ev.data_evento else None,
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
    db.commit()
    db.refresh(sol)
    return _serialize(sol)


@router.post("/{solicitacao_id}/gerar", response_model=CortesiaSolicitacaoResponse)
def gerar_cupom(
    solicitacao_id: int,
    data: CortesiaSolicitacaoGerarUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_permission(CORTESIA_SOLICITACAO_PERMISSION, "pode_editar")),
):
    sol = db.query(CortesiaSolicitacao).filter(
        CortesiaSolicitacao.id == solicitacao_id,
        CortesiaSolicitacao.deleted_at.is_(None),
    ).first()
    if not sol:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    if sol.tipo != TIPO_CUPOM:
        raise HTTPException(status_code=400, detail="Somente solicitações do tipo cupom podem ser marcadas como geradas")
    if sol.status == STATUS_GERADO:
        raise HTTPException(status_code=400, detail="Esta solicitação já foi marcada como gerada")

    codigo = (data.codigo_cupom or "").strip()
    if not codigo:
        raise HTTPException(status_code=400, detail="Informe o(s) código(s) do cupom gerado")

    sol.codigo_cupom = codigo
    sol.status = STATUS_GERADO
    sol.gerado_por = current_user.id
    from datetime import datetime
    from zoneinfo import ZoneInfo
    sol.gerado_em = datetime.now(ZoneInfo('America/Sao_Paulo')).replace(tzinfo=None)
    db.commit()
    db.refresh(sol)
    return _serialize(sol)


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
