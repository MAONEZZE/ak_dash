"""Monta a resposta de `GET /financeiro`: 2 cards (Faturamento/Liquidado,
sem meta — número puro do período) e a tabela de vendas detalhadas, mais
recente primeiro.

Faturamento = valor bruto das vendas fechadas dentro do período.
Liquidado = líquido dos recebimentos cujo mês cai no período (calendário),
inclusive de vendas fechadas antes do período.
"""
from __future__ import annotations

from app.metricas import NOME_EXIBICAO
from app.periodo import Periodo

_CARDS = ("faturamento", "liquidado")


def _valor(venda: dict, chave: str) -> float:
    if chave == "faturamento":
        return venda["valor_bruto_contrato"]
    # Liquidado = soma do líquido dos recebimentos do período, pelo calendário
    # (pago/líquido por mês vêm da BASE_VENDAS da planilha).
    return sum(r["liquido"] for r in venda.get("recebimentos", []))


def _na_data_do_periodo(periodo: Periodo, venda: dict) -> bool:
    return periodo.inicio.isoformat() <= venda["data_venda"][:10] <= periodo.fim.isoformat()


def montar_resposta_financeiro(periodo: Periodo, vendas: list[dict]) -> dict:
    cards = [
        {
            "metrica": chave,
            "nome_exibicao": NOME_EXIBICAO[chave],
            "realizado": sum(
                _valor(v, chave)
                for v in vendas
                if chave != "faturamento" or _na_data_do_periodo(periodo, v)
            ),
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
