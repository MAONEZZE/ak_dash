from __future__ import annotations

from app import planilha_financeiro


CABECALHO = ["ID", "Data da Venda", "Cliente", "Telefone"] + [""] * 42


def test_linha_da_base_vira_venda_com_campos_do_banco():
    linha = [8, 46037, "Fernando Seguim", "", "LinkedIn", "", "", "Produto de Ativação", 9893.8, "À vista", 9893.8, "PIX", "", 0.1, 0, 8904.42, 1000, "Cartão", 12, 0.1949, 724.59, "Dom antecipou"] + [""] * 24

    vendas = planilha_financeiro.ler_base_vendas([CABECALHO, linha], 2026)

    assert len(vendas) == 1
    venda = vendas[0]
    assert venda.venda == {
        "id_planilha": 8,
        "data_venda": "2026-01-15T00:00:00",
        "canal": "LinkedIn",
        "user_sdr": None,
        "user_closer": None,
        "produto": "Produto de Ativação",
        "valor_bruto_contrato": 9893.8,
        "condicao_pagamento": "À vista",
        "valor_entrada": 9893.8,
        "metodo_pagamento": "PIX",
        "num_parcelas": None,
        "imposto": 0.1,
        "taxa": 0,
        "liquido_entrada": 8904.42,
        "valor_pgto_2": 1000,
        "forma_pgto_2": "Cartão",
        "num_parcelas_pgto_2": 12,
        "taxa_pgto_2": 0.1949,
        "liquido_pgto_2": 724.59,
        "observacoes": "Dom antecipou",
    }
    assert venda.cliente_nome == "Fernando Seguim"
    assert venda.recebimentos == []
