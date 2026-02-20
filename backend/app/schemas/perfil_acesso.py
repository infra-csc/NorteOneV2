from pydantic import BaseModel
from typing import Optional, List


MODULOS_SISTEMA = [
    {"key": "dashboard", "label": "Dashboard"},
    {"key": "nori", "label": "Nori - Assistente"},
    {"key": "categorias_atletas", "label": "Categorias Atletas"},
    {"key": "eventos", "label": "Eventos"},
    {"key": "orcamento", "label": "Orçamento"},
    {"key": "atletas", "label": "Atletas"},
    {"key": "marketing_dashboard", "label": "Marketing - Dashboard ISC"},
    {"key": "marketing_pricing", "label": "Marketing - Análise de Pricing"},
    {"key": "marketing_comparativo", "label": "Marketing - Comparativo"},
    {"key": "marketing_configuracoes", "label": "Marketing - Configurações"},
    {"key": "admin_dados_consolidados", "label": "Admin - Dados Consolidados"},
    {"key": "admin_sku_mappings", "label": "Admin - Mapeamento SKUs"},
    {"key": "admin_usuarios", "label": "Admin - Usuários"},
    {"key": "admin_centros_custo", "label": "Admin - Centros de Custo"},
    {"key": "admin_contas", "label": "Admin - Contas"},
    {"key": "admin_perfis_acesso", "label": "Admin - Perfis de Acesso"},
]


class PermissaoBase(BaseModel):
    modulo: str
    pode_visualizar: bool = False
    pode_criar: bool = False
    pode_editar: bool = False
    pode_deletar: bool = False


class PermissaoResponse(PermissaoBase):
    id: int
    perfil_acesso_id: int

    class Config:
        from_attributes = True


class PerfilAcessoBase(BaseModel):
    nome: str
    descricao: Optional[str] = None


class PerfilAcessoCreate(PerfilAcessoBase):
    permissoes: List[PermissaoBase] = []


class PerfilAcessoUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    ativo: Optional[bool] = None
    permissoes: Optional[List[PermissaoBase]] = None


class PerfilAcessoResponse(PerfilAcessoBase):
    id: int
    is_sistema: bool
    is_admin: bool = False
    ativo: bool
    permissoes: List[PermissaoResponse] = []

    class Config:
        from_attributes = True


class PerfilAcessoListResponse(BaseModel):
    id: int
    nome: str
    descricao: Optional[str] = None
    is_sistema: bool
    is_admin: bool = False
    ativo: bool
    total_usuarios: int = 0

    class Config:
        from_attributes = True


class ModuloInfo(BaseModel):
    key: str
    label: str


class UserPermissoesResponse(BaseModel):
    perfil_acesso_id: Optional[int] = None
    perfil_acesso_nome: Optional[str] = None
    is_admin: bool = False
    permissoes: dict = {}
