"""Monta a resposta de `GET /financeiro`: o período pedido e as notas da
planilha do financeiro, da mais recente para a mais antiga (por
`data_referencia`). Os cards saíram: o front agrega as notas.
"""
from __future__ import annotations

from app.periodo import Periodo


def montar_resposta_financeiro(periodo: Periodo, notas: list[dict]) -> dict:
    return {
        "periodo": {
            "granularidade": periodo.granularidade,
            "inicio": periodo.inicio.isoformat(),
            "fim": periodo.fim.isoformat(),
        },
        "notas": sorted(notas, key=lambda n: n["data_referencia"], reverse=True),
    }
