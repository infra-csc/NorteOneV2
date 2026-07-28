---
name: Ticket Atual fallback & multi-promo resolution
description: Regras para resolver Ticket Atual com múltiplos kits promo e fallback quando a leitura ao vivo do Magento falha
---
- Eventos acumulam MÚLTIPLOS kits promo entre campanhas (ex.: "R$ 50 OFF" desativada + "R$70 OFF" vigente), muitas vezes sem `is_promo_principal`. A resolução deve ser determinística: promos ordenadas por `bundle_entity_id` DESC (mais novo primeiro) + duas passadas de status — 1ª só `status_kit=="ativo"` confirmado; 2ª aceita desconhecido (`None`/`''`); `"inativo"` NUNCA é elegível.
- O fallback de preço/status NUNCA pode fabricar status "ativo". Fonte persistida correta: `kit_mapping_snapshot` (preço: `pi_pai_min_price` → `special_price` com Regra B → `price`; status real do último sync). A estimativa receita/qtd (`MargemBundleRevSnapshot`) é ÚLTIMO recurso e não carrega status (fica `None` → só entra na 2ª passada).

**Why:** o fallback antigo fazia `status or "ativo"` e percorria promos em ordem arbitrária de query — uma promo ENCERRADA ganhava o Ticket Atual com preço médio histórico errado (99,98 em vez de 129,99) sempre que a leitura ao vivo falhava.

**How to apply:** qualquer novo caminho de fallback de kits deve propagar status desconhecido como `None` e deixar a resolução decidir; nunca preencher default "ativo". Cache do mapa de tickets: 30 min (`clear_ticket_atual_cache()` existe; restart também limpa).
