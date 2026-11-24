import dataclasses
from datetime import date

import httpx
import pytest

from app.fontes import banco, supabase


def _capturar(monkeypatch, resposta=None):
    registros = []
    monkeypatch.setattr(
        banco,
        "settings",
        dataclasses.replace(banco.settings, supabase_url="https://sb.test", supabase_service_key="chave", supabase_schema="dash_new"),
    )

    def _registrar(metodo):
        def _chamada(url, **k):
            registros.append(
                {
                    "metodo": metodo,
                    "url": url,
                    "params": dict(k.get("params") or {}),
                    "json": k.get("json"),
                    "headers": k.get("headers"),
                }
            )
            return httpx.Response(200, json=resposta or [], request=httpx.Request(metodo, url))

        return _chamada

    monkeypatch.setattr(banco.httpx, "get", _registrar("GET"))
    monkeypatch.setattr(banco.httpx, "post", _registrar("POST"))
    monkeypatch.setattr(banco.httpx, "delete", _registrar("DELETE"))
    return registros


def _sem_paginacao(params):
    return {k: v for k, v in params.items() if k not in ("limit", "offset")}


@pytest.mark.parametrize(
    "leitura, tabela, params_esperados",
    [
        ("ler_usuarios_ativos", "users", {"select": "*", "active": "eq.true"}),
        ("ler_cargos_dos_usuarios", "user_cargos", {"select": "id_user,cargo"}),
        ("ler_metas", "metas", {"select": "id_user,cargo,metrica,valor_diario"}),
    ],
)
def test_leituras_de_pessoas_e_metas_mandam_a_requisicao_de_hoje(monkeypatch, leitura, tabela, params_esperados):
    registros = _capturar(monkeypatch)

    getattr(supabase, leitura)()

    assert len(registros) == 1
    requisicao = registros[0]
    assert requisicao["metodo"] == "GET"
    assert requisicao["url"] == f"https://sb.test/rest/v1/{tabela}"
    assert _sem_paginacao(requisicao["params"]) == params_esperados
    assert requisicao["headers"]["Accept-Profile"] == "dash_new"


def test_leitura_devolve_as_linhas_do_banco(monkeypatch):
    _capturar(monkeypatch, [{"id": 1}])

    assert supabase.ler_usuarios_ativos() == [{"id": 1}]


def test_ler_metricas_do_cargo_filtra_a_view_por_cargo_pessoas_e_datas(monkeypatch):
    registros = _capturar(monkeypatch)

    supabase.ler_metricas_do_cargo("sdr", [9, 14], date(2026, 11, 1), date(2026, 11, 30))

    assert len(registros) == 1
    requisicao = registros[0]
    assert requisicao["url"] == "https://sb.test/rest/v1/vw_metricas"
    assert _sem_paginacao(requisicao["params"]) == {
        "select": "data,id_user,metrica,valor,conta",
        "id_user": "in.(9,14)",
        "and": "(data.gte.2026-11-01,data.lte.2026-11-30)",
        "cargo": "eq.sdr",
    }
