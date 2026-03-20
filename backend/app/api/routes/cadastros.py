from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload
from typing import List
from datetime import datetime, date
from decimal import Decimal

from app.core.database import get_db
from ...core.security import get_current_user
from app.models.cadastro_evento import (
    CadastroEvento, CadastroCortesia, CadastroTaxa,
    CadastroKitProduto, CadastroKitProdutoItem,
    CadastroFaixaPrecoSite, CadastroFaixaPrecoGrupos,
    CircuitoProduto, Localizacao
)
from app.models.dimensoes import DimProjeto
from app.schemas.cadastro_evento import (
    CadastroEventoCreate, CadastroEventoUpdate, CadastroEventoResponse,
    InfoGeral, AtletasData, RetiradaKit, FaixasPrecoByKit,
    CortesiaItemResponse, TaxaItemResponse, KitProdutoResponse, ProdutoItemResponse,
    FaixaPrecoItemBase, CircuitoProdutoSchema, LocalizacaoSchema, AppaiData
)

router = APIRouter(prefix="/cadastros", tags=["Cadastros"], dependencies=[Depends(get_current_user)])

_CADASTRO_EAGER = [
    selectinload(CadastroEvento.cortesias),
    selectinload(CadastroEvento.taxas),
    selectinload(CadastroEvento.kit_produtos).selectinload(CadastroKitProduto.produtos),
    selectinload(CadastroEvento.faixas_preco_site),
    selectinload(CadastroEvento.faixas_preco_grupos),
]


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
        appai=AppaiData(pago=cadastro.atletas_appai_pago or 0, tkt_medio=float(cadastro.atletas_appai_tkt_medio or 0))
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
    
    faixas_site_basico = [
        FaixaPrecoItemBase(faixa=f.faixa, qtd=f.qtd, tkt_medio=f.tkt_medio or Decimal("0"), total=f.total or Decimal("0"))
        for f in cadastro.faixas_preco_site if f.tipo_kit == "kit_basico"
    ]
    faixas_site_participacao = [
        FaixaPrecoItemBase(faixa=f.faixa, qtd=f.qtd, tkt_medio=f.tkt_medio or Decimal("0"), total=f.total or Decimal("0"))
        for f in cadastro.faixas_preco_site if f.tipo_kit == "kit_participacao"
    ]
    
    faixas_grupos_basico = [
        FaixaPrecoItemBase(faixa=f.faixa, qtd=f.qtd, tkt_medio=f.tkt_medio or Decimal("0"), total=f.total or Decimal("0"))
        for f in cadastro.faixas_preco_grupos if f.tipo_kit == "kit_basico"
    ]
    faixas_grupos_participacao = [
        FaixaPrecoItemBase(faixa=f.faixa, qtd=f.qtd, tkt_medio=f.tkt_medio or Decimal("0"), total=f.total or Decimal("0"))
        for f in cadastro.faixas_preco_grupos if f.tipo_kit == "kit_participacao"
    ]
    
    return {
        "id": cadastro.id,
        "projeto_id": cadastro.projeto_id,
        "nome": cadastro.nome,
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
        "faixas_preco_site": FaixasPrecoByKit(kit_basico=faixas_site_basico, kit_participacao=faixas_site_participacao),
        "faixas_preco_grupos": FaixasPrecoByKit(kit_basico=faixas_grupos_basico, kit_participacao=faixas_grupos_participacao),
        "created_at": cadastro.created_at,
        "updated_at": cadastro.updated_at
    }


@router.get("/", response_model=List[CadastroEventoResponse])
def listar_cadastros(
    skip: int = 0,
    limit: int = 100,
    status: str = None,
    db: Session = Depends(get_db)
):
    """Lista todos os cadastros de eventos"""
    query = db.query(CadastroEvento).options(*_CADASTRO_EAGER)
    
    if status:
        query = query.filter(CadastroEvento.status == status)
    
    cadastros = query.order_by(CadastroEvento.id.desc()).offset(skip).limit(limit).all()
    
    return [db_to_response(c) for c in cadastros]


@router.get("/{cadastro_id}", response_model=CadastroEventoResponse)
def obter_cadastro(cadastro_id: int, db: Session = Depends(get_db)):
    """Obtém um cadastro específico"""
    cadastro = db.query(CadastroEvento).options(*_CADASTRO_EAGER).filter(CadastroEvento.id == cadastro_id).first()
    
    if not cadastro:
        raise HTTPException(status_code=404, detail="Cadastro não encontrado")
    
    return db_to_response(cadastro)


