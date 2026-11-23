"""Testes de `dominios/funil/evento.py` — regras do Funil de Evento (Imersão)."""
from __future__ import annotations

from datetime import date

from app.dominios.funil import evento


def test_data_do_evento_e_o_dia_em_sao_paulo():
    assert evento.data_do_evento_sp("2026-12-02T16:00:00+00:00") == date(2026, 12, 2)
    assert evento.data_do_evento_sp("2026-12-03T01:00:00+00:00") == date(2026, 12, 2)
    assert evento.data_do_evento_sp("2026-11-18T22:00:00") == date(2026, 11, 18)


def test_etiqueta_do_evento_casa_sem_maiuscula_acento_e_com_ano_opcional():
    etiquetas = {
        130: "imersão_02/12",
        157: "Imersão_08/12",
        189: "IMERSÃO_17/11",
        161: "Imersão_23/09/2026",
        162: "Imersão_02/12/2025",
        128: "Prosp_Evento",
        152: "CONFRARIA_02/12",
    }
    assert evento.ids_etiquetas_do_evento(etiquetas, date(2026, 12, 2)) == {130}
    assert evento.ids_etiquetas_do_evento(etiquetas, date(2026, 11, 17)) == {189}
    assert evento.ids_etiquetas_do_evento(etiquetas, date(2026, 9, 23)) == {161}
