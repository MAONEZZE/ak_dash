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

Quem data o valor é `user_metas.atualizado_em`: a meta vale no mês em que foi
atualizada. Na virada de mês o time só edita o `valor_meta` das linhas que já
existem (que seguem apontando pra `metricas_metas` do mês anterior) — datar
pelo `metricas_metas.periodo` deixava o mês novo sem meta nenhuma. Linha sem
`atualizado_em` cai no `periodo` da meta pra qual aponta. Duas linhas da mesma
pessoa/métrica no mesmo mês: vale a atualizada por último.

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


def _proximo_mes(d: date) -> date:
    return date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)


def buscar_metas(inicio: date, fim: date) -> Metas:
    meses = meses_no_intervalo(inicio, fim)
    if not meses:
        return Metas({})

    # Sem filtro de `periodo`: o mês sai de `user_metas.atualizado_em`, então
    # uma meta declarada em setembro e atualizada em outubro vale em outubro.
    linhas = query("metricas_metas")
    if not linhas:
        return Metas({})

    # id da meta -> (métrica, `periodo` como fallback de data).
    alvo_por_meta: dict[int, tuple[str, date | None]] = {}
    for r in linhas:
        metrica, id_meta = r.get("metrica"), r.get("id")
        if metrica is None or id_meta is None:
            continue
        try:
            periodo = primeiro_dia_do_mes(date.fromisoformat(str(r["periodo"])[:10]))
        except (KeyError, ValueError):
            periodo = None
        alvo_por_meta[int(id_meta)] = (str(metrica), periodo)

    if not alvo_por_meta:
        return Metas({})

    ids = ",".join(str(i) for i in sorted(alvo_por_meta))
    de, ate = meses[0].isoformat(), _proximo_mes(meses[-1]).isoformat()
    vinculos = query(
        "user_metas",
        {
            "id_meta": f"in.({ids})",
            "or": f"(and(atualizado_em.gte.{de},atualizado_em.lt.{ate}),atualizado_em.is.null)",
        },
    )

    valores: dict[tuple[date, int, str], int] = {}
    atualizado_por_chave: dict[tuple[date, int, str], str] = {}
    for v in vinculos:
        id_meta, id_user, valor = v.get("id_meta"), v.get("id_user"), v.get("valor_meta")
        if id_meta is None or id_user is None or valor is None:
            continue
        alvo = alvo_por_meta.get(int(id_meta))
        if alvo is None:
            continue
        metrica, periodo = alvo
        atualizado = v.get("atualizado_em")
        try:
            mes = primeiro_dia_do_mes(date.fromisoformat(str(atualizado)[:10])) if atualizado else periodo
        except ValueError:
            mes = periodo
        if mes is None or mes not in meses:
            continue
        chave = (mes, int(id_user), metrica)
        marca = str(atualizado or "")
        if chave in valores and marca < atualizado_por_chave[chave]:
            continue
        valores[chave] = int(valor)
        atualizado_por_chave[chave] = marca

    return Metas(valores)
