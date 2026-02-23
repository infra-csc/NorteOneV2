from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func as sa_func
from typing import List, Optional
from ...core.database import get_db
from ...core.security import get_current_user, require_admin, require_permission
from ...models.user import Usuario
from ...models.cotacao import ViagemCotacao, Cotacao, Fornecedor, CustoImportacao, CotacaoEvento
from ...models.cadastro_evento import CadastroEvento
from ...schemas.cotacao import (
    ViagemCotacaoCreate, ViagemCotacaoUpdate, ViagemCotacaoListResponse, ViagemCotacaoDetailResponse,
    CotacaoCreate, CotacaoUpdate, CotacaoResponse, CotacaoEventoResponse,
    FornecedorCreate, FornecedorResponse,
    CustoImportacaoCreate, CustoImportacaoResponse,
    CotacaoEventoCreate,
    DashboardCotacaoResponse,
)
import httpx
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cotacoes", tags=["Cotações & Importação"])


_view_cotacao = require_permission("cotacoes_importacao", "pode_visualizar")
_edit_cotacao = require_permission("cotacoes_importacao", "pode_editar")


@router.get("/cambio")
def get_cambio(current_user: Usuario = Depends(_view_cotacao)):

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get("https://economia.awesomeapi.com.br/json/last/USD-BRL")
            data = resp.json()
            usd_brl = data.get("USDBRL", {})
            return {
                "taxa": float(usd_brl.get("bid", 0)),
                "variacao": float(usd_brl.get("varBid", 0)),
                "data": usd_brl.get("create_date", ""),
            }
    except Exception as e:
        logger.error(f"Erro ao buscar câmbio: {e}")
        return {"taxa": 0, "variacao": 0, "data": "", "erro": str(e)}


@router.get("/fornecedores", response_model=List[FornecedorResponse])
def list_fornecedores(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_view_cotacao)
):

    return db.query(Fornecedor).filter(Fornecedor.ativo == True).order_by(Fornecedor.nome).all()


@router.post("/fornecedores", response_model=FornecedorResponse, status_code=201)
def create_fornecedor(
    data: FornecedorCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_edit_cotacao)
):

    f = Fornecedor(**data.dict())
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


@router.put("/fornecedores/{fid}", response_model=FornecedorResponse)
def update_fornecedor(
    fid: int,
    data: FornecedorCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_edit_cotacao)
):

    f = db.query(Fornecedor).filter(Fornecedor.id == fid).first()
    if not f:
        raise HTTPException(status_code=404, detail="Fornecedor não encontrado")
    for k, v in data.dict().items():
        setattr(f, k, v)
    db.commit()
    db.refresh(f)
    return f


@router.delete("/fornecedores/{fid}")
def delete_fornecedor(
    fid: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_edit_cotacao)
):

    f = db.query(Fornecedor).filter(Fornecedor.id == fid).first()
    if not f:
        raise HTTPException(status_code=404, detail="Fornecedor não encontrado")
    f.ativo = False
    db.commit()
    return {"message": "Fornecedor desativado"}


@router.get("/viagens", response_model=List[ViagemCotacaoListResponse])
def list_viagens(
    ano: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_view_cotacao)
):

    query = db.query(ViagemCotacao)
    if ano:
        query = query.filter(ViagemCotacao.ano_competencia == ano)
    viagens = query.order_by(ViagemCotacao.created_at.desc()).all()

    result = []
    for v in viagens:
        cotacoes_sel = [c for c in v.cotacoes if c.selecionado]
        total_usd = sum(float(c.valor_total_usd or 0) for c in cotacoes_sel)
        total_brl = sum(float(c.valor_total_brl or 0) for c in cotacoes_sel)
        result.append(ViagemCotacaoListResponse(
            id=v.id,
            titulo=v.titulo,
            destino=v.destino,
            ano_competencia=v.ano_competencia,
            data_inicio=v.data_inicio,
            data_fim=v.data_fim,
            status=v.status,
            observacoes=v.observacoes,
            total_cotacoes=len(v.cotacoes),
            total_usd=total_usd,
            total_brl=total_brl,
            criador_nome=v.criador.nome if v.criador else None,
            created_at=v.created_at,
        ))
    return result


