-- Planilha de SDRs ganhou as colunas Oportunidades, Abordagens e Responderam
-- (e perdeu Ligações Efetuadas/Realizadas). O worker grava Abordagens e
-- Responderam aqui; as colunas de ligações ficam com o histórico.
--
-- Idempotente. Rodar: .venv/bin/python -m scripts.rodar_sql sql/2026-11-16-funil-sdr-etapas.sql

alter table dash_new.metricas_funil_sdr add column if not exists abordagens integer;
alter table dash_new.metricas_funil_sdr add column if not exists respondidos integer;

notify pgrst, 'reload schema';
