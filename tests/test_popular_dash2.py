from __future__ import annotations

from datetime import datetime

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


def test_ler_aba_le_dias_preenchidos_e_pula_vazios_e_total():
    ws = _aba(
        "Thalyson",
        [
            ["Dia", "Ligações Agendada", "Reuniões Realizada"],
            ["Meta diária", 0, 4],
            [None, None, None],
            [1, 0, 5],
            [2, None, None],
            [3.0, 2, None],
            ["TOTAL", 2, 5],
            [datetime(2026, 10, 4), 1, 1],
        ],
    )

    aba = popular_dash2.ler_aba(ws)

    assert aba.dias == {1: {"ligacoes_agendadas": 0, "reunioes_realizadas": 5}, 3: {"ligacoes_agendadas": 2, "reunioes_realizadas": None}}
    assert aba.metas == {"ligacoes_agendadas": 0, "reunioes_realizadas": 4}
