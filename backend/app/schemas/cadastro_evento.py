from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal


class CortesiaItemBase(BaseModel):
    cliente: str
    quantidade: int = 0


class CortesiaItemCreate(CortesiaItemBase):
    pass


class CortesiaItemResponse(CortesiaItemBase):
    id: int
    
    class Config:
        from_attributes = True


class TaxaItemBase(BaseModel):
    valor_unitario: Decimal = Decimal("0")
    percentual_inscricao: Decimal = Decimal("0")
    validado: bool = False
    data_validacao: Optional[str] = None


class TaxaItemCreate(TaxaItemBase):
    pass


class TaxaItemResponse(TaxaItemBase):
    id: int
    
    class Config:
        from_attributes = True


class ProdutoItemBase(BaseModel):
    nome: str
    valor_unitario: Decimal = Decimal("0")


class ProdutoItemCreate(ProdutoItemBase):
    pass


class ProdutoItemResponse(ProdutoItemBase):
    id: int
    
    class Config:
        from_attributes = True


class KitProdutoBase(BaseModel):
    kit: str = ""
    produtos: List[ProdutoItemCreate] = []


class KitProdutoCreate(KitProdutoBase):
    pass


class KitProdutoResponse(BaseModel):
    id: int
    kit: str
    produtos: List[ProdutoItemResponse] = []
    
    class Config:
        from_attributes = True


class FaixaPrecoItemBase(BaseModel):
    faixa: str
    qtd: int = 0
    tkt_medio: Decimal = Decimal("0")
    total: Decimal = Decimal("0")


class FaixaPrecoItemCreate(FaixaPrecoItemBase):
    tipo_kit: str


class FaixaPrecoItemResponse(FaixaPrecoItemBase):
    id: int
    tipo_kit: str
    
    class Config:
        from_attributes = True


class FaixasPrecoByKit(BaseModel):
    kit_basico: List[FaixaPrecoItemBase] = []
    kit_participacao: List[FaixaPrecoItemBase] = []


class AtletasData(BaseModel):
    site: dict = {"pago": 0, "tkt_medio": 0}
    grupos: dict = {"pago": 0, "tkt_medio": 0}
    cortesia: int = 0


class InfoGeral(BaseModel):
    data: str = ""
    horario_largada: str = ""
    local: str = ""
    distancias: List[str] = []


class RetiradaKit(BaseModel):
    local: str = ""
    data_horario: str = ""


class CadastroEventoBase(BaseModel):
    projeto_id: Optional[int] = None
    nome: str
    imagem_kv: str = ""
    status: str = "Em andamento"
    modalidade: str = "Corrida"
    sku: Optional[str] = None
    produto: Optional[str] = None
    tipo_evento: Optional[str] = None
    lei: Optional[str] = None
    capacidade_maxima: Optional[int] = None
    info_geral: InfoGeral = InfoGeral()
    atletas: AtletasData = AtletasData()
    cortesias: List[CortesiaItemCreate] = []
    taxas: List[TaxaItemCreate] = []
    retirada_kit: RetiradaKit = RetiradaKit()
    kit_produto: List[KitProdutoCreate] = []
    trofeus: int = 0
    faixas_preco_site: FaixasPrecoByKit = FaixasPrecoByKit()
    faixas_preco_grupos: FaixasPrecoByKit = FaixasPrecoByKit()


class CadastroEventoCreate(CadastroEventoBase):
    pass


class CadastroEventoUpdate(BaseModel):
    projeto_id: Optional[int] = None
    nome: Optional[str] = None
    imagem_kv: Optional[str] = None
    status: Optional[str] = None
    modalidade: Optional[str] = None
    sku: Optional[str] = None
    produto: Optional[str] = None
    tipo_evento: Optional[str] = None
    lei: Optional[str] = None
    capacidade_maxima: Optional[int] = None
    info_geral: Optional[InfoGeral] = None
    atletas: Optional[AtletasData] = None
    cortesias: Optional[List[CortesiaItemCreate]] = None
    taxas: Optional[List[TaxaItemCreate]] = None
    retirada_kit: Optional[RetiradaKit] = None
    kit_produto: Optional[List[KitProdutoCreate]] = None
    trofeus: Optional[int] = None
    faixas_preco_site: Optional[FaixasPrecoByKit] = None
    faixas_preco_grupos: Optional[FaixasPrecoByKit] = None


class CadastroEventoResponse(BaseModel):
    id: int
    projeto_id: Optional[int] = None
    nome: str
    imagem_kv: str = ""
    status: str = "Em andamento"
    modalidade: str = "Corrida"
    sku: Optional[str] = None
    produto: Optional[str] = None
    tipo_evento: Optional[str] = None
    lei: Optional[str] = None
    capacidade_maxima: Optional[int] = None
    info_geral: InfoGeral = InfoGeral()
    atletas: AtletasData = AtletasData()
    cortesias: List[CortesiaItemResponse] = []
    taxas: List[TaxaItemResponse] = []
    retirada_kit: RetiradaKit = RetiradaKit()
    kit_produto: List[KitProdutoResponse] = []
    trofeus: int = 0
    faixas_preco_site: FaixasPrecoByKit = FaixasPrecoByKit()
    faixas_preco_grupos: FaixasPrecoByKit = FaixasPrecoByKit()
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
