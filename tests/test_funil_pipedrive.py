"""Testes de `dominios/funil/pipedrive.py` — métricas do Pipedrive nos funis LinkedIn, Instagram e SDR."""
from __future__ import annotations

import dataclasses
from datetime import date

import pytest

from app.dominios.funil import pipedrive
from app.dominios.funil.pipedrive import Fato


@pytest.fixture(autouse=True)
def _ids(monkeypatch):
    monkeypatch.setattr(
        pipedrive,
        "settings",
        dataclasses.replace(
            pipedrive.settings,
            pipe_id_pipeline_instagram=3,
            pipe_id_abordados_pipeline_linkedin=11,
            pipe_id_respondidos_pipeline_linkedin=12,
            pipe_id_abordados_pipeline_instagram=21,
            pipe_id_respondidos_pipeline_instagram=22,
            pipe_id_etiqueta_negocio_linkedin=101,
            pipe_id_etiqueta_negocio_indicacao=102,
        ),
    )


def test_criado_no_periodo_vira_numero_captado_do_canal():
    a = {"id": 1, "add_time": "2026-11-05T15:00:00Z", "pipeline_id": 1, "label_ids": [101], "owner_id": 25564860, "person_id": 501}
    # 23h do dia 04 em SP
    b = {"id": 2, "add_time": "2026-11-05T02:00:00Z", "pipeline_id": 3, "label_ids": [], "owner_id": 28932026, "person_id": 502}
    # sem etiqueta e fora do Instagram
    c = {"id": 3, "add_time": "2026-11-06T12:00:00Z", "pipeline_id": 1, "label_ids": None, "owner_id": 1, "person_id": None}
    # depois do fim
    d = {"id": 4, "add_time": "2026-12-01T12:00:00Z", "pipeline_id": 3, "label_ids": [101], "owner_id": 1, "person_id": 503}

    assert pipedrive.contar([a, b, c, d], {}, date(2026, 11, 1), date(2026, 11, 30)) == [
        Fato("numeros_captados", "linkedin", 25564860, 501, "2026-11-05"),
        Fato("numeros_captados", "instagram", 28932026, 502, "2026-11-04"),
    ]


def test_negocio_na_coluna_2_ou_3_conta_pela_data_de_entrada():
    e = {"id": 5, "stage_id": 11, "stage_change_time": "2026-11-10T13:00:00Z", "owner_id": 28932026, "person_id": 601}
    # entrou antes do início
    f = {"id": 6, "stage_id": 11, "stage_change_time": "2026-10-31T13:00:00Z", "owner_id": 28932026, "person_id": 602}
    g = {"id": 7, "stage_id": 22, "stage_change_time": "2026-11-11T13:00:00Z", "owner_id": 1, "person_id": 603}
    # sem data de entrada
    i = {"id": 9, "stage_id": 22, "stage_change_time": None, "owner_id": 1, "person_id": 605}
    # estágio não configurado
    h = {"id": 8, "stage_id": 99, "stage_change_time": "2026-11-11T13:00:00Z", "owner_id": 1, "person_id": 604}
    por_estagio = {11: [e, f], 22: [g, i], 99: [h]}

    assert pipedrive.contar([], por_estagio, date(2026, 11, 1), date(2026, 11, 30)) == [
        Fato("abordagens", "linkedin", 28932026, 601, "2026-11-10"),
        Fato("respondidos", "instagram", 1, 603, "2026-11-11"),
    ]
