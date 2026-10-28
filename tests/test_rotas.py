"""Smoke test de integração: sobe o app de verdade (TestClient) e bate em

cada rota — pega erro de fiação (import errado, nome de setting trocado,
etc.) que os testes unitários por módulo não veem porque nunca passam pelas
rotas do FastAPI. Toda I/O de banco é substituída por `query()` monkeypatched.
"""
from __future__ import annotations

import threading
from datetime import date

from fastapi.testclient import TestClient

from app import cache
from app import metas as metas_mod
from app import workers
from app.auth import exigir_usuario
from app.dominios.comercial import banco as comercial_banco_mod
from app.dominios.financeiro import banco as financeiro_banco_mod
from app.dominios.geral import banco as geral_banco_mod
from app.dominios.geral import rotas as geral_rotas_mod
from app.dominios.pessoas import banco as pessoas_banco_mod
from app.main import app

# Pessoas vêm de `dash2.users` + `dash2.user_cargos` (um vínculo por cargo).
_USERS = [
    {"id": 9, "nome": "Nathan", "email": "nathan@x.com", "imagem_url": None, "active": True},
    {"id": 1, "nome": "Jacob", "email": "jacob@x.com", "imagem_url": None, "active": True},
]
_USER_CARGOS = [{"id_user": 9, "cargo": "sdr"}, {"id_user": 1, "cargo": "closer"}]


def _fake_query(tabela, filtros=None, schema="dash", colunas="*", **kwargs):
    if tabela == "users":
        return _USERS
    if tabela == "user_cargos":
        return _USER_CARGOS
    return []


def _sobrescrever_query(monkeypatch) -> None:
    for mod in (pessoas_banco_mod, comercial_banco_mod, geral_banco_mod, financeiro_banco_mod, metas_mod):
        monkeypatch.setattr(mod, "query", _fake_query)


def _client(monkeypatch) -> TestClient:
    _sobrescrever_query(monkeypatch)
    cache.invalidar()
    app.dependency_overrides[exigir_usuario] = lambda: {"sub": "dev"}
    client = TestClient(app)
    return client


def test_saude():
    assert TestClient(app).get("/saude").status_code == 200


def test_saude_mostra_status_dos_workers(monkeypatch):
    w = workers.Worker(workers.PLANILHAS[0], "ID", lambda _id: [])
    w.status = {"ultima_leitura_ok": "2026-10-27T10:00:00-03:00", "ultimo_erro": None}
    monkeypatch.setattr(workers, "ATIVOS", [w])
    resposta = TestClient(app).get("/saude")
    assert resposta.status_code == 200
    assert resposta.json() == {
        "status": "ok",
        "workers": {"sellers": {"ultima_leitura_ok": "2026-10-27T10:00:00-03:00", "ultimo_erro": None}},
    }


def test_lifespan_inicia_e_para_os_workers(monkeypatch):
    eventos: list[threading.Event] = []
    monkeypatch.setattr(workers, "iniciar", lambda config: eventos.append(threading.Event()) or eventos[-1])

    with TestClient(app) as client:
        client.get("/saude")

    assert len(eventos) == 1
    assert eventos[0].is_set() is True


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
    assert set(corpo["dias_uteis"]) == {"decorridos", "total"}


def test_comercial_closer_200(monkeypatch):
    resposta = _client(monkeypatch).get("/comercial/closer", params={"granularidade": "mes", "periodo": "2026-09"})
    assert resposta.status_code == 200


def test_comercial_seller_200_so_com_metricas_de_seller(monkeypatch):
    monkeypatch.setattr(f"{__name__}._USER_CARGOS", [*_USER_CARGOS, {"id_user": 9, "cargo": "seller"}])
    resposta = _client(monkeypatch).get("/comercial/seller", params={"granularidade": "mes", "periodo": "2026-09"})
    assert resposta.status_code == 200
    pessoas = resposta.json()["pessoas"]
    assert [p["nome"] for p in pessoas] == ["Nathan"]
    assert [m["metrica"] for m in pessoas[0]["metricas"]] == ["fups", "numeros_captados", "indicacoes"]


def test_comercial_400_parametro_invalido(monkeypatch):
    resposta = _client(monkeypatch).get("/comercial/sdr", params={"granularidade": "mes", "periodo": "2026-13"})
    assert resposta.status_code == 400
    assert resposta.json()["erro"]["codigo"] == "parametro_invalido"


def test_geral_200_periodo_atual(monkeypatch):
    resposta = _client(monkeypatch).get("/geral")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert len(corpo["cards"]) == 6
    assert corpo["termometro"]["meta"] == 380_000
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


def test_geral_em_dia_busca_faturamento_do_dia_e_do_mes_corrente(monkeypatch):
    """Cards escuros (Faturamento/Liquidado) são sempre do MÊS; o resto da
    página segue o recorte pedido — então sob `dia` a rota faz DUAS consultas a
    `metricas_faturamento`, uma por intervalo."""
    intervalos: list[str] = []

    def query_espiã(tabela, filtros=None, schema="dash", colunas="*", **kwargs):
        if tabela == "metricas_faturamento":
            intervalos.append((filtros or {})["and"])
        return _fake_query(tabela, filtros, schema, colunas, **kwargs)

    for mod in (pessoas_banco_mod, comercial_banco_mod, geral_banco_mod, financeiro_banco_mod, metas_mod):
        monkeypatch.setattr(mod, "query", query_espiã)
    cache.invalidar()
    app.dependency_overrides[exigir_usuario] = lambda: {"sub": "dev"}

    # Data fixa: no dia 1º os dois intervalos coincidiriam e a rota reaproveita
    # a mesma consulta — o cenário que interessa é um dia no meio do mês.
    monkeypatch.setattr(geral_rotas_mod, "hoje_sp", lambda: date(2026, 9, 14))

    resposta = TestClient(app).get("/geral", params={"granularidade": "dia"})
    assert resposta.status_code == 200

    assert len(intervalos) == 2
    assert "data_venda.gte.2026-09-14" in intervalos[0]  # tabela/pódios: só o dia
    assert "data_venda.gte.2026-09-01" in intervalos[1]  # cards escuros: o mês
