from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime


class FornecedorBase(BaseModel):
    nome: str
    contato: Optional[str] = None
    localizacao: Optional[str] = None
    observacoes: Optional[str] = None


class FornecedorCreate(FornecedorBase):
    pass


class FornecedorResponse(FornecedorBase):
    id: int
    ativo: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CotacaoEventoBase(BaseModel):
    cadastro_evento_id: Optional[int] = None
    evento_nome_manual: Optional[str] = None
    quantidade: int = 1
    observacoes: Optional[str] = None


class CotacaoEventoCreate(CotacaoEventoBase):
    pass


class CotacaoEventoResponse(CotacaoEventoBase):
    id: int
    cotacao_id: int
    evento_nome: Optional[str] = None

    class Config:
        from_attributes = True


class CotacaoBase(BaseModel):
    produto_nome: str
    descricao: Optional[str] = None
    fornecedor_id: Optional[int] = None
    valor_unitario_usd: float = 0
    quantidade: int = 1
    taxa_cambio: Optional[float] = None
    data_cotacao: Optional[date] = None
    observacoes: Optional[str] = None


class CotacaoCreate(CotacaoBase):
    pass


class CotacaoUpdate(BaseModel):
    produto_nome: Optional[str] = None
    descricao: Optional[str] = None
    fornecedor_id: Optional[int] = None
    valor_unitario_usd: Optional[float] = None
    quantidade: Optional[int] = None
    taxa_cambio: Optional[float] = None
    selecionado: Optional[bool] = None
    data_cotacao: Optional[date] = None
    observacoes: Optional[str] = None


class CotacaoResponse(CotacaoBase):
    id: int
    viagem_id: int
    valor_unitario_brl: Optional[float] = None
    valor_total_usd: Optional[float] = None
    valor_total_brl: Optional[float] = None
    selecionado: bool = False
    fornecedor_nome: Optional[str] = None
    eventos: List[CotacaoEventoResponse] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CustoImportacaoBase(BaseModel):
    descricao: str
    tipo: str
    valor_usd: float = 0
    valor_brl: float = 0
    observacoes: Optional[str] = None


class CustoImportacaoCreate(CustoImportacaoBase):
    pass


class CustoImportacaoResponse(CustoImportacaoBase):
    id: int
    viagem_id: int

    class Config:
        from_attributes = True


class ViagemCotacaoBase(BaseModel):
    titulo: str
    destino: str = "China"
    ano_competencia: int
    data_inicio: Optional[date] = None
    data_fim: Optional[date] = None
    status: str = "Planejada"
    observacoes: Optional[str] = None


class ViagemCotacaoCreate(ViagemCotacaoBase):
    pass


class ViagemCotacaoUpdate(BaseModel):
    titulo: Optional[str] = None
    destino: Optional[str] = None
    ano_competencia: Optional[int] = None
    data_inicio: Optional[date] = None
    data_fim: Optional[date] = None
    status: Optional[str] = None
    observacoes: Optional[str] = None


class ViagemCotacaoListResponse(ViagemCotacaoBase):
    id: int
    total_cotacoes: int = 0
    total_usd: float = 0
    total_brl: float = 0
    criador_nome: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ViagemCotacaoDetailResponse(ViagemCotacaoBase):
    id: int
    cotacoes: List[CotacaoResponse] = []
    custos_importacao: List[CustoImportacaoResponse] = []
    criador_nome: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DashboardCotacaoResponse(BaseModel):
    total_viagens: int = 0
    viagens_em_andamento: int = 0
    total_produtos_cotados: int = 0
    total_selecionados: int = 0
    total_usd: float = 0
    total_brl: float = 0
    total_custos_importacao_usd: float = 0
    total_custos_importacao_brl: float = 0
    custo_total_brl: float = 0
    total_fornecedores: int = 0
    total_eventos_vinculados: int = 0
    por_evento: List[dict] = []
    por_fornecedor: List[dict] = []
    por_status: List[dict] = []


class CotacaoFobCreate(BaseModel):
    circuito: str
    produto: str
    valor_fob: float = 0
    indice_importacao: Optional[float] = None
    bec: Optional[float] = None
    cotacao_cambio: Optional[float] = None
    valor_nacionalizado: Optional[float] = None
    taxa_cambio: Optional[float] = None
    valor_brl: Optional[float] = None


class CotacaoFobUpdate(BaseModel):
    circuito: Optional[str] = None
    produto: Optional[str] = None
    valor_fob: Optional[float] = None
    indice_importacao: Optional[float] = None
    bec: Optional[float] = None
    cotacao_cambio: Optional[float] = None
    valor_nacionalizado: Optional[float] = None
    taxa_cambio: Optional[float] = None
    valor_brl: Optional[float] = None


class CotacaoFobResponse(BaseModel):
    id: int
    circuito: str
    produto: str
    valor_fob: float
    indice_importacao: Optional[float] = None
    bec: Optional[float] = None
    cotacao_cambio: Optional[float] = None
    valor_nacionalizado: Optional[float] = None
    taxa_cambio: Optional[float] = None
    valor_brl: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
