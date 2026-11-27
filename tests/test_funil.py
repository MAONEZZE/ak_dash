"""Testes de `dominios/funil/banco.py` — contas de funil (LinkedIn/Instagram) e somas de `metricas_contas`."""
from __future__ import annotations

from datetime import date

from app.dominios.funil import banco as funil_banco
from app.fontes import supabase
from app.planilhas import COLUNAS_POR_TABELA


def test_buscar_contas_soma_metricas_por_conta_no_periodo(monkeypatch):
    chamadas: dict = {}

    def fake_contas(canal):
        chamadas["canal"] = canal
        return [
            {"id": 2, "nome": "Jonathan", "id_seller": 4},
            {"id": 1, "nome": "Jacob", "id_seller": 4},
        ]

    def fake_metricas(inicio, fim, ids=None):
        chamadas["metricas"] = (inicio, fim, ids)
        vazio = {c: None for c in COLUNAS_POR_TABELA["metricas_contas"]}
        return [
            {**vazio, "id_conta": 1, "data": "2026-11-03", "conexoes_enviadas": 38, "numeros_captados": None},
            {**vazio, "id_conta": 1, "data": "2026-11-02", "conexoes_enviadas": 43, "numeros_captados": 0},
        ]

    monkeypatch.setattr(supabase, "ler_contas_do_canal", fake_contas)
    monkeypatch.setattr(supabase, "ler_metricas_das_contas", fake_metricas)

    contas = funil_banco.buscar_contas("linkedin", date(2026, 11, 1), date(2026, 11, 30))

    zeros = {c: 0 for c in COLUNAS_POR_TABELA["metricas_contas"]}
    assert contas == [
        funil_banco.ContaFunil(
            id_conta=1,
            nome="Jacob",
            id_seller=4,
            metricas={**zeros, "conexoes_enviadas": 81},
            serie=[
                {"data": "2026-11-02", "metricas": {**zeros, "conexoes_enviadas": 43}},
                {"data": "2026-11-03", "metricas": {**zeros, "conexoes_enviadas": 38}},
            ],
        ),
        funil_banco.ContaFunil(id_conta=2, nome="Jonathan", id_seller=4, metricas=zeros, serie=[]),
    ]

    assert chamadas["canal"] == "linkedin"
    assert chamadas["metricas"] == (date(2026, 11, 1), date(2026, 11, 30), [1, 2])


def test_buscar_contas_serie_desde_inicio_serie_mas_soma_so_o_periodo(monkeypatch):
    """Filtro de dia: a série traz a semana até o dia (gráfico com linha); o total é só do dia."""
    chamadas: dict = {}
    vazio = {c: None for c in COLUNAS_POR_TABELA["metricas_contas"]}

    def fake_contas(canal):
        return [{"id": 1, "nome": "Jacob", "id_seller": None}]

    def fake_metricas(inicio, fim, ids=None):
        chamadas["metricas"] = (inicio, fim, ids)
        return [
            {**vazio, "id_conta": 1, "data": "2026-11-10", "fups": 5},
            {**vazio, "id_conta": 1, "data": "2026-11-16", "fups": 2},
        ]

    monkeypatch.setattr(supabase, "ler_contas_do_canal", fake_contas)
    monkeypatch.setattr(supabase, "ler_metricas_das_contas", fake_metricas)

    (conta,) = funil_banco.buscar_contas("linkedin", date(2026, 11, 16), date(2026, 11, 16), date(2026, 11, 10))

    assert conta.metricas["fups"] == 2
    assert [d["data"] for d in conta.serie] == ["2026-11-10", "2026-11-16"]
    assert chamadas["metricas"][0] == date(2026, 11, 10)
    assert chamadas["metricas"][1] == date(2026, 11, 16)


def test_inicio_serie_dia_e_semana_trazem_os_6_dias_anteriores_ao_inicio():
    """No gráfico, dia e semana mostram os 7 dias até o fim do filtro (ou até hoje): na segunda-feira a semana teria um ponto só."""
    from app.dominios.funil.rotas import _inicio_serie
    from app.periodo import Periodo

    assert _inicio_serie(Periodo("dia", date(2026, 11, 23), date(2026, 11, 23))) == date(2026, 11, 17)
    assert _inicio_serie(Periodo("semana", date(2026, 11, 23), date(2026, 11, 29))) == date(2026, 11, 17)
    assert _inicio_serie(Periodo("mes", date(2026, 11, 1), date(2026, 11, 30))) == date(2026, 11, 1)
