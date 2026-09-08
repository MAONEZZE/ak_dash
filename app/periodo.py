"""Mês de referência sempre em America/Sao_Paulo (stdlib, sem dependência) e dias úteis decorridos."""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ_SP = ZoneInfo("America/Sao_Paulo")


def hoje_sp() -> date:
    return datetime.now(TZ_SP).date()


@dataclass(frozen=True)
class Periodo:
    granularidade: str  # "dia" | "mes" | "ano"
    inicio: date
    fim: date


def resolver_periodo(granularidade: str, valor: str) -> Periodo:
    """Levanta ValueError (com mensagem para o usuário) em parâmetro mal formado."""
    if granularidade == "dia":
        try:
            d = date.fromisoformat(valor)
        except ValueError as exc:
            raise ValueError(f"periodo inválido para granularidade 'dia': esperado AAAA-MM-DD") from exc
        return Periodo("dia", d, d)

    if granularidade == "mes":
        try:
            ano_str, mes_str = valor.split("-")
            ano, mes = int(ano_str), int(mes_str)
            if not (1 <= mes <= 12):
                raise ValueError
        except ValueError as exc:
            raise ValueError("periodo inválido para granularidade 'mes': esperado AAAA-MM") from exc
        inicio = date(ano, mes, 1)
        fim = date(ano, mes, calendar.monthrange(ano, mes)[1])
        return Periodo("mes", inicio, fim)

    if granularidade == "ano":
        try:
            ano = int(valor)
        except ValueError as exc:
            raise ValueError("periodo inválido para granularidade 'ano': esperado AAAA") from exc
        return Periodo("ano", date(ano, 1, 1), date(ano, 12, 31))

    raise ValueError(f"granularidade inválida: '{granularidade}' (esperado dia, mes ou ano)")


def dias_uteis_decorridos(inicio: date, fim: date, hoje: date | None = None) -> int:
    """Dias úteis (seg-sex) entre inicio e fim, nunca contando além de hoje (sem futuro)."""
    hoje = hoje or hoje_sp()
    fim_efetivo = min(fim, hoje)
    if fim_efetivo < inicio:
        return 0
    dias = 0
    d = inicio
    while d <= fim_efetivo:
        if d.weekday() < 5:
            dias += 1
        d += timedelta(days=1)
    return dias