@router.post("/viagens", response_model=ViagemCotacaoListResponse, status_code=201)
def create_viagem(
    data: ViagemCotacaoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_edit_cotacao)
):

    v = ViagemCotacao(**data.dict(), created_by=current_user.id)
    db.add(v)
    db.commit()
    db.refresh(v)
    return ViagemCotacaoListResponse(
        id=v.id, titulo=v.titulo, destino=v.destino,
        ano_competencia=v.ano_competencia, data_inicio=v.data_inicio,
        data_fim=v.data_fim, status=v.status, observacoes=v.observacoes,
        total_cotacoes=0, total_usd=0, total_brl=0,
        criador_nome=current_user.nome, created_at=v.created_at,
    )


@router.get("/viagens/{vid}", response_model=ViagemCotacaoDetailResponse)
def get_viagem(
    vid: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_view_cotacao)
):

    v = db.query(ViagemCotacao).options(
        joinedload(ViagemCotacao.cotacoes).joinedload(Cotacao.fornecedor),
        joinedload(ViagemCotacao.cotacoes).joinedload(Cotacao.eventos),
        joinedload(ViagemCotacao.custos_importacao),
        joinedload(ViagemCotacao.criador),
    ).filter(ViagemCotacao.id == vid).first()
    if not v:
        raise HTTPException(status_code=404, detail="Viagem não encontrada")

    cotacoes_resp = []
    for c in v.cotacoes:
        eventos_resp = []
        for ce in c.eventos:
            ev = db.query(CadastroEvento).filter(CadastroEvento.id == ce.cadastro_evento_id).first()
            eventos_resp.append(CotacaoEventoResponse(
                id=ce.id, cotacao_id=ce.cotacao_id,
                cadastro_evento_id=ce.cadastro_evento_id,
                quantidade=ce.quantidade, observacoes=ce.observacoes,
                evento_nome=ev.nome if ev else None,
            ))
        cotacoes_resp.append(CotacaoResponse(
            id=c.id, viagem_id=c.viagem_id,
            fornecedor_id=c.fornecedor_id,
            produto_nome=c.produto_nome, descricao=c.descricao,
            valor_unitario_usd=float(c.valor_unitario_usd or 0),
            quantidade=c.quantidade,
            taxa_cambio=float(c.taxa_cambio) if c.taxa_cambio else None,
            valor_unitario_brl=float(c.valor_unitario_brl) if c.valor_unitario_brl else None,
            valor_total_usd=float(c.valor_total_usd) if c.valor_total_usd else None,
            valor_total_brl=float(c.valor_total_brl) if c.valor_total_brl else None,
            selecionado=c.selecionado,
            data_cotacao=c.data_cotacao,
            observacoes=c.observacoes,
            fornecedor_nome=c.fornecedor.nome if c.fornecedor else None,
            eventos=eventos_resp,
            created_at=c.created_at,
            updated_at=c.updated_at,
        ))

    custos_resp = [CustoImportacaoResponse(
        id=ci.id, viagem_id=ci.viagem_id,
        descricao=ci.descricao, tipo=ci.tipo,
        valor_usd=float(ci.valor_usd or 0),
        valor_brl=float(ci.valor_brl or 0),
        observacoes=ci.observacoes,
    ) for ci in v.custos_importacao]

    return ViagemCotacaoDetailResponse(
        id=v.id, titulo=v.titulo, destino=v.destino,
        ano_competencia=v.ano_competencia, data_inicio=v.data_inicio,
        data_fim=v.data_fim, status=v.status, observacoes=v.observacoes,
        cotacoes=cotacoes_resp, custos_importacao=custos_resp,
        criador_nome=v.criador.nome if v.criador else None,
        created_at=v.created_at, updated_at=v.updated_at,
    )


