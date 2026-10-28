-- Libera a escrita dos workers das planilhas em dash2.
--
-- PROBLEMA: `sql/2026-10-26-dash2-schema.sql` deu ao `service_role` só
-- `select` em dash2 — foi escrito quando o n8n ainda ia gravar as métricas.
-- Os workers (`app/workers.py`) gravam com a chave do BFF (service_role) e
-- todo upsert volta 403 do PostgREST:
--
--   HTTPStatusError: Client error '403 Forbidden' for url
--   '.../rest/v1/metricas_sellers?on_conflict=key_data_ref_user'
--
-- O `/saude` mostra o erro em `ultimo_erro` de cada worker, mas o dash não:
-- os dados só param de chegar (ficou parado em 27/10).
--
-- Upsert = insert + update. Meta apagada na planilha é removida de
-- dash2.metas, então ela também precisa de delete.
--
-- Rodar: .venv/bin/python -m scripts.rodar_sql sql/2026-10-28-grant-escrita-workers.sql

grant insert, update on dash2.metricas_sellers, dash2.metricas_sdrs, dash2.metricas_closers, dash2.metricas_dripify to service_role;
grant insert, update, delete on dash2.metas to service_role;
-- As colunas `id` são identity; não precisa, mas não custa.
grant usage on all sequences in schema dash2 to service_role;

notify pgrst, 'reload schema';

-- Confere: cada tabela tem que listar INSERT e UPDATE (metas também DELETE).
-- select table_name, string_agg(privilege_type, ',') from information_schema.role_table_grants
--  where grantee = 'service_role' and table_schema = 'dash2' group by 1;
