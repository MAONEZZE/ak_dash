import dataclasses
from datetime import datetime

import httpx
import pytest

from app.fontes import pipedrive
from app.periodo import TZ_SP


@pytest.fixture(autouse=True)
def _configurado(monkeypatch):
    monkeypatch.setattr(
        pipedrive,
        "settings",
        dataclasses.replace(pipedrive.settings, pipe_token="tok", pipe_base_url_v2="https://x.pipedrive.com/api/v2"),
    )


def _resposta(corpo):
    return httpx.Response(200, json=corpo, request=httpx.Request("GET", "https://x.pipedrive.com"))


def test_negocios_no_estagio_pagina_pelo_cursor(monkeypatch):
    chamadas = []
    respostas = [
        _resposta({"data": [{"id": 1}], "additional_data": {"next_cursor": "c2"}}),
        _resposta({"data": [{"id": 2}], "additional_data": {"next_cursor": None}}),
    ]

    def _get(url, params=None, headers=None, **kwargs):
        chamadas.append((url, params, headers))
        return respostas.pop(0)

    monkeypatch.setattr(pipedrive.httpx, "get", _get)

    negocios = pipedrive.negocios_no_estagio(11, datetime(2026, 11, 1, tzinfo=TZ_SP))

    assert negocios == [{"id": 1}, {"id": 2}]
    assert chamadas[0][0] == "https://x.pipedrive.com/api/v2/deals"
    assert chamadas[0][1] == {"stage_id": "11", "updated_since": "2026-11-01T03:00:00Z", "limit": "500"}
    assert chamadas[1][1]["cursor"] == "c2"
    assert chamadas[0][2] == {"x-api-token": "tok"}
