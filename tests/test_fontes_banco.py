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
