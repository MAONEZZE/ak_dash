## Contrato de gravação (dash2)

Esta seção descreve como os fluxos n8n devem gravar no schema `dash2`.

> **Atenção:** o n8n precisa ser trocado para gravar em `dash2`. Enquanto ele gravar em `dash`, o dash fica congelado em silêncio (os dados novos não aparecem e nenhum erro é exibido).

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

### (e) Aviso de migração

O n8n precisa ser trocado para gravar em `dash2`. Enquanto gravar em `dash`, o dash fica congelado em silêncio.

### (f) Configuração

- Env `SUPABASE_SCHEMA`: padrão `dash2`.
- Para rollback, definir `SUPABASE_SCHEMA=dash`.