@router.put("/viagens/{vid}", response_model=ViagemCotacaoListResponse)
def update_viagem(
    vid: int,
    data: ViagemCotacaoUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_edit_cotacao)
):

    v = db.query(ViagemCotacao).filter(ViagemCotacao.id == vid).first()
    if not v:
        raise HTTPException(status_code=404, detail="Viagem não encontrada")
    for k, val in data.dict(exclude_unset=True).items():
        setattr(v, k, val)
    db.commit()
    db.refresh(v)
    cotacoes_sel = [c for c in v.cotacoes if c.selecionado]
    return ViagemCotacaoListResponse(
        id=v.id, titulo=v.titulo, destino=v.destino,
        ano_competencia=v.ano_competencia, data_inicio=v.data_inicio,
        data_fim=v.data_fim, status=v.status, observacoes=v.observacoes,
        total_cotacoes=len(v.cotacoes),
        total_usd=sum(float(c.valor_total_usd or 0) for c in cotacoes_sel),
        total_brl=sum(float(c.valor_total_brl or 0) for c in cotacoes_sel),
        criador_nome=v.criador.nome if v.criador else None,
        created_at=v.created_at,
    )


@router.delete("/viagens/{vid}")
def delete_viagem(
    vid: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_edit_cotacao)
):

    v = db.query(ViagemCotacao).filter(ViagemCotacao.id == vid).first()
    if not v:
        raise HTTPException(status_code=404, detail="Viagem não encontrada")
    db.delete(v)
    db.commit()
    return {"message": "Viagem excluída"}


@router.post("/viagens/{vid}/cotacoes", response_model=CotacaoResponse, status_code=201)
def create_cotacao(
    vid: int,
    data: CotacaoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_edit_cotacao)
):

    v = db.query(ViagemCotacao).filter(ViagemCotacao.id == vid).first()
    if not v:
        raise HTTPException(status_code=404, detail="Viagem não encontrada")

    c = Cotacao(viagem_id=vid, **data.dict())
    if c.taxa_cambio and c.valor_unitario_usd:
        c.valor_unitario_brl = float(c.valor_unitario_usd) * float(c.taxa_cambio)
    c.valor_total_usd = float(c.valor_unitario_usd or 0) * (c.quantidade or 1)
    if c.taxa_cambio:
        c.valor_total_brl = float(c.valor_total_usd) * float(c.taxa_cambio)

    db.add(c)
    db.commit()
    db.refresh(c)

    fornecedor_nome = None
    if c.fornecedor_id:
        f = db.query(Fornecedor).filter(Fornecedor.id == c.fornecedor_id).first()
        fornecedor_nome = f.nome if f else None

    return CotacaoResponse(
        id=c.id, viagem_id=c.viagem_id,
        fornecedor_id=c.fornecedor_id,
        produto_nome=c.produto_nome, descricao=c.descricao,
        valor_unitario_usd=float(c.valor_unitario_usd or 0),
        quantidade=c.quantidade,
        taxa_cambio=float(c.taxa_cambio) if c.taxa_cambio else None,
        valor_unitario_brl=float(c.valor_unitario_brl) if c.valor_unitario_brl else None,
        valor_total_usd=float(c.valor_total_usd) if c.valor_total_usd else None,
        valor_total_brl=float(c.valor_total_brl) if c.valor_total_brl else None,
        selecionado=c.selecionado,
        data_cotacao=c.data_cotacao,
        observacoes=c.observacoes,
        fornecedor_nome=fornecedor_nome,
        eventos=[],
        created_at=c.created_at, updated_at=c.updated_at,
    )


