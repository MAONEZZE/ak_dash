"""Mês de referência sempre em America/Sao_Paulo (stdlib, sem dependência) e dias úteis decorridos."""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ_SP = ZoneInfo("America/Sao_Paulo")

DIAS_UTEIS_MES = 22


def hoje_sp() -> date:
    return datetime.now(TZ_SP).date()


@dataclass(frozen=True)
class Periodo:
    granularidade: str  # "dia" | "semana" | "mes" | "ano" | "custom"
    inicio: date
    fim: date


def semana_iso(d: date) -> str:
    """Rótulo "AAAA-Wnn" da semana ISO em que `d` cai — o valor que o filtro de

    semana manda na querystring. Vem do calendário ISO (não do ano civil): 31/12
    pode pertencer à semana 1 do ano seguinte, e é assim que tem que ser gravado.
    """
    ano, semana, _ = d.isocalendar()
    return f"{ano:04d}-W{semana:02d}"


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

    if granularidade == "semana":
        # Semana ISO (segunda a domingo), formato "AAAA-Wnn" — mesmo vocabulário
        # do `<input type="week">` e do `isocalendar()` do Python.
        try:
            ano_str, semana_str = valor.upper().split("-W")
            ano, semana = int(ano_str), int(semana_str)
            inicio = date.fromisocalendar(ano, semana, 1)
        except ValueError as exc:
            raise ValueError("periodo inválido para granularidade 'semana': esperado AAAA-Wnn") from exc
        return Periodo("semana", inicio, inicio + timedelta(days=6))

    if granularidade == "ano":
        try:
            ano = int(valor)
        except ValueError as exc:
            raise ValueError("periodo inválido para granularidade 'ano': esperado AAAA") from exc
        return Periodo("ano", date(ano, 1, 1), date(ano, 12, 31))

    if granularidade == "custom":
        # Intervalo livre do calendário do filtro: "AAAA-MM-DD..AAAA-MM-DD", fim incluso.
        try:
            inicio_str, fim_str = valor.split("..")
            inicio, fim = date.fromisoformat(inicio_str), date.fromisoformat(fim_str)
        except ValueError as exc:
            raise ValueError("periodo inválido para granularidade 'custom': esperado AAAA-MM-DD..AAAA-MM-DD") from exc
        if fim < inicio:
            raise ValueError("periodo inválido para granularidade 'custom': fim antes do início")
        return Periodo("custom", inicio, fim)

    raise ValueError(f"granularidade inválida: '{granularidade}' (esperado dia, semana, mes, ano ou custom)")


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


def dias_uteis_totais(inicio: date, fim: date) -> int:
    """Total de dias úteis do período, sem cortar por hoje.

    regra da planilha: mês tem sempre 22 dias úteis.
    """
    if inicio.day == 1 and (inicio.year, inicio.month) == (fim.year, fim.month) and fim.day == calendar.monthrange(fim.year, fim.month)[1]:
        return DIAS_UTEIS_MES
    if inicio == date(inicio.year, 1, 1) and fim == date(inicio.year, 12, 31):
        return DIAS_UTEIS_MES * 12
    return dias_uteis_decorridos(inicio, fim, hoje=fim)


def dias_uteis_meta(inicio: date, fim: date, hoje: date) -> dict[str, int]:
    """Decorridos e total do período; decorridos nunca passa do total."""
    total = dias_uteis_totais(inicio, fim)
    return {"decorridos": min(dias_uteis_decorridos(inicio, fim, hoje=hoje), total), "total": total}


def horas_restantes(dia: date, agora: datetime, inicio: time, fim: time) -> float:
    """Horas de expediente que ainda sobram no `dia` a partir de `agora` (SP)."""
    agora = agora.astimezone(TZ_SP)

    def _horas(t: time) -> float:
        return t.hour + t.minute / 60 + t.second / 3600

    if dia < agora.date():
        return 0.0
    if dia > agora.date():
        return round(_horas(fim) - _horas(inicio), 1)
    return round(max(0.0, _horas(fim) - max(_horas(inicio), _horas(agora.time()))), 1)
