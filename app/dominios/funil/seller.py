"""Página Seller: Números Captados do mês por seller, das contas dos funis ligadas a ele (contas_funil.id_seller), com o Pipedrive já aplicado."""
from __future__ import annotations

from datetime import date

from app.dominios.funil.banco import ContaFunil
from app.metas import Metas
from app.periodo import Periodo


def montar_resposta_pagina_seller(
    periodo: Periodo,
    sellers: list[dict],
    contas_por_canal: dict[str, tuple[list[ContaFunil], dict[str, int]]],
    metas: Metas,
    hoje: date,
) -> dict:
    dia = hoje.isoformat()
    itens = []
    for s in sellers:
        id_seller = s["id"]
        numeros_captados = 0
        numeros_captados_hoje = 0
        for contas, sem_conta in contas_por_canal.values():
            do_seller = [c for c in contas if c.id_seller == id_seller]
            numeros_captados += sum(c.metricas["numeros_captados"] for c in do_seller)
            # O sem_conta do canal só é do seller quando ele é o único seller ligado às contas do canal.
            if {c.id_seller for c in contas if c.id_seller is not None} == {id_seller}:
                numeros_captados += sem_conta["numeros_captados"]
            for c in do_seller:
                numeros_captados_hoje += sum(p["metricas"]["numeros_captados"] for p in c.serie if p["data"] == dia)
        itens.append(
            {
                "id_user": str(id_seller),
                "nome": s["nome"],
                "imagem_url": s["imagem_url"],
                "numeros_captados": numeros_captados,
                "numeros_captados_hoje": numeros_captados_hoje,
                "meta": metas.somar(periodo.inicio, periodo.fim, [id_seller], "seller", "numeros_captados"),
            }
        )
    return {
        "periodo": {"granularidade": periodo.granularidade, "inicio": periodo.inicio.isoformat(), "fim": periodo.fim.isoformat()},
        "sellers": itens,
    }
