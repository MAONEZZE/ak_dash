-- Histórico de estágios do Pipedrive (página Funil SDR: Abordados e Respondidos).
--
-- Antes, Abordados/Respondidos contavam os negócios que estão HOJE no estágio: quem
-- avançava para o estágio seguinte sumia da contagem. Agora o WorkerPipedrive lê o
-- histórico de cada negócio (/v1/deals/{id}/flow) e grava a PRIMEIRA entrada em cada
-- estágio; a página conta as entradas no período.
--
-- pipedrive_negocios: um por negócio já sincronizado; `stage_change_time` (texto cru da
--   API) diz se o histórico precisa ser relido; dono e pessoa são os atuais do negócio.
-- pipedrive_entradas_estagio: (negócio, estágio) -> quando entrou pela primeira vez (UTC).
-- vw_pipedrive_entradas_estagio: as duas juntas, o que o BFF lê.
--
-- Idempotente. Rodar: .venv/bin/python -m scripts.rodar_sql sql/2026-11-25-pipedrive-estagios.sql

create table if not exists dash_new.pipedrive_negocios (
  id_deal bigint primary key,
  id_dono bigint,
  id_pessoa bigint,
  stage_change_time text,
  atualizado_em timestamptz not null default now()
);

create table if not exists dash_new.pipedrive_entradas_estagio (
  id_deal bigint not null references dash_new.pipedrive_negocios(id_deal) on delete cascade,
  id_estagio integer not null,
  entrou_em timestamptz not null,
  atualizado_em timestamptz not null default now(),
  primary key (id_deal, id_estagio)
);

create index if not exists pipedrive_entradas_estagio_estagio_data
  on dash_new.pipedrive_entradas_estagio (id_estagio, entrou_em);

create or replace view dash_new.vw_pipedrive_entradas_estagio as
select e.id_deal, e.id_estagio, e.entrou_em, n.id_dono, n.id_pessoa
  from dash_new.pipedrive_entradas_estagio e
  join dash_new.pipedrive_negocios n using (id_deal);

grant select, insert, update, delete on dash_new.pipedrive_negocios, dash_new.pipedrive_entradas_estagio to service_role;
grant select on dash_new.vw_pipedrive_entradas_estagio to service_role;

notify pgrst, 'reload schema';
