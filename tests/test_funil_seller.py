"""Testes de `dominios/funil/seller.py` — página Seller: Números Captados do mês por seller."""
from __future__ import annotations

from datetime import date

from app.dominios.funil import seller
from app.metas import Metas
from app.periodo import resolver_periodo


def test_montar_resposta_pagina_seller_soma_numeros_captados_do_banco_no_mes_e_hoje_com_a_meta():
    periodo = resolver_periodo("mes", "2026-11")
    sellers = [{"id": 4, "nome": "Duda", "imagem_url": None}, {"id": 13, "nome": "Lucas", "imagem_url": "l.png"}]
    linhas = [
        {"data": "2026-11-26", "id_user": 13, "metrica": "numeros_captados", "valor": 11},
        {"data": "2026-11-27", "id_user": 13, "metrica": "numeros_captados", "valor": 6},
        {"data": "2026-11-27", "id_user": 13, "metrica": "fups", "valor": 130},
        {"data": "2026-11-27", "id_user": 4, "metrica": "numeros_captados", "valor": 8},
        {"data": "2026-11-03", "id_user": 4, "metrica": "numeros_captados", "valor": None},
    ]
    metas = Metas({(13, "seller", "numeros_captados"): 21})
    hoje = date(2026, 11, 27)

    assert seller.montar_resposta_pagina_seller(periodo, sellers, linhas, metas, hoje) == {
        "periodo": {"granularidade": "mes", "inicio": "2026-11-01", "fim": "2026-11-30"},
        "sellers": [
            {"id_user": "4", "nome": "Duda", "imagem_url": None, "numeros_captados": 8, "numeros_captados_hoje": 8, "meta": None},
            {"id_user": "13", "nome": "Lucas", "imagem_url": "l.png", "numeros_captados": 17, "numeros_captados_hoje": 6, "meta": 462},
        ],
    }
