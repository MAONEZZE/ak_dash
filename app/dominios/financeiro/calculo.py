"""Monta a resposta de `GET /financeiro`: 2 cards (Faturamento/Liquidado,

sem meta — número puro do período) e a tabela de vendas detalhadas, mais
recente primeiro.
"""
from __future__ import annotations

from app.metricas import NOME_EXIBICAO
from app.periodo import Periodo

_CARDS = ("faturamento", "liquidado")


def _valor(venda: dict, chave: str) -> float:
    if chave == "faturamento":
        return venda["valor_bruto_contrato"]
    # Liquidado = os dois pagamentos da venda, mesma conta do card da Geral.
    return venda["liquido_entrada"] + venda.get("liquido_pgto_2", 0)


def montar_resposta_financeiro(periodo: Periodo, vendas: list[dict]) -> dict:
    cards = [
        {
            "metrica": chave,
            "nome_exibicao": NOME_EXIBICAO[chave],
            "realizado": sum(_valor(v, chave) for v in vendas),
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
