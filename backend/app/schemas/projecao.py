from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class AreaProjecaoResponse(BaseModel):
    id: int
    nome: str
    ativo: bool
    usa_cutoff_customizado: bool = False
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AreaProjecaoUsuarioResponse(BaseModel):
    id: int
    area_projecao_id: int
    usuario_id: int
    usuario_nome: Optional[str] = None
    usuario_email: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AreaProjecaoDetailResponse(AreaProjecaoResponse):
    usuarios: List[AreaProjecaoUsuarioResponse] = []

    class Config:
        from_attributes = True


class AreaProjecaoCreate(BaseModel):
    nome: str


class AreaProjecaoUsuarioCreate(BaseModel):
    area_projecao_id: int
    usuario_id: int


class AreaProjecaoUsuarioBulk(BaseModel):
    area_projecao_id: int
    usuario_ids: List[int]


class ClienteProjecaoItem(BaseModel):
    nome_cliente: str
    quantidade: int


class ClienteProjecaoResponse(BaseModel):
    id: int
    projecao_id: int
    nome_cliente: str
    quantidade: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class KitProjecaoItem(BaseModel):
    nome_kit: str
    quantidade: int


class KitProjecaoResponse(BaseModel):
    id: int
    projecao_id: int
    nome_kit: str
    quantidade: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProjecaoInscritosCreate(BaseModel):
    evento_id: int
    area_projecao_id: int
    quantidade: int
    clientes: Optional[List[ClienteProjecaoItem]] = None
    kits: Optional[List[KitProjecaoItem]] = None


class ProjecaoInscritosUpdate(BaseModel):
    quantidade: int
    clientes: Optional[List[ClienteProjecaoItem]] = None
    kits: Optional[List[KitProjecaoItem]] = None


class ProjecaoInscritosResponse(BaseModel):
    id: int
    evento_id: int
    evento_nome: Optional[str] = None
    evento_data: Optional[str] = None
    evento_tipo: Optional[str] = None
    evento_modalidade: Optional[str] = None
    area_projecao_id: int
    area_projecao_nome: Optional[str] = None
    quantidade: int
    clientes: List[ClienteProjecaoResponse] = []
    kits: List[KitProjecaoResponse] = []
    created_by: int
    created_by_nome: Optional[str] = None
    updated_by: Optional[int] = None
    updated_by_nome: Optional[str] = None
    locked_at: Optional[datetime] = None
    locked_by_nome: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    deleted_by_nome: Optional[str] = None

    class Config:
        from_attributes = True


class HistoricoResponse(BaseModel):
    id: int
    projecao_id: int
    acao: str
    campo_alterado: Optional[str] = None
    valor_anterior: Optional[str] = None
    valor_novo: Optional[str] = None
    usuario_id: int
    usuario_nome: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ConsolidadoAreaItem(BaseModel):
    area_projecao_id: int
    area_projecao_nome: str
    # quantidade/kits = distribuição AO VIVO atual (= Projeção Ajuste / Corte 2).
    quantidade: int
    kits: List[KitProjecaoItem] = []
    # Distribuição congelada do Corte 1 (= Projeção Convicta) por área/kit.
    # Vem da foto `projecao_corte_dist_snapshot`; quando não há foto (evento ainda
    # não chegou no Corte 1), espelha os valores ao vivo (fallback aproximado).
    convicta_quantidade: int = 0
    convicta_kits: List[KitProjecaoItem] = []
    # Teto da "Camiseta avulsa" (valor de "Kit Completo - Sem camiseta"
    # congelado no Corte 1). None = Corte 1 não congelado para esta área.
    camiseta_avulsa_teto: Optional[int] = None


class CorteDistAreaResponse(BaseModel):
    """Distribuição congelada do Corte 1 para uma (evento, área), usada pelo
    layout aditivo do Corte 2 (coluna de leitura). `fonte` indica se veio da
    foto real ('snapshot') ou de aproximação pelos valores atuais ('aproximado',
    p/ eventos que já estavam no Corte 2 antes da foto passar a ser gravada)."""
    evento_id: int
    area_projecao_id: int
    quantidade: int = 0
    kits: List[KitProjecaoItem] = []
    clientes: List[ClienteProjecaoItem] = []
    fonte: str = "snapshot"
    congelado_em: Optional[datetime] = None
    # Fonte autoritativa da fase do corte para o evento (ProjecaoCorteSnapshot),
    # para o frontend decidir o layout aditivo sem depender do consolidado.
    em_corte2: bool = False


class CamisetaAvulsaInfoResponse(BaseModel):
    """Info para o formulário decidir se 'Kit Completo - Sem camiseta' já virou
    'Camiseta avulsa' (Corte 1 congelado) e qual o teto máximo."""
    corte1_congelado: bool = False
    teto: int = 0


