from __future__ import annotations

import pytest

from app import planilha_financeiro


CABECALHO = ["ID", "Data da Venda", "Cliente", "Telefone"] + [""] * 42


def _linha(trocas: dict[int, object] | None = None) -> list:
    linha = [8, 46037, "Fernando Seguim", "", "LinkedIn", "", "", "Produto de Ativação", 9893.8, "À vista", 9893.8, "PIX", "", 0.1, 0, 8904.42, 1000, "Cartão", 12, 0.1949, 724.59, "Dom antecipou"] + [""] * 24
    for indice, valor in (trocas or {}).items():
        linha[indice] = valor
    return linha


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


def test_data_em_texto_dd_mm_aaaa_e_aceita():
    vendas = planilha_financeiro.ler_base_vendas([CABECALHO, _linha({1: "23/10/2026"})], 2026)

    assert vendas[0].venda["data_venda"] == "2026-10-23T00:00:00"


def test_linha_sem_id_e_ignorada():
    vendas = planilha_financeiro.ler_base_vendas(
        [CABECALHO, _linha(), _linha({0: ""}), [], _linha({0: 9})], 2026
    )

    assert [v.venda["id_planilha"] for v in vendas] == [8, 9]


def test_apelidos_de_sdr_e_closer_viram_id_de_users():
    vendas = planilha_financeiro.ler_base_vendas(
        [
            CABECALHO,
            _linha({0: 1, 5: "Jonny", 6: "Jacob"}),
            _linha({0: 2, 5: "Nathan", 6: "Mary"}),
            _linha({0: 3, 5: " jennifer ", 6: "Thalyson"}),
            _linha({0: 4, 5: "Fulano", 6: "Alex"}),
        ],
        2026,
    )

    assert [(v.venda["user_sdr"], v.venda["user_closer"]) for v in vendas] == [
        (2, 1),
        (None, 5),
        (4, 8),
        (None, 3),
    ]
    assert vendas[3].sdr == "Fulano"
    assert vendas[3].closer == "Alex"


def test_cabecalho_fora_do_formato_levanta_value_error():
    with pytest.raises(ValueError, match="BASE_VENDAS"):
        planilha_financeiro.ler_base_vendas([["Data", "ID"], _linha()], 2026)
    with pytest.raises(ValueError, match="BASE_VENDAS"):
        planilha_financeiro.ler_base_vendas([], 2026)
