from __future__ import annotations

from app import planilhas


def test_ler_linhas_aceita_linhas_curtas_do_google():
    linhas = [
        ["Dia", "Abordagens", "Inmails enviados"],
        ["Meta diária", 20],
        [],
        [1.0, 5],
        [2.0, None, 3],
        ["TOTAL", 5, 3],
    ]

    aba = planilhas.ler_linhas("Linkedin Jacob", linhas)

    assert aba == planilhas.Aba(
        pessoa="Jacob",
        metas={"abordagens": 20},
        dias={1: {"abordagens": 5, "in_mails": None}, 2: {"abordagens": None, "in_mails": 3}},
    )


def test_ler_linhas_de_aba_vazia_devolve_none():
    assert planilhas.ler_linhas("Juca", []) is None
