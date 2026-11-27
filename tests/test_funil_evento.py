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


def test_conta_negocios_da_etiqueta_sem_olhar_data():
    ids = {130}
    inscritos = [
        {"label_ids": [130]},
        {"label_ids": [999]},
    ]
    agendados = [
        {"label_ids": [130], "stage_change_time": "2025-01-01T10:00:00Z"},
        {"label_ids": [999]},
    ]
    realizados = [
        {"label_ids": [130, 5]},
        {"label_ids": None},
    ]
    ganhos = [
        {"label_ids": [130], "won_time": "2024-06-01T10:00:00Z"},
        {"label_ids": [130]},
    ]
    assert evento.contar_pipedrive_evento(ids, inscritos, agendados, realizados, ganhos) == {
        "inscritos": 1,
        "onboarding_agendado": 1,
        "onboarding_realizado": 1,
        "vendas": 2,
    }


def test_almoco_pago_conta_198_ou_199_so_com_a_etiqueta_do_evento():
    ids = {130}
    chave = "k"
    realizados = [
        {"label_ids": [130], "custom_fields": {"k": [198]}},
        {"label_ids": [130], "custom_fields": {"k": [199]}},
        {"label_ids": [130], "custom_fields": {"k": [198, 201]}},
        {"label_ids": [130], "custom_fields": {"k": [200]}},
        {"label_ids": [130], "custom_fields": {"k": None}},
        {"label_ids": [130]},
        {"label_ids": [999], "custom_fields": {"k": [198]}},
    ]
    assert evento.contar_almocos_pagos(ids, realizados, chave) == 3


def test_buscar_pipedrive_evento_conta_inscritos_e_onboardings_com_a_etiqueta_e_ganhos_desde_180_dias_antes(monkeypatch):
    monkeypatch.setattr(
        evento,
        "settings",
        dataclasses.replace(
            evento.settings,
            pipe_id_inscrito_pipeline_principal=7,
            pipe_id_onboarding_agendado_pipeline_principal=44,
            pipe_id_onboarding_realizado_pipeline_principal=46,
        ),
    )
    monkeypatch.setattr(evento.api, "etiquetas_de_negocio", lambda: {130: "imersão_02/12", 131: "imersão_30/03"})
    estagios_pedidos = []
    ganhos_pedidos = []

    def no_estagio_atual(id_estagio):
        estagios_pedidos.append(id_estagio)
        if id_estagio == 7:
            return [{"label_ids": [130]}, {"label_ids": [130, 5]}, {"label_ids": [131]}]
        if id_estagio == 44:
            return [{"label_ids": [130]}]
        return [{"label_ids": [131]}]

    def ganhos_desde(desde):
        ganhos_pedidos.append(desde)
        return [{"label_ids": [130]}]

    monkeypatch.setattr(evento.api, "negocios_atuais_no_estagio", no_estagio_atual)
    monkeypatch.setattr(evento.api, "negocios_ganhos_desde", ganhos_desde)

    resultado = evento.buscar_pipedrive_evento(date(2026, 12, 2))

    assert resultado == {"inscritos": 2, "onboarding_agendado": 1, "onboarding_realizado": 0, "vendas": 1}
    assert estagios_pedidos == [7, 44, 46]
    assert ganhos_pedidos == [datetime(2026, 6, 5, tzinfo=TZ_SP)]


def test_buscar_almocos_pagos_le_quem_esta_hoje_em_onboarding_realizado(monkeypatch):
    monkeypatch.setattr(
        evento,
        "settings",
        dataclasses.replace(
            evento.settings,
            pipe_id_onboarding_realizado_pipeline_principal=46,
            pipe_id_campo_almoco="k",
        ),
    )
    monkeypatch.setattr(evento.api, "etiquetas_de_negocio", lambda: {130: "imersão_02/12"})
    estagios_pedidos = []

    def no_estagio_atual(id_estagio):
        estagios_pedidos.append(id_estagio)
        return [
            {"label_ids": [130], "custom_fields": {"k": [198]}},
            {"label_ids": [130], "custom_fields": {"k": [200]}},
        ]

    monkeypatch.setattr(evento.api, "negocios_atuais_no_estagio", no_estagio_atual)

    assert evento.buscar_almocos_pagos(date(2026, 12, 2)) == 1
    assert estagios_pedidos == [46]


def test_pipedrive_fora_do_ar_zera_e_registra_falha(monkeypatch):
    def fora():
        raise evento.api.PipedriveIndisponivel("timeout")

    monkeypatch.setattr(evento.api, "etiquetas_de_negocio", fora)
    banco.iniciar_registro_de_falhas()

    resultado = evento.buscar_pipedrive_evento(date(2026, 12, 2))

    assert resultado == {"inscritos": 0, "onboarding_agendado": 0, "onboarding_realizado": 0, "vendas": 0}
    assert banco.tabelas_com_falha() == ["pipedrive"]


def test_almocos_pagos_com_pipedrive_fora_do_ar_zera_e_registra_falha(monkeypatch):
    monkeypatch.setattr(
        evento,
        "settings",
        dataclasses.replace(
            evento.settings,
            pipe_id_onboarding_realizado_pipeline_principal=46,
            pipe_id_campo_almoco="k",
        ),
    )

    def fora():
        raise evento.api.PipedriveIndisponivel("fora")

    monkeypatch.setattr(evento.api, "etiquetas_de_negocio", fora)
    banco.iniciar_registro_de_falhas()

    resultado = evento.buscar_almocos_pagos(date(2026, 12, 2))

    assert resultado == 0
    assert "pipedrive" in banco.tabelas_com_falha()
