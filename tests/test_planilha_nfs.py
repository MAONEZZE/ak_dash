from __future__ import annotations

from app.workers import planilha_nfs


def test_mes_da_aba_reconhece_nfs_e_ignora_outras_abas():
    titulos = ["NFS novembro", "NFS outubro", "NFS Março", "NFs Junho", " nfs  julho ", "Parcelas cartões - ASAAS", "dados clientes", "NFS"]

    meses = [planilha_nfs.mes_da_aba(t) for t in titulos]

    assert meses == [11, 10, 3, 6, 7, None, None, None]
