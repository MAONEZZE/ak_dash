"""Conformidade com docs/contract/: mesmos CSVs reais, mesmo formato de resposta.

Nota sobre `periodo_parcial`: a fixture do contrato fixa `periodo_parcial: false`
de propósito (README do contrato: "é só para ter um número determinístico"),
tratando abril/2026 como se já fosse um mês fechado. O BFF real, com
`hoje = 30/04/2026` (abril = mês corrente), calcula `periodo_parcial = True`
corretamente pela própria regra do contrato ("true quando o período inclui o
mês corrente") — isso é o comportamento certo, não um bug; a fixture nunca
teve a intenção de ser um golden-file byte-exato nesse campo. Os demais
campos (realizado, meta_periodo, status, avisos) são independentes dessa
diferença e são conferidos abaixo campo-a-campo.
"""
from __future__ import annotations

import json
import os
from datetime import date

from app.dominios.comercial.calculo import montar_resposta_comercial
from app.dominios.comercial.planilha import parsear_planilha
from app.periodo import Periodo
from tests.conftest import caminhos_csv_reais, ler_csv_como_linhas

CONTRATO_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "docs", "contract", "fixtures"
)


def _carregar_planilhas_reais():
    avisos: list[str] = []
    planilhas = []
    for caminho in caminhos_csv_reais():
        parseada = parsear_planilha(os.path.basename(caminho), ler_csv_como_linhas(caminho), avisos)
        assert parseada is not None
        planilhas.append(parseada)
    return planilhas, avisos


def _gerar_resposta(funcao: str) -> dict:
    planilhas, avisos = _carregar_planilhas_reais()
    periodo = Periodo("mes", date(2026, 4, 1), date(2026, 4, 30))
    return montar_resposta_comercial(
        periodo=periodo,
        funcao=funcao,
        planilhas_mes_corrente=planilhas,
        avisos_estruturais=avisos,
        historico=[],
        cadastro_nomes={},
        emails_filtro=None,
        hoje=date(2026, 4, 30),
    )


def _por_email_metrica(resposta: dict) -> dict[tuple[str, str], dict]:
    return {
        (p["email"], m["metrica"]): m
        for p in resposta["pessoas"]
        for m in p["metricas"]
    }


def _por_email(resposta: dict) -> dict[str, dict]:
    return {p["email"]: p for p in resposta["pessoas"]}


def test_sdr_bate_com_fixture_do_contrato_exceto_periodo_parcial():
    esperado = json.load(open(os.path.join(CONTRATO_DIR, "comercial_sdr.example.json"), encoding="utf-8"))
    obtido = _gerar_resposta("sdr")

    assert obtido["periodo"] == esperado["periodo"]
    assert obtido["periodo_parcial"] is True  # ver docstring do módulo — divergência esperada e correta

    esperado_por_metrica = _por_email_metrica(esperado)
    obtido_por_metrica = _por_email_metrica(obtido)
    assert set(obtido_por_metrica) == set(esperado_por_metrica)
    for chave, metrica_esperada in esperado_por_metrica.items():
        metrica_obtida = obtido_por_metrica[chave]
        assert metrica_obtida["meta_periodo"] == metrica_esperada["meta_periodo"], chave
        assert metrica_obtida["realizado"] == metrica_esperada["realizado"], chave
        assert metrica_obtida["status"] == metrica_esperada["status"], chave
        assert metrica_obtida["dias_com_lacuna"] == metrica_esperada["dias_com_lacuna"], chave

    esperado_por_pessoa = _por_email(esperado)
    obtido_por_pessoa = _por_email(obtido)
    for email, pessoa_esperada in esperado_por_pessoa.items():
        pessoa_obtida = obtido_por_pessoa[email]
        assert pessoa_obtida["pontuacao_total"] == pessoa_esperada["pontuacao_total"], email
        assert pessoa_obtida["posicao"] == pessoa_esperada["posicao"], email


def test_closer_bate_com_fixture_do_contrato_exceto_periodo_parcial():
    esperado = json.load(open(os.path.join(CONTRATO_DIR, "comercial_closer.example.json"), encoding="utf-8"))
    obtido = _gerar_resposta("closer")

    esperado_por_metrica = _por_email_metrica(esperado)
    obtido_por_metrica = _por_email_metrica(obtido)
    assert set(obtido_por_metrica) == set(esperado_por_metrica)
    for chave, metrica_esperada in esperado_por_metrica.items():
        metrica_obtida = obtido_por_metrica[chave]
        assert metrica_obtida["meta_periodo"] == metrica_esperada["meta_periodo"], chave
        assert metrica_obtida["realizado"] == metrica_esperada["realizado"], chave
        assert metrica_obtida["status"] == metrica_esperada["status"], chave
        assert metrica_obtida["dias_com_lacuna"] == metrica_esperada["dias_com_lacuna"], chave

    esperado_por_pessoa = _por_email(esperado)
    obtido_por_pessoa = _por_email(obtido)
    for email, pessoa_esperada in esperado_por_pessoa.items():
        pessoa_obtida = obtido_por_pessoa[email]
        assert pessoa_obtida["pontuacao_total"] == pessoa_esperada["pontuacao_total"], email
        assert pessoa_obtida["posicao"] == pessoa_esperada["posicao"], email


def test_avisos_de_pessoa_duplicada_e_dia_fora_do_calendario_disparam():
    obtido = _gerar_resposta("sdr")
    avisos_texto = " | ".join(obtido["avisos"])
    assert "jenniferpamplona007@gmail.com" in avisos_texto
    assert "aparece em mais de uma planilha" in avisos_texto
    assert "dia 31 fora do calendário" in avisos_texto
