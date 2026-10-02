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

create or replace view dash.vw_metricas as
with sdr_manual as (
  select s.id_user,
         case when s.key_data_ref_user ~ '^\d{2}/\d{2}/\d{4}'
              then to_date(left(s.key_data_ref_user, 10), 'DD/MM/YYYY') end as data,
         s.fups, s.numeros_captados, s.ligacoes_realizadas, s.reunioes_agendadas,
         s.indicacoes, s.inscricoes_realizadas
    from dash.metricas_sdrs s
),
closer_manual as (
  select c.id_user,
         case when c.key_data_ref_user ~ '^\d{2}/\d{2}/\d{4}'
              then to_date(left(c.key_data_ref_user, 10), 'DD/MM/YYYY') end as data,
         c.ligacoes_agendadas, c.ligacoes_realizadas, c.reunioes_agendadas,
         c.reunioes_realizadas, c.indicacoes, c.inscricoes_realizadas
    from dash.metricas_closers c
),
linkedin as (
  select d.id_user,
         case when d.key_data_ref_user ~ '^\d{2}/\d{2}/\d{4}'
              then to_date(left(d.key_data_ref_user, 10), 'DD/MM/YYYY') end as data,
         d.conta_usuario,
         d.conexoes_enviadas, d.conexoes_aceitas, d.abordagens, d.in_mails
    from dash.metricas_dripify d
)
select s.data, s.id_user, u.nome, c.cargo, null::text as conta, v.metrica, v.valor
  from sdr_manual s
  join dash.users u on u.id = s.id_user
  join dash.metricas_cargo c on c.id = u.id_cargo and c.cargo = 'sdr'
 cross join lateral (values
        ('fups',                  s.fups),
        ('numeros_captados',      s.numeros_captados),
        ('ligacoes_realizadas',   s.ligacoes_realizadas),
        ('reunioes_agendadas',    s.reunioes_agendadas),
        ('indicacoes',            s.indicacoes),
        ('inscricoes_realizadas', s.inscricoes_realizadas)
      ) as v(metrica, valor)
 where s.data is not null and v.valor is not null

union all

select c2.data, c2.id_user, u.nome, c.cargo, null::text as conta, v.metrica, v.valor
  from closer_manual c2
  join dash.users u on u.id = c2.id_user
  join dash.metricas_cargo c on c.id = u.id_cargo and c.cargo = 'closer'
 cross join lateral (values
        ('ligacoes_agendadas',    c2.ligacoes_agendadas),
        ('ligacoes_realizadas',   c2.ligacoes_realizadas),
        ('reunioes_agendadas',    c2.reunioes_agendadas),
        ('reunioes_realizadas',   c2.reunioes_realizadas),
        ('indicacoes',            c2.indicacoes),
        ('inscricoes_realizadas', c2.inscricoes_realizadas)
      ) as v(metrica, valor)
 where c2.data is not null and v.valor is not null

union all

select l.data, l.id_user, u.nome, c.cargo, l.conta_usuario as conta, v.metrica, v.valor
  from linkedin l
  join dash.users u on u.id = l.id_user
  join dash.metricas_cargo c on c.id = u.id_cargo and c.cargo = 'sdr'
 cross join lateral (values
        ('conexoes_enviadas', l.conexoes_enviadas),
        ('conexoes_aceitas',  l.conexoes_aceitas),
        ('abordagens',        l.abordagens),
        ('in_mails',          l.in_mails)
      ) as v(metrica, valor)
 where l.data is not null and v.valor is not null;

grant select on dash.vw_metricas to service_role;
