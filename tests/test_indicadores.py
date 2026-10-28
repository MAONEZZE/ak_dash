import pytest

from app.indicadores import pct_atingimento


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
