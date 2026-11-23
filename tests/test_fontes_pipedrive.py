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
        dataclasses.replace(
            pipedrive.settings,
            pipe_token="tok",
            pipe_base_url_v2="https://x.pipedrive.com/api/v2",
            pipe_base_url_v1="https://x.pipedrive.com/api/v1",
        ),
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


def test_negocios_criados_desde_para_no_primeiro_anterior_ao_inicio(monkeypatch):
    chamadas = []
    respostas = [
        _resposta({"data": [{"id": 3, "add_time": "2026-11-02T12:00:00Z"}, {"id": 2, "add_time": "2026-11-01T03:00:00Z"}], "additional_data": {"next_cursor": "c2"}}),
        _resposta({"data": [{"id": 1, "add_time": "2026-11-01T02:59:59Z"}, {"id": 0, "add_time": "2026-10-20T10:00:00Z"}], "additional_data": {"next_cursor": "c3"}}),
    ]

    def _get(url, params=None, headers=None, **kwargs):
        chamadas.append((url, params, headers))
        if not respostas:
            raise AssertionError("não devia pedir mais páginas")
        return respostas.pop(0)

    monkeypatch.setattr(pipedrive.httpx, "get", _get)

    negocios = pipedrive.negocios_criados_desde(datetime(2026, 11, 1, tzinfo=TZ_SP))

    assert [n["id"] for n in negocios] == [3, 2]
    assert len(chamadas) == 2
    assert chamadas[0][1] == {"sort_by": "add_time", "sort_direction": "desc", "limit": "500"}


def test_etiquetas_das_pessoas_em_lotes_de_100(monkeypatch):
    chamadas = []

    def _get(url, params=None, headers=None, **kwargs):
        chamadas.append((url, params))
        ids = params["ids"].split(",")
        corpo = {
            "data": [{"id": int(i), "label_ids": None if i == "7" else [int(i) * 10]} for i in ids],
            "additional_data": {"next_cursor": None},
        }
        return _resposta(corpo)

    monkeypatch.setattr(pipedrive.httpx, "get", _get)

    resultado = pipedrive.etiquetas_das_pessoas(list(range(1, 151)) + [7, 7])

    assert [c[0] for c in chamadas] == ["https://x.pipedrive.com/api/v2/persons"] * 2
    assert chamadas[0][1]["ids"] == ",".join(str(i) for i in range(1, 101))
    assert chamadas[1][1]["ids"] == ",".join(str(i) for i in range(101, 151))
    assert len(resultado) == 150
    assert resultado[1] == (10,)
    assert resultado[150] == (1500,)
    assert resultado[7] == ()

    chamadas.clear()
    assert pipedrive.etiquetas_das_pessoas([]) == {}
    assert chamadas == []


def test_etiquetas_de_negocio_le_as_opcoes_do_campo_label_na_v1(monkeypatch):
    chamadas = []

    def _get(url, params=None, headers=None, **kwargs):
        chamadas.append(url)
        return _resposta({"data": [{"key": "title"}, {"key": "label", "options": [{"id": 130, "label": "imersão_02/12"}, {"id": 189, "label": "IMERSÃO_17/11"}]}]})

    monkeypatch.setattr(pipedrive.httpx, "get", _get)

    assert pipedrive.etiquetas_de_negocio() == {130: "imersão_02/12", 189: "IMERSÃO_17/11"}
    assert chamadas == ["https://x.pipedrive.com/api/v1/dealFields"]


def test_sem_configuracao_ou_com_erro_sobe_pipedrive_indisponivel(monkeypatch):
    monkeypatch.setattr(pipedrive, "settings", dataclasses.replace(pipedrive.settings, pipe_token=None))

    def _nao_deve_chamar(url, params=None, headers=None, **kwargs):
        raise AssertionError("httpx.get não devia ser chamado sem configuração")

    monkeypatch.setattr(pipedrive.httpx, "get", _nao_deve_chamar)

    with pytest.raises(pipedrive.PipedriveIndisponivel):
        pipedrive.negocios_no_estagio(11, datetime(2026, 11, 1, tzinfo=TZ_SP))

    monkeypatch.setattr(pipedrive, "settings", dataclasses.replace(pipedrive.settings, pipe_token="tok", pipe_base_url_v2="https://x.pipedrive.com/api/v2"))

    monkeypatch.setattr(
        pipedrive.httpx,
        "get",
        lambda url, params=None, headers=None, **kwargs: httpx.Response(401, json={"success": False}, request=httpx.Request("GET", "https://x.pipedrive.com")),
    )

    with pytest.raises(pipedrive.PipedriveIndisponivel):
        pipedrive.negocios_no_estagio(11, datetime(2026, 11, 1, tzinfo=TZ_SP))

    def _timeout(url, params=None, headers=None, **kwargs):
        raise httpx.ReadTimeout("lento")

    monkeypatch.setattr(pipedrive.httpx, "get", _timeout)

    with pytest.raises(pipedrive.PipedriveIndisponivel):
        pipedrive.negocios_no_estagio(11, datetime(2026, 11, 1, tzinfo=TZ_SP))
