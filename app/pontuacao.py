"""Pontuação e ranking — usada hoje só por `/comercial/*`.

`/geral` tem sua própria regra de pontuação (soma bruta de quantidade, não
percentual de meta — ver `_pontuacao_por_quantidade` em
`app/dominios/geral/calculo.py`); só usa `atribuir_ranking` daqui, que é
agnóstica à fórmula de pontuação.

Pontuação: `Σ(realizado/meta × 100) / qtd_metricas`, escala 0-100+, SEM cap,
contra a meta cheia do período. Só calculada quando TODAS as métricas têm
meta cadastrada e valor realizado disponível; caso contrário `None` — nunca
uma média parcial disfarçada de total.

Meta 0 = "não é cobrado nesta métrica": a métrica sai da média antes do
cálculo. Se, depois de tirar as de meta 0, não sobrar nenhuma, a pontuação é
`None` — a pessoa fica sem pontuação e fora do pódio, em vez de empatar em
1º com 100 por não ser cobrada em nada.

Ranking: dense rank (1-based) de pontuação decrescente, só entre quem tem
pontuação. Empate = mesma posição, sem pular número. Quem não tem pontuação
fica com `posicao: None` — fora do ranking, nunca um último lugar fabricado.
"""
from __future__ import annotations


def calcular_pontuacao(metricas: list[dict]) -> float | None:
    """`metricas`: lista de `{"realizado": int|None, "meta_periodo": int|None}`."""
    if not metricas:
        return None
    if any(m["realizado"] is None or m["meta_periodo"] is None for m in metricas):
        return None
    consideradas = [m for m in metricas if m["meta_periodo"] > 0]
    if not consideradas:
        return None
    parcelas = [m["realizado"] / m["meta_periodo"] * 100 for m in consideradas]
    return round(sum(parcelas) / len(parcelas), 1)


def atribuir_ranking(pessoas: list[dict], campo: str) -> None:
    elegiveis = [p for p in pessoas if p[campo] is not None]
    pontos_unicos = sorted({p[campo] for p in elegiveis}, reverse=True)
    posicao_por_pontos = {pontos: i + 1 for i, pontos in enumerate(pontos_unicos)}
    for p in pessoas:
        p["posicao"] = posicao_por_pontos.get(p[campo])
