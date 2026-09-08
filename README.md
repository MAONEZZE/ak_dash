# ak_dash — BFF do Dashboard Akeel

FastAPI. Contrato de resposta em `../docs/contract/` (openapi.yaml, types.ts, fixtures/).

## Escopo desta versão

Só o domínio **comercial** (`/comercial/sdr`, `/comercial/closer`) + `/pessoas`,
conforme os passos 1-4 de "Ordem de execução" em
`../docs/plans/dashboard-akeel.md`. Financeiro e imersão ficam para quando o
CSV de cada um chegar.

## Rodando local

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # preencher quando as credenciais chegarem
uvicorn app.main:app --reload
```

Sem `GOOGLE_SERVICE_ACCOUNT_JSON`/`DRIVE_PASTA_ID` configurados, `/comercial/*`
devolve `pessoas: []` (sem planilha carregada) em vez de quebrar. Sem
`SUPABASE_URL`/`SUPABASE_SERVICE_KEY`, `/pessoas` e o histórico comercial
degradam da mesma forma. **Sem `SUPABASE_JWT_SECRET`, todo endpoint autenticado
devolve 401** — é o único pré-requisito real para testar localmente; gere um
JWT HS256 com `aud: "authenticated"` assinado com o mesmo segredo para simular
um usuário logado.

## Testes

```bash
pytest
```

27 testes, todos contra lógica pura (parser, cálculo, união de períodos) —
sem mock de rota, sem mock da API do Google, conforme o plano manda. Inclui
`tests/test_contrato.py`, que roda o pipeline real contra os 3 CSVs de
`../dados_template/` e confere campo-a-campo com as fixtures em
`../docs/contract/fixtures/`.

## Estrutura

```
app/
  main.py              FastAPI, CORS, handler de erro no formato do contrato
  config.py            env vars
  cache.py             cache em memória com TTL
  auth.py              validação do JWT do Supabase
  periodo.py            mês corrente em America/Sao_Paulo, dias úteis decorridos
  fontes/              clientes crus: Drive, Sheets, Supabase (REST)
  dominios/
    comercial/          parser da planilha, histórico do banco, cálculo, rotas
    pessoas/            leitura da tabela `pessoas`, rota
```

## Schema do Supabase assumido (não confirmado)

`dominios/comercial/banco.py` assume uma tabela `metricas_comerciais_mensais`
(email, funcao, metrica, ano, mes, meta_periodo, realizado, dias_com_lacuna,
dias_considerados) para o histórico comercial — **schema real ainda pendente**
("aguardando você" no plano). Ajustar os nomes de coluna quando o processo de
fechamento de mês definir a tabela de verdade; a lógica de união em
`calculo.py` não muda.

## Divergência deliberada do contrato

O JSON de exemplo em `docs/contract/fixtures/comercial_sdr.example.json` fixa
`periodo_parcial: false` para abril/2026 "para ter um número determinístico"
(ver o README do contrato). O BFF real, com abril/2026 como mês corrente,
calcula `periodo_parcial: true` — que é o comportamento certo pela própria
regra do contrato ("true quando o período inclui o mês corrente"). Ver
docstring de `tests/test_contrato.py`.
