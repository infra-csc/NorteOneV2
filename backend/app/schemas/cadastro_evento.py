from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
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
    ativo_categoria: Optional[str] = None
    produtos: List[ProdutoItemCreate] = []


class KitProdutoCreate(KitProdutoBase):
    pass


class KitProdutoResponse(BaseModel):
    id: int
    kit: str
    ativo_categoria: Optional[str] = None
    produtos: List[ProdutoItemResponse] = []
    
    class Config:
        from_attributes = True


class MerchanProdutoItemBase(BaseModel):
    nome: str
    valor_venda: Decimal = Decimal("0")


class MerchanProdutoItemCreate(MerchanProdutoItemBase):
    pass


class MerchanProdutoItemResponse(MerchanProdutoItemBase):
    id: int

    class Config:
        from_attributes = True


class MerchanKitBase(BaseModel):
    kit: str = ""
    itens: List[MerchanProdutoItemCreate] = []


class MerchanKitCreate(MerchanKitBase):
    pass


class MerchanKitResponse(BaseModel):
    id: int
    kit: str
    itens: List[MerchanProdutoItemResponse] = []

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
    kit_sem_bike: List[FaixaPrecoItemBase] = []
    kit_com_bike: List[FaixaPrecoItemBase] = []


class AppaiData(BaseModel):
    pago: int = 0
    tkt_medio: float = 0

class CiclismoCenariosData(BaseModel):
    participacao_pago: int = 0
    sem_bike_pago: int = 0
    sem_bike_tkt_medio: float = 0
    com_bike_pago: int = 0
    com_bike_tkt_medio: float = 0

class AtletasData(BaseModel):
    site: dict = {"pago": 0, "tkt_medio": 0}
    grupos: dict = {"pago": 0, "tkt_medio": 0}
    cortesia: int = 0
    appai: Optional[AppaiData] = AppaiData()
    ciclismo: Optional[CiclismoCenariosData] = CiclismoCenariosData()


class InfoGeral(BaseModel):
    data: str = ""
    horario_largada: str = ""
    local: str = ""
    distancias: list = []
    dias_encerramento_inscricao: int = 2


class RetiradaKit(BaseModel):
    local: str = ""
    data_horario: str = ""


class CircuitoProdutoSchema(BaseModel):
    id: Optional[int] = None
    nome: str

    class Config:
        from_attributes = True


class LocalizacaoSchema(BaseModel):
    id: Optional[int] = None
    nome: str

    class Config:
        from_attributes = True


class CadastroEventoBase(BaseModel):
    projeto_id: Optional[int] = None
    nome: str
    circuito_produto: Optional[str] = None
    localizacao_evento: Optional[str] = None
    ano_evento: Optional[int] = None
    imagem_kv: str = ""
    status: str = "Em andamento"
    modalidade: str = "Corrida"
    sku: Optional[str] = None
    produto: Optional[str] = None
    tipo_evento: Optional[str] = None
    lei: Optional[str] = None
    capacidade_maxima: Optional[int] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None
    gratuito: bool = False
    info_geral: InfoGeral = InfoGeral()
    atletas: AtletasData = AtletasData()
    cortesias: List[CortesiaItemCreate] = []
    taxas: List[TaxaItemCreate] = []
    retirada_kit: RetiradaKit = RetiradaKit()
    kit_produto: List[KitProdutoCreate] = []
    merchan: List[MerchanKitCreate] = []
    faixas_preco_site: FaixasPrecoByKit = FaixasPrecoByKit()
    faixas_preco_grupos: FaixasPrecoByKit = FaixasPrecoByKit()


class CadastroEventoCreate(CadastroEventoBase):
    pass


class CadastroEventoUpdate(BaseModel):
    projeto_id: Optional[int] = None
    nome: Optional[str] = None
    circuito_produto: Optional[str] = None
    localizacao_evento: Optional[str] = None
    ano_evento: Optional[int] = None
    imagem_kv: Optional[str] = None
    status: Optional[str] = None
    modalidade: Optional[str] = None
    sku: Optional[str] = None
    produto: Optional[str] = None
    tipo_evento: Optional[str] = None
    lei: Optional[str] = None
    capacidade_maxima: Optional[int] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None
    gratuito: Optional[bool] = None
    info_geral: Optional[InfoGeral] = None
    atletas: Optional[AtletasData] = None
    cortesias: Optional[List[CortesiaItemCreate]] = None
    taxas: Optional[List[TaxaItemCreate]] = None
    retirada_kit: Optional[RetiradaKit] = None
    kit_produto: Optional[List[KitProdutoCreate]] = None
    merchan: Optional[List[MerchanKitCreate]] = None
    faixas_preco_site: Optional[FaixasPrecoByKit] = None
    faixas_preco_grupos: Optional[FaixasPrecoByKit] = None


class CadastroEventoResponse(BaseModel):
    id: int
    projeto_id: Optional[int] = None
    nome: str
    id_evento_magento: Optional[int] = None
    circuito_produto: Optional[str] = None
    localizacao_evento: Optional[str] = None
    ano_evento: Optional[int] = None
    imagem_kv: str = ""
    status: str = "Em andamento"
    modalidade: str = "Corrida"
    sku: Optional[str] = None
    produto: Optional[str] = None
    tipo_evento: Optional[str] = None
    lei: Optional[str] = None
    capacidade_maxima: Optional[int] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None
    gratuito: bool = False
    info_geral: InfoGeral = InfoGeral()
    atletas: AtletasData = AtletasData()
    cortesias: List[CortesiaItemResponse] = []
    taxas: List[TaxaItemResponse] = []
    retirada_kit: RetiradaKit = RetiradaKit()
    kit_produto: List[KitProdutoResponse] = []
    merchan: List[MerchanKitResponse] = []
    faixas_preco_site: FaixasPrecoByKit = FaixasPrecoByKit()
    faixas_preco_grupos: FaixasPrecoByKit = FaixasPrecoByKit()
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
