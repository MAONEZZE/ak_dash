"""Leitura de `dash.metricas_faturamento` — uma linha por VENDA, não mais uma

linha por pessoa/período. `buscar_faturamento` soma `valor_bruto_contrato` e
`liquido_entrada` de toda venda com `data_venda` dentro do período pedido; o
filtro usa `lt` no dia seguinte ao fim (nunca `lte`), porque `data_venda` é
timestamp e `lte` na data perderia venda com hora ≠ meia-noite.

O card da empresa soma TODA venda do período, inclusive de quem já saiu do
time (`ids_pessoas` não filtra a consulta). Por pessoa, agrupa
`liquido_entrada` por `user_closer`; venda sem `user_closer` entra no total
da empresa e em ninguém. `inscritos`/`aprovados` continuam sempre `None`
aqui — não existem nesta tabela, vêm do SED (ver `buscar_eventos_proximos`).

Também lê o SEGUNDO Supabase (`SED.events`/`SED.registrations`), que
alimenta os cards de Inscritos/Aprovados — ver `buscar_eventos_proximos`.

As métricas de atividade (números captados, ligações, reuniões, indicações)
NÃO passam por aqui: a Geral lê as mesmas `buscar_totais`/`dash.vw_metricas`
que o Comercial.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from app.config import settings
from app.fontes.banco import query

CHAVES_FATURAMENTO = ("faturamento", "liquidado", "inscritos", "aprovados")

# Cards de Inscritos/Aprovados: os N próximos eventos de `SED.events` giram
# no card, um por vez. 3 é decisão de produto (3 barrinhas no rodapé).
LIMITE_EVENTOS = 3

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
    fim_exclusivo = fim + timedelta(days=1)
    linhas = query(
        "metricas_faturamento",
        {"and": f"(data_venda.gte.{inicio.isoformat()},data_venda.lt.{fim_exclusivo.isoformat()})"},
    )

    empresa: dict[str, float | None] = {**_linha_vazia(), "faturamento": 0.0, "liquidado": 0.0}
    por_pessoa: dict[int, dict[str, float | None]] = {}

    for r in linhas:
        empresa["faturamento"] += r.get("valor_bruto_contrato") or 0
        empresa["liquidado"] += r.get("liquido_entrada") or 0

        id_user = r.get("user_closer")
        if id_user is None:
            continue
        pessoa = por_pessoa.setdefault(int(id_user), {**_linha_vazia(), "liquidado": 0.0})
        pessoa["liquidado"] += r.get("liquido_entrada") or 0

    return Faturamento(empresa=empresa, por_pessoa=por_pessoa)


@dataclass(frozen=True)
class EventoInscricoes:
    """Um evento de `SED.events` + as contagens de `SED.registrations` dele.

    `inscritos` conta TODAS as inscrições do evento, qualquer status;
    `aprovados`, só os `approved` — daí `aprovados <= inscritos` sempre.
    `capacidade` é `None` quando o evento não tem limite cadastrado.
    """

    id: str
    titulo: str
    data: str  # `event_date` cru (ISO 8601 sem fuso), formatado no frontend
    capacidade: int | None
    inscritos: int
    aprovados: int


def _instante_utc(momento: datetime) -> str:
    """ISO-8601 em UTC com sufixo `Z`.

    `Z` em vez do `+00:00` que o `isoformat()` produz: o `+` depende de
    percent-encoding correto para não virar espaço na querystring, e `Z` não
    tem essa armadilha. Datetime ingênuo é assumido como UTC.
    """
    if momento.tzinfo is None:
        return momento.isoformat(timespec="seconds") + "Z"
    return momento.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def buscar_eventos_proximos(agora: datetime) -> list[EventoInscricoes]:
    """Próximos `LIMITE_EVENTOS` eventos do segundo Supabase (`SED.events`),

    por data crescente, com a contagem de inscrições de cada um.

    Evento sem `event_date` fica de fora — o filtro `gte` já o descarta no
    banco, e sem data não haveria como ordená-lo na fila nem rotulá-lo no
    card. Sem as envs `SUPABASE_INSCRICOES_*`, `query()` devolve vazio e a
    lista sai `[]` — o card degrada pra estado vazio, nunca derruba /geral.

    `agora` chega com fuso e o filtro é montado em UTC com sufixo `Z`. Esse
    formato é correto nos dois esquemas possíveis da coluna, o que permite
    migrar `event_date` para `timestamptz` sem tocar aqui:

    - sendo `timestamp` sem fuso, o Postgres descarta o `Z` e compara relógio
      de parede contra relógio de parede — e a coluna guarda UTC, porque é
      assim que o Prisma grava;
    - sendo `timestamptz`, o `Z` é respeitado e a comparação é de instantes.

    Mandar o horário de São Paulo aqui (com ou sem fuso) quebraria o primeiro
    caso, adiantando o corte em 3h.
    """
    eventos = query(
        "events",
        {
            "event_date": f"gte.{_instante_utc(agora)}",
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
        {"event_id": f"in.({ids})"},
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
