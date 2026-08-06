"""
Mapeamento fixo Área de Projeção -> Canal de vendas (Site / Cortesia / Grupos/B2B).

Usado para agregar a "Projeção de Inscritos" (lançada por área) nos mesmos 3
canais usados no Detalhamento de Eventos ("Inscritos por Canal"), permitindo
comparar Inscritos (real) x Projetado por canal na mesma tela.

Regra de negócio estável, confirmada com o usuário (Task #256):
- Site → Site
- Atendimento, Marketing, Relações Institucionais, Comercial, Cortesia RH,
  Proprietário → Cortesia
- Saúde Corporativa → Grupos/B2B

Áreas ativas que não constam neste mapa (ex.: uma área nova criada depois)
NÃO são silenciosamente jogadas em um canal "adivinhado" — ficam de fora da
agregação e são logadas como aviso, para que o mapeamento seja atualizado
deliberadamente quando isso acontecer.
"""
from typing import Dict, List

AREA_PARA_CANAL: Dict[str, str] = {
    "Site": "Site",
    "Atendimento": "Cortesia",
    "Marketing": "Cortesia",
    "Relações Institucionais": "Cortesia",
    "Comercial": "Cortesia",
    "Cortesia RH": "Cortesia",
    "Proprietário": "Cortesia",
    "Saúde Corporativa": "Grupos/B2B",
}

# Canais existentes no Detalhamento de Eventos (mesmos usados em `por_canal`).
CANAIS_DETALHE: List[str] = ["Site", "Cortesia", "Grupos/B2B"]
