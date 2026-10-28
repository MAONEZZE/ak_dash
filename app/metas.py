"""Leitura das metas — valor DIÁRIO por (PESSOA, cargo, métrica).

Fonte: `dash2.metas`, uma linha por (`id_user`, `cargo`, `metrica`) com o
`valor_diario`, preenchido pela planilha.

A meta ATUAL vale pra qualquer período (decisão do usuário, 2026-10-05): não
há mais meta "do mês". Antes a meta era datada por `user_metas.atualizado_em`
e editar todas em 05/10 deixou setembro inteiro sem meta.

`valor_diario` é a meta de UM DIA ÚTIL daquela pessoa naquele cargo (ex: 4
números captados/dia). A meta de um período é `valor_diario × dias úteis do
período` — ver `Metas.por_usuario`.

A meta dos cards da empresa NÃO vem de uma linha própria: é a SOMA das metas
das pessoas ativas que compõem o card (ver `dominios/geral/calculo.py`).

Sem linha cadastrada é `None`; linha com `valor_diario = 0` é `0` — o
frontend mostra os dois como métrica aberta (barra azul).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from app.fontes.banco import query
from app.periodo import dias_uteis_totais


def dias_uteis_no_periodo(inicio: date, fim: date) -> int:
    """Multiplicador da meta diária: mês inteiro = 22, ano inteiro = 264, resto = dias úteis reais.

    Mês e ano seguem a regra da planilha (22 dias úteis por mês, sem olhar o
    calendário). Qualquer outro intervalo conta os dias úteis (seg-sex) de
    [inicio, fim]: uma semana dá 5; um sábado sozinho dá 0.
    """
    return dias_uteis_totais(inicio, fim)


@dataclass(frozen=True)
class Metas:
    # (id_user, cargo, metrica) -> meta diária
    _valores: dict[tuple[int, str, str], int]

    @property
    def vazio(self) -> bool:
        return not self._valores

    def diaria(self, id_user: int, cargo: str, metrica: str) -> int | None:
        return self._valores.get((id_user, cargo, metrica))

    def por_usuario(self, inicio: date, fim: date, id_user: int, cargo: str, metrica: str) -> int | None:
        """Meta DAQUELA pessoa, naquele cargo, no intervalo: diária × dias úteis.

        `None` se a pessoa não tem meta cadastrada nessa métrica e cargo.
        """
        diaria = self.diaria(id_user, cargo, metrica)
        if diaria is None:
            return None
        return diaria * dias_uteis_no_periodo(inicio, fim)

    def somar(self, inicio: date, fim: date, ids_user: Iterable[int], cargo: str, metrica: str) -> int | None:
        """Meta de um GRUPO — a soma das metas individuais. Quem está sem meta

        fica de fora da soma. `None` só quando ninguém do grupo tem meta.
        Grupo vazio soma 0.
        """
        ids = list(ids_user)
        if not ids:
            return 0
        metas = [self.por_usuario(inicio, fim, id_user, cargo, metrica) for id_user in ids]
        com_meta = [m for m in metas if m is not None]
        return sum(com_meta) if com_meta else None


def buscar_metas() -> Metas:
    linhas = query("metas", colunas="id_user,cargo,metrica,valor_diario")
    valores: dict[tuple[int, str, str], int] = {}
    for r in linhas:
        id_user, cargo, metrica, valor = r.get("id_user"), r.get("cargo"), r.get("metrica"), r.get("valor_diario")
        if id_user is None or cargo is None or metrica is None or valor is None:
            continue
        valores[(int(id_user), str(cargo), str(metrica))] = int(valor)
    return Metas(valores)
