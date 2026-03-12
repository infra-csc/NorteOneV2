from app.models.user import Usuario
from app.models.dimensoes import DimCentroCusto, DimProjeto, DimCategoriaAtleta, DimTempo, AcaoComercial
from app.models.tarefas import Tarefa
from app.models.perfil_acesso import PerfilAcesso, PerfilPermissao, PerfilPermissaoCampo
from app.models.cadastro_evento import (
    CadastroEvento, CadastroCortesia, CadastroTaxa, 
    CadastroKitProduto, CadastroKitProdutoItem,
    CadastroFaixaPrecoSite, CadastroFaixaPrecoGrupos,
    CircuitoProduto, Localizacao, DistanciaOpcao
)
from app.models.cotacao import (
    ViagemCotacao, Fornecedor, Cotacao, CustoImportacao, CotacaoEvento
)
from app.models.cache_entry import CacheEntry
from app.models.vendas_snapshot import VendasDiariaSnapshot, CurvaHistoricaSnapshot
from app.models.kit_config import KitConfig
