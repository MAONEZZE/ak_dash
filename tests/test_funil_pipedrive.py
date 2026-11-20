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
