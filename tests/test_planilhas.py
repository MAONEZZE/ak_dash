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


def test_ler_linhas_ignora_aba_de_funil():
    linhas = [[], [None, "Painel de acompanhamento do funil de prospecção LinkedIn"]]

    assert planilhas.ler_linhas("Funil de Vendas LinkedIn", linhas) is None
    assert planilhas.ler_linhas("funil de vendas instagram", linhas) is None


def test_ler_linhas_mapeia_cabecalhos_das_planilhas_de_funil():
    linkedin = planilhas.ler_linhas(
        "Linkedin Jacob",
        [
            ["Dia", "Conexões Enviadas", "Conexões Aceitas", "Mensagem de Abordagem", "Abordagens", "Follow de abordagem", "Respondidos", "InMails Enviados", "Follow-ups", "Números Captados"],
            ["Meta diária", 40, 20, 20, 20, 30, 10, 5, 150, 0],
            [],
            [2, 43, 17, 17, 69, 52, 13, 27, None, 0],
        ],
    )
    instagram = planilhas.ler_linhas(
        "Mary",
        [
            ["Dia", "Abordagens feita", "Follow Up", "Respondidos", "Números Captados", "Indicações Captadas"],
            ["Meta diária", 50, 50, 20, 7, 0],
            [],
            [11, None, None, None, 6],
        ],
    )

    assert linkedin.pessoa == "Jacob"
    assert linkedin.dias[2] == {
        "conexoes_enviadas": 43,
        "conexoes_aceitas": 17,
        "mensagens_abordagem": 17,
        "abordagens": 69,
        "follows_abordagem": 52,
        "respondidos": 13,
        "in_mails": 27,
        "fups": None,
        "numeros_captados": 0,
    }
    assert instagram.pessoa == "Mary"
    assert instagram.dias[11] == {"abordagens": None, "fups": None, "respondidos": None, "numeros_captados": 6, "indicacoes": None}
    assert instagram.metas == {"abordagens": 50, "fups": 50, "respondidos": 20, "numeros_captados": 7, "indicacoes": 0}
