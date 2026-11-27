from __future__ import annotations

import re
from datetime import date

import pytest

from app.workers import planilha_nfs


def test_mes_da_aba_reconhece_nfs_e_ignora_outras_abas():
    titulos = ["NFS novembro", "NFS outubro", "NFS Março", "NFs Junho", " nfs  julho ", "Parcelas cartões - ASAAS", "dados clientes", "NFS"]

    meses = [planilha_nfs.mes_da_aba(t) for t in titulos]

    assert meses == [11, 10, 3, 6, 7, None, None, None]


def test_valor_monetario_aceita_numero_e_texto_em_reais():
    entradas = [5000, 1010.33, "R$ 1.000,00", "R$ 4.000", "R$ 2.500,50", "R$5k", "", None]

    valores = [planilha_nfs.valor_monetario(x) for x in entradas]

    assert valores == [5000.0, 1010.33, 1000.0, 4000.0, 2500.5, None, None, None]


def test_categoria_produto_e_forma_saem_normalizados():
    assert planilha_nfs.categoria("Venda nova ") == "venda nova"
    assert planilha_nfs.categoria("mensalidade cliente") == "mensalidade cliente"
    assert planilha_nfs.categoria("UPSELL") == "upsell"
    assert planilha_nfs.categoria("outra") is None
    assert planilha_nfs.categoria(None) is None

    assert planilha_nfs.produto("Aceleracao") == "Aceleração"
    assert planilha_nfs.produto("Aceleração ") == "Aceleração"
    assert planilha_nfs.produto("tração") == "Tração"
    assert planilha_nfs.produto("Ativação") == "Ativação"
    assert planilha_nfs.produto("The Green House") == "The Green House"
    assert planilha_nfs.produto(" Sprint ") == "Sprint"
    assert planilha_nfs.produto("") is None
    assert planilha_nfs.produto(None) is None

    assert planilha_nfs.forma_pagamento("PIX") == "PIX"
    assert planilha_nfs.forma_pagamento("Pix parcelado") == "PIX"
    assert planilha_nfs.forma_pagamento("Cartão de crédito") == "Cartão"
    assert planilha_nfs.forma_pagamento("Link") == "Cartão"
    assert planilha_nfs.forma_pagamento("Boleto") == "Boleto"
    assert planilha_nfs.forma_pagamento("PIX + Cartão de crédito") == "Outros"
    assert planilha_nfs.forma_pagamento("PIX e Cartão ") == "Outros"
    assert planilha_nfs.forma_pagamento(None) == "Outros"
    assert planilha_nfs.forma_pagamento("Dinheiro") == "Outros"


def test_data_venda_valida_serial_e_texto_e_recusa_lixo():
    assert planilha_nfs.data_venda(46335, 2026) == date(2026, 11, 9)
    assert planilha_nfs.data_venda(46294, 2026) == date(2026, 9, 29)
    assert planilha_nfs.data_venda("23/10/2026", 2026) == date(2026, 10, 23)
    assert planilha_nfs.data_venda(42701, 2026) is None
    assert planilha_nfs.data_venda("abril", 2026) is None
    assert planilha_nfs.data_venda(None, 2026) is None
    assert planilha_nfs.data_venda("", 2026) is None


def test_ler_aba_nfs_monta_notas_pelo_nome_da_coluna():
    linhas = [
        ["Status", "Cliente ", "Categoria", "Produto", "Valor pago", "Valor da venda", "Data de Venda", "Forma de pagto", "Origem do lead", "Vendedor"],
        ["Emitida", "Ana ", "venda nova", "Aceleracao", "R$ 5.000,00", 30000, 46335, "Cartão de crédito", "LinkedIn", " Jacob"],
        [None, None, None, None, None, None, None, None, None, None],
        ["", "Bruno", "", "Sprint", 1000, None, "abril", "PIX"],
    ]

    notas = planilha_nfs.ler_aba_nfs(linhas, 2026, 11)

    assert notas == [
        {"chave": "2026-11:2", "mes": "2026-11-01", "linha": 2, "cliente": "Ana", "categoria": "venda nova", "produto": "Aceleração", "valor_pago": 5000.0, "valor_venda": 30000.0, "data_venda": "2026-11-09", "data_referencia": "2026-11-09", "forma_pagamento": "Cartão", "canal": "LinkedIn", "vendedor": "Jacob", "status": "Emitida"},
        {"chave": "2026-11:4", "mes": "2026-11-01", "linha": 4, "cliente": "Bruno", "categoria": None, "produto": "Sprint", "valor_pago": 1000.0, "valor_venda": None, "data_venda": None, "data_referencia": "2026-11-01", "forma_pagamento": "PIX", "canal": None, "vendedor": None, "status": None},
    ]


def test_ler_aba_nfs_sem_cliente_ou_valor_pago_levanta_value_error():
    mensagem = re.escape("aba NFS 06/2026 sem as colunas Cliente e Valor pago")
    linhas_sem_colunas = [["Cliente", "NFSE", "Data", "Descrição do Serviço", "Valor contábil"], ["X", 1, 46174, "s", 10]]

    with pytest.raises(ValueError, match=mensagem):
        planilha_nfs.ler_aba_nfs(linhas_sem_colunas, 2026, 6)
    with pytest.raises(ValueError, match=mensagem):
        planilha_nfs.ler_aba_nfs([], 2026, 6)
