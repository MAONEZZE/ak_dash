"""Pontuação e ranking — regra única, usada por `/comercial/*` e `/geral`.

Pontuação: `Σ(realizado/meta × 100) / qtd_metricas`, escala 0-100+, SEM cap,
contra a meta cheia do período. Só calculada quando TODAS as métricas
consideradas têm meta cadastrada (e valor realizado disponível); caso
contrário `None` — nunca uma média parcial disfarçada de total.

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
    parcelas = [
        (m["realizado"] / m["meta_periodo"] * 100) if m["meta_periodo"] > 0 else 100.0
        for m in metricas
    ]
    return round(sum(parcelas) / len(parcelas), 1)


def atribuir_ranking(pessoas: list[dict], campo: str) -> None:
    elegiveis = [p for p in pessoas if p[campo] is not None]
    pontos_unicos = sorted({p[campo] for p in elegiveis}, reverse=True)
    posicao_por_pontos = {pontos: i + 1 for i, pontos in enumerate(pontos_unicos)}
    for p in pessoas:
        p["posicao"] = posicao_por_pontos.get(p[campo])
