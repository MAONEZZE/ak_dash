"""Leitura das metas — valor DIÁRIO por (PESSOA, métrica).

Duas tabelas: `dash.metricas_metas` diz qual métrica cada meta mede
(`id`, `metrica`) e `dash.user_metas` guarda O VALOR de cada pessoa pra
aquela meta (`id_user`, `id_meta`, `valor_meta`).

A meta ATUAL vale pra qualquer período (decisão do usuário, 2026-10-05): não
há mais meta "do mês". Antes a meta era datada por `user_metas.atualizado_em`
e editar todas em 05/10 deixou setembro inteiro sem meta. Duas linhas da
mesma pessoa/métrica: vale a atualizada por último.

`valor_meta` é a meta de UM DIA ÚTIL daquela pessoa (ex: 4 números
captados/dia). A meta de um período é `valor_meta × dias úteis do período` —
ver `Metas.por_usuario`.

A meta dos cards da empresa NÃO vem de uma linha própria: é a SOMA das metas
das pessoas ativas que compõem o card (ver `dominios/geral/calculo.py`).

Sem linha cadastrada é `None`; linha com `valor_meta = 0` é `0` — o
frontend mostra os dois como métrica aberta (barra azul).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from app.fontes.banco import query
from app.periodo import dias_uteis_decorridos


def dias_uteis_no_periodo(inicio: date, fim: date) -> int:
    """Dias úteis (seg-sex) em [inicio, fim] inteiro, futuro incluído — o

    multiplicador da meta diária. Setembro/2026 dá 22; uma semana dá 5; um
    sábado sozinho dá 0.
    """
    return dias_uteis_decorridos(inicio, fim, hoje=fim)


@dataclass(frozen=True)
class Metas:
    # (id_user, metrica) -> meta diária
    _valores: dict[tuple[int, str], int]

    @property
    def vazio(self) -> bool:
        return not self._valores

    def diaria(self, id_user: int, metrica: str) -> int | None:
        return self._valores.get((id_user, metrica))

    def por_usuario(self, inicio: date, fim: date, id_user: int, metrica: str) -> int | None:
        """Meta DAQUELA pessoa no intervalo: diária × dias úteis. `None` se a

        pessoa não tem meta cadastrada nessa métrica.
        """
        diaria = self.diaria(id_user, metrica)
        if diaria is None:
            return None
        return diaria * dias_uteis_no_periodo(inicio, fim)

    def somar(self, inicio: date, fim: date, ids_user: Iterable[int], metrica: str) -> int | None:
        """Meta de um GRUPO — a soma das metas individuais. Quem está sem meta

        fica de fora da soma. `None` só quando ninguém do grupo tem meta.
        Grupo vazio soma 0.
        """
        ids = list(ids_user)
        if not ids:
            return 0
        metas = [self.por_usuario(inicio, fim, id_user, metrica) for id_user in ids]
        com_meta = [m for m in metas if m is not None]
        return sum(com_meta) if com_meta else None


def buscar_metas() -> Metas:
    linhas = query("metricas_metas")
    metrica_por_meta = {
        int(r["id"]): str(r["metrica"]) for r in linhas if r.get("id") is not None and r.get("metrica") is not None
    }
    if not metrica_por_meta:
        return Metas({})

    ids = ",".join(str(i) for i in sorted(metrica_por_meta))
    vinculos = query("user_metas", {"id_meta": f"in.({ids})"})

    valores: dict[tuple[int, str], int] = {}
    atualizado_por_chave: dict[tuple[int, str], str] = {}
    for v in vinculos:
        id_meta, id_user, valor = v.get("id_meta"), v.get("id_user"), v.get("valor_meta")
        if id_meta is None or id_user is None or valor is None:
            continue
        metrica = metrica_por_meta.get(int(id_meta))
        if metrica is None:
            continue
        chave = (int(id_user), metrica)
        marca = str(v.get("atualizado_em") or "")
        if chave in valores and marca < atualizado_por_chave[chave]:
            continue
        valores[chave] = int(valor)
        atualizado_por_chave[chave] = marca

    return Metas(valores)
