# ak_dash — BFF do Dashboard Akeel

FastAPI. Contrato de resposta em `../docs/contract/` (openapi.yaml, types.ts, fixtures/).

## Escopo desta versão

Domínios **comercial** (`/comercial/sdr`, `/comercial/closer`), **geral**
(`/geral`) e `/pessoas`. Fonte única de dado: Supabase — `dash.vw_metricas`
(métricas diárias, formato longo), `dash.metricas_metas` + `dash.metas_cargo`
(meta diária por métrica e os cargos em que ela vale — todo SDR compartilha a
mesma meta, todo Closer compartilha outra, via `dash.metricas_cargo`),
`dash.metricas_faturamento` (faturamento — ainda sem as colunas de negócio,
ver abaixo) e `dash.users`. A integração com Google Drive/Sheets foi removida
(ver `../docs/plans/migracao-banco-pagina-geral.md`). Financeiro detalhado e
imersão ficam pendentes.

## Rodando local

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # preencher com as credenciais do Supabase
uvicorn app.main:app --reload
```

Sem `SUPABASE_URL`/`SUPABASE_SERVICE_KEY`, toda consulta ao Supabase degrada
pra lista vazia — os endpoints respondem, só que sem pessoa/métrica nenhuma.
**Sem `SUPABASE_JWT_SECRET`, todo endpoint autenticado devolve 401** — é o
único pré-requisito real para testar localmente; gere um JWT HS256 com
`aud: "authenticated"` assinado com o mesmo segredo pra simular um usuário
logado.

`SUPABASE_INSCRICOES_*` é o segundo Supabase (schema `SED`), de onde vêm os
cards de Inscritos/Aprovados: `SED.events` (próximos 3 eventos, por
`event_date`) + `SED.registrations` (inscrições `pending`/`approved` de cada
um). Em branco, ou sem `grant usage on schema "SED"` pro `service_role`,
`/geral` devolve `eventos: []` e os cards mostram "Sem eventos futuros" —
nunca erro.

## Testes

```bash
pytest
```

Tudo contra lógica pura (cálculo, agregação, pontuação) com `query()`
monkeypatchado — sem chamada de rede — mais um smoke test de integração
(`tests/test_rotas.py`, sobe o app de verdade com `TestClient`) e um guarda
de conformidade com `docs/contract/openapi.yaml` (`tests/test_contrato.py`).

## Estrutura

```
app/
  main.py              FastAPI, CORS, handler de erro no formato do contrato
  config.py            env vars
  cache.py             cache em memória com TTL
  auth.py              validação do JWT do Supabase
  periodo.py           período (dia/semana/mes/ano) em America/Sao_Paulo, dias úteis decorridos
  metricas.py           vocabulário de métricas (nome da coluna de origem, igual dos dois lados)
  metas.py             leitura de dash.metricas_metas + dash.metas_cargo — meta DIÁRIA por
                        (mês, cargo, métrica), multiplicada pelos dias úteis do período pedido
  cargos.py             leitura de dash.metricas_cargo — id_cargo <-> nome ("sdr"/"closer"/"empresa")
  pontuacao.py          fórmula de pontuação + ranking, compartilhada por comercial e geral
  fontes/
    banco.py             cliente PostgREST (Supabase) — paginação embutida
  dominios/
    comercial/           leitura de vw_metricas, cálculo, rotas
    geral/                faturamento, eventos (SED), cálculo, rotas (o realizado vem do
                          mesmo buscar_totais/vw_metricas do comercial)
    pessoas/              leitura de dash.users, rota
