"""Testes do fallback por banco na curva comparativa global.

Cenários cobertos (espelhando a redação do "Done looks like" da tarefa):
1. Um banco falha ao vivo mas tem dado anterior (last-good) →
   contribuição do banco falho é preenchida pelo dado anterior;
   resposta inclui fallback_info com fonte="ultimo_dado_bom".
2. Um banco falha ao vivo e NÃO há dado anterior (cold start) →
   resposta inclui fallback_info com fonte="sem_dados_anteriores";
   contribuição do banco falho fica zerada (comportamento anterior);
   resposta NÃO é cacheada.
3. Ambos os bancos falham →
   comportamento atual preservado: zeros, sem fallback_info, sem cache.
4. Comportamento de cache:
   - Falha em qualquer banco → resultado não entra no cache (próximo
     request tenta de novo ao vivo).
   - Ambos os bancos ao vivo → resultado entra no cache.
"""
import os
import sys
import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

# Garante que o diretório raiz do backend está no sys.path
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

# Importa o módulo de rotas e os objetos de estado que vamos manipular
import app.api.routes.marketing as mkt


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_curva_state():
    """Limpa o estado global de cache e last-good antes de cada teste."""
    with mkt._curva_last_good_lock:
        mkt._curva_last_good_ativo.clear()
        mkt._curva_last_good_magento.clear()
    mkt._curva_cache.clear()
    mkt._curva_cache_timestamp = None
    yield
    # Limpeza pós-teste também
    with mkt._curva_last_good_lock:
        mkt._curva_last_good_ativo.clear()
        mkt._curva_last_good_magento.clear()
    mkt._curva_cache.clear()
    mkt._curva_cache_timestamp = None


# Dados fictícios suficientes para as asserções
ANO_ATUAL = datetime.now().year
ANO_ANTERIOR = ANO_ATUAL - 1

_ATIVO_ROWS = [
    {"ano": ANO_ATUAL, "mes": 1, "qtd": 100, "receita": 10000.0},
    {"ano": ANO_ANTERIOR, "mes": 1, "qtd": 80, "receita": 8000.0},
]
_MAGENTO_ROWS = [
    {"ano": ANO_ATUAL, "mes": 1, "qtd": 50, "receita": 6000.0},
    {"ano": ANO_ANTERIOR, "mes": 1, "qtd": 40, "receita": 4000.0},
]


def _call_endpoint():
    """Chama get_curva_comparativa com dependências mockadas."""
    fake_db = MagicMock()
    fake_user = MagicMock()
    return mkt.get_curva_comparativa(db=fake_db, current_user=fake_user)


# ---------------------------------------------------------------------------
# Cenário 1: Um banco ao vivo + um banco via last-good
# ---------------------------------------------------------------------------

class TestFallbackComDadoAnterior:
    """Magento falha ao vivo, mas last-good já foi populado por request anterior."""

    def test_totais_incluem_dado_anterior_do_banco_falho(self):
        # Pre-seed last-good para Magento
        with mkt._curva_last_good_lock:
            mkt._curva_last_good_magento["data"] = _MAGENTO_ROWS
            mkt._curva_last_good_magento["at"] = "2026-08-04T03:00:00-03:00"

        with patch.object(mkt, "_fetch_monthly_sales_ativo", return_value=(_ATIVO_ROWS, None)), \
             patch.object(mkt, "_fetch_monthly_sales_magento", return_value=([], "Fila cheia")):
            result = _call_endpoint()

        jan = next(e for e in result["data"] if e["mes"] == "Jan")
        # Ativo (100) + Magento fallback (50) = 150; sem fallback seria só 100
        assert jan[f"vendas_{ANO_ATUAL}"] == 150

    def test_fallback_info_presente_e_correto(self):
        with mkt._curva_last_good_lock:
            mkt._curva_last_good_magento["data"] = _MAGENTO_ROWS
            mkt._curva_last_good_magento["at"] = "2026-08-04T03:00:00-03:00"

        with patch.object(mkt, "_fetch_monthly_sales_ativo", return_value=(_ATIVO_ROWS, None)), \
             patch.object(mkt, "_fetch_monthly_sales_magento", return_value=([], "Fila cheia")):
            result = _call_endpoint()

        assert "fallback_info" in result
        assert "magento" in result["fallback_info"]
        fb = result["fallback_info"]["magento"]
        assert fb["fonte"] == "ultimo_dado_bom"
        assert fb["capturado_em"] == "2026-08-04T03:00:00-03:00"
        assert "Fila cheia" in fb["erro"]
        # Ativo funcionou ao vivo — não deve aparecer em fallback_info
        assert "ativo" not in result["fallback_info"]

    def test_resultado_nao_entra_no_cache_quando_banco_falha(self):
        with mkt._curva_last_good_lock:
            mkt._curva_last_good_magento["data"] = _MAGENTO_ROWS
            mkt._curva_last_good_magento["at"] = "2026-08-04T03:00:00-03:00"

        with patch.object(mkt, "_fetch_monthly_sales_ativo", return_value=(_ATIVO_ROWS, None)), \
             patch.object(mkt, "_fetch_monthly_sales_magento", return_value=([], "Fila cheia")):
            _call_endpoint()

        # Cache não deve ter sido populado
        assert mkt._curva_cache_timestamp is None


# ---------------------------------------------------------------------------
# Cenário 2: Um banco falha sem dado anterior (cold start)
# ---------------------------------------------------------------------------

