---
name: Kit special_price source
description: De onde vem o special_price no Mapeamento de Kits, Regra B e pi_pai_min_price (bypass do filtro para o índice do Magento).
---

# special_price do Mapeamento de Kits

`special_price` (preço promocional/entrada do kit, usado pelo "ticket atual" no
Dash ISC) vem de `catalog_product_index_price.min_price` do **bundle pai**
(`pi_pai`, website_id=1, customer_group_id=0). Fallback (kit inativo, que não
entra no index): soma do `final_price` dos componentes simples via
`pi_filho` — MAX(componente Distância/Modalidade) + MAX(addon não-blacklisted),
ambos com `COALESCE(...,0)` e o todo embrulhado em `NULLIF(...,0)`.

**Why:** `min_price` já reflete as catalog price rules ativas (promoções
vigentes) do Magento — é a fonte canônica do preço de vitrine. Uma versão
anterior trocou isso por uma cadeia de fallback baseada em
`catalog_product_entity_event_lot_price` (lotes), que devolvia valores errados
(somava lote do evento + addon, etc.). Não reintroduzir a lógica de lotes para
special_price.

**How to apply:** Editar só o bloco `special_price` em `MAGENTO_KITS_QUERY`
(`kit_config.py`). A 1ª parcela do fallback PRECISA de `COALESCE(...,0)` (igual
ao `price`): bundles cujo componente "distância" foge da nomenclatura padrão
(ex.: "BPC26SP1MB-5Km") não casam na branch e `NULL + addon` zeraria tudo.
`pi_pai.min_price` é coluna não-agregada → tem que entrar no `GROUP BY`.
Manter intactas as colunas `price`, `current_price` e `bundle_entity_id` (o
resto do sistema depende: bundle_entity_id é PK do snapshot; current_price
alimenta o ticket_atual ISC).

## Regra B e pi_pai_min_price (Jun/2026)

A **Regra B** (descartar `special_price >= price`) **NUNCA** deve ser aplicada
ao valor vindo de `pi_pai.min_price` (índice do Magento), pois o índice reflete
o preço real atual do bundle — que pode legitimamente ser MAIOR que a soma dos
componentes EAV (`price`). Exemplo: Troféu Brasil 2ª Etapa tem
`pi_pai.min_price = 1299,99` e `price` (EAV attr 77) = 999,99; sem o bypass,
a Regra B zeraria o campo e o ISC cairia para o `current_price` (lote = 999,99).

A Regra B só deve ser aplicada ao fallback (soma de componentes, quando
`pi_pai.min_price` é NULL — caso de kits inativos, ex.: Night Run João Pessoa
onde lot_value fantasma de R$129,99 > preço real R$99,99).

**Implementação:** A query `MAGENTO_KITS_QUERY` expõe `pi_pai.min_price` como
coluna separada `pi_pai_min_price` (já está no GROUP BY, sem custo). O
`kit_mapping_snapshot` tem coluna própria `pi_pai_min_price` (migration 008).
No read path (overlay de snapshot e `_fetch_ticket_atual_map`): se
`pi_pai_min_price > 0` → usa diretamente, sem Regra B; senão → aplica
`_normalize_special_price` ao fallback. Cache version bumped para v26.

**Após deploy:** reiniciar backend + clicar "Atualizar" no Mapeamento de Kits
para popular `pi_pai_min_price` no snapshot existente (ticket ISC já corrige
imediatamente pois usa Magento ao vivo, não o snapshot).

## Bypass Ativo sem-combo (task #186, jul/2026)

Kits do Ativo em modalidade simples (sem combo cadastrado) não têm par
"de/por": `ATIVO_KITS_QUERY` preenche `price` E `special_price` com o MESMO
valor por construção (não é resíduo obsoleto, é o dado correto). A Regra B
raw estava zerando `special_price` nesses casos porque `special_price >=
price` sempre é verdade quando são iguais.

**Sinal para o bypass:** `fonte == "ativo"` (case-insensitive) E
`tipo_categoria` vazio/blank — a metade "combo" do UNION ALL sempre traz
`tipo_categoria` não-vazio; a metade "modalidade" sempre grava vazio.
Verificado contra dados reais: 0 exceções. Ver `_is_ativo_kit_sem_combo` e o
kwarg `is_ativo_sem_combo` de `_normalize_special_price` em `kit_config.py` —
mesmo padrão de bypass do `pi_pai_min_price`, aplicado nos 3 call-sites
(live, overlay de snapshot, e o cálculo de `special_price_base` de cada um).
