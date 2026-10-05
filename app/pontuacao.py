"""Pontuação e ranking — uma regra só pro dash inteiro (Geral e Comercial).

Pontuação = Σ realizado × peso da métrica no cargo (decisão do usuário,
2026-10-05). Não depende de meta: todo mundo do cargo pontua, inclusive quem
está sem meta cadastrada. Métrica fora da tabela de pesos não pontua.

`ligacoes_agendadas` vale 3 no closer e não entra no SDR: a coluna saiu de
`dash.metricas_sdrs` em 02/10/2026, então não há o que somar.

Ranking: dense rank (1-based) de pontuação decrescente, só entre quem tem
pontuação. Empate = mesma posição, sem pular número.
"""
from __future__ import annotations

from typing import Mapping

PESOS: dict[str, dict[str, int]] = {
    "sdr": {
        "inscricoes_realizadas": 15,
        "ligacoes_realizadas": 10,
        "numeros_captados": 7,
        "reunioes_agendadas": 7,
        "indicacoes": 5,
    },
    "closer": {
        "reunioes_realizadas": 15,
        "inscricoes_realizadas": 15,
        "ligacoes_realizadas": 10,
        "reunioes_agendadas": 5,
        "indicacoes": 5,
        "ligacoes_agendadas": 3,
    },
}


def calcular_pontuacao(cargo: str, realizado_por_metrica: Mapping[str, float | None]) -> int:
    pesos = PESOS.get(cargo, {})
    return int(sum((realizado_por_metrica.get(m) or 0) * peso for m, peso in pesos.items()))


def atribuir_ranking(pessoas: list[dict], campo: str) -> None:
    elegiveis = [p for p in pessoas if p[campo] is not None]
    pontos_unicos = sorted({p[campo] for p in elegiveis}, reverse=True)
    posicao_por_pontos = {pontos: i + 1 for i, pontos in enumerate(pontos_unicos)}
    for p in pessoas:
        p["posicao"] = posicao_por_pontos.get(p[campo])
