"""Smoke test de integração: sobe o app de verdade (TestClient) e bate em

cada rota — pega erro de fiação (import errado, nome de setting trocado,
etc.) que os testes unitários por módulo não veem porque nunca passam pelas
rotas do FastAPI. Toda I/O de banco é substituída por `query()` monkeypatched.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app import cache
from app import cargos as cargos_mod
from app import metas as metas_mod
from app.auth import exigir_usuario
from app.dominios.comercial import banco as comercial_banco_mod
from app.dominios.financeiro import banco as financeiro_banco_mod
from app.dominios.geral import banco as geral_banco_mod
from app.dominios.pessoas import banco as pessoas_banco_mod
from app.main import app

# O cargo vem de `users.id_cargo` -> `dash.metricas_cargo`, não mais de uma
# coluna de texto em `users`.
_USERS = [
    {"id": 9, "nome": "Nathan", "id_cargo": 2, "email": "nathan@x.com", "imagem_url": None, "active": True},
    {"id": 1, "nome": "Jacob", "id_cargo": 1, "email": "jacob@x.com", "imagem_url": None, "active": True},
]
_CARGOS = [{"id": 1, "cargo": "closer"}, {"id": 2, "cargo": "sdr"}, {"id": 3, "cargo": "empresa"}]


def _fake_query(tabela, filtros=None, schema="dash", colunas="*", **kwargs):
    if tabela == "users":
        return _USERS
    if tabela == "metricas_cargo":
        return _CARGOS
    return []


def _sobrescrever_query(monkeypatch) -> None:
    for mod in (pessoas_banco_mod, comercial_banco_mod, geral_banco_mod, financeiro_banco_mod, metas_mod, cargos_mod):
        monkeypatch.setattr(mod, "query", _fake_query)


def _client(monkeypatch) -> TestClient:
    _sobrescrever_query(monkeypatch)
    cache.invalidar()
    app.dependency_overrides[exigir_usuario] = lambda: {"sub": "dev"}
    client = TestClient(app)
    return client


def test_saude():
    assert TestClient(app).get("/saude").status_code == 200


def test_pessoas_200(monkeypatch):
    resposta = _client(monkeypatch).get("/pessoas")
    assert resposta.status_code == 200
    assert len(resposta.json()) == 2


def test_comercial_sdr_200(monkeypatch):
    resposta = _client(monkeypatch).get("/comercial/sdr", params={"granularidade": "mes", "periodo": "2026-09"})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["periodo"]["inicio"] == "2026-09-01"
    assert len(corpo["pessoas"]) == 1  # só o Nathan é sdr


def test_comercial_closer_200(monkeypatch):
    resposta = _client(monkeypatch).get("/comercial/closer", params={"granularidade": "mes", "periodo": "2026-09"})
    assert resposta.status_code == 200


def test_comercial_400_parametro_invalido(monkeypatch):
    resposta = _client(monkeypatch).get("/comercial/sdr", params={"granularidade": "mes", "periodo": "2026-13"})
    assert resposta.status_code == 400
    assert resposta.json()["erro"]["codigo"] == "parametro_invalido"


def test_geral_200_periodo_atual(monkeypatch):
    resposta = _client(monkeypatch).get("/geral")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert len(corpo["cards"]) == 6
    assert corpo["eventos"] == []  # `events` vazia no fake de query
    assert len(corpo["pessoas"]) == 2


def test_geral_400_periodo_invalido(monkeypatch):
    resposta = _client(monkeypatch).get("/geral", params={"periodo": "2026-99"})
    assert resposta.status_code == 400


def test_financeiro_200_periodo_atual(monkeypatch):
    resposta = _client(monkeypatch).get("/financeiro", params={"granularidade": "mes"})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["vendas"] == []  # `metricas_faturamento` vazia no fake de query


def test_financeiro_400_periodo_inteiramente_no_futuro(monkeypatch):
    # `hoje_sp()` é real (não mockado) — dezembro de qualquer ano futuro
    # próximo cai sempre depois de hoje.
    resposta = _client(monkeypatch).get("/financeiro", params={"granularidade": "mes", "periodo": "2099-12"})
    assert resposta.status_code == 400
    assert resposta.json()["erro"]["codigo"] == "periodo_no_futuro"


def test_sem_token_401(monkeypatch):
    _sobrescrever_query(monkeypatch)
    cache.invalidar()
    app.dependency_overrides.pop(exigir_usuario, None)
    resposta = TestClient(app).get("/geral")
    assert resposta.status_code == 401
