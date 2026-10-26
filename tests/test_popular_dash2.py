from __future__ import annotations

import openpyxl

from scripts import popular_dash2


def _aba(titulo, linhas):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = titulo
    for linha in linhas:
        ws.append(linha)
    return ws


def test_ler_aba_mapeia_cabecalho_e_le_meta_diaria():
    ws = _aba(
        "Isaque",
        [
            ["Dia", "Follow-ups", "Números Captados", "Indicações Captadas", "Please specify what you would like"],
            ["Meta diária", 50, 3, None, "x"],
        ],
    )

    aba = popular_dash2.ler_aba(ws)

    assert aba == popular_dash2.Aba(pessoa="Isaque", metas={"fups": 50, "numeros_captados": 3}, dias={})