@router.put("/cotacoes/{cid}", response_model=CotacaoResponse)
def update_cotacao(
    cid: int,
    data: CotacaoUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_edit_cotacao)
):

    c = db.query(Cotacao).filter(Cotacao.id == cid).first()
    if not c:
        raise HTTPException(status_code=404, detail="Cotação não encontrada")

    for k, val in data.dict(exclude_unset=True).items():
        setattr(c, k, val)

    if c.taxa_cambio and c.valor_unitario_usd:
        c.valor_unitario_brl = float(c.valor_unitario_usd) * float(c.taxa_cambio)
    c.valor_total_usd = float(c.valor_unitario_usd or 0) * (c.quantidade or 1)
    if c.taxa_cambio:
        c.valor_total_brl = float(c.valor_total_usd) * float(c.taxa_cambio)

    db.commit()
    db.refresh(c)

    fornecedor_nome = None
    if c.fornecedor_id:
        f = db.query(Fornecedor).filter(Fornecedor.id == c.fornecedor_id).first()
        fornecedor_nome = f.nome if f else None

    eventos_resp = []
    for ce in c.eventos:
        ev = db.query(CadastroEvento).filter(CadastroEvento.id == ce.cadastro_evento_id).first()
        eventos_resp.append(CotacaoEventoResponse(
            id=ce.id, cotacao_id=ce.cotacao_id,
            cadastro_evento_id=ce.cadastro_evento_id,
            quantidade=ce.quantidade, observacoes=ce.observacoes,
            evento_nome=ev.nome if ev else None,
        ))

    return CotacaoResponse(
        id=c.id, viagem_id=c.viagem_id,
        fornecedor_id=c.fornecedor_id,
        produto_nome=c.produto_nome, descricao=c.descricao,
        valor_unitario_usd=float(c.valor_unitario_usd or 0),
        quantidade=c.quantidade,
        taxa_cambio=float(c.taxa_cambio) if c.taxa_cambio else None,
        valor_unitario_brl=float(c.valor_unitario_brl) if c.valor_unitario_brl else None,
        valor_total_usd=float(c.valor_total_usd) if c.valor_total_usd else None,
        valor_total_brl=float(c.valor_total_brl) if c.valor_total_brl else None,
        selecionado=c.selecionado,
        data_cotacao=c.data_cotacao,
        observacoes=c.observacoes,
        fornecedor_nome=fornecedor_nome,
        eventos=eventos_resp,
        created_at=c.created_at, updated_at=c.updated_at,
    )


@router.delete("/cotacoes/{cid}")
def delete_cotacao(
    cid: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_edit_cotacao)
):

    c = db.query(Cotacao).filter(Cotacao.id == cid).first()
    if not c:
        raise HTTPException(status_code=404, detail="Cotação não encontrada")
    db.delete(c)
    db.commit()
    return {"message": "Cotação excluída"}


@router.post("/cotacoes/{cid}/eventos", response_model=CotacaoEventoResponse, status_code=201)
def add_evento_to_cotacao(
    cid: int,
    data: CotacaoEventoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_edit_cotacao)
):

    c = db.query(Cotacao).filter(Cotacao.id == cid).first()
    if not c:
        raise HTTPException(status_code=404, detail="Cotação não encontrada")
    ev = db.query(CadastroEvento).filter(CadastroEvento.id == data.cadastro_evento_id).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Evento não encontrado")

    ce = CotacaoEvento(cotacao_id=cid, **data.dict())
    db.add(ce)
    db.commit()
    db.refresh(ce)
    return CotacaoEventoResponse(
        id=ce.id, cotacao_id=ce.cotacao_id,
        cadastro_evento_id=ce.cadastro_evento_id,
        quantidade=ce.quantidade, observacoes=ce.observacoes,
        evento_nome=ev.nome,
    )


@router.delete("/cotacoes-evento/{ce_id}")
def remove_evento_from_cotacao(
    ce_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_edit_cotacao)
):

    ce = db.query(CotacaoEvento).filter(CotacaoEvento.id == ce_id).first()
    if not ce:
        raise HTTPException(status_code=404, detail="Vínculo não encontrado")
    db.delete(ce)
    db.commit()
    return {"message": "Vínculo removido"}


@router.post("/viagens/{vid}/custos", response_model=CustoImportacaoResponse, status_code=201)
def add_custo_importacao(
    vid: int,
    data: CustoImportacaoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_edit_cotacao)
):

    v = db.query(ViagemCotacao).filter(ViagemCotacao.id == vid).first()
    if not v:
        raise HTTPException(status_code=404, detail="Viagem não encontrada")
    ci = CustoImportacao(viagem_id=vid, **data.dict())
    db.add(ci)
    db.commit()
    db.refresh(ci)
    return CustoImportacaoResponse(
        id=ci.id, viagem_id=ci.viagem_id,
        descricao=ci.descricao, tipo=ci.tipo,
        valor_usd=float(ci.valor_usd or 0),
        valor_brl=float(ci.valor_brl or 0),
        observacoes=ci.observacoes,
    )


