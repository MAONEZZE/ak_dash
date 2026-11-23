"""Testes de `dominios/funil/evento.py` — regras do Funil de Evento (Imersão)."""
from __future__ import annotations

import dataclasses
from datetime import date, datetime

from app.dominios.funil import evento
from app.fontes import banco
from app.periodo import TZ_SP


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


def test_conta_so_negocios_da_etiqueta_com_data_no_periodo():
    ids = {130}
    agendados = [
        {"label_ids": [130], "stage_change_time": "2026-11-10T13:00:00Z"},
        {"label_ids": [131], "stage_change_time": "2026-11-10T13:00:00Z"},
        {"label_ids": [130], "stage_change_time": "2026-10-31T13:00:00Z"},
        {"label_ids": [130], "stage_change_time": "2026-12-01T02:00:00Z"},
    ]
    realizados = [
        {"label_ids": [130], "stage_change_time": "2026-11-05T12:00:00Z"},
        {"label_ids": None, "stage_change_time": "2026-11-05T12:00:00Z"},
    ]
    ganhos = [
        {"label_ids": [130, 123], "won_time": "2026-11-20T15:00:00Z"},
        {"label_ids": [130], "won_time": None},
        {"label_ids": [130], "won_time": "2026-12-01T12:00:00Z"},
    ]
    assert evento.contar_pipedrive_evento(ids, agendados, realizados, ganhos, date(2026, 11, 1), date(2026, 11, 30)) == {
        "onboarding_agendado": 2,
        "onboarding_realizado": 1,
        "vendas": 1,
    }


def test_buscar_pipedrive_evento_busca_as_colunas_de_onboarding_desde_o_inicio_do_periodo(monkeypatch):
    monkeypatch.setattr(
        evento,
        "settings",
        dataclasses.replace(
            evento.settings,
            pipe_id_onboarding_agendado_pipeline_linkedin=44,
            pipe_id_onboarding_realizado_pipeline_linkedin=46,
        ),
    )
    monkeypatch.setattr(evento.api, "etiquetas_de_negocio", lambda: {130: "imersão_02/12", 131: "imersão_30/03"})
    estagios_pedidos = []
    ganhos_pedidos = []

    def no_estagio(id_estagio, desde):
        estagios_pedidos.append((id_estagio, desde))
        if id_estagio == 44:
            return [{"label_ids": [130], "stage_change_time": "2026-11-10T13:00:00Z"}]
        return [{"label_ids": [131], "stage_change_time": "2026-11-10T13:00:00Z"}]

    def ganhos_desde(desde):
        ganhos_pedidos.append(desde)
        return [{"label_ids": [130], "won_time": "2026-11-20T15:00:00Z"}]

    monkeypatch.setattr(evento.api, "negocios_no_estagio", no_estagio)
    monkeypatch.setattr(evento.api, "negocios_ganhos_desde", ganhos_desde)

    resultado = evento.buscar_pipedrive_evento(date(2026, 12, 2), date(2026, 11, 1), date(2026, 11, 30))

    desde = datetime(2026, 11, 1, tzinfo=TZ_SP)
    assert resultado == {"onboarding_agendado": 1, "onboarding_realizado": 0, "vendas": 1}
    assert estagios_pedidos == [(44, desde), (46, desde)]
    assert ganhos_pedidos == [desde]


def test_pipedrive_fora_do_ar_zera_e_registra_falha(monkeypatch):
    def fora():
        raise evento.api.PipedriveIndisponivel("timeout")

    monkeypatch.setattr(evento.api, "etiquetas_de_negocio", fora)
    banco.iniciar_registro_de_falhas()

    resultado = evento.buscar_pipedrive_evento(date(2026, 12, 2), date(2026, 11, 1), date(2026, 11, 30))

    assert resultado == {"onboarding_agendado": 0, "onboarding_realizado": 0, "vendas": 0}
    assert banco.tabelas_com_falha() == ["pipedrive"]