class TestFallbackSemDadoAnterior:
    """Magento falha ao vivo e não há nenhum dado anterior disponível."""

    def test_fallback_info_marca_sem_dados_anteriores(self):
        with patch.object(mkt, "_fetch_monthly_sales_ativo", return_value=(_ATIVO_ROWS, None)), \
             patch.object(mkt, "_fetch_monthly_sales_magento", return_value=([], "Tunnel expirou")):
            result = _call_endpoint()

        assert "fallback_info" in result
        fb = result["fallback_info"]["magento"]
        assert fb["fonte"] == "sem_dados_anteriores"
        assert fb["capturado_em"] is None
        assert "Tunnel expirou" in fb["erro"]

    def test_resultado_nao_entra_no_cache_quando_sem_dado_anterior(self):
        with patch.object(mkt, "_fetch_monthly_sales_ativo", return_value=(_ATIVO_ROWS, None)), \
             patch.object(mkt, "_fetch_monthly_sales_magento", return_value=([], "Tunnel expirou")):
            _call_endpoint()

        assert mkt._curva_cache_timestamp is None

    def test_ativo_falha_sem_dado_anterior_tambem_marcado(self):
        """Mesma semântica quando é o Ativo que falha sem dado anterior."""
        with patch.object(mkt, "_fetch_monthly_sales_ativo", return_value=([], "SSH down")), \
             patch.object(mkt, "_fetch_monthly_sales_magento", return_value=(_MAGENTO_ROWS, None)):
            result = _call_endpoint()

        assert "fallback_info" in result
        fb = result["fallback_info"]["ativo"]
        assert fb["fonte"] == "sem_dados_anteriores"
        assert fb["capturado_em"] is None
        assert "SSH down" in fb["erro"]
        assert "magento" not in result["fallback_info"]


# ---------------------------------------------------------------------------
# Cenário 3: Ambos os bancos falham
# ---------------------------------------------------------------------------

class TestAmbosBancosFalham:
    """Quando os dois bancos falham, comportamento original é preservado."""

    def test_sem_fallback_info_quando_dois_bancos_falham(self):
        with patch.object(mkt, "_fetch_monthly_sales_ativo", return_value=([], "SSH down")), \
             patch.object(mkt, "_fetch_monthly_sales_magento", return_value=([], "Magento down")):
            result = _call_endpoint()

        # Sem fallback_info — não queremos servir dados parciais como se
        # fossem bons quando AMBOS os bancos estão indisponíveis.
        assert "fallback_info" not in result

    def test_totais_zerados_quando_dois_bancos_falham(self):
        with patch.object(mkt, "_fetch_monthly_sales_ativo", return_value=([], "SSH down")), \
             patch.object(mkt, "_fetch_monthly_sales_magento", return_value=([], "Magento down")):
            result = _call_endpoint()

        jan = next(e for e in result["data"] if e["mes"] == "Jan")
        assert jan[f"vendas_{ANO_ATUAL}"] == 0
        assert jan[f"vendas_{ANO_ANTERIOR}"] == 0

    def test_sem_cache_quando_dois_bancos_falham(self):
        with patch.object(mkt, "_fetch_monthly_sales_ativo", return_value=([], "SSH down")), \
             patch.object(mkt, "_fetch_monthly_sales_magento", return_value=([], "Magento down")):
            _call_endpoint()

        assert mkt._curva_cache_timestamp is None


# ---------------------------------------------------------------------------
# Cenário 4: Cache populado apenas com dados totalmente ao vivo
# ---------------------------------------------------------------------------

class TestCacheComportamento:

    def test_cache_populado_quando_ambos_ao_vivo(self):
        with patch.object(mkt, "_fetch_monthly_sales_ativo", return_value=(_ATIVO_ROWS, None)), \
             patch.object(mkt, "_fetch_monthly_sales_magento", return_value=(_MAGENTO_ROWS, None)):
            result = _call_endpoint()

        assert mkt._curva_cache_timestamp is not None
        assert "fallback_info" not in result

    def test_request_seguinte_usa_cache_quando_ao_vivo(self):
        with patch.object(mkt, "_fetch_monthly_sales_ativo", return_value=(_ATIVO_ROWS, None)), \
             patch.object(mkt, "_fetch_monthly_sales_magento", return_value=(_MAGENTO_ROWS, None)):
            _call_endpoint()

        # Segundo call com fetchers que lancariam erro — cache deve ser servido
        with patch.object(mkt, "_fetch_monthly_sales_ativo", side_effect=Exception("não deve ser chamado")), \
             patch.object(mkt, "_fetch_monthly_sales_magento", side_effect=Exception("não deve ser chamado")):
            result = _call_endpoint()

        # Se chegou aqui sem exceção, o cache foi servido corretamente
        assert result["status"] == "success"

    def test_last_good_atualizado_apos_fetch_bem_sucedido(self):
        with patch.object(mkt, "_fetch_monthly_sales_ativo", return_value=(_ATIVO_ROWS, None)), \
             patch.object(mkt, "_fetch_monthly_sales_magento", return_value=(_MAGENTO_ROWS, None)):
            _call_endpoint()

        with mkt._curva_last_good_lock:
            assert mkt._curva_last_good_ativo.get("data") == _ATIVO_ROWS
            assert mkt._curva_last_good_magento.get("data") == _MAGENTO_ROWS
