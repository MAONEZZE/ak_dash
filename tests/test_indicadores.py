import pytest

from app.indicadores import falta_folga, media_necessaria, pct_atingimento


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
