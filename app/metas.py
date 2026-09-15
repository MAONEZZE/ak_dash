"""Leitura das metas — valor DIÁRIO por (mês, cargo, métrica).

Duas tabelas: `dash.metricas_metas` guarda a meta em si
(`metrica`, `periodo`, `valor`) e `dash.metas_cargo` liga cada meta aos
cargos que ela vale (N:N — `reunioes_agendadas` e `indicacoes` valem pra SDR
e pra closer com valores próprios, e as metas de empresa, faturamento e
liquidado, vão pro cargo `empresa`). Meta sem linha em `metas_cargo` não
existe pra ninguém: não há mais fallback de "meta global".

`valor` é a meta de UM DIA ÚTIL de UMA pessoa daquele cargo (ex: 4 números
captados/dia por SDR). A meta de um período é `valor × dias úteis do
período` — ver `Metas.por_cargo`. Quem cadastra só informa a diária; dia,
semana, mês e ano saem sozinhos, sem recadastrar nada.

`periodo` é sempre o primeiro dia do mês-alvo (coluna `date`). A meta dos
cards da empresa NÃO vem de uma linha própria: é a meta do cargo
multiplicada por quantas pessoas ativas daquele cargo existem (ver
`dominios/geral/calculo.py`), então entrar/sair gente ajusta sozinho.

Tabelas pequenas (dezenas de linhas mesmo cheias) — busca tudo no intervalo
e cruza em Python, em vez de montar join no PostgREST.

Nunca inventa denominador: sem linha cadastrada é sempre `None`, nunca `0`.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from app.fontes.banco import query
from app.periodo import dias_uteis_decorridos


def _ultimo_dia_do_mes(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def dias_uteis_do_mes_no_periodo(mes: date, inicio: date, fim: date) -> int:
    """Dias úteis do `mes` que caem dentro de [inicio, fim] — o multiplicador

    da meta diária. Mês inteiro de setembro/2026 dá 22; uma semana dá 5; um
    dia útil dá 1; um período só de sábado/domingo dá 0 (meta 0 = sem barra,
    nunca a meta cheia do mês cobrada num fim de semana).
    """
    ini, f = max(mes, inicio), min(_ultimo_dia_do_mes(mes), fim)
    if f < ini:
        return 0
    return dias_uteis_decorridos(ini, f, hoje=f)


def primeiro_dia_do_mes(d: date) -> date:
    return date(d.year, d.month, 1)


def meses_no_intervalo(inicio: date, fim: date) -> list[date]:
    meses = []
    cursor = primeiro_dia_do_mes(inicio)
    fim_mes = primeiro_dia_do_mes(fim)
    while cursor <= fim_mes:
        meses.append(cursor)
        cursor = date(cursor.year + 1, 1, 1) if cursor.month == 12 else date(cursor.year, cursor.month + 1, 1)
    return meses


@dataclass(frozen=True)
class Metas:
    _valores: dict[tuple[date, int, str], int]

    @property
    def vazio(self) -> bool:
        return not self._valores

    def por_cargo(self, inicio: date, fim: date, id_cargo: int, metrica: str) -> int | None:
        """Meta do cargo no intervalo — todo mundo daquele cargo compartilha o

        mesmo valor. A meta cadastrada é DIÁRIA; aqui vira a meta do período
        pedido, multiplicando pelos dias úteis de cada mês dentro dele. Um dia
        útil devolve a diária; uma semana, 5×; um mês de 22 dias úteis, 22×;
        um ano, a soma dos meses cadastrados. `None` se NENHUM mês do
        intervalo tiver meta cadastrada pra esse cargo — nunca soma parcial
        disfarçada de total, nunca 0.
        """
        total = 0
        algum_mes_com_meta = False
        for mes in meses_no_intervalo(inicio, fim):
            diaria = self._valores.get((mes, id_cargo, metrica))
            if diaria is not None:
                algum_mes_com_meta = True
                total += diaria * dias_uteis_do_mes_no_periodo(mes, inicio, fim)
        return total if algum_mes_com_meta else None


def buscar_metas(inicio: date, fim: date) -> Metas:
    meses = meses_no_intervalo(inicio, fim)
    if not meses:
        return Metas({})

    linhas = query(
        "metricas_metas",
        {"and": f"(periodo.gte.{meses[0].isoformat()},periodo.lte.{meses[-1].isoformat()})"},
    )
    if not linhas:
        return Metas({})

    # id da meta -> cargos em que ela vale. Sem vínculo, a meta é ignorada.
    cargos_por_meta: dict[int, list[int]] = {}
    for v in query("metas_cargo"):
        id_meta, id_cargo = v.get("id_meta"), v.get("id_cargo")
        if id_meta is None or id_cargo is None:
            continue
        cargos_por_meta.setdefault(int(id_meta), []).append(int(id_cargo))

    valores: dict[tuple[date, int, str], int] = {}
    for r in linhas:
        try:
            mes = primeiro_dia_do_mes(date.fromisoformat(str(r["periodo"])[:10]))
        except (KeyError, ValueError):
            continue
        metrica, valor, id_meta = r.get("metrica"), r.get("valor"), r.get("id")
        if metrica is None or valor is None or id_meta is None:
            continue
        for id_cargo in cargos_por_meta.get(int(id_meta), []):
            valores[(mes, id_cargo, metrica)] = int(valor)

    return Metas(valores)
