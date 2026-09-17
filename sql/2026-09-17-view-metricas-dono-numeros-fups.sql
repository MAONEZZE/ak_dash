-- Corrige o dono de `fups` e `numeros_captados` em dash.vw_metricas.
--
-- PROBLEMA: sql/2026-09-15-view-metricas.sql deu a `metricas_dripify` a posse
-- exclusiva dessas duas colunas ("dono único por métrica", pra não dobrar o
-- valor somando as três tabelas). Só que `metricas_dripify` parou de receber
-- dado em 10/09/2026 — enquanto `metricas_sdrs` segue sendo gravada todo dia
-- (17/09 às 15:08). Resultado: número captado lançado hoje não aparece na UI,
-- sem erro nenhum.
--
-- POR QUE TROCAR O DONO É SEGURO (conferido linha a linha em 17/09/2026):
--   · toda chave (key_data_ref_user, id_user) de metricas_dripify existe
--     também em metricas_sdrs — 428 de 428;
--   · `fups` e `numeros_captados` são IDÊNTICOS nas duas em todas as 428
--     chaves em comum (totais históricos: fups 17372, numeros_captados 465);
--   · metricas_sdrs tem 24 chaves a mais, que são justamente os dias que
--     faltam (11/09 em diante).
-- Ou seja: nenhum número histórico muda, e os dias novos passam a aparecer.
--
-- CONTINUA QUEBRADO DEPOIS DESTE SCRIPT (não é problema de view):
--   conexoes_enviadas, conexoes_aceitas, abordagens e in_mails só existem em
--   metricas_dripify. Enquanto a ingestão do Dripify não voltar, essas quatro
--   seguem congeladas em 10/09 na UI. Consertar lá, não aqui.
--
-- `conta` sai null nessas duas métricas: `metricas_dripify.conta_usuario` é
-- null em 100% das linhas hoje, então não se perde nada.

create or replace view dash.vw_metricas as
with sdr_manual as (
  select s.id_user,
         case when s.key_data_ref_user ~ '^\d{2}/\d{2}/\d{4}'
              then to_date(left(s.key_data_ref_user, 10), 'DD/MM/YYYY') end as data,
         s.ligacoes_agendadas, s.reunioes_agendadas, s.indicacoes,
         s.fups, s.numeros_captados
    from dash.metricas_sdrs s
),
closer_manual as (
  select c.id_user,
         case when c.key_data_ref_user ~ '^\d{2}/\d{2}/\d{4}'
              then to_date(left(c.key_data_ref_user, 10), 'DD/MM/YYYY') end as data,
         c.ligacoes_realizadas, c.reunioes_agendadas, c.reunioes_realizadas, c.indicacoes
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
        ('ligacoes_agendadas', s.ligacoes_agendadas),
        ('reunioes_agendadas', s.reunioes_agendadas),
        ('indicacoes',         s.indicacoes),
        ('fups',               s.fups),
        ('numeros_captados',   s.numeros_captados)
      ) as v(metrica, valor)
 where s.data is not null and v.valor is not null

union all

select c2.data, c2.id_user, u.nome, c.cargo, null::text as conta, v.metrica, v.valor
  from closer_manual c2
  join dash.users u on u.id = c2.id_user
  join dash.metricas_cargo c on c.id = u.id_cargo and c.cargo = 'closer'
 cross join lateral (values
        ('ligacoes_realizadas', c2.ligacoes_realizadas),
        ('reunioes_agendadas',  c2.reunioes_agendadas),
        ('reunioes_realizadas', c2.reunioes_realizadas),
        ('indicacoes',          c2.indicacoes)
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

-- Conferência: numeros_captados de setembro deve sair 53 (era 28), e 17/09
-- deve passar a existir pra nathan (23) e jennifer (2).
-- select metrica, sum(valor) from dash.vw_metricas
--  where data between '2026-09-01' and '2026-09-30' group by metrica order by metrica;
-- select * from dash.vw_metricas
--  where data = '2026-09-17' and metrica = 'numeros_captados';
