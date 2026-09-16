from __future__ import annotations

from datetime import date

import pytest

from app.periodo import agora_sp, dias_uteis_decorridos, resolver_periodo, semana_iso


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


# --- granularidade "semana" (segunda a domingo, ISO)


def test_semana_iso_vai_de_segunda_a_domingo():
    p = resolver_periodo("semana", "2026-W38")
    assert (p.granularidade, p.inicio, p.fim) == ("semana", date(2026, 9, 14), date(2026, 9, 20))
    assert p.inicio.weekday() == 0 and p.fim.weekday() == 6


def test_semana_iso_do_dia_e_a_semana_que_contem_o_dia():
    assert semana_iso(date(2026, 9, 15)) == "2026-W38"
    p = resolver_periodo("semana", semana_iso(date(2026, 9, 15)))
    assert p.inicio <= date(2026, 9, 15) <= p.fim


def test_semana_virada_de_ano_usa_calendario_iso_nao_o_civil():
    # 31/12/2025 cai na semana 1 de 2026 pelo ISO — o rótulo tem que dizer 2026.
    assert semana_iso(date(2025, 12, 31)) == "2026-W01"


def test_semana_com_formato_invalido_levanta_valueerror():
    for valor in ("2026-38", "2026-W99", "abc", ""):
        with pytest.raises(ValueError):
            resolver_periodo("semana", valor)


def test_semana_tem_5_dias_uteis():
    p = resolver_periodo("semana", "2026-W38")
    assert dias_uteis_decorridos(p.inicio, p.fim, hoje=p.fim) == 5


# O corte de `buscar_eventos_proximos` precisa de um instante inequívoco:
# ingênuo, o valor seria interpretado como UTC e adiantaria o filtro em 3h.
def test_agora_sp_tem_fuso():
    agora = agora_sp()
    assert agora.tzinfo is not None
    assert agora.utcoffset() is not None
