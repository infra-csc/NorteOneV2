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
    evento_status: Optional[str] = None
    tem_cupons_gerados: bool = False
    areas: List[SaldoAreaItem] = []


class EventoFilaOpcao(BaseModel):
    """Opção enxuta para o filtro por evento da fila de cupons —
    só id/nome/data, sem os números de saldo (que não fazem sentido aqui)."""
    evento_id: int
    evento_nome: str
    evento_data: Optional[str] = None


class CortesiaSolicitacaoCupomCreate(BaseModel):
    evento_id: int
    area_projecao_id: int
    quantidade: int
    observacao: Optional[str] = None


class CortesiaCupomColarRequest(BaseModel):
    """Código(s) de cupom já gerados manualmente no Magento, colados pelo
    usuário para vincular a uma solicitação pendente — o app não gera mais
    o código sozinho."""
    codigos: List[str]


class CupomCodigoItem(BaseModel):
    id: int
    codigo: str
    usado: bool
    usado_em: Optional[datetime] = None
    usado_por_nome: Optional[str] = None

    class Config:
        from_attributes = True


class ImportarCupomLinhaResultado(BaseModel):
    """Resultado de uma linha do .txt de importação em lote (Task #244) —
    uma por código informado (linhas de cabeçalho/comentário/modelo ainda
    sem código não entram aqui, só contam em ImportarCupomResumo.ignorados)."""
    linha: int
    texto: str
    aplicado: bool
    mensagem: str


class ImportarCupomResumo(BaseModel):
    total: int
    aplicados: int
    rejeitados: int
    ignorados: int
    resultados: List[ImportarCupomLinhaResultado] = []


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