class ConsolidadoEventoResponse(BaseModel):
    evento_id: int
    evento_nome: str
    evento_data: Optional[str] = None
    inscritos_reais: int
    projecoes: List[ConsolidadoAreaItem]
    total_projecoes: int
    projecao_site: int = 0
    total_geral: int
    # Projeção de camisetas = total de projeções - "Inscrição Participação"
    # alocada na distribuição por kit (inscrições sem camiseta).
    inscricao_participacao: int = 0
    projecao_camisetas: int = 0
    # Cortes congelados (None = ainda não congelado, mostra prévia ao vivo)
    corte_dias_1: Optional[int] = None
    corte_dias_2: Optional[int] = None
    corte_ativo: bool = False
    corte_valor_1: Optional[int] = None
    corte_congelado_1_em: Optional[datetime] = None
    corte_valor_2: Optional[int] = None
    corte_congelado_2_em: Optional[datetime] = None
    # Data de corte Envio (regra principal do Corte 1; None = usa fallback D-N)
    corte_data_envio: Optional[str] = None
    # Data de saída do caminhão (informativo)
    data_saida_caminhao: Optional[str] = None
    # Reaberto manualmente pelo admin: corte volta a acompanhar ao vivo e NÃO
    # recongela automaticamente (só via "Congelar agora").
    reaberto_manual_corte_1: bool = False
    reaberto_manual_corte_2: bool = False
    # True quando o Corte 1 está congelado — sinaliza ao frontend que a divisão
    # Convicta x Ajuste é significativa (antes disso ambas são iguais ao vivo).
    em_corte2: bool = False


class CutoffRuleCreate(BaseModel):
    nome: str
    dias_antes_evento: int
    ativo: Optional[bool] = True


class CutoffRuleUpdate(BaseModel):
    nome: Optional[str] = None
    dias_antes_evento: Optional[int] = None
    ativo: Optional[bool] = None


class CutoffRuleResponse(BaseModel):
    id: int
    nome: str
    dias_antes_evento: int
    ativo: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AreaPendenteItem(BaseModel):
    area_projecao_id: int
    area_projecao_nome: str


class PendenciaItem(BaseModel):
    evento_id: int
    evento_nome: str
    evento_data: Optional[str] = None
    dias_ate_evento: int
    cutoff_dias: int
    cutoff_nome: str
    cutoff_customizado: bool = False
    cutoff_data: Optional[str] = None
    areas_pendentes: List[AreaPendenteItem]


class PendenciasResponse(BaseModel):
    total_eventos: int
    total_areas: int
    pendencias: List[PendenciaItem]


class AreaCutoffCustomizadoToggle(BaseModel):
    ativo: bool


class CutoffEventoAreaUpsert(BaseModel):
    evento_id: int
    area_projecao_id: int
    data_corte_1: Optional[str] = None  # ISO date YYYY-MM-DD
    data_corte_2: Optional[str] = None
    data_saida_caminhao: Optional[str] = None  # ISO date YYYY-MM-DD
    observacao_corte_1: Optional[str] = None


class CutoffEventoAreaResponse(BaseModel):
    id: int
    evento_id: int
    area_projecao_id: int
    area_projecao_nome: Optional[str] = None
    data_corte_1: Optional[str] = None
    data_corte_2: Optional[str] = None
    data_saida_caminhao: Optional[str] = None
    observacao_corte_1: Optional[str] = None
    updated_by: Optional[int] = None
    updated_by_nome: Optional[str] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AutoLockConfigUpdate(BaseModel):
    dias_antes_evento: int
    hora_trava: str = "00:00"
    ativo: bool


class AutoLockConfigResponse(BaseModel):
    dias_antes_evento: int
    hora_trava: str = "00:00"
    ativo: bool
    updated_by_nome: Optional[str] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CorteConfigUpdate(BaseModel):
    dias_corte_1: int
    dias_corte_2: int
    ativo: bool


class CorteConfigResponse(BaseModel):
    dias_corte_1: int
    dias_corte_2: int
    dias_alerta_envio: int = 30
    notif_email_ativo: bool = False
    notif_email_hora: int = 8
    notif_canal: str = 'email'
    ativo: bool
    updated_by_nome: Optional[str] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AlertaConfigUpdate(BaseModel):
    dias_alerta_envio: int


class NotifConfigUpdate(BaseModel):
    notif_email_ativo: bool
    notif_email_hora: int
    notif_canal: str = 'email'


class AlteracaoNotifAreaUpsert(BaseModel):
    area_projecao_id: int
    ativo: bool
    emails: List[str] = []


class AlteracaoNotifAreaResponse(BaseModel):
    area_projecao_id: int
    area_projecao_nome: Optional[str] = None
    ativo: bool = False
    emails: List[str] = []
    updated_by_nome: Optional[str] = None
    updated_at: Optional[datetime] = None


class CorteSnapshotResponse(BaseModel):
    evento_id: int
    valor_corte_1: Optional[int] = None
    congelado_corte_1_em: Optional[datetime] = None
    valor_corte_2: Optional[int] = None
    congelado_corte_2_em: Optional[datetime] = None

    class Config:
        from_attributes = True

