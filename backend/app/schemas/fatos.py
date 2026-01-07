from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from decimal import Decimal

class OrcamentoBase(BaseModel):
    tempo_id: Optional[int] = None
    centro_custo_id: int
    conta_id: int
    projeto_id: int
    valor_orcado: Decimal
    quantidade_orcada: Optional[Decimal] = None
    versao_orcamento: str = "V1"
    ano_referencia: int

class OrcamentoCreate(OrcamentoBase):
    pass

class OrcamentoUpdate(BaseModel):
    valor_orcado: Optional[Decimal] = None
    quantidade_orcada: Optional[Decimal] = None
    versao_orcamento: Optional[str] = None

class OrcamentoResponse(OrcamentoBase):
    id: int
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class ProjecaoBase(BaseModel):
    tempo_id: Optional[int] = None
    centro_custo_id: int
    conta_id: int
    projeto_id: int
    valor_projetado: Decimal
    quantidade_projetada: Optional[Decimal] = None
    versao: int = 1
    justificativa: Optional[str] = None
    status: str = "RASCUNHO"

class ProjecaoCreate(ProjecaoBase):
    pass

class ProjecaoUpdate(BaseModel):
    valor_projetado: Optional[Decimal] = None
    quantidade_projetada: Optional[Decimal] = None
    justificativa: Optional[str] = None
    status: Optional[str] = None

class ProjecaoResponse(ProjecaoBase):
    id: int
    created_by: Optional[int] = None
    approved_by: Optional[int] = None
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class RealizadoBase(BaseModel):
    tempo_id: Optional[int] = None
    centro_custo_id: int
    conta_id: int
    projeto_id: int
    valor_realizado: Decimal
    quantidade_realizada: Optional[Decimal] = None
    documento_referencia: Optional[str] = None
    descricao: Optional[str] = None

class RealizadoCreate(RealizadoBase):
    pass

class RealizadoResponse(RealizadoBase):
    id: int
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# === Schemas para Atletas Metricas (principal) ===
class AtletasMetricasBase(BaseModel):
    projeto_id: int
    categoria_atleta_id: Optional[int] = None
    tempo_id: Optional[int] = None
    cenario: str  # ORCADO, PROJETADO, REALIZADO
    qtd_atletas: int = 0
    qtd_atletas_pago: int = 0
    qtd_atletas_cortesia: int = 0
    tkt_medio: Optional[Decimal] = None
    inscricao: Optional[Decimal] = None
    custo_kit_unitario: Optional[Decimal] = None
    versao_projecao: int = 1
    observacao: Optional[str] = None

class AtletasMetricasCreate(AtletasMetricasBase):
    pass

class AtletasMetricasUpdate(BaseModel):
    qtd_atletas: Optional[int] = None
    qtd_atletas_pago: Optional[int] = None
    qtd_atletas_cortesia: Optional[int] = None
    tkt_medio: Optional[Decimal] = None
    inscricao: Optional[Decimal] = None
    custo_kit_unitario: Optional[Decimal] = None
    observacao: Optional[str] = None

class AtletasMetricasResponse(AtletasMetricasBase):
    id: int
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# === Schemas para Atletas Canais ===
class AtletasCanaisBase(BaseModel):
    projeto_id: int
    categoria_atleta_id: Optional[int] = None
    tempo_id: Optional[int] = None
    canal: str  # SITE, GRUPOS, APPAI
    cenario: str  # ORCADO, PROJETADO, REALIZADO
    qtd_atletas: int = 0
    tkt_medio: Optional[Decimal] = None
    inscricao: Optional[Decimal] = None
    versao_projecao: int = 1
    observacao: Optional[str] = None

class AtletasCanaisCreate(AtletasCanaisBase):
    pass

class AtletasCanaisUpdate(BaseModel):
    qtd_atletas: Optional[int] = None
    tkt_medio: Optional[Decimal] = None
    inscricao: Optional[Decimal] = None
    observacao: Optional[str] = None

class AtletasCanaisResponse(AtletasCanaisBase):
    id: int
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# === Schemas para Atletas Kits ===
class AtletasKitsBase(BaseModel):
    projeto_id: int
    categoria_atleta_id: Optional[int] = None
    tempo_id: Optional[int] = None
    tipo_kit: str  # VIP, PLUS, SUPER, PRODUTO
    cenario: str  # ORCADO, PROJETADO, REALIZADO
    qtd_kit: int = 0
    tkt_medio: Optional[Decimal] = None
    inscricao: Optional[Decimal] = None
    custo_unitario: Optional[Decimal] = None
    versao_projecao: int = 1
    observacao: Optional[str] = None

class AtletasKitsCreate(AtletasKitsBase):
    pass

class AtletasKitsUpdate(BaseModel):
    qtd_kit: Optional[int] = None
    tkt_medio: Optional[Decimal] = None
    inscricao: Optional[Decimal] = None
    custo_unitario: Optional[Decimal] = None
    observacao: Optional[str] = None

class AtletasKitsResponse(AtletasKitsBase):
    id: int
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# === Schemas para Atletas Custos ===
class AtletasCustosBase(BaseModel):
    projeto_id: int
    categoria_atleta_id: Optional[int] = None
    tempo_id: Optional[int] = None
    tipo_custo: str  # AGUA, ISOTONICO, HIDRATACAO, NUMERO_PEITO, CHIP, ALFINETE, IDENTIFICACAO
    cenario: str  # ORCADO, PROJETADO, REALIZADO
    custo_unitario: Optional[Decimal] = None
    qtd_por_atleta: Optional[Decimal] = None
    custo_total: Optional[Decimal] = None
    versao_projecao: int = 1
    observacao: Optional[str] = None

class AtletasCustosCreate(AtletasCustosBase):
    pass

class AtletasCustosUpdate(BaseModel):
    custo_unitario: Optional[Decimal] = None
    qtd_por_atleta: Optional[Decimal] = None
    custo_total: Optional[Decimal] = None
    observacao: Optional[str] = None

class AtletasCustosResponse(AtletasCustosBase):
    id: int
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
