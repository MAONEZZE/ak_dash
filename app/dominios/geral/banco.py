"""Leitura de `dash.metricas_faturamento` — uma linha por VENDA, não mais uma

linha por pessoa/período. `buscar_faturamento` soma `valor_bruto_contrato` e
`liquido_entrada` de toda venda com `data_venda` dentro do período pedido; o
filtro usa `lt` no dia seguinte ao fim (nunca `lte`), porque `data_venda` é
timestamp e `lte` na data perderia venda com hora ≠ meia-noite.

O card da empresa soma TODA venda do período, inclusive de quem já saiu do
time (`ids_pessoas` não filtra a consulta). Por pessoa, agrupa
`liquido_entrada` por `user_closer`; venda sem `user_closer` entra no total
da empresa e em ninguém. `inscritos`/`aprovados` continuam sempre `None`
aqui — não existem nesta tabela, vêm do SED (ver `buscar_confrarias_do_mes`).

Também lê o SEGUNDO Supabase (`SED.events`/`SED.registrations`), que
alimenta a tabela de Confrarias da Geral — ver `buscar_confrarias_do_mes` —
e `dash.metricas_dripify` por conta — ver `buscar_dripify_por_conta`.

As métricas de atividade (números captados, ligações, reuniões, indicações)
NÃO passam por aqui: a Geral lê as mesmas `buscar_totais`/`dash.vw_metricas`
que o Comercial.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from app.config import settings
from app.periodo import TZ_SP
from app.fontes.banco import query

CHAVES_FATURAMENTO = ("faturamento", "liquidado", "inscritos", "aprovados")

# Uma tabela de Confrarias na Geral, de 10 linhas — a segunda virou a tabela
# de contas do Dripify (decisão do usuário, 2026-10-05).
LIMITE_EVENTOS = 10

# A Geral só mostra as Confrarias (decisão do usuário, 2026-10-05). `ilike`
# com `*` dos dois lados = "contém", sem diferenciar maiúsculas.
FILTRO_TITULO_EVENTOS = "ilike.*confraria akeel*"

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
        # `liquido_entrada` é só o líquido do PRIMEIRO pagamento da venda —
        # quando ela tem um segundo pagamento (`valor_pgto_2`/`liquido_pgto_2`,
        # ex.: entrada no PIX + resto no cartão, cada um com sua taxa), o
        # líquido de verdade é a soma dos dois. Sem isso o card subestimava o
        # liquidado toda vez que uma venda vinha parcelada em duas formas —
        # mesmo bug encontrado e corrigido em dominios/financeiro/banco.py.
        liquido_venda = (r.get("liquido_entrada") or 0) + (r.get("liquido_pgto_2") or 0)

        empresa["faturamento"] += r.get("valor_bruto_contrato") or 0
        empresa["liquidado"] += liquido_venda

        id_user = r.get("user_closer")
        if id_user is None:
            continue
        pessoa = por_pessoa.setdefault(int(id_user), {**_linha_vazia(), "liquidado": 0.0})
        pessoa["liquidado"] += liquido_venda

    return Faturamento(empresa=empresa, por_pessoa=por_pessoa)


@dataclass(frozen=True)
class EventoInscricoes:
    """Um evento de `SED.events` + as contagens de `SED.registrations` dele.

    `inscritos` conta TODAS as inscrições do evento, qualquer status;
    `aprovados`, só os `approved`; `pendentes`, só os `pending` — os dois
    são subconjuntos de `inscritos`.
    `capacidade` é `None` quando o evento não tem limite cadastrado.
    """

    id: str
    titulo: str
    data: str  # `event_date` cru (ISO 8601 sem fuso), formatado no frontend
    capacidade: int | None
    inscritos: int
    aprovados: int
    pendentes: int = 0


def _instante_utc(momento: datetime) -> str:
    """ISO-8601 em UTC com sufixo `Z`.

    `Z` em vez do `+00:00` que o `isoformat()` produz: o `+` depende de
    percent-encoding correto para não virar espaço na querystring, e `Z` não
    tem essa armadilha. Datetime ingênuo é assumido como UTC.
    """
    if momento.tzinfo is None:
        return momento.isoformat(timespec="seconds") + "Z"
    return momento.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def buscar_confrarias_do_mes(inicio: date, fim: date) -> list[EventoInscricoes]:
    """Confrarias ("confraria akeel" no título) de `inicio` a `fim` (o mês
    corrente inteiro, inclusive as que já passaram) do segundo Supabase
    (`SED.events`), por data crescente, com a contagem de inscrições de cada
    uma — no máximo `LIMITE_EVENTOS`.

    Os limites são meia-noite de São Paulo convertida pra UTC com sufixo `Z`.
    Esse formato é correto nos dois esquemas possíveis da coluna:

    - sendo `timestamp` sem fuso, o Postgres descarta o `Z` e compara relógio
      de parede contra relógio de parede — e a coluna guarda UTC, porque é
      assim que o Prisma grava;
    - sendo `timestamptz`, o `Z` é respeitado e a comparação é de instantes.

    Os valores vão entre aspas dentro do `and=(...)`: `:` é reservado na
    árvore lógica do PostgREST. Sem as envs `SUPABASE_INSCRICOES_*`,
    `query()` devolve vazio e a lista sai `[]` — nunca derruba /geral.
    """
    de = _instante_utc(datetime.combine(inicio, time.min, tzinfo=TZ_SP))
    ate = _instante_utc(datetime.combine(fim + timedelta(days=1), time.min, tzinfo=TZ_SP))
    eventos = query(
        "events",
        {
            "and": f'(event_date.gte."{de}",event_date.lt."{ate}")',
            "title": FILTRO_TITULO_EVENTOS,
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
    pendentes = Counter(r.get("event_id") for r in inscricoes if r.get("status") == "pending")

    return [
        EventoInscricoes(
            id=str(e["id"]),
            titulo=e.get("title") or "Sem título",
            data=e["event_date"],
            capacidade=e.get("capacity"),
            inscritos=inscritos[e["id"]],
            aprovados=aprovados[e["id"]],
            pendentes=pendentes[e["id"]],
        )
        for e in eventos
    ]


@dataclass(frozen=True)
class ContaDripify:
    conta: str
    conexoes_aceitas: int
    numeros_captados: int


def _data_da_chave(chave: str | None) -> date | None:
    """`key_data_ref_user` é "DD/MM/AAAA-nome" — mesma regra da `vw_metricas`."""
    try:
        return datetime.strptime((chave or "")[:10], "%d/%m/%Y").date()
    except ValueError:
        return None


def buscar_dripify_por_conta(inicio: date, fim: date) -> list[ContaDripify]:
    """Conexões aceitas e números captados de cada conta do LinkedIn
    (`dash.metricas_dripify`, uma conta por `id_user`) somados de `inicio` a
    `fim`, da maior pra menor em conexões aceitas.

    Lê a tabela direto, não a `vw_metricas`: a view só emite Dripify de quem é
    SDR, e as contas rodam também no nome de closers e de quem já saiu do
    time (Jacob, Mariana...). A data só existe dentro de `key_data_ref_user`
    (texto), então o filtro de período é feito aqui, não no PostgREST.
    """
    linhas = query("metricas_dripify", colunas="id_user,key_data_ref_user,conexoes_aceitas,numeros_captados")

    somas: dict[int, list[int]] = {}
    for r in linhas:
        dia = _data_da_chave(r.get("key_data_ref_user"))
        if r.get("id_user") is None or dia is None or not inicio <= dia <= fim:
            continue
        soma = somas.setdefault(int(r["id_user"]), [0, 0])
        soma[0] += r.get("conexoes_aceitas") or 0
        soma[1] += r.get("numeros_captados") or 0
    if not somas:
        return []

    usuarios = query("users", {"id": f"in.({','.join(str(i) for i in somas)})"}, colunas="id,nome")
    nomes = {int(u["id"]): u.get("nome") for u in usuarios}

    contas = [
        ContaDripify(conta=nomes.get(id_user) or f"Conta {id_user}", conexoes_aceitas=aceitas, numeros_captados=captados)
        for id_user, (aceitas, captados) in somas.items()
    ]
    return sorted(contas, key=lambda c: (-c.conexoes_aceitas, c.conta))
