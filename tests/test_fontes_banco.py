import dataclasses

import httpx
import pytest

from app import cache
from app.fontes import banco


def _query(tabela):
    return banco.query(tabela, url_base="https://exemplo.supabase.co", service_key="chave")


@pytest.fixture(autouse=True)
def _cache_limpo():
    cache.invalidar()
    yield
    cache.invalidar()


def _resposta(linhas):
    return httpx.Response(200, json=linhas, request=httpx.Request("GET", "https://exemplo.supabase.co"))


def test_timeout_isolado_tenta_de_novo_e_devolve_o_dado(monkeypatch):
    respostas = [httpx.ReadTimeout("lento"), _resposta([{"id": 1}])]

    def _get(*a, **k):
        r = respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(banco.httpx, "get", _get)
    assert _query("metricas_metas") == [{"id": 1}]


def test_timeout_persistente_degrada_para_vazio(monkeypatch):
    def _get(*a, **k):
        raise httpx.ReadTimeout("lento")

    monkeypatch.setattr(banco.httpx, "get", _get)
    assert _query("metricas_metas") == []


def test_resultado_de_consulta_que_falhou_nao_fica_no_cache(monkeypatch):
    fora_do_ar = True

    def _get(*a, **k):
        if fora_do_ar:
            raise httpx.ReadTimeout("lento")
        return _resposta([{"id": 1}])

    monkeypatch.setattr(banco.httpx, "get", _get)
    assert cache.obter_ou_calcular("metas", 60, lambda: _query("metricas_metas")) == []

    fora_do_ar = False
    assert cache.obter_ou_calcular("metas", 60, lambda: _query("metricas_metas")) == [{"id": 1}]


def test_resultado_de_consulta_bem_sucedida_fica_no_cache(monkeypatch):
    chamadas = []

    def _get(*a, **k):
        chamadas.append(1)
        return _resposta([{"id": 1}])

    monkeypatch.setattr(banco.httpx, "get", _get)
    cache.obter_ou_calcular("metas", 60, lambda: _query("metricas_metas"))
    cache.obter_ou_calcular("metas", 60, lambda: _query("metricas_metas"))
    assert len(chamadas) == 1


def test_schema_padrao_vem_de_settings(monkeypatch):
    monkeypatch.setattr(banco, "settings", dataclasses.replace(banco.settings, supabase_schema="dash_teste"))
    headers_recebidos = []

    def _get(*a, **k):
        headers_recebidos.append(k["headers"])
        return _resposta([])

    monkeypatch.setattr(banco.httpx, "get", _get)
    _query("users")
    assert headers_recebidos[-1]["Accept-Profile"] == "dash_teste"

    banco.query("events", schema="SED", url_base="https://exemplo.supabase.co", service_key="chave")
    assert headers_recebidos[-1]["Accept-Profile"] == "SED"


def test_tabela_que_falhou_fica_registrada_pra_virar_aviso(monkeypatch):
    def _get(*a, **k):
        return httpx.Response(404, json={"code": "PGRST205"}, request=httpx.Request("GET", "https://exemplo.supabase.co"))

    monkeypatch.setattr(banco.httpx, "get", _get)
    banco.iniciar_registro_de_falhas()
    assert _query("vw_metricas") == []
    assert _query("vw_metricas") == []
    assert banco.tabelas_com_falha() == ["vw_metricas"]

    banco.iniciar_registro_de_falhas()
    assert banco.tabelas_com_falha() == []


def test_upsert_envia_linhas_com_on_conflict_e_merge(monkeypatch):
    monkeypatch.setattr(
        banco,
        "settings",
        dataclasses.replace(
            banco.settings,
            supabase_url="https://exemplo.supabase.co",
            supabase_service_key="chave",
            supabase_schema="dash2",
        ),
    )
    chamadas = []

    def _post(url, **kwargs):
        chamadas.append((url, kwargs))
        return httpx.Response(201, request=httpx.Request("POST", "https://exemplo.supabase.co"))

    monkeypatch.setattr(banco.httpx, "post", _post)
    banco.upsert("metricas_sellers", [{"id_user": 1, "fups": 3}], on_conflict="key_data_ref_user")

    assert len(chamadas) == 1
    url, kwargs = chamadas[0]
    assert url == "https://exemplo.supabase.co/rest/v1/metricas_sellers"
    assert kwargs["params"] == {"on_conflict": "key_data_ref_user"}
    assert kwargs["json"] == [{"id_user": 1, "fups": 3}]
    assert kwargs["headers"]["apikey"] == "chave"
    assert kwargs["headers"]["Authorization"] == "Bearer chave"
    assert kwargs["headers"]["Content-Profile"] == "dash2"
    assert kwargs["headers"]["Prefer"] == "resolution=merge-duplicates,return=minimal"


def test_upsert_sem_linhas_nao_faz_chamada(monkeypatch):
    def _post(*a, **k):
        raise AssertionError("não deveria chamar o Supabase")

    monkeypatch.setattr(banco.httpx, "post", _post)
    banco.upsert("metricas_sellers", [], on_conflict="key_data_ref_user")


def test_upsert_propaga_erro_do_postgrest(monkeypatch):
    monkeypatch.setattr(
        banco,
        "settings",
        dataclasses.replace(
            banco.settings,
            supabase_url="https://exemplo.supabase.co",
            supabase_service_key="chave",
            supabase_schema="dash2",
        ),
    )

    def _post(*a, **k):
        return httpx.Response(
            400,
            json={"message": "column x does not exist"},
            request=httpx.Request("POST", "https://exemplo.supabase.co"),
        )

    monkeypatch.setattr(banco.httpx, "post", _post)
    with pytest.raises(httpx.HTTPStatusError):
        banco.upsert("metricas_sellers", [{"id_user": 1}], on_conflict="key_data_ref_user")
