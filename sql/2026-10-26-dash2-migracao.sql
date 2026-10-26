-- Migração do histórico do schema `dash` para `dash2` (B3.S1).
--
-- O que migra (mesmos ids em dash2):
--   · usuários (dash.users), exceto Nathan (id 9) e Jonathan (id 10)
--   · cargos: o de dash.users.id_cargo (sdr/closer) + dripify para quem tem
--     linha em dash.metricas_dripify
--   · métricas de SDR, Closer e Dripify até 30/09/2026
--   · faturamento (metricas_faturamento), clientes (cliente_faturamento) e sync_log
--
-- O que NÃO migra, e por quê:
--   · Nathan (id 9) foi removido. No faturamento, as referências a ele viram null.
--   · Jonathan (id 10) foi fundido no usuário 2 (mesma pessoa, cadastro duplicado).
--     Nas métricas e no faturamento, o id 10 vira 2.
--   · Outubro/2026 em diante vem das planilhas (scripts/popular_dash2.py).
--   · Métricas de seller não existiam em dash.
--   · A coluna `numeros_captados` do SDR foi descontinuada (não entra em dash2).
--   · Linhas sem data válida na key_data_ref_user ficam de fora.
--
-- Idempotente: todo insert usa on conflict do nothing, então pode rodar de novo.
-- Pré-requisito: sql/2026-10-26-dash2-schema.sql já aplicado.

-- 1. Usuários (sem Nathan=9; Jonathan=10 é fundido no 2)
insert into dash2.users (id, nome, email, imagem_url, active, role, criado_em, atualizado_em)
overriding system value
select id, nome, nullif(email, ''), imagem_url, coalesce(active, true), coalesce(role, 'member'),
       coalesce(criado_em, now()), coalesce(atualizado_em, now())
  from dash.users
 where id not in (9, 10)
on conflict (id) do nothing;
select setval(pg_get_serial_sequence('dash2.users', 'id'), (select max(id) from dash2.users));

-- 2. Cargos: o de dash.users.id_cargo + dripify pra quem tem linha em dash.metricas_dripify
insert into dash2.user_cargos (id_user, cargo)
select case when u.id = 10 then 2 else u.id end, c.cargo
  from dash.users u
  join dash.metricas_cargo c on c.id = u.id_cargo
 where u.id <> 9 and c.cargo in ('sdr', 'closer')
on conflict do nothing;

insert into dash2.user_cargos (id_user, cargo)
select distinct case when d.id_user = 10 then 2 else d.id_user end, 'dripify'
  from dash.metricas_dripify d
 where d.id_user is not null and d.id_user <> 9
on conflict do nothing;

-- 3. Métricas até 30/09/2026 (outubro vem das planilhas)
insert into dash2.metricas_sdrs (id_user, data, key_data_ref_user,
       ligacoes_realizadas, inscricoes_realizadas, indicacoes, reunioes_agendadas)
select u2.id, x.data, to_char(x.data, 'DD/MM/YYYY') || '-' || lower(u2.nome),
       s.ligacoes_realizadas, s.inscricoes_realizadas, s.indicacoes, s.reunioes_agendadas
  from dash.metricas_sdrs s
  join dash.users u on u.id = s.id_user and u.id_cargo = 2
  join dash2.users u2 on u2.id = case when s.id_user = 10 then 2 else s.id_user end
 cross join lateral (select case when s.key_data_ref_user ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}'
                                 then to_date(left(s.key_data_ref_user, 10), 'DD/MM/YYYY') end as data) x
 where x.data is not null and x.data < date '2026-10-01'
on conflict do nothing;

insert into dash2.metricas_closers (id_user, data, key_data_ref_user,
       ligacoes_agendadas, ligacoes_realizadas, reunioes_agendadas, reunioes_realizadas, indicacoes, inscricoes_realizadas)
select u2.id, x.data, to_char(x.data, 'DD/MM/YYYY') || '-' || lower(u2.nome),
       c.ligacoes_agendadas, c.ligacoes_realizadas, c.reunioes_agendadas, c.reunioes_realizadas,
       c.indicacoes, c.inscricoes_realizadas
  from dash.metricas_closers c
  join dash.users u on u.id = c.id_user and u.id_cargo = 1
  join dash2.users u2 on u2.id = case when c.id_user = 10 then 2 else c.id_user end
 cross join lateral (select case when c.key_data_ref_user ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}'
                                 then to_date(left(c.key_data_ref_user, 10), 'DD/MM/YYYY') end as data) x
 where x.data is not null and x.data < date '2026-10-01'
on conflict do nothing;

insert into dash2.metricas_dripify (id_user, data, key_data_ref_user,
       conexoes_enviadas, conexoes_aceitas, abordagens, in_mails, fups, numeros_captados)
select u2.id, x.data, to_char(x.data, 'DD/MM/YYYY') || '-' || lower(u2.nome),
       d.conexoes_enviadas, d.conexoes_aceitas, d.abordagens, d.in_mails, d.fups, d.numeros_captados
  from dash.metricas_dripify d
  join dash2.users u2 on u2.id = case when d.id_user = 10 then 2 else d.id_user end
 cross join lateral (select case when d.key_data_ref_user ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}'
                                 then to_date(left(d.key_data_ref_user, 10), 'DD/MM/YYYY') end as data) x
 where x.data is not null and x.data < date '2026-10-01'
on conflict do nothing;

-- 4. Faturamento, clientes e sync_log (cópia integral, mesmos ids)
insert into dash2.cliente_faturamento (id, criado_em, atualizado_em, nome, telefone)
overriding system value
select id, criado_em, atualizado_em, nome, telefone from dash.cliente_faturamento
on conflict (id) do nothing;

insert into dash2.metricas_faturamento (id, criado_em, atualizado_em, user_sdr, user_closer, metodo_pagamento,
       produto, canal, data_venda, valor_bruto_contrato, valor_entrada, condicao_pagamento, num_parcelas,
       imposto, taxa, liquido_entrada, id_cliente, key_id_cliente_data_venda, taxa_pgto_2, liquido_pgto_2,
       valor_pgto_2, forma_pgto_2)
overriding system value
select id, criado_em, atualizado_em,
       case when user_sdr = 9 then null when user_sdr = 10 then 2 else user_sdr end,
       case when user_closer = 9 then null when user_closer = 10 then 2 else user_closer end,
       metodo_pagamento, produto, canal, data_venda, valor_bruto_contrato, valor_entrada, condicao_pagamento,
       num_parcelas, imposto, taxa, liquido_entrada, id_cliente, key_id_cliente_data_venda, taxa_pgto_2,
       liquido_pgto_2, valor_pgto_2, forma_pgto_2
  from dash.metricas_faturamento
on conflict (id) do nothing;

insert into dash2.sync_log (id, rodou_em, linhas, status, erro)
overriding system value
select id, rodou_em, linhas, status, erro from dash.sync_log
on conflict (id) do nothing;

select setval(pg_get_serial_sequence('dash2.cliente_faturamento', 'id'), (select coalesce(max(id), 1) from dash2.cliente_faturamento));
select setval(pg_get_serial_sequence('dash2.metricas_faturamento', 'id'), (select coalesce(max(id), 1) from dash2.metricas_faturamento));
select setval(pg_get_serial_sequence('dash2.sync_log', 'id'), (select coalesce(max(id), 1) from dash2.sync_log));

notify pgrst, 'reload schema';
