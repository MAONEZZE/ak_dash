"""Página Seller: Números Captados do mês por seller, lidos do banco (metricas_sellers via vw_metricas), sem Pipedrive.

`metricas_sellers` é preenchida pelo WorkerFunil a partir da aba do seller na planilha do funil (ex.: aba "Lucas"
da planilha do Instagram). A meta é a do cadastro `metas` (seller, numeros_captados) × dias úteis do período.
"""
from __future__ import annotations

from datetime import date

from app.metas import Metas
from app.periodo import Periodo


def montar_resposta_pagina_seller(
    periodo: Periodo,
    sellers: list[dict],
    linhas: list[dict],
    metas: Metas,
    hoje: date,
) -> dict:
    """`linhas`: formato de `vw_metricas` (`data`, `id_user`, `metrica`, `valor`) dos sellers no período."""
    dia = hoje.isoformat()
    total: dict[int, int] = {}
    do_dia: dict[int, int] = {}
    for r in linhas:
        if r.get("metrica") != "numeros_captados" or r.get("valor") is None:
            continue
        id_user = int(r["id_user"])
        valor = int(r["valor"])
        total[id_user] = total.get(id_user, 0) + valor
        if str(r["data"])[:10] == dia:
            do_dia[id_user] = do_dia.get(id_user, 0) + valor

    return {
        "periodo": {"granularidade": periodo.granularidade, "inicio": periodo.inicio.isoformat(), "fim": periodo.fim.isoformat()},
        "sellers": [
            {
                "id_user": str(s["id"]),
                "nome": s["nome"],
                "imagem_url": s["imagem_url"],
                "numeros_captados": total.get(s["id"], 0),
                "numeros_captados_hoje": do_dia.get(s["id"], 0),
                "meta": metas.somar(periodo.inicio, periodo.fim, [s["id"]], "seller", "numeros_captados"),
            }
            for s in sellers
        ],
    }
