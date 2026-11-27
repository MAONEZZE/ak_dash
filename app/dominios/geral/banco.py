"""Leitura de `dash.notas_financeiro` — uma linha por nota do calendário
financeiro da planilha.

`buscar_faturamento` soma `valor_venda` das notas cuja `data_referencia` cai
dentro do período pedido (de `inicio` a `fim`, inclusive, comparando datas ISO).

O liquidado da empresa NÃO vem da venda: é a soma de `valor_pago` das notas
cujo `mes` (dia 1 do mês) cai entre o dia 1 do mês de `inicio` e `fim`. Assim o
líquido cai no mês em que a parcela foi recebida, não no mês em que a venda foi
fechada.

O card da empresa soma TODA nota do período, inclusive de quem já saiu do
time (`ids_pessoas` não filtra a consulta). Por pessoa, o liquidado é o
`valor_pago` das notas com `id_vendedor`; nota sem vendedor entra no total da
empresa e em ninguém.
`inscritos`/`aprovados` continuam sempre `None`
aqui — não existem nesta tabela, vêm do SED (ver `buscar_confrarias_do_mes`).

Também lê o SEGUNDO Supabase (`SED.events`/`SED.registrations`, via
`app.fontes.sed`), que
alimenta a tabela de Confrarias da Geral — ver `buscar_confrarias_do_mes` —
e `logs_pipedrive`, o espelho da planilha de logs — ver `buscar_logs`.

As métricas de atividade (números captados, ligações, reuniões, indicações)
NÃO passam por aqui: a Geral lê as mesmas `buscar_totais`/`dash.vw_metricas`
que o Comercial.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.periodo import TZ_SP
from app.fontes import sed
from app.fontes import supabase

CHAVES_FATURAMENTO = ("faturamento", "liquidado", "inscritos", "aprovados")

# Teto de Confrarias do mês na Geral. A tabela mostra 9 linhas e rola o resto
# (2026-11-02); o teto só evita mandar uma lista sem fim.
LIMITE_EVENTOS = 50

# A Geral só mostra as Confrarias (decisão do usuário, 2026-10-05). Título
# "contém", sem diferenciar maiúsculas: o `ilike` é montado em `app.fontes.sed`.
TITULO_EVENTOS = "confraria akeel"

# Funil Evento: só Imersões ("imers" pega Imersão e Imersao).
TITULO_IMERSOES = "imers"

# "Inscrito" = TODA linha de `SED.registrations` do evento, seja qual for o
# status — o card mede captação (quanta gente se inscreveu), não ocupação de
# vaga. Por isso não há filtro de status na consulta.
#
# Era `("pending", "approved")`, que excluía os recusados: a Imersão Alta
# Cadência tinha 70 inscrições no banco e o card mostrava 65, porque 5 eram
# `rejected`. Decisão de produto em 17/09/2026: o número da tela tem que ser o
# mesmo que se conta no banco.
#
# Consequência a vigiar: status novo que signifique desistência (`cancelled`,
# por exemplo) passaria a contar como inscrito. Hoje só existem `pending`,
# `approved` e `rejected`. `aprovados` segue contando só `approved`.


@dataclass(frozen=True)
class Faturamento:
    empresa: dict[str, float | None]
    por_pessoa: dict[int, dict[str, float | None]]


def _linha_vazia() -> dict[str, float | None]:
    return {chave: None for chave in CHAVES_FATURAMENTO}


def buscar_faturamento(inicio: date, fim: date, ids_pessoas: list[int]) -> Faturamento:
    notas = supabase.ler_notas_financeiro_do_periodo(inicio, fim)

    ini, f = inicio.isoformat(), fim.isoformat()
    mes_ini = inicio.replace(day=1).isoformat()
    empresa: dict[str, float | None] = {**_linha_vazia(), "faturamento": 0.0, "liquidado": 0.0}
    por_pessoa: dict[int, dict[str, float | None]] = {}

    for n in notas:
        if ini <= n["data_referencia"][:10] <= f:
            empresa["faturamento"] += n.get("valor_venda") or 0
        if mes_ini <= n["mes"][:10] <= f:
            pago = n.get("valor_pago") or 0
            empresa["liquidado"] += pago
            if n.get("id_vendedor") is not None:
                pessoa = por_pessoa.setdefault(int(n["id_vendedor"]), {**_linha_vazia(), "liquidado": 0.0})
                pessoa["liquidado"] += pago

    return Faturamento(empresa=empresa, por_pessoa=por_pessoa)


@dataclass(frozen=True)
class EventoInscricoes:
    """Um evento de `SED.events` + as contagens de `SED.registrations` dele.

    `inscritos` conta TODAS as inscrições do evento, qualquer status;
    `aprovados`, só os `approved`; `pendentes`, só os `pending`;
    `rejeitados`, só os `rejected` — os três são subconjuntos de `inscritos`.
    `capacidade` é `None` quando o evento não tem limite cadastrado.
    """

    id: str
    titulo: str
    data: str  # `event_date` cru (ISO 8601 sem fuso), formatado no frontend
    capacidade: int | None
    inscritos: int
    aprovados: int
    pendentes: int = 0
    rejeitados: int = 0


def buscar_confrarias_do_mes(inicio: date, fim: date) -> list[EventoInscricoes]:
    """Confrarias ("confraria akeel" no título) de `inicio` a `fim` (o mês
    corrente inteiro, inclusive as que já passaram) do segundo Supabase
    (`SED.events`), por data crescente, com a contagem de inscrições de cada
    uma — no máximo `LIMITE_EVENTOS`.

    Os limites são meia-noite de São Paulo; o formato que o PostgREST recebe
    fica em `app.fontes.sed`. Sem as envs `SUPABASE_INSCRICOES_*`, a lista sai
    `[]` — nunca derruba /geral.
    """
    eventos = sed.ler_eventos_entre(
        datetime.combine(inicio, time.min, tzinfo=TZ_SP),
        datetime.combine(fim + timedelta(days=1), time.min, tzinfo=TZ_SP),
        TITULO_EVENTOS,
        LIMITE_EVENTOS,
    )[:LIMITE_EVENTOS]
    return _com_inscricoes(eventos)


def buscar_proximo_evento(agora: datetime) -> EventoInscricoes | None:
    """O evento (qualquer título, não só Confraria) com `event_date` a partir de
    `agora` mais próximo, com as inscrições dele — padrão do velocímetro do
    Funil SDR. `None` quando não há nenhum agendado (ou sem as envs do SED)."""
    eventos = _com_inscricoes(sed.ler_eventos_a_partir_de(agora, 1)[:1])
    return eventos[0] if eventos else None


def buscar_proxima_imersao(agora: datetime) -> EventoInscricoes | None:
    """A Imersão com `event_date` a partir de `agora` mais próxima, com as inscrições — padrão do
    Funil Evento sem evento escolhido. `None` quando não há nenhuma agendada."""
    eventos = _com_inscricoes(sed.ler_eventos_a_partir_de(agora, 1, titulo_contem=TITULO_IMERSOES)[:1])
    return eventos[0] if eventos else None


def listar_proximos_eventos(agora: datetime, limite: int = LIMITE_EVENTOS) -> list[dict]:
    """Opções do filtro de evento do Funil SDR: todos os eventos a partir de
    `agora` (qualquer título), do mais próximo ao mais distante, só
    id/título/data — sem contar inscrições, que só o escolhido precisa."""
    eventos = sed.ler_eventos_a_partir_de(agora, limite, colunas="id,title,event_date")[:limite]
    return [{"id": str(e["id"]), "titulo": e.get("title") or "Sem título", "data": e["event_date"]} for e in eventos]


def listar_imersoes(limite: int = LIMITE_EVENTOS) -> list[dict]:
    """Opções do filtro de evento do Funil Evento: Imersões com data, passadas e futuras, da mais
    recente/futura para a mais antiga — só id/título/data."""
    eventos = sed.ler_imersoes(TITULO_IMERSOES, limite)[:limite]
    return [{"id": str(e["id"]), "titulo": e.get("title") or "Sem título", "data": e["event_date"]} for e in eventos]


def buscar_evento(id_evento: str) -> EventoInscricoes | None:
    """Um evento pelo id (qualquer título), com as inscrições — o escolhido no
    filtro de evento. Quem chama valida o id antes: ele vai dentro do filtro do PostgREST."""
    eventos = _com_inscricoes(sed.ler_evento_por_id(id_evento)[:1])
    return eventos[0] if eventos else None


def contar_inscritos_no_periodo(id_evento: str, inicio: date, fim: date) -> int:
    """Inscrições `approved`/`pending` do evento feitas (`created_at`) de
    `inicio` a `fim`, dias de São Paulo — velocímetro do Funil SDR, que segue o
    filtro de data. Quem chama valida o id: ele vai dentro do filtro do PostgREST."""
    return len(
        sed.ler_inscricoes_no_periodo(
            id_evento,
            datetime.combine(inicio, time.min, tzinfo=TZ_SP),
            datetime.combine(fim + timedelta(days=1), time.min, tzinfo=TZ_SP),
        )
    )


def contar_comparecimento(id_evento: str) -> int:
    """Check-ins do evento (`attended = true`), qualquer status — etapa Comparecimento do Funil Evento.
    Sem horário de check-in no SED, então não segue o filtro de data. Quem chama valida o id."""
    return len(sed.ler_comparecimentos(id_evento))


def _com_inscricoes(eventos: list[dict]) -> list[EventoInscricoes]:
    if not eventos:
        return []
    inscricoes = sed.ler_inscricoes_dos_eventos([str(e["id"]) for e in eventos])

    inscritos = Counter(r.get("event_id") for r in inscricoes)
    aprovados = Counter(r.get("event_id") for r in inscricoes if r.get("status") == "approved")
    pendentes = Counter(r.get("event_id") for r in inscricoes if r.get("status") == "pending")
    rejeitados = Counter(r.get("event_id") for r in inscricoes if r.get("status") == "rejected")

    return [
        EventoInscricoes(
            id=str(e["id"]),
            titulo=e.get("title") or "Sem título",
            data=e["event_date"],
            capacidade=e.get("capacity"),
            inscritos=inscritos[e["id"]],
            aprovados=aprovados[e["id"]],
            pendentes=pendentes[e["id"]],
            rejeitados=rejeitados[e["id"]],
        )
        for e in eventos
    ]


# Teto de logs do card Logs da Geral — a tabela mostra 9 linhas e rola o resto.
LIMITE_LOGS = 50


@dataclass(frozen=True)
class LogAtividade:
    data: str
    hora: str | None
    usuario: str | None
    atividade: str
    cliente: str | None


def buscar_logs(inicio: date, fim: date) -> list[LogAtividade]:
    """Os `LIMITE_LOGS` logs mais recentes de `inicio` a `fim` em
    `logs_pipedrive` (espelho da aba Logs da planilha `PLANILHA_LOGS_ID`,
    mantido pelo WorkerLogs), do mais novo pro mais antigo.
    """
    linhas = supabase.ler_logs_do_periodo(inicio, fim)
    linhas.sort(key=lambda r: (str(r.get("data") or ""), str(r.get("hora") or "")), reverse=True)
    return [
        LogAtividade(
            data=str(r["data"]),
            hora=r.get("hora"),
            usuario=r.get("usuario_acao"),
            atividade=r["atividade"],
            cliente=r.get("cliente_nome"),
        )
        for r in linhas[:LIMITE_LOGS]
    ]
