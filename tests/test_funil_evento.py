"""Testes de `dominios/funil/evento.py` — regras do Funil de Evento (Imersão)."""
from __future__ import annotations

from datetime import date

from app.dominios.funil import evento


def test_data_do_evento_e_o_dia_em_sao_paulo():
    assert evento.data_do_evento_sp("2026-12-02T16:00:00+00:00") == date(2026, 12, 2)
    assert evento.data_do_evento_sp("2026-12-03T01:00:00+00:00") == date(2026, 12, 2)
    assert evento.data_do_evento_sp("2026-11-18T22:00:00") == date(2026, 11, 18)
