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
from app.dominios.funil import banco as funil_banco_mod
from app.dominios.funil import sdr as funil_sdr_mod
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

_CONTAS = [{"id": 1, "nome": "Jacob", "id_seller": None}]


def _fake_query(tabela, filtros=None, schema="dash", colunas="*", **kwargs):
    if tabela == "users":
        return _USERS
    if tabela == "user_cargos":
        return _USER_CARGOS
    if tabela == "contas_funil":
        return _CONTAS
    if tabela == "metricas_funil_sdr":
        return [
            {"id_user": 9, "data": "2026-11-03", "abordagens": 12, "respondidos": 5, "inscricoes_realizadas": 3, "indicacoes": 2, "reunioes_agendadas": 1}
        ]
    if tabela == "metas_funil_sdr":
        return [{"metrica": "inscricoes_realizadas", "periodo": "mes", "id_user": None, "valor": 88}]
    if tabela == "metricas_contas":
        return [
            {
                "id_conta": 1,
                "data": "2026-11-02",
                "conexoes_enviadas": 43,
                "conexoes_aceitas": None,
                "mensagens_abordagem": None,
                "abordagens": None,
                "follows_abordagem": None,
                "respondidos": None,
                "in_mails": None,
                "fups": None,
                "numeros_captados": None,
                "indicacoes": None,
            }
        ]
    return []


def _sobrescrever_query(monkeypatch) -> None:
    for mod in (pessoas_banco_mod, comercial_banco_mod, geral_banco_mod, financeiro_banco_mod, funil_banco_mod, funil_sdr_mod, metas_mod):
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
    w = workers.Worker(workers.SDRS, "ID", lambda _id: [])
    w.status = {"ultima_leitura_ok": "2026-10-27T10:00:00-03:00", "ultimo_erro": None}
    monkeypatch.setattr(workers, "ATIVOS", [w])
    monkeypatch.setattr(workers, "MOTIVO_INATIVOS", None)
    resposta = TestClient(app).get("/saude")
    assert resposta.status_code == 200
    assert resposta.json() == {
        "status": "ok",
        "workers": {"sdrs": {"ultima_leitura_ok": "2026-10-27T10:00:00-03:00", "ultimo_erro": None}},
        "workers_motivo": None,
    }


