"""Testes de `dominios/funil/seller.py` — página Seller: Números Captados do mês por seller."""
from __future__ import annotations

from datetime import date

from app.dominios.funil.banco import ContaFunil
from app.dominios.funil import seller
from app.metas import Metas
from app.periodo import resolver_periodo
from app.planilhas import COLUNAS_POR_TABELA


def test_montar_resposta_pagina_seller_soma_as_contas_do_seller_o_sem_conta_do_canal_e_a_meta_do_mes():
    COLUNAS = COLUNAS_POR_TABELA["metricas_contas"]

    def _m(**kw):
        return {c: kw.get(c, 0) for c in COLUNAS}

    periodo = resolver_periodo("mes", "2026-11")
    sellers = [{"id": 4, "nome": "Duda", "imagem_url": None}, {"id": 13, "nome": "Lucas", "imagem_url": "l.png"}]
    contas_por_canal = {
        "linkedin": (
            [
                ContaFunil(1, "Jacob", 4, _m(numeros_captados=5), [{"data": "2026-11-24", "metricas": _m(numeros_captados=3)}, {"data": "2026-11-25", "metricas": _m(numeros_captados=2)}]),
                ContaFunil(2, "Mariana", 4, _m(numeros_captados=1), []),
            ],
            _m(numeros_captados=2),
        ),
        "instagram": (
            [
                ContaFunil(3, "Mary", 13, _m(numeros_captados=4), [{"data": "2026-11-25", "metricas": _m(numeros_captados=1)}]),
                ContaFunil(4, "Akeel", None, _m(numeros_captados=9), []),
            ],
            _m(numeros_captados=3),
        ),
    }
    metas = Metas({(4, "seller", "numeros_captados"): 4})
    hoje = date(2026, 11, 25)

    assert seller.montar_resposta_pagina_seller(periodo, sellers, contas_por_canal, metas, hoje) == {
        "periodo": {"granularidade": "mes", "inicio": "2026-11-01", "fim": "2026-11-30"},
        "sellers": [
            {"id_user": "4", "nome": "Duda", "imagem_url": None, "numeros_captados": 8, "numeros_captados_hoje": 2, "meta": 88},
            {"id_user": "13", "nome": "Lucas", "imagem_url": "l.png", "numeros_captados": 7, "numeros_captados_hoje": 1, "meta": None},
        ],
    }

    # Com outro seller no canal do Instagram, o sem_conta dele não vai para ninguém.
    contas_por_canal["instagram"][0].append(ContaFunil(5, "X", 4, _m(numeros_captados=1), []))
    resposta = seller.montar_resposta_pagina_seller(periodo, sellers, contas_por_canal, metas, hoje)
    numeros = {s["id_user"]: s["numeros_captados"] for s in resposta["sellers"]}
    assert numeros == {"4": 9, "13": 4}
