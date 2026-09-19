"""Monta a resposta de `GET /financeiro`: 2 cards (Faturamento/Liquidado,

sem meta — número puro do período) e a tabela de vendas detalhadas, mais
recente primeiro.
"""
from __future__ import annotations

from app.metricas import NOME_EXIBICAO
from app.periodo import Periodo

_CARDS = ("faturamento", "liquidado")


def montar_resposta_financeiro(periodo: Periodo, vendas: list[dict]) -> dict:
    cards = [
        {
            "metrica": chave,
            "nome_exibicao": NOME_EXIBICAO[chave],
            "realizado": sum(v["valor_bruto_contrato" if chave == "faturamento" else "liquido_entrada"] for v in vendas),
        }
        for chave in _CARDS
    ]

    vendas_ordenadas = sorted(vendas, key=lambda v: v["data_venda"], reverse=True)

    return {
        "periodo": {
            "granularidade": periodo.granularidade,
            "inicio": periodo.inicio.isoformat(),
            "fim": periodo.fim.isoformat(),
        },
        "cards": cards,
        "vendas": vendas_ordenadas,
    }
