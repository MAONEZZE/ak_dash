-- Financeiro lendo as abas NFS da planilha nova (docs/plans/financeiro-nfs.md, B0.S1).
--
-- notas_financeiro: uma linha por linha das abas "NFS <mês>". chave = "AAAA-MM:<nº da linha na aba>".
--   mes = dia 1 do mês da aba (receita líquida = valor_pago cai aqui).
--   data_referencia = data_venda válida, senão dia 1 do mês da aba (faturamento e nº de vendas caem aqui).
-- Gravada pelo WorkerFinanceiro (mês corrente + anterior) e por scripts/carga_financeiro.py (todas as abas).
--
-- Idempotente. Rodar: .venv/bin/python -m scripts.rodar_sql sql/2026-11-27-notas-financeiro.sql

create table if not exists dash_new.notas_financeiro (
  chave text primary key,
  mes date not null,
  linha integer not null,
  cliente text,
  categoria text,
  produto text,
  valor_pago double precision,
  valor_venda double precision,
  data_venda date,
  data_referencia date not null,
  forma_pagamento text not null,
  canal text,
  vendedor text,
  id_vendedor bigint,
  status text,
  atualizado_em timestamptz not null default now()
);

create index if not exists notas_financeiro_mes_idx on dash_new.notas_financeiro (mes);
create index if not exists notas_financeiro_data_referencia_idx on dash_new.notas_financeiro (data_referencia);

grant select, insert, update, delete on dash_new.notas_financeiro to service_role;
