"""Leitura de `dash.metricas_faturamento` — combinado como uma coluna por

métrica (`id_user, periodo, faturamento, liquidado, inscritos, aprovados`),
mas a tabela hoje só tem `id` e `created_at` (sem essas colunas, sem linha
nenhuma). Isolado nesta função só: quando as colunas existirem, só este
módulo muda. Até lá, `.get()` (nunca indexação) devolve `None` pra tudo —
nunca `0`, nunca uma linha inventada.

Também lê o SEGUNDO Supabase (`SED.events`/`SED.registrations`), que
alimenta os cards de Inscritos/Aprovados — ver `buscar_eventos_proximos`.

As métricas de atividade (números captados, ligações, reuniões, indicações)
NÃO passam por aqui: a Geral lê as mesmas `buscar_totais`/`dash.vw_metricas`
que o Comercial. A leitura direta de `metricas_sdrs`/`metricas_closers` que
existia neste módulo morreu com a recriação da view — ela agora lê essas
mesmas tabelas em tempo real, então não há mais um lote "atrasado" pra
complementar.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime

from app.config import settings
from app.fontes.banco import query

CHAVES_FATURAMENTO = ("faturamento", "liquidado", "inscritos", "aprovados")

# Cards de Inscritos/Aprovados: os N próximos eventos de `SED.events` giram
# no card, um por vez. 3 é decisão de produto (3 barrinhas no rodapé).
LIMITE_EVENTOS = 3
# "Inscrito" = quem se inscreveu e não foi recusado; `rejected` e afins
# nunca entram em nenhum dos dois números.
STATUS_INSCRICAO = ("pending", "approved")


@dataclass(frozen=True)
class Faturamento:
    empresa: dict[str, float | None]
    por_pessoa: dict[int, dict[str, float | None]]


def _linha_vazia() -> dict[str, float | None]:
    return {chave: None for chave in CHAVES_FATURAMENTO}


def buscar_faturamento(inicio: date, fim: date, ids_pessoas: list[int]) -> Faturamento:
    linhas = query(
        "metricas_faturamento",
        {"and": f"(periodo.gte.{inicio.isoformat()},periodo.lte.{fim.isoformat()})"},
    )

    empresa = _linha_vazia()
    por_pessoa: dict[int, dict[str, float | None]] = {}

    for r in linhas:
        id_user = r.get("id_user")
        alvo = empresa if id_user is None else por_pessoa.setdefault(int(id_user), _linha_vazia())
        for chave in CHAVES_FATURAMENTO:
            valor = r.get(chave)
            if valor is not None:
                alvo[chave] = valor

    return Faturamento(empresa=empresa, por_pessoa=por_pessoa)


@dataclass(frozen=True)
class EventoInscricoes:
    """Um evento de `SED.events` + as contagens de `SED.registrations` dele.

    `inscritos` conta `pending` + `approved` (todo mundo na lista);
    `aprovados`, só os `approved` — daí `aprovados <= inscritos` sempre.
    `capacidade` é `None` quando o evento não tem limite cadastrado.
    """

    id: str
    titulo: str
    data: str  # `event_date` cru (ISO 8601 sem fuso), formatado no frontend
    capacidade: int | None
    inscritos: int
    aprovados: int


def buscar_eventos_proximos(agora: datetime) -> list[EventoInscricoes]:
    """Próximos `LIMITE_EVENTOS` eventos do segundo Supabase (`SED.events`),

    por data crescente, com a contagem de inscrições de cada um.

    Evento sem `event_date` fica de fora — o filtro `gte` já o descarta no
    banco, e sem data não haveria como ordená-lo na fila nem rotulá-lo no
    card. Sem as envs `SUPABASE_INSCRICOES_*`, `query()` devolve vazio e a
    lista sai `[]` — o card degrada pra estado vazio, nunca derruba /geral.

    `event_date` é `timestamp` sem fuso no banco, então `agora` também tem
    que chegar aqui ingênuo (horário de São Paulo) — comparar um com fuso
    e outro sem deslocaria o corte em 3 horas.
    """
    eventos = query(
        "events",
        {
            "event_date": f"gte.{agora.isoformat(timespec='seconds')}",
            "order": "event_date.asc",
        },
        schema=settings.supabase_inscricoes_schema or "public",
        colunas="id,title,event_date,capacity",
        url_base=settings.supabase_inscricoes_url,
        service_key=settings.supabase_inscricoes_service_key,
    )[:LIMITE_EVENTOS]
    if not eventos:
        return []

    ids = ",".join(f'"{e["id"]}"' for e in eventos)
    inscricoes = query(
        "registrations",
        {
            "event_id": f"in.({ids})",
            "status": f"in.({','.join(STATUS_INSCRICAO)})",
        },
        schema=settings.supabase_inscricoes_schema or "public",
        colunas="event_id,status",
        url_base=settings.supabase_inscricoes_url,
        service_key=settings.supabase_inscricoes_service_key,
    )

    inscritos = Counter(r.get("event_id") for r in inscricoes)
    aprovados = Counter(r.get("event_id") for r in inscricoes if r.get("status") == "approved")

    return [
        EventoInscricoes(
            id=str(e["id"]),
            titulo=e.get("title") or "Sem título",
            data=e["event_date"],
            capacidade=e.get("capacity"),
            inscritos=inscritos[e["id"]],
            aprovados=aprovados[e["id"]],
        )
        for e in eventos
    ]
