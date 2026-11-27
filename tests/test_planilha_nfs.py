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
