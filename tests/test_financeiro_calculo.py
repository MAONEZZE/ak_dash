from __future__ import annotations

from datetime import date

from app.dominios.financeiro.calculo import montar_resposta_financeiro
from app.periodo import Periodo


def _periodo():
    return Periodo("mes", date(2026, 8, 1), date(2026, 8, 31))


def _venda(**over):
    base = {
        "id": 1,
        "data_venda": "2026-08-05T00:00:00",
        "cliente": "Maria Silva",
        "produto": "Mentoria",
        "canal": "Instagram",
        "metodo_pagamento": "Pix",
        "num_parcelas": 1,
        "valor_bruto_contrato": 10000,
        "liquido_entrada": 9500,
    }
    base.update(over)
    return base


def test_cards_somam_faturamento_e_liquidado_das_vendas():
    vendas = [
        _venda(id=1, valor_bruto_contrato=10000, liquido_entrada=9500),
        _venda(id=2, valor_bruto_contrato=5000, liquido_entrada=4500),
    ]
    resposta = montar_resposta_financeiro(_periodo(), vendas)
    card_faturamento = next(c for c in resposta["cards"] if c["metrica"] == "faturamento")
    card_liquidado = next(c for c in resposta["cards"] if c["metrica"] == "liquidado")
    assert card_faturamento["realizado"] == 15000
    assert card_liquidado["realizado"] == 14000


def test_sem_venda_os_cards_ficam_zerados_nao_none():
    resposta = montar_resposta_financeiro(_periodo(), [])
    for card in resposta["cards"]:
        assert card["realizado"] == 0
    assert resposta["vendas"] == []


def test_vendas_saem_ordenadas_por_data_decrescente():
    vendas = [
        _venda(id=1, data_venda="2026-08-05T00:00:00"),
        _venda(id=2, data_venda="2026-08-20T00:00:00"),
        _venda(id=3, data_venda="2026-08-12T00:00:00"),
    ]
    resposta = montar_resposta_financeiro(_periodo(), vendas)
    assert [v["id"] for v in resposta["vendas"]] == [2, 3, 1]


def test_periodo_sai_no_formato_do_contrato():
    resposta = montar_resposta_financeiro(_periodo(), [])
    assert resposta["periodo"] == {"granularidade": "mes", "inicio": "2026-08-01", "fim": "2026-08-31"}
