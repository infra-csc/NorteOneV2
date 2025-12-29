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

class AtletasBase(BaseModel):
    projeto_id: int
    categoria_atleta_id: int
    tempo_id: Optional[int] = None
    qtd_atletas_orcado: int = 0
    qtd_atletas_projetado: int = 0
    qtd_atletas_realizado: int = 0
    valor_inscricao_unitario: Optional[Decimal] = None
    custo_kit_unitario_orcado: Optional[Decimal] = None
    custo_kit_unitario_projetado: Optional[Decimal] = None
    custo_kit_unitario_realizado: Optional[Decimal] = None
    versao_projecao: int = 1
    observacao: Optional[str] = None

class AtletasCreate(AtletasBase):
    pass

class AtletasUpdate(BaseModel):
    qtd_atletas_orcado: Optional[int] = None
    qtd_atletas_projetado: Optional[int] = None
    qtd_atletas_realizado: Optional[int] = None
    valor_inscricao_unitario: Optional[Decimal] = None
    custo_kit_unitario_orcado: Optional[Decimal] = None
    custo_kit_unitario_projetado: Optional[Decimal] = None
    custo_kit_unitario_realizado: Optional[Decimal] = None
    observacao: Optional[str] = None

class AtletasResponse(AtletasBase):
    id: int
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
