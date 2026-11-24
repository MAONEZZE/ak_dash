import dataclasses
from datetime import datetime

import httpx
import pytest

from app.fontes import banco, sed
from app.periodo import TZ_SP


def _capturar(monkeypatch, resposta=None):
    monkeypatch.setattr(
        sed,
        "settings",
        dataclasses.replace(
            sed.settings,
            supabase_inscricoes_url="https://sed.test",
            supabase_inscricoes_service_key="chave-sed",
            supabase_inscricoes_schema="SED",
        ),
    )
    monkeypatch.setattr(
        banco,
        "settings",
        dataclasses.replace(
            banco.settings,
            supabase_inscricoes_url="https://sed.test",
            supabase_inscricoes_service_key="chave-sed",
            supabase_inscricoes_schema="SED",
        ),
    )
    registros = []

    def _get(url, params, headers, timeout):
        registros.append(
            {
                "url": url,
                "select": params["select"],
                "filtros": {k: v for k, v in params.items() if k not in ("select", "limit", "offset")},
                "headers": headers,
            }
        )
        return httpx.Response(200, json=resposta or [], request=httpx.Request("GET", url))

    monkeypatch.setattr(banco.httpx, "get", _get)
    return registros


agora = datetime(2026, 11, 17, 10, 30, tzinfo=TZ_SP)


@pytest.mark.parametrize(
    "chamar, select, filtros",
    [
        pytest.param(
            lambda: sed.ler_eventos_entre(
                datetime(2026, 9, 1, tzinfo=TZ_SP), datetime(2026, 10, 1, tzinfo=TZ_SP), "confraria akeel", 50
            ),
            "id,title,event_date,capacity",
            {
                "and": '(event_date.gte."2026-09-01T03:00:00Z",event_date.lt."2026-10-01T03:00:00Z")',
                "order": "event_date.asc",
                "title": "ilike.*confraria akeel*",
            },
            id="ler_eventos_entre",
        ),
        pytest.param(
            lambda: sed.ler_eventos_a_partir_de(agora, 1),
            "id,title,event_date,capacity",
            {"and": '(event_date.gte."2026-11-17T13:30:00Z")', "order": "event_date.asc"},
            id="ler_eventos_a_partir_de",
        ),
        pytest.param(
            lambda: sed.ler_eventos_a_partir_de(agora, 50, titulo_contem="imers", colunas="id,title,event_date"),
            "id,title,event_date",
            {
                "and": '(event_date.gte."2026-11-17T13:30:00Z")',
                "order": "event_date.asc",
                "title": "ilike.*imers*",
            },
            id="ler_eventos_a_partir_de_com_titulo",
        ),
        pytest.param(
            lambda: sed.ler_imersoes("imers", 50),
            "id,title,event_date",
            {"title": "ilike.*imers*", "event_date": "not.is.null", "order": "event_date.desc"},
            id="ler_imersoes",
        ),
    ],
)
def test_funcoes_de_eventos_consultam_o_sed_com_os_filtros_de_hoje(monkeypatch, chamar, select, filtros):
    registros = _capturar(monkeypatch)

    chamar()

    assert len(registros) == 1
    registro = registros[0]
    assert registro["url"] == "https://sed.test/rest/v1/events"
    assert registro["select"] == select
    assert registro["filtros"] == filtros
    assert registro["headers"]["apikey"] == "chave-sed"
    assert registro["headers"]["Accept-Profile"] == "SED"


def test_ler_evento_por_id_filtra_pelo_id(monkeypatch):
    registros = _capturar(monkeypatch)

    sed.ler_evento_por_id("e1")

    assert len(registros) == 1
    assert registros[0]["select"] == "id,title,event_date,capacity"
    assert registros[0]["filtros"] == {"and": '(id.eq."e1")', "order": "event_date.asc"}


@pytest.mark.parametrize(
    "chamar, select, filtros",
    [
        pytest.param(
            lambda: sed.ler_inscricoes_dos_eventos(["e1", "e2"]),
            "event_id,status",
            {"event_id": 'in.("e1","e2")'},
            id="ler_inscricoes_dos_eventos",
        ),
        pytest.param(
            lambda: sed.ler_inscricoes_no_periodo(
                "e1", datetime(2026, 11, 1, tzinfo=TZ_SP), datetime(2026, 12, 1, tzinfo=TZ_SP)
            ),
            "id",
            {
                "event_id": "eq.e1",
                "status": "in.(approved,pending)",
                "and": '(created_at.gte."2026-11-01T03:00:00Z",created_at.lt."2026-12-01T03:00:00Z")',
            },
            id="ler_inscricoes_no_periodo",
        ),
        pytest.param(
            lambda: sed.ler_comparecimentos("e1"),
            "id",
            {"event_id": "eq.e1", "attended": "is.true"},
            id="ler_comparecimentos",
        ),
    ],
)
def test_funcoes_de_inscricoes_consultam_registrations_com_os_filtros_de_hoje(monkeypatch, chamar, select, filtros):
    registros = _capturar(monkeypatch)

    chamar()

    assert len(registros) == 1
    registro = registros[0]
    assert registro["url"] == "https://sed.test/rest/v1/registrations"
    assert registro["select"] == select
    assert registro["filtros"] == filtros
    assert registro["headers"]["Accept-Profile"] == "SED"


def test_falha_no_sed_degrada_para_vazio_com_aviso_da_tabela(monkeypatch):
    _capturar(monkeypatch)
    monkeypatch.setattr(
        banco.httpx,
        "get",
        lambda url, params, headers, timeout: httpx.Response(500, json={}, request=httpx.Request("GET", "https://sed.test")),
    )
    banco.iniciar_registro_de_falhas()

    assert sed.ler_comparecimentos("e1") == []
    assert banco.tabelas_com_falha() == ["registrations"]
