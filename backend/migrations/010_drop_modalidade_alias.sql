-- Remove a tabela modalidade_alias e a tela "Configuração Modalidade".
-- Nunca teve linhas em uso (prod ou dev); a normalização de modalidade real
-- já é coberta por detalhe_dimensao_alias ("Padrões de Dimensão"), que também
-- suporta regex e ordenação por regra. Ver DROP em backend/main.py (_run_column_migrations).
DROP TABLE IF EXISTS modalidade_alias;
