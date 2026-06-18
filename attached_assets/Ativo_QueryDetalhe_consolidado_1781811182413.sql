-- =====================================================================
-- ATIVO (0_transfer) | Detalhe de inscricoes por evento  (CONTRATO CONSOLIDADO)
-- ---------------------------------------------------------------------
-- Saida ALINHADA ao mesmo contrato de colunas da query do Magento, para
-- merge na camada de aplicacao (Node). Bancos distintos => consolidacao
-- feita no back (rodar as duas, concatenar, reagrupar).
--
-- CONTRATO (ordem fixa, identica nas duas queries):
--   banco, id_evento, evento, canal, kit, distancia, modalidade,
--   pelotao, produtos, tamanho_camiseta,
--   inscritos, receita_bruta, receita_liquida, ticket_medio
--
-- produtos = NULL (Ativo nao tem essa dimensao; existe so no Magento).
--
-- MANUTENCAO: o CASE de 'canal' precisa ser IDENTICO no SELECT e no GROUP BY.
-- =====================================================================
SELECT
    'Ativo'                                                                         AS banco,
    b.id_evento                                                                     AS id_evento,
    b.ds_evento                                                                     AS evento,

    -- canal (IDENTICO ao GROUP BY)
    CASE
        WHEN a.nr_preco = 0                                        THEN 'Cortesia'
        WHEN cupom.en_cupom_classificacao = 'Grupos'               THEN 'Grupos/B2B'
        WHEN h.ds_categoria LIKE '%Grup%'                          THEN 'Grupos/B2B'
        ELSE                                                            'Site'
    END                                                                             AS canal,

    h.ds_categoria                                                                  AS kit,
    m.ds_modalidade                                                                 AS distancia,
    q.nm_modalidade                                                                 AS modalidade,

    -- Pelotao: site usa g.pelotao (sa_usuario); balcao usa w.pelotao (sa_usuario_balcao)
    COALESCE(IF(c.fl_local_inscricao = 1, g.pelotao, w.pelotao), 'Branco')          AS pelotao,

    NULL                                                                            AS produtos,  -- Ativo nao tem dimensao de produtos

    IF(x.id_tamanho_camiseta = 2, 'BL', x.ds_tamanho)                               AS tamanho_camiseta,

    COUNT(DISTINCT a.id_pedido_evento)                                              AS inscritos,

    SUM( a.nr_preco )                                                               AS receita_bruta,  -- cortesia => nr_preco = 0 (zera naturalmente)

    SUM(IF(
        a.nr_preco
        - IF(a.nr_desconto_individual IS NULL, 0, a.nr_desconto_individual)
        - IF(h.vl_kit IS NULL, 0, h.vl_kit) < 0,
        0,
        a.nr_preco
        - IF(a.nr_desconto_individual IS NULL, 0, a.nr_desconto_individual)
        - IF(h.vl_kit IS NULL, 0, h.vl_kit)
    ))                                                                              AS receita_liquida,

    SUM(IF(
        a.nr_preco
        - IF(a.nr_desconto_individual IS NULL, 0, a.nr_desconto_individual)
        - IF(h.vl_kit IS NULL, 0, h.vl_kit) < 0,
        0,
        a.nr_preco
        - IF(a.nr_desconto_individual IS NULL, 0, a.nr_desconto_individual)
        - IF(h.vl_kit IS NULL, 0, h.vl_kit)
    )) / NULLIF(COUNT(DISTINCT a.id_pedido_evento), 0)                              AS ticket_medio

FROM sa_evento AS b
INNER JOIN sa_pedido_evento AS a
    ON a.id_evento = b.id_evento
INNER JOIN sa_pedido AS c
    ON c.id_pedido = a.id_pedido
    AND c.id_pedido_status IN (2)            -- 2 = PAGO
   -- AND c.fl_local_inscricao = '1'         -- toggle
LEFT JOIN sa_modalidade_categoria AS h
    ON h.id_categoria = a.id_categoria
LEFT JOIN sa_evento_modalidade AS m
    ON m.id_modalidade = a.id_modalidade
    AND m.id_evento = b.id_evento

-- ===== Dimensoes complementares =======================================
LEFT JOIN sa_evento_modalidade AS q          -- 'modalidade' (pela modalidade da categoria)
    ON q.id_modalidade = h.id_modalidade
LEFT JOIN sa_usuario AS g                    -- Pelotao / inscrito (site)
    ON g.id_usuario = c.id_usuario
LEFT JOIN sa_usuario_balcao AS w             -- Pelotao (balcao)
    ON w.id_usuario = a.id_usuario_balcao
LEFT JOIN sa_tamanho_camiseta AS x           -- Tamanho Camiseta
    ON x.id_tamanho_camiseta = a.id_tamanho_camiseta
-- =====================================================================

LEFT JOIN (
    SELECT
        e.id_cupom_desconto_item,
        f.en_cupom_classificacao
    FROM sa_cupom_desconto_item AS e
    INNER JOIN sa_cupom_desconto AS f
        ON f.id_cupom_desconto = e.id_cupom_desconto
) AS cupom
    ON cupom.id_cupom_desconto_item = a.id_cupom_individual

WHERE
    b.dt_evento BETWEEN MAKEDATE(YEAR(CURDATE()), 1)
                    AND MAKEDATE(YEAR(CURDATE()) + 1, 1) - INTERVAL 1 DAY
    AND (b.id_campanha_salesforce IS NULL
         OR b.id_campanha_salesforce NOT LIKE '701d0000000%')
 --  AND b.id_evento IN (40174) -- Filtro evento (toggle)

GROUP BY
    b.id_evento,
    b.ds_evento,
    -- canal: IDENTICO ao SELECT
    CASE
        WHEN a.nr_preco = 0                                        THEN 'Cortesia'
        WHEN cupom.en_cupom_classificacao = 'Grupos'               THEN 'Grupos/B2B'
        WHEN h.ds_categoria LIKE '%Grup%'                          THEN 'Grupos/B2B'
        ELSE                                                            'Site'
    END,
    h.id_categoria,
    h.ds_categoria,
    m.id_modalidade,
    m.ds_modalidade,
    q.nm_modalidade,
    COALESCE(IF(c.fl_local_inscricao = 1, g.pelotao, w.pelotao), 'Branco'),
    IF(x.id_tamanho_camiseta = 2, 'BL', x.ds_tamanho)

ORDER BY
    b.id_evento,
    canal,
    inscritos DESC;
