from datetime import date, datetime, time

import pytest

from app.indicadores import calcular_indicadores, falta_folga, media_necessaria, pct_atingimento, previsao
from app.periodo import Periodo, TZ_SP


@pytest.mark.parametrize(
    ("realizado", "meta", "esperado"),
    [
        (30, 88, 34.1),
        (88, 88, 100.0),
        (100, 88, 113.6),
        (5, None, None),
        (5, 0, None),
    ],
)
def test_pct_atingimento(realizado, meta, esperado):
    assert pct_atingimento(realizado, meta) == esperado


@pytest.mark.parametrize(
    ("realizado", "meta", "esperado"),
    [
        (30, 88, {"tipo": "falta", "valor": 58}),
        (88, 88, {"tipo": "folga", "valor": 0}),
        (100, 88, {"tipo": "folga", "valor": 12}),
        (5, None, None),
        (5, 0, None),
    ],
)
def test_falta_folga(realizado, meta, esperado):
    assert falta_folga(realizado, meta) == esperado


@pytest.mark.parametrize(
    ("realizado", "meta", "restantes", "unidade", "esperado"),
    [
        (30, 88, 12, "dia", {"valor": 4.8, "unidade": "dia", "situacao": "pendente"}),
        (10, 40, 3.5, "hora", {"valor": 8.6, "unidade": "hora", "situacao": "pendente"}),
        (88, 88, 12, "dia", {"valor": None, "unidade": "dia", "situacao": "meta_batida"}),
        (30, 88, 0, "dia", {"valor": None, "unidade": "dia", "situacao": "periodo_encerrado"}),
        (30, 88, 0.0, "hora", {"valor": None, "unidade": "hora", "situacao": "expediente_encerrado"}),
        (5, None, 12, "dia", None),
        (5, 0, 12, "dia", None),
    ],
)
def test_media_necessaria(realizado, meta, restantes, unidade, esperado):
    assert media_necessaria(realizado, meta, restantes, unidade) == esperado


@pytest.mark.parametrize(
    ("realizado", "decorridos", "total", "esperado"),
    [
        (30, 10, 22, 66.0),
        (7, 3, 22, 51.3),
        (30, 0, 22, None),
    ],
)
def test_previsao(realizado, decorridos, total, esperado):
    assert previsao(realizado, decorridos, total) == esperado


def test_calcular_indicadores_no_dia_usa_horas_restantes():
    periodo = Periodo("dia", date(2026, 10, 28), date(2026, 10, 28))
    dias_uteis = {"decorridos": 1, "total": 1}
    agora = datetime(2026, 10, 28, 15, 30, tzinfo=TZ_SP)

    resultado = calcular_indicadores(10, 40, periodo, dias_uteis, agora, time(10, 0), time(19, 0))

    assert resultado == {
        "pct_atingimento": 25.0,
        "falta_folga": {"tipo": "falta", "valor": 30},
        "horas_restantes": 3.5,
        "media_necessaria": {"valor": 8.6, "unidade": "hora", "situacao": "pendente"},
        "previsao": None,
    }


def test_calcular_indicadores_na_semana_e_no_mes_usa_dias_restantes():
    agora = datetime(2026, 10, 28, 15, 30, tzinfo=TZ_SP)
    expediente = (time(10, 0), time(19, 0))

    semana = calcular_indicadores(
        10, 20, Periodo("semana", date(2026, 10, 26), date(2026, 11, 1)), {"decorridos": 3, "total": 5}, agora, *expediente
    )
    mes = calcular_indicadores(
        30, 88, Periodo("mes", date(2026, 9, 1), date(2026, 9, 30)), {"decorridos": 10, "total": 22}, agora, *expediente
    )
    mes_sem_meta = calcular_indicadores(
        0, None, Periodo("mes", date(2026, 9, 1), date(2026, 9, 30)), {"decorridos": 10, "total": 22}, agora, *expediente
    )

    assert semana == {
        "pct_atingimento": 50.0,
        "falta_folga": {"tipo": "falta", "valor": 10},
        "horas_restantes": None,
        "media_necessaria": {"valor": 5.0, "unidade": "dia", "situacao": "pendente"},
        "previsao": None,
    }
    assert mes == {
        "pct_atingimento": 34.1,
        "falta_folga": {"tipo": "falta", "valor": 58},
        "horas_restantes": None,
        "media_necessaria": {"valor": 4.8, "unidade": "dia", "situacao": "pendente"},
        "previsao": 66.0,
    }
    assert mes_sem_meta == {
        "pct_atingimento": None,
        "falta_folga": None,
        "horas_restantes": None,
        "media_necessaria": None,
        "previsao": 0.0,
    }
