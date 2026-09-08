from __future__ import annotations

import os

from app.dominios.comercial.planilha import normalizar_cabecalho, parsear_planilha
from tests.conftest import CSV_DIR, caminhos_csv_reais, ler_csv_como_linhas


def test_normaliza_cabecalho_com_quebra_de_linha():
    assert normalizar_cabecalho("Conexões\nEnviadas") == "conexoes enviadas"
    assert normalizar_cabecalho("Follow-\nups") == "follow-ups"
    assert normalizar_cabecalho("InMails\nEnviados") == "inmails enviados"


def test_email_sdr_closer_em_coluna_variavel():
    # Jonathan: anotação na coluna 1. Jacob: anotação na coluna 9. Regex varre a
    # linha inteira e ignora a posição.
    caminho_jonathan = os.path.join(
        CSV_DIR, "Linkedin Jonathan _ SDR_ Nathan _ Closer_ Thalyson - Métricas Diárias.csv"
    )
    caminho_jacob = os.path.join(
        CSV_DIR, "Linkedin Jacob _ SDR_ Jennifer _ Closer_ Jacob - Métricas Diárias.csv"
    )
    avisos: list[str] = []
    p1 = parsear_planilha("jonathan.csv", ler_csv_como_linhas(caminho_jonathan), avisos)
    p2 = parsear_planilha("jacob.csv", ler_csv_como_linhas(caminho_jacob), avisos)

    assert p1 is not None and p1.email_sdr == "nathanmayumi5@gmail.com"
    assert p1.email_closer == "thalyson.teixeira@akeel.com.br"
    assert p2 is not None and p2.email_sdr == "jenniferpamplona007@gmail.com"
    assert p2.email_closer == "jacob@akeel.com.br"
    assert avisos == []


def test_linha_total_e_anotacao_descartadas_dos_valores():
    caminho = os.path.join(
        CSV_DIR, "Linkedin Jonathan _ SDR_ Nathan _ Closer_ Thalyson - Métricas Diárias.csv"
    )
    avisos: list[str] = []
    parseada = parsear_planilha("jonathan.csv", ler_csv_como_linhas(caminho), avisos)
    assert parseada is not None
    # 31 dias (1..31), nunca 32+ (TOTAL) nem 0 (anotação/cabeçalho).
    dias_presentes = set(parseada.valores["conexoes_enviadas"].keys())
    assert dias_presentes == set(range(1, 32))


def test_meta_diaria_lida_da_propria_planilha_indicacoes_varia():
    avisos: list[str] = []
    metas_indicacoes = []
    for caminho in caminhos_csv_reais():
        parseada = parsear_planilha(os.path.basename(caminho), ler_csv_como_linhas(caminho), avisos)
        assert parseada is not None
        metas_indicacoes.append(parseada.metas["indicacoes"])
    # O plano documenta que a meta de Indicações do Closer varia por planilha (15/10/8).
    assert sorted(metas_indicacoes) == [8, 10, 15]
    # Já as metas de função SDR são fixas entre planilhas (40 conexões enviadas etc.).
    for caminho in caminhos_csv_reais():
        parseada = parsear_planilha(os.path.basename(caminho), ler_csv_como_linhas(caminho), [])
        assert parseada.metas["conexoes_enviadas"] == 40


def test_vazio_nao_e_zero():
    # Linha 2 (dia 1) do CSV "Alex" tem Follow-ups vazio -> deve virar None, não 0.
    caminho = os.path.join(
        CSV_DIR, "Linkedin Alex _ SDR_ Jenni _ Closer_ Alex - Métricas Diárias.csv"
    )
    linhas = ler_csv_como_linhas(caminho)
    assert linhas[3][0] == "1"
    assert linhas[3][5] == ""  # Follow-ups (índice 5) do dia 1 vazio no CSV real
    parseada = parsear_planilha("alex.csv", linhas, [])
    assert parseada is not None
    assert parseada.valores["follow_ups"][1] is None
    # Uma célula com "0" explícito deve continuar 0, nunca virar None.
    assert linhas[3][1] == "0"
    assert parseada.valores["conexoes_enviadas"][1] == 0


def test_coluna_desconhecida_gera_aviso_sem_quebrar():
    linhas = [
        ["Dia", "Conexões\nEnviadas", "Coluna Nova Desconhecida"],
        ["Meta diária", "40", "5"],
        ["", "SDR: sdr@teste.com Closer: closer@teste.com", ""],
        ["1", "10", "99"],
    ]
    avisos: list[str] = []
    parseada = parsear_planilha("teste.csv", linhas, avisos)
    assert parseada is not None
    assert any("coluna desconhecida" in a.lower() for a in avisos)
    assert "coluna nova desconhecida" not in parseada.metas


def test_planilha_sem_email_vira_aviso_e_none():
    linhas = [
        ["Dia", "Conexões\nEnviadas"],
        ["Meta diária", "40"],
        ["", "sem emails aqui"],
        ["1", "10"],
    ]
    avisos: list[str] = []
    parseada = parsear_planilha("sem_email.csv", linhas, avisos)
    assert parseada is None
    assert any("emails ausentes" in a for a in avisos)
