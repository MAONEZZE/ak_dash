-- Libera a leitura de dash.user_metas pro BFF.
--
-- PROBLEMA: dash.user_metas foi criada (meta por pessoa, substituindo o par
-- dash.metricas_metas.valor + dash.metas_cargo) sem GRANT pro `service_role`,
-- que é o papel da chave que o BFF usa. O PostgREST responde:
--
--   {"code":"42501","message":"permission denied for table user_metas"}
--
-- e `app/fontes/banco.py` degrada toda falha de consulta pra lista vazia (por
-- design: tabela/coluna que ainda não existe, rede fora, RLS). O efeito é
-- silencioso e fácil de ler errado: NENHUMA meta carrega, todo card mostra
-- "Meta não cadastrada", os dois pódios somem (sem meta não há pontuação) e a
-- resposta vem com o aviso `metas_nao_cadastradas` — sem erro nenhum no log
-- da aplicação. Mesma classe do que já aconteceu com o schema SED.
--
-- Rodar no SQL Editor do Supabase. Depois disso o dash volta a mostrar meta
-- sem precisar reiniciar nada (o cache do BFF expira em 60s).

GRANT USAGE ON SCHEMA dash TO service_role;
GRANT SELECT ON dash.user_metas TO service_role;

-- Confere: tem que devolver linha (e não 42501).
-- SELECT id_user, id_meta, valor_meta FROM dash.user_metas LIMIT 5;
