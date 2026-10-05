-- Recria dash.vw_metricas com as colunas novas de metricas_sdrs/metricas_closers.
--
-- PROBLEMA: `ligacoes_agendadas` foi removida de dash.metricas_sdrs. A view
-- dependia dela, então caiu junto (PostgREST responde PGRST205 pra
-- vw_metricas) e o dashboard ficou sem dado nenhum de SDR/Closer.
--
-- O QUE MUDA em relação a sql/2026-09-17-view-metricas-dono-numeros-fups.sql:
--   · SDR: sai `ligacoes_agendadas`; entram `ligacoes_realizadas` e
--     `inscricoes_realizadas`;
--   · Closer: entram `ligacoes_agendadas` e `inscricoes_realizadas`;
--   · Dripify (conexoes_enviadas, conexoes_aceitas, abordagens, in_mails):
--     sem mudança.
-- Formato longo, joins e filtro por cargo (`users.id_cargo`) são os mesmos.
--
-- Sem drop/alter: a view não existe mais, `create or replace` só a cria.
-- Apelidos longos (sdr/clo/drip) de propósito: no SQL Editor do Supabase o
-- autocompletar engolia texto depois de `d.` ao colar.

create or replace view dash.vw_metricas as
with sdr_manual as (
  select sdr.id_user,
         case when sdr.key_data_ref_user ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}'
              then to_date(left(sdr.key_data_ref_user, 10), 'DD/MM/YYYY') end as data,
         sdr.fups, sdr.numeros_captados, sdr.ligacoes_realizadas, sdr.reunioes_agendadas,
         sdr.indicacoes, sdr.inscricoes_realizadas
    from dash.metricas_sdrs sdr
),
closer_manual as (
  select clo.id_user,
         case when clo.key_data_ref_user ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}'
              then to_date(left(clo.key_data_ref_user, 10), 'DD/MM/YYYY') end as data,
         clo.ligacoes_agendadas, clo.ligacoes_realizadas, clo.reunioes_agendadas,
         clo.reunioes_realizadas, clo.indicacoes, clo.inscricoes_realizadas
    from dash.metricas_closers clo
),
linkedin as (
  select drip.id_user,
         case when drip.key_data_ref_user ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}'
              then to_date(left(drip.key_data_ref_user, 10), 'DD/MM/YYYY') end as data,
         drip.conta_usuario,
         drip.conexoes_enviadas, drip.conexoes_aceitas, drip.abordagens, drip.in_mails
    from dash.metricas_dripify drip
)
select sm.data, sm.id_user, usr.nome, cg.cargo, null::text as conta, v.metrica, v.valor
  from sdr_manual sm
  join dash.users usr on usr.id = sm.id_user
  join dash.metricas_cargo cg on cg.id = usr.id_cargo and cg.cargo = 'sdr'
 cross join lateral (values
        ('fups',                  sm.fups),
        ('numeros_captados',      sm.numeros_captados),
        ('ligacoes_realizadas',   sm.ligacoes_realizadas),
        ('reunioes_agendadas',    sm.reunioes_agendadas),
        ('indicacoes',            sm.indicacoes),
        ('inscricoes_realizadas', sm.inscricoes_realizadas)
      ) as v(metrica, valor)
 where sm.data is not null and v.valor is not null

union all

select cm.data, cm.id_user, usr.nome, cg.cargo, null::text as conta, v.metrica, v.valor
  from closer_manual cm
  join dash.users usr on usr.id = cm.id_user
  join dash.metricas_cargo cg on cg.id = usr.id_cargo and cg.cargo = 'closer'
 cross join lateral (values
        ('ligacoes_agendadas',    cm.ligacoes_agendadas),
        ('ligacoes_realizadas',   cm.ligacoes_realizadas),
        ('reunioes_agendadas',    cm.reunioes_agendadas),
        ('reunioes_realizadas',   cm.reunioes_realizadas),
        ('indicacoes',            cm.indicacoes),
        ('inscricoes_realizadas', cm.inscricoes_realizadas)
      ) as v(metrica, valor)
 where cm.data is not null and v.valor is not null

union all

select li.data, li.id_user, usr.nome, cg.cargo, li.conta_usuario as conta, v.metrica, v.valor
  from linkedin li
  join dash.users usr on usr.id = li.id_user
  join dash.metricas_cargo cg on cg.id = usr.id_cargo and cg.cargo = 'sdr'
 cross join lateral (values
        ('conexoes_enviadas', li.conexoes_enviadas),
        ('conexoes_aceitas',  li.conexoes_aceitas),
        ('abordagens',        li.abordagens),
        ('in_mails',          li.in_mails)
      ) as v(metrica, valor)
 where li.data is not null and v.valor is not null;

grant select on dash.vw_metricas to service_role;

-- Recarrega o cache do PostgREST pra view aparecer na hora (sem isso, 404 até o reload automático).
notify pgrst, 'reload schema';
