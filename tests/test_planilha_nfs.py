from __future__ import annotations

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
