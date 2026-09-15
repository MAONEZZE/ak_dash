-- Reconstrução da fonte de leitura do BFF depois do redesenho do schema `dash`
-- (metas renomeadas, metas_cargo criada, vw_metricas apagada, tabelas de
-- métrica divididas por cargo). Rodar no SQL editor do Supabase, em ordem.

-- 1. O BFF (service_role) não enxerga a tabela nova.
grant select on dash.metas_cargo to service_role;

-- 2. Devolver a DATA às linhas antigas.
--    A divisão de `dash.metricas` (hoje `metricas_backup`) em
--    metricas_sdrs/metricas_closers/metricas_dripify copiou os valores mas
--    deixou `data_referente` para trás: das 443 linhas herdadas, nenhuma tem
--    data. O único lugar que a guarda é `key_data_ref_user` ("DD/MM/AAAA-nome",
--    a chave de upsert que o n8n já grava), preenchida só nas linhas de hoje.
--    Como `metricas_backup` tem os mesmos `id`, dá pra reconstruir a chave.
--    Sem duplicar: (data_referente, id_user) é único no backup (conferido).
update dash.metricas_sdrs s
   set key_data_ref_user = to_char(b.data_referente, 'DD/MM/YYYY') || '-' || lower(u.nome)
  from dash.metricas_backup b
  join dash.users u on u.id = b.id_user
 where b.id = s.id and s.key_data_ref_user is null;

update dash.metricas_closers c
   set key_data_ref_user = to_char(b.data_referente, 'DD/MM/YYYY') || '-' || lower(u.nome)
  from dash.metricas_backup b
  join dash.users u on u.id = b.id_user
 where b.id = c.id and c.key_data_ref_user is null;

update dash.metricas_dripify d
   set key_data_ref_user = to_char(b.data_referente, 'DD/MM/YYYY') || '-' || lower(u.nome)
  from dash.metricas_backup b
  join dash.users u on u.id = b.id_user
 where b.id = d.id and d.key_data_ref_user is null;

-- 3. A view que o BFF lê: formato longo (uma linha por dia × pessoa × métrica),
--    data extraída da chave, cargo vindo de `users.id_cargo`.
--
--    DONO ÚNICO POR MÉTRICA. As três tabelas receberam a MESMA linha do
--    backup (mesmos `id`), então somar as três dobraria `fups` e
--    `numeros_captados`. O corte é pela origem do dado:
--      · metricas_dripify  -> o que vem da automação do LinkedIn
--                             (conexões, abordagens, in mails, fups, números)
--      · metricas_sdrs     -> o que o SDR lança na mão (ligações agendadas,
--                             reuniões agendadas, indicações)
--      · metricas_closers  -> o que o closer lança na mão
--    Efeito colateral: as colunas `fups`/`numeros_captados` de metricas_sdrs
--    ficam fora da view (são cópia da mesma informação do Dripify).
--
--    O cargo de cada linha vem da pessoa, não da tabela: metricas_sdrs e
--    metricas_closers têm as 443 linhas de TODO mundo, inclusive de quem é do
--    outro cargo. O join com `metricas_cargo` descarta essas.
create or replace view dash.vw_metricas as
with sdr_manual as (
  select s.id_user,
         case when s.key_data_ref_user ~ '^\d{2}/\d{2}/\d{4}'
              then to_date(left(s.key_data_ref_user, 10), 'DD/MM/YYYY') end as data,
         s.ligacoes_agendadas, s.reunioes_agendadas, s.indicacoes
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
         d.conexoes_enviadas, d.conexoes_aceitas, d.abordagens, d.in_mails, d.fups, d.numeros_captados
    from dash.metricas_dripify d
)
select s.data, s.id_user, u.nome, c.cargo, null::text as conta, v.metrica, v.valor
  from sdr_manual s
  join dash.users u on u.id = s.id_user
  join dash.metricas_cargo c on c.id = u.id_cargo and c.cargo = 'sdr'
 cross join lateral (values
        ('ligacoes_agendadas', s.ligacoes_agendadas),
        ('reunioes_agendadas', s.reunioes_agendadas),
        ('indicacoes',         s.indicacoes)
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
        ('in_mails',          l.in_mails),
        ('fups',              l.fups),
        ('numeros_captados',  l.numeros_captados)
      ) as v(metrica, valor)
 where l.data is not null and v.valor is not null;

grant select on dash.vw_metricas to service_role;

-- 4. Uma métrica de indicação só (decisão: SDR e closer medem a mesma coisa,
--    o que muda é a meta de cada cargo). A linha `indicacoes_captadas` (4/dia)
--    não é apagada: vira a meta de `indicacoes` do SDR, e a de 10/dia fica
--    sendo a do closer. Apagar perderia a meta do SDR.
update dash.metricas_metas set metrica = 'indicacoes' where metrica = 'indicacoes_captadas';

-- 5. Vincular cada meta ao cargo. Sem linha em metas_cargo a meta não existe
--    para o BFF — não há mais fallback de "meta global". Metas de empresa
--    (faturamento, liquidado) vão para o cargo `empresa` (id 3).
--    Confira antes o que já existe: select * from dash.metas_cargo;
insert into dash.metas_cargo (id_meta, id_cargo)
select m.id, c.id
  from dash.metricas_metas m
  join dash.metricas_cargo c
    on c.cargo = case
         when m.metrica in ('conexoes_enviadas','conexoes_aceitas','abordagens',
                            'in_mails','fups','numeros_captados','ligacoes_agendadas') then 'sdr'
         when m.metrica in ('ligacoes_realizadas','reunioes_realizadas')                then 'closer'
         when m.metrica in ('faturamento','liquidado')                                  then 'empresa'
       end
 where not exists (select 1 from dash.metas_cargo mc
                    where mc.id_meta = m.id and mc.id_cargo = c.id);

-- reunioes_agendadas: uma linha só (4/dia), vale para os DOIS cargos.
insert into dash.metas_cargo (id_meta, id_cargo)
select m.id, c.id
  from dash.metricas_metas m
  cross join dash.metricas_cargo c
 where m.metrica = 'reunioes_agendadas'
   and c.cargo in ('sdr','closer')
   and not exists (select 1 from dash.metas_cargo mc
                    where mc.id_meta = m.id and mc.id_cargo = c.id);

-- indicacoes: DUAS linhas, uma por cargo — a de 4/dia (ex-`indicacoes_captadas`,
-- id 4) é do SDR, a de 10/dia (id 12) é do closer. Confira os ids antes:
--   select id, metrica, valor from dash.metricas_metas where metrica = 'indicacoes';
insert into dash.metas_cargo (id_meta, id_cargo)
select m.id, c.id
  from dash.metricas_metas m
  join dash.metricas_cargo c on c.cargo = case when m.valor <= 4 then 'sdr' else 'closer' end
 where m.metrica = 'indicacoes'
   and not exists (select 1 from dash.metas_cargo mc
                    where mc.id_meta = m.id and mc.id_cargo = c.id);

-- 6. Conferência: deve voltar setembro/2026 com os mesmos números do backup.
-- select metrica, sum(valor) from dash.vw_metricas
--  where data between '2026-09-01' and '2026-09-30' group by metrica order by metrica;