@router.put("/custos/{ci_id}", response_model=CustoImportacaoResponse)
def update_custo_importacao(
    ci_id: int,
    data: CustoImportacaoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_edit_cotacao)
):

    ci = db.query(CustoImportacao).filter(CustoImportacao.id == ci_id).first()
    if not ci:
        raise HTTPException(status_code=404, detail="Custo não encontrado")
    for k, v in data.dict().items():
        setattr(ci, k, v)
    db.commit()
    db.refresh(ci)
    return CustoImportacaoResponse(
        id=ci.id, viagem_id=ci.viagem_id,
        descricao=ci.descricao, tipo=ci.tipo,
        valor_usd=float(ci.valor_usd or 0),
        valor_brl=float(ci.valor_brl or 0),
        observacoes=ci.observacoes,
    )


@router.delete("/custos/{ci_id}")
def delete_custo_importacao(
    ci_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_edit_cotacao)
):

    ci = db.query(CustoImportacao).filter(CustoImportacao.id == ci_id).first()
    if not ci:
        raise HTTPException(status_code=404, detail="Custo não encontrado")
    db.delete(ci)
    db.commit()
    return {"message": "Custo excluído"}


@router.get("/dashboard", response_model=DashboardCotacaoResponse)
def get_dashboard(
    ano: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(_view_cotacao)
):


    query = db.query(ViagemCotacao)
    if ano:
        query = query.filter(ViagemCotacao.ano_competencia == ano)
    viagens = query.all()

    total_viagens = len(viagens)
    viagens_em_andamento = len([v for v in viagens if v.status == "Em Andamento"])

    all_cotacoes = []
    for v in viagens:
        all_cotacoes.extend(v.cotacoes)

    cotacoes_sel = [c for c in all_cotacoes if c.selecionado]
    total_usd = sum(float(c.valor_total_usd or 0) for c in cotacoes_sel)
    total_brl = sum(float(c.valor_total_brl or 0) for c in cotacoes_sel)

    all_custos = []
    for v in viagens:
        all_custos.extend(v.custos_importacao)
    total_custos_usd = sum(float(ci.valor_usd or 0) for ci in all_custos)
    total_custos_brl = sum(float(ci.valor_brl or 0) for ci in all_custos)

    fornecedores_ids = set(c.fornecedor_id for c in all_cotacoes if c.fornecedor_id)
    eventos_ids = set()
    for c in cotacoes_sel:
        for ce in c.eventos:
            eventos_ids.add(ce.cadastro_evento_id)

    evento_custos = {}
    for c in cotacoes_sel:
        for ce in c.eventos:
            eid = ce.cadastro_evento_id
            if eid not in evento_custos:
                ev = db.query(CadastroEvento).filter(CadastroEvento.id == eid).first()
                evento_custos[eid] = {"evento": ev.nome if ev else f"ID {eid}", "total_usd": 0, "total_brl": 0}
            evento_custos[eid]["total_usd"] += float(c.valor_total_usd or 0)
            evento_custos[eid]["total_brl"] += float(c.valor_total_brl or 0)

    fornecedor_custos = {}
    for c in cotacoes_sel:
        fid = c.fornecedor_id or 0
        fname = c.fornecedor.nome if c.fornecedor else "Sem fornecedor"
        if fid not in fornecedor_custos:
            fornecedor_custos[fid] = {"fornecedor": fname, "total_usd": 0, "total_brl": 0, "qtd_cotacoes": 0}
        fornecedor_custos[fid]["total_usd"] += float(c.valor_total_usd or 0)
        fornecedor_custos[fid]["total_brl"] += float(c.valor_total_brl or 0)
        fornecedor_custos[fid]["qtd_cotacoes"] += 1

    status_count = {}
    for v in viagens:
        s = v.status
        if s not in status_count:
            status_count[s] = 0
        status_count[s] += 1

    return DashboardCotacaoResponse(
        total_viagens=total_viagens,
        viagens_em_andamento=viagens_em_andamento,
        total_produtos_cotados=len(all_cotacoes),
        total_selecionados=len(cotacoes_sel),
        total_usd=total_usd,
        total_brl=total_brl,
        total_custos_importacao_usd=total_custos_usd,
        total_custos_importacao_brl=total_custos_brl,
        custo_total_brl=total_brl + total_custos_brl,
        total_fornecedores=len(fornecedores_ids),
        total_eventos_vinculados=len(eventos_ids),
        por_evento=list(evento_custos.values()),
        por_fornecedor=list(fornecedor_custos.values()),
        por_status=[{"status": k, "quantidade": v} for k, v in status_count.items()],
    )
