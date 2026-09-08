from __future__ import annotations

from datetime import date

import pytest

from app.periodo import dias_uteis_decorridos, resolver_periodo


def test_resolver_periodo_dia():
    p = resolver_periodo("dia", "2026-04-15")
    assert p.inicio == p.fim == date(2026, 4, 15)


def test_resolver_periodo_mes():
    p = resolver_periodo("mes", "2026-04")
    assert p.inicio == date(2026, 4, 1)
    assert p.fim == date(2026, 4, 30)


def test_resolver_periodo_ano():
    p = resolver_periodo("ano", "2026")
    assert p.inicio == date(2026, 1, 1)
    assert p.fim == date(2026, 12, 31)


def test_resolver_periodo_invalido_levanta_value_error():
    with pytest.raises(ValueError):
        resolver_periodo("mes", "2026-04-15")  # granularidade mes mas formato de dia
    with pytest.raises(ValueError):
        resolver_periodo("semana", "2026-04")  # granularidade inexistente


def test_dias_uteis_decorridos_sem_contar_futuro():
    # Abril/2026: dia 1 é quarta-feira. Pedindo o mês inteiro mas com "hoje"
    # no dia 3 (sexta), só conta seg/qua/qui/sex = 3 dias úteis decorridos.
    dias = dias_uteis_decorridos(date(2026, 4, 1), date(2026, 4, 30), hoje=date(2026, 4, 3))
    assert dias == 3


def test_dias_uteis_decorridos_mes_inteiro_ja_passado():
    # Abril/2026 completo: 22 dias úteis.
    dias = dias_uteis_decorridos(date(2026, 4, 1), date(2026, 4, 30), hoje=date(2026, 4, 30))
    assert dias == 22


def test_dias_uteis_decorridos_periodo_futuro_e_zero():
    dias = dias_uteis_decorridos(date(2026, 5, 1), date(2026, 5, 31), hoje=date(2026, 4, 3))
    assert dias == 0