def test_saude_mostra_motivo_dos_workers_inativos(monkeypatch):
    monkeypatch.setattr(workers, "ATIVOS", [])
    monkeypatch.setattr(workers, "MOTIVO_INATIVOS", "GOOGLE_SERVICE_ACCOUNT_JSON ausente ou ilegível no .env")
    resposta = TestClient(app).get("/saude")
    assert resposta.status_code == 200
    assert resposta.json() == {
        "status": "ok",
        "workers": {},
        "workers_motivo": "GOOGLE_SERVICE_ACCOUNT_JSON ausente ou ilegível no .env",
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


def test_comercial_sdr_devolve_metricas_time_com_os_indicadores(monkeypatch):
    resposta = _client(monkeypatch).get("/comercial/sdr", params={"granularidade": "mes", "periodo": "2026-09"})
    assert resposta.status_code == 200
    metricas_time = resposta.json()["metricas_time"]
    assert len(metricas_time) == 5
    chaves = {"metrica", "nome_exibicao", "meta_periodo", "realizado", "pct_atingimento", "falta_folga", "horas_restantes", "media_necessaria", "previsao"}
    for item in metricas_time:
        assert set(item) == chaves


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


def test_funil_linkedin_200_com_contas_do_periodo(monkeypatch):
    resposta = _client(monkeypatch).get("/funil/linkedin", params={"granularidade": "mes", "periodo": "2026-11"})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["periodo"] == {"granularidade": "mes", "inicio": "2026-11-01", "fim": "2026-11-30"}
    assert corpo["contas"] == [
        {
            "id_conta": "1",
            "nome": "Jacob",
            "metricas": {
                "conexoes_enviadas": 43,
                "conexoes_aceitas": 0,
                "mensagens_abordagem": 0,
                "abordagens": 0,
                "follows_abordagem": 0,
                "respondidos": 0,
                "in_mails": 0,
                "fups": 0,
                "numeros_captados": 0,
                "indicacoes": 0,
            },
            "serie": [
                {
                    "data": "2026-11-02",
                    "metricas": {
                        "conexoes_enviadas": 43,
                        "conexoes_aceitas": 0,
                        "mensagens_abordagem": 0,
                        "abordagens": 0,
                        "follows_abordagem": 0,
                        "respondidos": 0,
                        "in_mails": 0,
                        "fups": 0,
                        "numeros_captados": 0,
                        "indicacoes": 0,
                    },
                }
            ],
        }
    ]
    assert corpo["avisos"] == []
    assert set(corpo) == {"periodo", "avisos", "contas", "meta_numeros_captados"}


def test_funil_devolve_meta_de_numeros_captados_do_seller_no_periodo(monkeypatch):
    monkeypatch.setattr(
        f"{__name__}._USERS",
        [*_USERS, {"id": 4, "nome": "Duda", "email": None, "imagem_url": None, "active": True}],
    )
    monkeypatch.setattr(f"{__name__}._USER_CARGOS", [*_USER_CARGOS, {"id_user": 4, "cargo": "seller"}])
    monkeypatch.setattr(f"{__name__}._CONTAS", [{"id": 1, "nome": "Jacob", "id_seller": 4}])
    cliente = _client(monkeypatch)
    monkeypatch.setattr(
        metas_mod,
        "query",
        lambda tabela, *a, **kw: [{"id_user": 4, "cargo": "seller", "metrica": "numeros_captados", "valor_diario": 4}],
    )

    mes = cliente.get("/funil/linkedin", params={"granularidade": "mes", "periodo": "2026-11"}).json()
    assert mes["meta_numeros_captados"] == 88  # 4 por dia × 22 dias úteis do mês
    assert "dashboard" not in mes

    semana = cliente.get("/funil/linkedin", params={"granularidade": "semana", "periodo": "2026-W46"}).json()
    assert semana["meta_numeros_captados"] == 20  # 4 × 5


def test_funil_sem_seller_ligado_nao_tem_meta(monkeypatch):
    corpo = _client(monkeypatch).get("/funil/linkedin", params={"granularidade": "mes", "periodo": "2026-11"}).json()
    assert corpo["meta_numeros_captados"] is None


def test_funil_canal_invalido_404(monkeypatch):
    resposta = _client(monkeypatch).get("/funil/tiktok", params={"granularidade": "mes", "periodo": "2026-11"})
    assert resposta.status_code == 404
    assert resposta.json() == {"erro": {"codigo": "canal_invalido", "mensagem": "canal deve ser linkedin ou instagram"}}


def test_funil_sdr_200_com_sdrs_e_metricas_do_dashboard(monkeypatch):
    client = _client(monkeypatch)

    # Uma conta por canal, com 7 números captados no período.
    def query_com_numeros(tabela, *a, **kw):
        if tabela == "metricas_contas":
            return [{"id_conta": 1, "data": "2026-11-02", "numeros_captados": 7}]
        return _fake_query(tabela, *a, **kw)

    monkeypatch.setattr(funil_banco_mod, "query", query_com_numeros)
    resposta = client.get("/funil-sdr", params={"granularidade": "mes", "periodo": "2026-11"})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert set(corpo) == {"periodo", "dias_uteis", "avisos", "metricas_time", "funil", "sdrs", "evento"}
    assert corpo["evento"] is None  # sem Confraria agendada
    # Oportunidades = números captados LinkedIn (7) + Instagram (7) + indicações dos SDRs (2).
    assert corpo["funil"] == {
        "numeros_captados": 14, "indicacoes": 2, "oportunidades": 16, "abordados": 12, "respondidos": 5, "inscritos": 3,
    }
    assert [(s["id_user"], s["nome"], s["metricas"]["inscricoes_realizadas"]) for s in corpo["sdrs"]] == [("9", "Nathan", 3)]
    inscricoes = corpo["metricas_time"][0]
    assert (inscricoes["metrica"], inscricoes["realizado"], inscricoes["meta_periodo"]) == ("inscricoes_realizadas", 3, 88)
    assert corpo["avisos"] == []


def test_funil_sdr_traz_a_proxima_confraria_para_o_velocimetro(monkeypatch):
    client = _client(monkeypatch)

    def query_com_evento(tabela, *a, **kw):
        if tabela == "events":
            return [{"id": "e1", "title": "Confraria Akeel SP", "event_date": "2026-11-20T22:00:00", "capacity": 80}]
        if tabela == "registrations":
            return [{"event_id": "e1", "status": s} for s in ("pending", "pending", "approved", "rejected")]
        return _fake_query(tabela, *a, **kw)

    monkeypatch.setattr(geral_banco_mod, "query", query_com_evento)
    corpo = client.get("/funil-sdr", params={"granularidade": "mes", "periodo": "2026-11"}).json()
    assert corpo["evento"] == {
        "titulo": "Confraria Akeel SP", "data": "2026-11-20T22:00:00",
        "inscritos": 3, "aprovados": 1, "pendentes": 2, "rejeitados": 1, "capacidade": 80,
    }


def test_funil_sdr_periodo_invalido_400(monkeypatch):
    resposta = _client(monkeypatch).get("/funil-sdr", params={"granularidade": "mes", "periodo": "xx"})
    assert resposta.status_code == 400


def test_funil_sdr_no_filtro_de_dia_busca_a_semana_ate_o_dia_para_o_grafico(monkeypatch):
    client = _client(monkeypatch)
    filtros_sdr: list[dict] = []

    def query_espia(tabela, filtros=None, *a, **kw):
        if tabela == "metricas_funil_sdr":
            filtros_sdr.append(filtros)
        return _fake_query(tabela, filtros, *a, **kw)

    monkeypatch.setattr(funil_sdr_mod, "query", query_espia)
    resposta = client.get("/funil-sdr", params={"granularidade": "dia", "periodo": "2026-11-16"})
    assert resposta.status_code == 200
    assert filtros_sdr == [{"and": "(data.gte.2026-11-10,data.lte.2026-11-16)"}]