@router.post("/", response_model=CadastroEventoResponse)
def criar_cadastro(data: CadastroEventoCreate, db: Session = Depends(get_db)):
    """Cria um novo cadastro de evento"""
    
    if data.sku and data.sku.strip():
        existing_sku = db.query(CadastroEvento).filter(
            CadastroEvento.sku == data.sku.strip()
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
        except:
            pass
    
    retirada_dt = None
    if data.retirada_kit.data_horario:
        try:
            retirada_dt = datetime.fromisoformat(data.retirada_kit.data_horario)
        except:
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
        retirada_kit_local=data.retirada_kit.local,
        retirada_kit_data_horario=retirada_dt
    )
    
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
            except:
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
    
    for faixa in data.faixas_preco_site.kit_basico:
        db.add(CadastroFaixaPrecoSite(
            cadastro_id=cadastro.id,
            tipo_kit="kit_basico",
            faixa=faixa.faixa,
            qtd=faixa.qtd,
            tkt_medio=faixa.tkt_medio,
            total=faixa.total
        ))
    
    for faixa in data.faixas_preco_site.kit_participacao:
        db.add(CadastroFaixaPrecoSite(
            cadastro_id=cadastro.id,
            tipo_kit="kit_participacao",
            faixa=faixa.faixa,
            qtd=faixa.qtd,
            tkt_medio=faixa.tkt_medio,
            total=faixa.total
        ))
    
    for faixa in data.faixas_preco_grupos.kit_basico:
        db.add(CadastroFaixaPrecoGrupos(
            cadastro_id=cadastro.id,
            tipo_kit="kit_basico",
            faixa=faixa.faixa,
            qtd=faixa.qtd,
            tkt_medio=faixa.tkt_medio,
            total=faixa.total
        ))
    
    for faixa in data.faixas_preco_grupos.kit_participacao:
        db.add(CadastroFaixaPrecoGrupos(
            cadastro_id=cadastro.id,
            tipo_kit="kit_participacao",
            faixa=faixa.faixa,
            qtd=faixa.qtd,
            tkt_medio=faixa.tkt_medio,
            total=faixa.total
        ))
    
    db.commit()
    db.refresh(cadastro)
    
    return db_to_response(cadastro)


