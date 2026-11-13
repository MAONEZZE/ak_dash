"""Testes de `dominios/funil/banco.py` — contas de funil (LinkedIn/Instagram) e somas de `metricas_contas`."""
from __future__ import annotations

from datetime import date

from app.dominios.funil import banco as funil_banco
from app.planilhas import COLUNAS_POR_TABELA


def test_buscar_contas_soma_metricas_por_conta_no_periodo(monkeypatch):
    chamadas: list[dict] = []

    def fake(tabela, filtros=None, schema=None, colunas="*", **kw):
        chamadas.append({"tabela": tabela, "filtros": filtros})
        if tabela == "contas_funil":
            return [
                {"id": 2, "nome": "Jonathan", "id_seller": 4},
                {"id": 1, "nome": "Jacob", "id_seller": 4},
            ]
        if tabela == "metricas_contas":
            vazio = {c: None for c in COLUNAS_POR_TABELA["metricas_contas"]}
            return [
                {**vazio, "id_conta": 1, "data": "2026-11-02", "conexoes_enviadas": 43, "numeros_captados": 0},
                {**vazio, "id_conta": 1, "data": "2026-11-03", "conexoes_enviadas": 38, "numeros_captados": None},
            ]
        raise AssertionError(f"tabela inesperada: {tabela}")

    monkeypatch.setattr(funil_banco, "query", fake)

    contas = funil_banco.buscar_contas("linkedin", date(2026, 11, 1), date(2026, 11, 30))

    zeros = {c: 0 for c in COLUNAS_POR_TABELA["metricas_contas"]}
    assert contas == [
        funil_banco.ContaFunil(
            id_conta=1, nome="Jacob", id_seller=4, metricas={**zeros, "conexoes_enviadas": 81}
        ),
        funil_banco.ContaFunil(id_conta=2, nome="Jonathan", id_seller=4, metricas=zeros),
    ]

    filtros_contas = next(c["filtros"] for c in chamadas if c["tabela"] == "contas_funil")
    assert filtros_contas == {"canal": "eq.linkedin"}

    filtros_metricas = next(c["filtros"] for c in chamadas if c["tabela"] == "metricas_contas")
    assert filtros_metricas["id_conta"] == "in.(1,2)"
    assert filtros_metricas["and"] == "(data.gte.2026-11-01,data.lte.2026-11-30)"
