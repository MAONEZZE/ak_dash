"""Leitura das metas — valor DIÁRIO por (mês, PESSOA, métrica).

Duas tabelas: `dash.metricas_metas` declara QUE existe meta de uma métrica
num mês (`metrica`, `periodo`) e `dash.user_metas` guarda O VALOR de cada
pessoa pra aquela meta (`id_user`, `id_meta`, `valor_meta`). A meta deixou de
ser do cargo e passou a ser de cada um: dois SDRs podem ter metas diferentes
de números captados no mesmo mês, e é isso que `dash.metas_cargo` (N:N
meta<->cargo, que não existe mais) não conseguia expressar.

Meta sem linha em `user_metas` não existe pra ninguém: não há fallback de
"meta do cargo" nem de "meta global".

`valor_meta` é a meta de UM DIA ÚTIL daquela pessoa (ex: 4 números
captados/dia). A meta de um período é `valor_meta × dias úteis do período` —
ver `Metas.por_usuario`. Quem cadastra só informa a diária; dia, semana, mês
e ano saem sozinhos, sem recadastrar nada.

`periodo` (coluna `date` de `metricas_metas`) é sempre o primeiro dia do
mês-alvo, e é ele que data a meta: `user_metas` não tem data própria, herda a
da linha que aponta.

A meta dos cards da empresa NÃO vem de uma linha própria: é a SOMA das metas
das pessoas ativas que compõem o card (ver `dominios/geral/calculo.py`),
então entrar/sair gente ajusta sozinho — mesma propriedade que o modelo
antigo tinha multiplicando a meta do cargo pelo tamanho do time.

Tabelas pequenas (dezenas de linhas por mês) — busca tudo no intervalo e
cruza em Python, em vez de montar join no PostgREST.

Nunca inventa denominador: sem linha cadastrada é sempre `None`, nunca `0`.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from typing import Iterable

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

    def por_usuario(self, inicio: date, fim: date, id_user: int, metrica: str) -> int | None:
        """Meta DAQUELA pessoa no intervalo. A meta cadastrada é DIÁRIA; aqui

        vira a meta do período pedido, multiplicando pelos dias úteis de cada
        mês dentro dele. Um dia útil devolve a diária; uma semana, 5×; um mês
        de 22 dias úteis, 22×; um ano, a soma dos meses cadastrados. `None` se
        NENHUM mês do intervalo tiver meta cadastrada pra essa pessoa — nunca
        soma parcial disfarçada de total, nunca 0.
        """
        total = 0
        algum_mes_com_meta = False
        for mes in meses_no_intervalo(inicio, fim):
            diaria = self._valores.get((mes, id_user, metrica))
            if diaria is not None:
                algum_mes_com_meta = True
                total += diaria * dias_uteis_do_mes_no_periodo(mes, inicio, fim)
        return total if algum_mes_com_meta else None

    def somar(self, inicio: date, fim: date, ids_user: Iterable[int], metrica: str) -> int | None:
        """Meta de um GRUPO — a soma das metas individuais. É assim que os

        cards da empresa acham o denominador deles agora que meta é de pessoa,
        não de cargo.

        `None` se QUALQUER pessoa do grupo estiver sem meta: o realizado do
        card soma o time inteiro, então uma meta parcial compararia 7 pessoas
        de realizado contra 3 de meta. Grupo vazio soma 0 — mesmo resultado
        que o modelo antigo dava multiplicando a meta do cargo por zero
        pessoas.
        """
        total = 0
        for id_user in ids_user:
            meta = self.por_usuario(inicio, fim, id_user, metrica)
            if meta is None:
                return None
            total += meta
        return total


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

    # id da meta -> (mês, métrica) que ela representa.
    alvo_por_meta: dict[int, tuple[date, str]] = {}
    for r in linhas:
        try:
            mes = primeiro_dia_do_mes(date.fromisoformat(str(r["periodo"])[:10]))
        except (KeyError, ValueError):
            continue
        metrica, id_meta = r.get("metrica"), r.get("id")
        if metrica is None or id_meta is None:
            continue
        alvo_por_meta[int(id_meta)] = (mes, str(metrica))

    if not alvo_por_meta:
        return Metas({})

    # Só os vínculos das metas do intervalo — `user_metas` cresce a cada mês
    # cadastrado, e não há por que trazer o histórico inteiro pra filtrar aqui.
    ids = ",".join(str(i) for i in sorted(alvo_por_meta))

    valores: dict[tuple[date, int, str], int] = {}
    for v in query("user_metas", {"id_meta": f"in.({ids})"}):
        id_meta, id_user, valor = v.get("id_meta"), v.get("id_user"), v.get("valor_meta")
        if id_meta is None or id_user is None or valor is None:
            continue
        alvo = alvo_por_meta.get(int(id_meta))
        if alvo is None:
            continue
        mes, metrica = alvo
        valores[(mes, int(id_user), metrica)] = int(valor)

    return Metas(valores)