@router.put("/{cadastro_id}", response_model=CadastroEventoResponse)
def atualizar_cadastro(cadastro_id: int, data: CadastroEventoUpdate, db: Session = Depends(get_db)):
    """Atualiza um cadastro existente"""
    cadastro = db.query(CadastroEvento).filter(CadastroEvento.id == cadastro_id).first()
    
    if not cadastro:
        raise HTTPException(status_code=404, detail="Cadastro não encontrado")
    
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
    
    if data.info_geral is not None:
        if data.info_geral.data:
            try:
                cadastro.data_evento = date.fromisoformat(data.info_geral.data)
            except:
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
    
    if data.retirada_kit is not None:
        cadastro.retirada_kit_local = data.retirada_kit.local
        if data.retirada_kit.data_horario:
            try:
                cadastro.retirada_kit_data_horario = datetime.fromisoformat(data.retirada_kit.data_horario)
            except:
                pass
    
    if data.cortesias is not None:
        for c in cadastro.cortesias:
            db.delete(c)
        for cortesia in data.cortesias:
            db.add(CadastroCortesia(
                cadastro_id=cadastro.id,
                cliente=cortesia.cliente,
                quantidade=cortesia.quantidade
            ))
    
    if data.taxas is not None:
        for t in cadastro.taxas:
            db.delete(t)
        for taxa in data.taxas:
            data_validacao = None
            if taxa.data_validacao:
                try:
                    data_validacao = date.fromisoformat(taxa.data_validacao)
                except:
                    pass
            db.add(CadastroTaxa(
                cadastro_id=cadastro.id,
                valor_unitario=taxa.valor_unitario,
                percentual_inscricao=taxa.percentual_inscricao,
                validado=taxa.validado,
                data_validacao=data_validacao
            ))
    
    if data.kit_produto is not None:
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
    
    if data.faixas_preco_site is not None:
        for f in cadastro.faixas_preco_site:
            db.delete(f)
        for faixa in data.faixas_preco_site.kit_basico:
            db.add(CadastroFaixaPrecoSite(
                cadastro_id=cadastro.id,
                tipo_kit="kit_basico",
                faixa=faixa.faixa,
                qtd=faixa.qtd,
                tkt_medio=faixa.tkt_medio,
                total=faixa.total
            ))
        for faixa in data.faixas_preco_site.kit_participacao:
            db.add(CadastroFaixaPrecoSite(
                cadastro_id=cadastro.id,
                tipo_kit="kit_participacao",
                faixa=faixa.faixa,
                qtd=faixa.qtd,
                tkt_medio=faixa.tkt_medio,
                total=faixa.total
            ))
    
    if data.faixas_preco_grupos is not None:
        for f in cadastro.faixas_preco_grupos:
            db.delete(f)
        for faixa in data.faixas_preco_grupos.kit_basico:
            db.add(CadastroFaixaPrecoGrupos(
                cadastro_id=cadastro.id,
                tipo_kit="kit_basico",
                faixa=faixa.faixa,
                qtd=faixa.qtd,
                tkt_medio=faixa.tkt_medio,
                total=faixa.total
            ))
        for faixa in data.faixas_preco_grupos.kit_participacao:
            db.add(CadastroFaixaPrecoGrupos(
                cadastro_id=cadastro.id,
                tipo_kit="kit_participacao",
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
    
    return db_to_response(cadastro)


@router.post("/resync-projetos")
def resync_dim_projetos(db: Session = Depends(get_db)):
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
def deletar_cadastro(cadastro_id: int, db: Session = Depends(get_db)):
    """Deleta um cadastro"""
    cadastro = db.query(CadastroEvento).filter(CadastroEvento.id == cadastro_id).first()
    
    if not cadastro:
        raise HTTPException(status_code=404, detail="Cadastro não encontrado")
    
    db.delete(cadastro)
    db.commit()
    
    return {"message": "Cadastro deletado com sucesso"}


@router.get("/opcoes/circuitos", response_model=List[CircuitoProdutoSchema])
def listar_circuitos(db: Session = Depends(get_db)):
    return db.query(CircuitoProduto).order_by(CircuitoProduto.nome).all()


@router.post("/opcoes/circuitos", response_model=CircuitoProdutoSchema)
def criar_circuito(data: CircuitoProdutoSchema, db: Session = Depends(get_db)):
    existing = db.query(CircuitoProduto).filter(CircuitoProduto.nome == data.nome).first()
    if existing:
        raise HTTPException(status_code=409, detail="Circuito já existe")
    item = CircuitoProduto(nome=data.nome)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/opcoes/circuitos/{item_id}", response_model=CircuitoProdutoSchema)
def atualizar_circuito(item_id: int, data: CircuitoProdutoSchema, db: Session = Depends(get_db)):
    item = db.query(CircuitoProduto).filter(CircuitoProduto.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Circuito não encontrado")
    item.nome = data.nome
    db.commit()
    db.refresh(item)
    return item


@router.delete("/opcoes/circuitos/{item_id}")
def deletar_circuito(item_id: int, db: Session = Depends(get_db)):
    item = db.query(CircuitoProduto).filter(CircuitoProduto.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Circuito não encontrado")
    db.delete(item)
    db.commit()
    return {"message": "Circuito deletado"}


@router.get("/opcoes/localizacoes", response_model=List[LocalizacaoSchema])
def listar_localizacoes(db: Session = Depends(get_db)):
    return db.query(Localizacao).order_by(Localizacao.nome).all()


@router.post("/opcoes/localizacoes", response_model=LocalizacaoSchema)
def criar_localizacao(data: LocalizacaoSchema, db: Session = Depends(get_db)):
    existing = db.query(Localizacao).filter(Localizacao.nome == data.nome).first()
    if existing:
        raise HTTPException(status_code=409, detail="Localização já existe")
    item = Localizacao(nome=data.nome)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/opcoes/localizacoes/{item_id}", response_model=LocalizacaoSchema)
def atualizar_localizacao(item_id: int, data: LocalizacaoSchema, db: Session = Depends(get_db)):
    item = db.query(Localizacao).filter(Localizacao.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Localização não encontrada")
    item.nome = data.nome
    db.commit()
    db.refresh(item)
    return item


@router.delete("/opcoes/localizacoes/{item_id}")
def deletar_localizacao(item_id: int, db: Session = Depends(get_db)):
    item = db.query(Localizacao).filter(Localizacao.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Localização não encontrada")
    db.delete(item)
    db.commit()
    return {"message": "Localização deletada"}
