from app.models.user import Usuario as Usuario
from app.models.user_pref import UserUiPref as UserUiPref
from app.models.dimensoes import (
    DimCentroCusto as DimCentroCusto,
    DimProjeto as DimProjeto,
    DimCategoriaAtleta as DimCategoriaAtleta,
    DimTempo as DimTempo,
    AcaoComercial as AcaoComercial,
)
from app.models.tarefas import Tarefa as Tarefa
from app.models.perfil_acesso import (
    PerfilAcesso as PerfilAcesso,
    PerfilPermissao as PerfilPermissao,
    PerfilPermissaoCampo as PerfilPermissaoCampo,
)
from app.models.kit_mapping_snapshot import KitMappingSnapshot as KitMappingSnapshot
from app.models.cadastro_evento import (
    CadastroEvento as CadastroEvento,
    CadastroCortesia as CadastroCortesia,
    CadastroTaxa as CadastroTaxa,
    CadastroKitProduto as CadastroKitProduto,
    CadastroKitProdutoItem as CadastroKitProdutoItem,
    CadastroFaixaPrecoSite as CadastroFaixaPrecoSite,
    CadastroFaixaPrecoGrupos as CadastroFaixaPrecoGrupos,
    CircuitoProduto as CircuitoProduto,
    Localizacao as Localizacao,
    DistanciaOpcao as DistanciaOpcao,
)
from app.models.cotacao import (
    ViagemCotacao as ViagemCotacao,
    Fornecedor as Fornecedor,
    Cotacao as Cotacao,
    CustoImportacao as CustoImportacao,
    CotacaoEvento as CotacaoEvento,
    CotacaoFob as CotacaoFob,
)
from app.models.cache_entry import CacheEntry as CacheEntry
from app.models.vendas_snapshot import (
    VendasDiariaSnapshot as VendasDiariaSnapshot,
    CurvaHistoricaSnapshot as CurvaHistoricaSnapshot,
)
from app.models.kit_config import KitConfig as KitConfig
from app.models.consolidacao_checkpoint import ConsolidacaoCheckpoint as ConsolidacaoCheckpoint
