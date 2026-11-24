"""Leitura do Supabase do SED (eventos e inscrições). URL, chave e schema vêm de `SUPABASE_INSCRICOES_*`; falha degrada para `[]` com aviso `fonte_indisponivel:<tabela>`, via `banco.query`."""
from __future__ import annotations

from datetime import datetime, timezone

from app.fontes import banco
from app.config import settings


def _instante_utc(momento: datetime) -> str:
    """ISO-8601 em UTC com sufixo `Z`.

    `Z` em vez do `+00:00` que o `isoformat()` produz: o `+` depende de
    percent-encoding correto para não virar espaço na querystring, e `Z` não
    tem essa armadilha. Datetime ingênuo é assumido como UTC.
    """
    if momento.tzinfo is None:
        return momento.isoformat(timespec="seconds") + "Z"
    return momento.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _query(tabela: str, filtros: dict[str, str], colunas: str) -> list[dict]:
    return banco.query(
        tabela,
        filtros,
        schema=settings.supabase_inscricoes_schema or "public",
        colunas=colunas,
        url_base=settings.supabase_inscricoes_url,
        service_key=settings.supabase_inscricoes_service_key,
    )


def ler_eventos_entre(de: datetime, ate: datetime, titulo_contem: str, limite: int) -> list[dict]:
    return _query(
        "events",
        {
            "and": f'(event_date.gte."{_instante_utc(de)}",event_date.lt."{_instante_utc(ate)}")',
            "order": "event_date.asc",
            "limit": str(limite),
            "title": f"ilike.*{titulo_contem}*",
        },
        "id,title,event_date,capacity",
    )


def ler_eventos_a_partir_de(
    agora: datetime,
    limite: int,
    titulo_contem: str | None = None,
    colunas: str = "id,title,event_date,capacity",
) -> list[dict]:
    filtros = {"and": f'(event_date.gte."{_instante_utc(agora)}")', "order": "event_date.asc", "limit": str(limite)}
    if titulo_contem is not None:
        filtros["title"] = f"ilike.*{titulo_contem}*"
    return _query("events", filtros, colunas)


def ler_evento_por_id(id_evento: str) -> list[dict]:
    return _query(
        "events",
        {"and": f'(id.eq."{id_evento}")', "order": "event_date.asc", "limit": "1"},
        "id,title,event_date,capacity",
    )


def ler_imersoes(titulo_contem: str, limite: int) -> list[dict]:
    return _query(
        "events",
        {
            "title": f"ilike.*{titulo_contem}*",
            "event_date": "not.is.null",
            "order": "event_date.desc",
            "limit": str(limite),
        },
        "id,title,event_date",
    )
