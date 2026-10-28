## Contrato de gravação (dash2)

Esta seção descreve como os fluxos n8n devem gravar no schema `dash2`.

As tabelas de métricas e `dash2.metas` são gravadas pelos workers das planilhas (`app/workers.py`), dentro do BFF, a cada `WORKER_INTERVALO_SEGUNDOS`. Os fluxos n8n de métricas devem ser desligados; o n8n continua gravando só o faturamento (d).

### (a) Tabelas de métricas

Uma linha por tabela de métrica. As colunas de métrica são exatamente as listadas abaixo.

| Tabela | Aba de origem (planilha) | Colunas de métrica |
|---|---|---|
| `metricas_sellers` | Sellers | `fups`, `numeros_captados`, `indicacoes` |
| `metricas_sdrs` | SDRs | `ligacoes_efetuadas`, `ligacoes_realizadas`, `inscricoes_realizadas`, `indicacoes`, `reunioes_agendadas` |
| `metricas_closers` | Closers | `ligacoes_agendadas`, `ligacoes_realizadas`, `reunioes_agendadas`, `reunioes_realizadas`, `indicacoes`, `inscricoes_realizadas` |
| `metricas_dripify` | Dripify | `conexoes_enviadas`, `conexoes_aceitas`, `abordagens`, `in_mails`, `fups`, `numeros_captados` |

### (b) Regra da chave

- `key_data_ref_user = DD/MM/AAAA-lower(dash2.users.nome)`
- Upsert com `on_conflict=key_data_ref_user`.
- `data` é obrigatória e deve ser o mesmo dia da chave.
- `id_user` é obrigatório.

### (c) Metas

- Tabela: `dash2.metas`.
- Upsert com `on_conflict=id_user,cargo,metrica`.
- `valor_diario` recebe a linha "Meta diária" da aba.
- O par `(id_user, cargo)` precisa existir antes em `dash2.user_cargos`.

### (d) Faturamento

As mesmas colunas de antes, agora gravadas em `dash2.metricas_faturamento` e `dash2.cliente_faturamento`.

### (f) Configuração

- Env `SUPABASE_SCHEMA`: padrão `dash2`.
- Para rollback, definir `SUPABASE_SCHEMA=dash`.

### (g) Workers das planilhas

Envs (ver `.env.example`):

- `WORKERS_ATIVOS` (padrão `false`): só com `true` os workers sobem.
- `WORKER_INTERVALO_SEGUNDOS` (padrão `5`).
- `GOOGLE_SERVICE_ACCOUNT_JSON`: JSON da service account. Ela (`client_email`) precisa ser compartilhada como leitora em cada planilha.
- `PLANILHA_SELLERS_ID`, `PLANILHA_SDRS_ID`, `PLANILHA_CLOSERS_ID`, `PLANILHA_DRIPIFY_ID`: worker sem ID de planilha não sobe.

Comportamento:

- Gravam só o que mudou, no mês corrente (America/Sao_Paulo).
- Célula apagada → `null`. Meta apagada → linha removida de `dash2.metas`.
- Aba de quem não está em `users` ou não tem o cargo é pulada (log).
- Na virada do mês, a planilha precisa ser zerada no dia 1.
- O `/saude` mostra `ultima_leitura_ok` e `ultimo_erro` por worker.
- A carga manual agora roda com `.venv/bin/python -m scripts.popular_dash2 --mes AAAA-MM`.
