-- Cópia dos dados do schema dash2 para dash_new (B1.S3).
--
-- O que copia (mesmos ids em dash_new):
--   · usuários (dash2.users), todos; depois a Duda (id 4) recebe o nome 'Duda'
--   · user_cargos e metas só de seller, sdr e closer
--   · métricas de seller, SDR e closer (metricas_sellers, metricas_sdrs, metricas_closers)
--   · faturamento (cliente_faturamento, metricas_faturamento, recebimentos_faturamento)
--   · logs_pipedrive
--
-- O que NÃO copia, e por quê:
--   · Dripify: metricas_dripify e o cargo 'dripify' não existem em dash_new (o funil
--     de LinkedIn/Instagram entra em contas_funil / metricas_contas).
--   · cargos: dash_new já tem a própria tabela de cargos, semeada pelo schema.
--   · sync_log: não existe em dash_new.
--
-- Idempotente: todo insert usa on conflict do nothing, então pode rodar de novo.
-- Pré-requisito: sql/2026-11-13-dash-new-schema.sql (B1.S2) já aplicado.
-- Rodar: .venv/bin/python -m scripts.rodar_sql sql/2026-11-13-dash-new-copia.sql

-- 1. Usuários (todos) e ajuste de nome da Duda
insert into dash_new.users (id, nome, email, imagem_url, active, role, criado_em, atualizado_em)
overriding system value
select id, nome, email, imagem_url, active, role, criado_em, atualizado_em
  from dash2.users
on conflict do nothing;

update dash_new.users set nome = 'Duda' where id = 4;

-- 2. Cargos e metas só de seller, sdr e closer
insert into dash_new.user_cargos (id_user, cargo, criado_em)
select id_user, cargo, criado_em
  from dash2.user_cargos
 where cargo in ('seller', 'sdr', 'closer')
on conflict do nothing;

insert into dash_new.metas (id, id_user, cargo, metrica, valor_diario, criado_em, atualizado_em)
overriding system value
select id, id_user, cargo, metrica, valor_diario, criado_em, atualizado_em
  from dash2.metas
 where cargo in ('seller', 'sdr', 'closer')
on conflict do nothing;

-- 3. Métricas de seller, SDR e closer
insert into dash_new.metricas_sellers (id, id_user, data, key_data_ref_user, fups, numeros_captados,
       indicacoes, criado_em, atualizado_em)
overriding system value
select id, id_user, data, key_data_ref_user, fups, numeros_captados,
       indicacoes, criado_em, atualizado_em
  from dash2.metricas_sellers
on conflict do nothing;

insert into dash_new.metricas_sdrs (id, id_user, data, key_data_ref_user, ligacoes_efetuadas,
       ligacoes_realizadas, inscricoes_realizadas, indicacoes, reunioes_agendadas, criado_em, atualizado_em)
overriding system value
select id, id_user, data, key_data_ref_user, ligacoes_efetuadas,
       ligacoes_realizadas, inscricoes_realizadas, indicacoes, reunioes_agendadas, criado_em, atualizado_em
  from dash2.metricas_sdrs
on conflict do nothing;

insert into dash_new.metricas_closers (id, id_user, data, key_data_ref_user, ligacoes_agendadas,
       ligacoes_realizadas, reunioes_agendadas, reunioes_realizadas, indicacoes, inscricoes_realizadas,
       criado_em, atualizado_em)
overriding system value
select id, id_user, data, key_data_ref_user, ligacoes_agendadas,
       ligacoes_realizadas, reunioes_agendadas, reunioes_realizadas, indicacoes, inscricoes_realizadas,
       criado_em, atualizado_em
  from dash2.metricas_closers
on conflict do nothing;

-- 4. Faturamento e logs do Pipedrive
insert into dash_new.cliente_faturamento (id, criado_em, atualizado_em, nome, telefone)
overriding system value
select id, criado_em, atualizado_em, nome, telefone
  from dash2.cliente_faturamento
on conflict do nothing;

insert into dash_new.metricas_faturamento (id, criado_em, atualizado_em, user_sdr, user_closer, metodo_pagamento,
       produto, canal, data_venda, valor_bruto_contrato, valor_entrada, condicao_pagamento, num_parcelas,
       imposto, taxa, liquido_entrada, id_cliente, key_id_cliente_data_venda, taxa_pgto_2, liquido_pgto_2,
       valor_pgto_2, forma_pgto_2, id_planilha, num_parcelas_pgto_2, observacoes)
overriding system value
select id, criado_em, atualizado_em, user_sdr, user_closer, metodo_pagamento,
       produto, canal, data_venda, valor_bruto_contrato, valor_entrada, condicao_pagamento, num_parcelas,
       imposto, taxa, liquido_entrada, id_cliente, key_id_cliente_data_venda, taxa_pgto_2, liquido_pgto_2,
       valor_pgto_2, forma_pgto_2, id_planilha, num_parcelas_pgto_2, observacoes
  from dash2.metricas_faturamento
on conflict do nothing;

insert into dash_new.recebimentos_faturamento (id, criado_em, atualizado_em, id_planilha_venda, mes, pago, liquido)
overriding system value
select id, criado_em, atualizado_em, id_planilha_venda, mes, pago, liquido
  from dash2.recebimentos_faturamento
on conflict do nothing;

insert into dash_new.logs_pipedrive (id, criado_em, atualizado_em, chave, ocorrencias, data, hora, usuario_acao,
       id_user, atividade, acao_evento, cliente_nome, telefone, telefone_digitos, quem_indicou,
       prospectado_por, linkedin, instagram, url_negocio)
overriding system value
select id, criado_em, atualizado_em, chave, ocorrencias, data, hora, usuario_acao,
       id_user, atividade, acao_evento, cliente_nome, telefone, telefone_digitos, quem_indicou,
       prospectado_por, linkedin, instagram, url_negocio
  from dash2.logs_pipedrive
on conflict do nothing;

-- 5. Sequências das tabelas com identity copiada: próximo id volta a sair do maior id copiado
select setval(pg_get_serial_sequence('dash_new.users', 'id'), coalesce((select max(id) from dash_new.users), 1));
select setval(pg_get_serial_sequence('dash_new.metas', 'id'), coalesce((select max(id) from dash_new.metas), 1));
select setval(pg_get_serial_sequence('dash_new.metricas_sellers', 'id'), coalesce((select max(id) from dash_new.metricas_sellers), 1));
select setval(pg_get_serial_sequence('dash_new.metricas_sdrs', 'id'), coalesce((select max(id) from dash_new.metricas_sdrs), 1));
select setval(pg_get_serial_sequence('dash_new.metricas_closers', 'id'), coalesce((select max(id) from dash_new.metricas_closers), 1));
select setval(pg_get_serial_sequence('dash_new.cliente_faturamento', 'id'), coalesce((select max(id) from dash_new.cliente_faturamento), 1));
select setval(pg_get_serial_sequence('dash_new.metricas_faturamento', 'id'), coalesce((select max(id) from dash_new.metricas_faturamento), 1));
select setval(pg_get_serial_sequence('dash_new.recebimentos_faturamento', 'id'), coalesce((select max(id) from dash_new.recebimentos_faturamento), 1));
select setval(pg_get_serial_sequence('dash_new.logs_pipedrive', 'id'), coalesce((select max(id) from dash_new.logs_pipedrive), 1));

notify pgrst, 'reload schema';
