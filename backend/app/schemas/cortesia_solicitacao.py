from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class SaldoAreaItem(BaseModel):
    area_projecao_id: int
    area_projecao_nome: str
    projetado: int
    solicitado: int
    saldo: int
    area_sigla: Optional[str] = None


class EventoSaldoResponse(BaseModel):
    evento_id: int
    evento_nome: str
    evento_data: Optional[str] = None
    evento_sku: Optional[str] = None
    areas: List[SaldoAreaItem] = []


class EventoFilaOpcao(BaseModel):
    """Opção enxuta para o filtro por evento da fila de geração de cupons —
    só id/nome/data, sem os números de saldo (que não fazem sentido aqui)."""
    evento_id: int
    evento_nome: str
    evento_data: Optional[str] = None


class CortesiaSolicitacaoCupomCreate(BaseModel):
    evento_id: int
    area_projecao_id: int
    quantidade: int
    observacao: Optional[str] = None


class CupomCodigoItem(BaseModel):
    id: int
    codigo: str
    usado: bool
    usado_em: Optional[datetime] = None
    usado_por_nome: Optional[str] = None

    class Config:
        from_attributes = True


class CortesiaSolicitacaoResponse(BaseModel):
    id: int
    evento_id: int
    evento_nome: Optional[str] = None
    evento_data: Optional[str] = None
    area_projecao_id: int
    area_projecao_nome: Optional[str] = None
    tipo: str
    quantidade: int
    status: str
    observacao: Optional[str] = None
    codigo_cupom: Optional[str] = None
    codigo_cupom_lista: List[str] = []
    codigos_detalhes: List[CupomCodigoItem] = []
    gerado_por_nome: Optional[str] = None
    gerado_em: Optional[datetime] = None
    nome_arquivo: Optional[str] = None
    quantidade_linhas: Optional[int] = None
    solicitado_por_nome: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