```

## `dash.metricas_faturamento` ainda não tem as colunas de negócio

Hoje a tabela só tem `id`/`created_at`. O formato combinado é uma coluna por
métrica: `id_user, periodo, faturamento, liquidado, inscritos, aprovados`
(`id_user IS NULL` = linha da empresa inteira). Até a tabela ganhar essas
colunas, `dominios/geral/banco.py` sempre devolve `None` pra elas — os 4
cards escuros da Geral e as colunas Liquidado/Aprovados da tabela de pessoas
ficam em "—", sem erro.

## `dash.vw_metricas` é uma view sobre as três tabelas de origem

Definição em `sql/2026-09-15-view-metricas.sql`. Ela lê
`metricas_sdrs`/`metricas_closers`/`metricas_dripify` em tempo real e devolve
formato longo (`data, id_user, nome, cargo, conta, metrica, valor`):

- **data**: extraída de `key_data_ref_user` ("DD/MM/AAAA-nome", a chave de
  upsert do n8n). Linha sem chave válida fica de fora — nunca é lida como se
  fosse de hoje.
- **cargo**: de `users.id_cargo`. As três tabelas receberam as mesmas 443
  linhas herdadas de `metricas_backup`, inclusive de quem é do outro cargo;
  o join com `metricas_cargo` descarta essas.
- **dono único por métrica**: como a mesma linha existe nas três tabelas,
  somar as três dobraria `fups`/`numeros_captados`. O corte é pela origem —
  Dripify traz o que vem da automação do LinkedIn (conexões, abordagens,
  in mails, fups, números captados); `metricas_sdrs`/`metricas_closers`
  trazem o que é lançado na mão.

## `reunioes_agendadas` e `indicacoes` são métricas dos DOIS cargos

SDR e Closer agendam reunião e trabalham indicação — com metas próprias, já
que o vínculo meta↔cargo é N:N (`dash.metas_cargo`). Por isso as duas estão
em `METRICAS_SDR` e em `METRICAS_CLOSER`, e o card da empresa soma os dois
cargos: a meta tem que refletir as 7 pessoas, não só um cargo.

## Pódio da Geral: nem toda coluna da tabela pontua

`liquidado` e `aprovados` continuam como colunas do Closer na tabela, mas
ficam fora da pontuação (`_METRICAS_PONTUACAO` em `dominios/geral/calculo.py`)
enquanto `dash.metricas_faturamento` não tiver as colunas de negócio: elas
voltam `None` pra todo closer, e uma métrica sem realizado zera a pontuação
inteira — era o que deixava o pódio de Closer vazio com o de SDR aparecendo.
Quando a tabela existir, devolva as duas ao conjunto.

## Metas: valor DIÁRIO por pessoa, multiplicado por dias úteis

`dash.metricas_metas.valor` é a meta de **um dia útil de uma pessoa** do cargo (ex: 4
números captados/dia por SDR). A meta do período é `valor × dias úteis`
(`metas.py::dias_uteis_do_mes_no_periodo`): dia = a diária, semana = 5×, mês
de 22 dias úteis = 22×, ano = soma dos meses cadastrados. Cadastre a diária;
dia, semana, mês e ano saem sozinhos.

`metrica` usa os nomes das colunas de origem (`numeros_captados`, `fups`,
`in_mails`, `reunioes_agendadas`…) — os mesmos que a view emite e que saem no
payload, sem tradução em lugar nenhum.

**A quais cargos a meta vale está em `dash.metas_cargo`** (`id_meta` ×
`id_cargo`, N:N): a mesma métrica pode ter uma meta pra SDR e outra pra
closer, e uma linha só pode valer pros dois. Meta sem vínculo ali não vale
pra ninguém — não existe fallback de meta global. Faturamento e liquidado
vão no cargo `empresa` (id 3).

**Meta dos cards da empresa não tem linha própria**: é a meta do cargo ×
pessoas ativas daquele cargo, somada sobre os cargos que compõem o card
(`_COMPOSICAO_CARDS_CLAROS` em `dominios/geral/calculo.py`). Reuniões
agendadas e indicações somam SDR + Closer; números captados e ligações
agendadas são só de SDR. Entrar ou sair gente ajusta o número sozinho. Falta
meta em qualquer parte do card ⇒ `null`, nunca meta parcial.

## Pendências (bloqueiam parte da UI, não o serviço)

1. **Vincular as metas aos cargos em `dash.metas_cargo`** (e dar
   `grant select` nela pro `service_role`) — meta sem vínculo é meta que não
   existe pro BFF, e sem meta não há barra de progresso, `%` do ritmo,
   pontuação nem ranking em nenhum endpoint. O resto funciona.
2. **Rodar `sql/2026-09-15-view-metricas.sql`** — recria `dash.vw_metricas`
   e devolve a data às 443 linhas herdadas. Sem isso, toda métrica de
   atividade sai zerada.
3. **Consertar o n8n do Dripify** — `dash.sync_log` acumula
   `status: "invalido"` com erro de sintaxe SQL no INSERT de
   `dash.metricas_dripify` (vírgula sobrando antes do `)` na lista de
   VALUES), então nenhuma linha nova de LinkedIn entra desde 15/09/2026.
4. **Definir e popular `metricas_faturamento`** com as colunas acima.
5. **Cadastrar eventos com `event_date` no futuro** em `SED.events` — sem
   nenhum, os cards de Inscritos/Aprovados ficam no estado vazio (evento
   sem data nunca entra na rotação).
