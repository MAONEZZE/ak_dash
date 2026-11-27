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
from app import workers
from app.auth import exigir_usuario
from app.dominios.funil import evento as funil_evento_mod
from app.dominios.funil import pipedrive as funil_pipedrive_mod
from app.dominios.funil.pipedrive import DadosPipedrive, Fato
from app.dominios.geral import rotas as geral_rotas_mod
from app.fontes import banco as fontes_banco_mod
from app.fontes import pipedrive as fonte_pipedrive_mod
from app.fontes import supabase as fontes_supabase_mod
from app.main import app

_BUSCAR_PIPEDRIVE_REAL = funil_pipedrive_mod.buscar_pipedrive

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
    monkeypatch.setattr(fontes_banco_mod, "query", _fake_query)


def _client(monkeypatch) -> TestClient:
    _sobrescrever_query(monkeypatch)
    monkeypatch.setattr(funil_pipedrive_mod, "buscar_pipedrive", lambda inicio, fim: funil_pipedrive_mod.VAZIO)
    monkeypatch.setattr(funil_evento_mod, "buscar_pipedrive_evento", lambda data_evento: dict(funil_evento_mod.ZERADO))
    monkeypatch.setattr(funil_evento_mod, "buscar_almocos_pagos", lambda data_evento: 0)
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

    monkeypatch.setattr(fontes_banco_mod, "query", query_espiã)
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
    assert set(corpo) == {"periodo", "avisos", "contas", "sem_conta", "meta_numeros_captados"}
    assert corpo["sem_conta"] == {k: 0 for k in corpo["contas"][0]["metricas"]}


def test_funil_linkedin_numeros_captados_vem_do_pipedrive(monkeypatch):
    cliente = _client(monkeypatch)
    chamadas = []
    monkeypatch.setattr(
        funil_pipedrive_mod,
        "buscar_pipedrive",
        lambda inicio, fim: chamadas.append((inicio, fim))
        or DadosPipedrive(
            [Fato("numeros_captados", "linkedin", 1, 501, "2026-11-02"), Fato("numeros_captados", "linkedin", 1, 502, "2026-11-03")],
            {501: (55,)},
        ),
    )
    monkeypatch.setenv("PIPE_ID_ETIQUETA_PESSOA_LINKEDIN_JACOB", "55")

    corpo = cliente.get("/funil/linkedin", params={"granularidade": "mes", "periodo": "2026-11"}).json()

    assert corpo["contas"][0]["metricas"]["numeros_captados"] == 1
    assert corpo["contas"][0]["metricas"]["conexoes_enviadas"] == 43  # planilha continua
    assert corpo["contas"][0]["serie"][0]["metricas"]["numeros_captados"] == 1
    assert corpo["sem_conta"]["numeros_captados"] == 1
    assert chamadas == [(date(2026, 11, 1), date(2026, 11, 30))]


def test_funil_devolve_meta_de_numeros_captados_do_seller_no_periodo(monkeypatch):
    monkeypatch.setattr(
        f"{__name__}._USERS",
        [*_USERS, {"id": 4, "nome": "Duda", "email": None, "imagem_url": None, "active": True}],
    )
    monkeypatch.setattr(f"{__name__}._USER_CARGOS", [*_USER_CARGOS, {"id_user": 4, "cargo": "seller"}])
    monkeypatch.setattr(f"{__name__}._CONTAS", [{"id": 1, "nome": "Jacob", "id_seller": 4}])
    cliente = _client(monkeypatch)
    monkeypatch.setattr(
        fontes_supabase_mod,
        "ler_metas",
        lambda: [{"id_user": 4, "cargo": "seller", "metrica": "numeros_captados", "valor_diario": 4}],
    )

    mes = cliente.get("/funil/linkedin", params={"granularidade": "mes", "periodo": "2026-11"}).json()
    assert mes["meta_numeros_captados"] == 88  # 4 por dia × 22 dias úteis do mês
    assert "dashboard" not in mes

    semana = cliente.get("/funil/linkedin", params={"granularidade": "semana", "periodo": "2026-W46"}).json()
    assert semana["meta_numeros_captados"] == 20  # 4 × 5


def test_funil_sem_seller_ligado_nao_tem_meta(monkeypatch):
    corpo = _client(monkeypatch).get("/funil/linkedin", params={"granularidade": "mes", "periodo": "2026-11"}).json()
    assert corpo["meta_numeros_captados"] is None


def test_funil_com_pipedrive_fora_do_ar_avisa_e_zera(monkeypatch):
    cliente = _client(monkeypatch)
    monkeypatch.setattr(funil_pipedrive_mod, "buscar_pipedrive", _BUSCAR_PIPEDRIVE_REAL)

    def negocios_fora_do_ar(inicio):
        raise fonte_pipedrive_mod.PipedriveIndisponivel("fora")

    monkeypatch.setattr(fonte_pipedrive_mod, "negocios_criados_desde", negocios_fora_do_ar)

    # Falha não vai pro cache: a 2ª requisição tenta o Pipedrive de novo e avisa de novo.
    for _ in range(2):
        corpo = cliente.get("/funil/linkedin", params={"granularidade": "mes", "periodo": "2026-11"}).json()
        assert "fonte_indisponivel:pipedrive" in corpo["avisos"]
        assert corpo["sem_conta"]["numeros_captados"] == 0


def test_funil_instagram_vem_so_da_planilha_sem_consultar_o_pipedrive(monkeypatch):
    # Decisão de 20/11/2026: o pipeline do Instagram no Pipedrive não é usado; a página volta para a planilha.
    cliente = _client(monkeypatch)

    def nao_devia_chamar(inicio, fim):
        raise AssertionError("/funil/instagram não deve consultar o Pipedrive")

    monkeypatch.setattr(funil_pipedrive_mod, "buscar_pipedrive", nao_devia_chamar)

    corpo = cliente.get("/funil/instagram", params={"granularidade": "mes", "periodo": "2026-11"}).json()

    assert corpo["avisos"] == []
    assert corpo["contas"][0]["metricas"]["conexoes_enviadas"] == 43
    assert corpo["sem_conta"] == {k: 0 for k in corpo["contas"][0]["metricas"]}


def test_funil_canal_invalido_404(monkeypatch):
    resposta = _client(monkeypatch).get("/funil/tiktok", params={"granularidade": "mes", "periodo": "2026-11"})
    assert resposta.status_code == 404
    assert resposta.json() == {"erro": {"codigo": "canal_invalido", "mensagem": "canal deve ser linkedin ou instagram"}}


def test_funil_sdr_200_com_sdrs_e_metricas_do_dashboard(monkeypatch):
    monkeypatch.setattr(f"{__name__}._USERS", [*_USERS, {"id": 14, "nome": "Juca", "email": None, "imagem_url": None, "active": True}])
    monkeypatch.setattr(f"{__name__}._USER_CARGOS", [*_USER_CARGOS, {"id_user": 14, "cargo": "sdr"}])
    client = _client(monkeypatch)
    monkeypatch.setattr(
        funil_pipedrive_mod,
        "buscar_pipedrive",
        lambda inicio, fim: DadosPipedrive(
            [
                Fato("numeros_captados", "linkedin", 1, 501, "2026-11-02"),
                Fato("numeros_captados", "linkedin", 1, 502, "2026-11-02"),
                Fato("numeros_captados", "instagram", 1, 503, "2026-11-02"),
                Fato("abordagens", "linkedin", 28932026, 504, "2026-11-03"),
                Fato("abordagens", "instagram", 28932026, 505, "2026-11-04"),
                Fato("respondidos", "linkedin", 28932026, 504, "2026-11-05"),
                Fato("indicacoes", None, 28932026, 506, "2026-11-05"),
                Fato("abordagens", "linkedin", 25564860, 507, "2026-11-03"),
            ],
            {501: (55,)},
        ),
    )
    monkeypatch.setenv("PIPE_ID_ETIQUETA_PESSOA_LINKEDIN_JACOB", "55")
    resposta = client.get("/funil-sdr", params={"granularidade": "mes", "periodo": "2026-11"})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert set(corpo) == {"periodo", "dias_uteis", "avisos", "metricas_time", "funil", "sdrs", "evento"}
    assert corpo["evento"] is None  # sem Confraria agendada
    # Oportunidades = números captados LinkedIn do Pipedrive (1 na conta + 1 sem conta) + Instagram da planilha (0;
    # o Fato do Instagram no Pipedrive é ignorado) + indicações do SDR (1).
    assert corpo["funil"] == {
        "numeros_captados": 2, "indicacoes": 1, "oportunidades": 3, "abordados": 2, "respondidos": 1, "inscritos": 3,
    }
    assert [(s["nome"], s["metricas"]["abordagens"], s["metricas"]["respondidos"], s["metricas"]["indicacoes"], s["metricas"]["inscricoes_realizadas"]) for s in corpo["sdrs"]] == [
        ("Nathan", 0, 0, 0, 3),
        ("Juca", 2, 1, 1, 0),
    ]
    indicacoes = next(m for m in corpo["metricas_time"] if m["metrica"] == "indicacoes")
    assert indicacoes["realizado"] == 1
    assert corpo["avisos"] == []


def test_funil_sdr_traz_a_proxima_confraria_para_o_velocimetro(monkeypatch):
    client = _client(monkeypatch)

    filtros_periodo: list[dict] = []

    def query_com_evento(tabela, filtros=None, *a, **kw):
        if tabela == "events":
            return [{"id": "e1", "title": "Confraria Akeel SP", "event_date": "2026-11-20T22:00:00", "capacity": 80}]
        if tabela == "registrations" and "created_at" in (filtros or {}).get("and", ""):
            filtros_periodo.append(filtros)
            return [{"id": "r1"}, {"id": "r2"}]
        if tabela == "registrations":
            return [{"event_id": "e1", "status": s} for s in ("pending", "pending", "approved", "rejected")]
        return _fake_query(tabela, filtros, *a, **kw)

    monkeypatch.setattr(fontes_banco_mod, "query", query_com_evento)
    corpo = client.get("/funil-sdr", params={"granularidade": "mes", "periodo": "2026-11"}).json()
    assert corpo["evento"] == {
        "id": "e1", "titulo": "Confraria Akeel SP", "data": "2026-11-20T22:00:00",
        "inscritos": 3, "inscritos_periodo": 2, "aprovados": 1, "pendentes": 2, "rejeitados": 1, "almocos_pagos": 0,
        "capacidade": 80, "meta_velocimetro": 80,  # mês: a capacidade
    }
    # Inscritos do velocímetro: só approved/pending, feitos no mês (meia-noite de SP em UTC).
    assert filtros_periodo == [{
        "event_id": "eq.e1",
        "status": "in.(approved,pending)",
        "and": '(created_at.gte."2026-11-01T03:00:00Z",created_at.lt."2026-12-01T03:00:00Z")',
    }]


def test_funil_sdr_no_filtro_de_dia_meta_do_velocimetro_e_o_que_falta_dividido_pelos_dias_ate_o_evento(monkeypatch):
    from app.dominios.funil import rotas as funil_rotas_mod

    client = _client(monkeypatch)
    monkeypatch.setattr(funil_rotas_mod, "hoje_sp", lambda: date(2026, 11, 23))
    filtros_hoje: list[dict] = []

    def query_com_evento(tabela, filtros=None, *a, **kw):
        if tabela == "events":
            # 26/11 às 19h de SP: faltam 23, 24 e 25 = 3 dias.
            return [{"id": "e1", "title": "Imersão", "event_date": "2026-11-26T22:00:00", "capacity": 80}]
        if tabela == "registrations" and "created_at" in (filtros or {}).get("and", ""):
            filtros_hoje.append(filtros)
            return [{"id": "r1"}, {"id": "r2"}]  # 2 inscrições feitas hoje
        if tabela == "registrations":
            # 70 aprovados/pendentes agora; até ontem eram 68.
            return [{"event_id": "e1", "status": "approved"}] * 70 + [{"event_id": "e1", "status": "rejected"}]
        return _fake_query(tabela, filtros, *a, **kw)

    monkeypatch.setattr(fontes_banco_mod, "query", query_com_evento)
    corpo = client.get("/funil-sdr", params={"granularidade": "dia", "periodo": "2026-11-23"}).json()
    # Faltam 80 − 68 = 12 em 3 dias (seg 23 a qua 25): 4 por dia (fixa no dia, as 2 de hoje não abatem).
    assert corpo["evento"]["meta_velocimetro"] == 4
    assert corpo["evento"]["inscritos_periodo"] == 2
    assert all('"2026-11-23T03:00:00Z"' in f["and"] for f in filtros_hoje)


def test_funil_sdr_na_semana_meta_do_velocimetro_e_a_diaria_vezes_6_limitada_ao_que_falta(monkeypatch):
    from app.dominios.funil import rotas as funil_rotas_mod

    client = _client(monkeypatch)
    monkeypatch.setattr(funil_rotas_mod, "hoje_sp", lambda: date(2026, 11, 23))

    def query_com_evento(tabela, filtros=None, *a, **kw):
        if tabela == "events":
            # 05/12: de seg 23/11 a sex 04/12 sem o domingo 29 = 11 dias.
            return [{"id": "e1", "title": "Imersão", "event_date": "2026-12-05T22:00:00", "capacity": 80}]
        if tabela == "registrations" and "created_at" in (filtros or {}).get("and", ""):
            return []
        if tabela == "registrations":
            return [{"event_id": "e1", "status": "approved"}] * 47
        return _fake_query(tabela, filtros, *a, **kw)

    monkeypatch.setattr(fontes_banco_mod, "query", query_com_evento)
    corpo = client.get("/funil-sdr", params={"granularidade": "semana", "periodo": "2026-W48"}).json()
    # Faltam 33 em 11 dias = 3/dia → semana 18.
    assert corpo["evento"]["meta_velocimetro"] == 18


def test_funil_sdr_com_evento_escolhido_traz_os_numeros_dele(monkeypatch):
    client = _client(monkeypatch)
    filtros_eventos: list[dict] = []

    def query_com_evento(tabela, filtros=None, *a, **kw):
        if tabela == "events":
            filtros_eventos.append(filtros)
            return [{"id": "e-antigo", "title": "Confraria Akeel RJ", "event_date": "2026-10-10T22:00:00", "capacity": 50}]
        if tabela == "registrations":
            return [{"event_id": "e-antigo", "status": s} for s in ("approved", "approved", "rejected")]
        return _fake_query(tabela, filtros, *a, **kw)

    monkeypatch.setattr(fontes_banco_mod, "query", query_com_evento)
    corpo = client.get("/funil-sdr", params={"granularidade": "mes", "periodo": "2026-11", "evento": "e-antigo"}).json()
    assert filtros_eventos[0]["and"] == '(id.eq."e-antigo")'
    assert (corpo["evento"]["id"], corpo["evento"]["aprovados"], corpo["evento"]["rejeitados"]) == ("e-antigo", 2, 1)


def test_funil_sdr_mostra_os_almocos_pagos_do_evento(monkeypatch):
    client = _client(monkeypatch)
    datas_almocos: list[date] = []

    def query_com_evento(tabela, filtros=None, *a, **kw):
        if tabela == "events":
            return [{"id": "e-antigo", "title": "Confraria Akeel RJ", "event_date": "2026-10-10T22:00:00", "capacity": 50}]
        if tabela == "registrations":
            return [{"event_id": "e-antigo", "status": s} for s in ("approved", "approved", "rejected")]
        return _fake_query(tabela, filtros, *a, **kw)

    def almocos_falso(data_evento):
        datas_almocos.append(data_evento)
        return 7

    monkeypatch.setattr(fontes_banco_mod, "query", query_com_evento)
    monkeypatch.setattr(funil_evento_mod, "buscar_almocos_pagos", almocos_falso)
    corpo = client.get("/funil-sdr", params={"granularidade": "mes", "periodo": "2026-11", "evento": "e-antigo"}).json()
    assert corpo["evento"]["almocos_pagos"] == 7
    assert datas_almocos == [date(2026, 10, 10)]


def test_funil_sdr_evento_com_caractere_invalido_400(monkeypatch):
    resposta = _client(monkeypatch).get(
        "/funil-sdr", params={"granularidade": "mes", "periodo": "2026-11", "evento": 'x",title.neq.y'}
    )
    assert resposta.status_code == 400


def test_sdr_200_com_ranking_previsao_e_serie_do_evento(monkeypatch):
    from app.dominios.funil import rotas as rotas_funil_mod

    client = _client(monkeypatch)
    monkeypatch.setattr(rotas_funil_mod, "hoje_sp", lambda: date(2026, 11, 23))

    def query_pagina_sdr(tabela, filtros=None, *a, **kw):
        if tabela == "events":
            return [{"id": "e1", "title": "Imersão", "event_date": "2026-12-02T16:00:00+00:00", "capacity": 60}]
        if tabela == "registrations" and "order" in (filtros or {}):
            return [{"created_at": "2026-11-20T15:00:00+00:00"}]
        if tabela == "registrations":
            return []
        if tabela == "metricas_sdrs":
            return [{"id_user": 9, "data": "2026-11-03", "key_data_ref_user": "x", "ligacoes_realizadas": 4}]
        return _fake_query(tabela, filtros, *a, **kw)

    monkeypatch.setattr(fontes_banco_mod, "query", query_pagina_sdr)
    pedidos = []

    def negocios_falso(inicio, fim, id_dash_por_dono):
        pedidos.append((inicio, fim))
        return {9: 40}

    monkeypatch.setattr(rotas_funil_mod.sdr, "buscar_negocios_sdr", negocios_falso)
    monkeypatch.setattr(
        fontes_supabase_mod, "ler_metas_do_cargo", lambda cargo: [{"id_user": 9, "metrica": "inscricoes_realizadas", "valor_diario": 4}]
    )
    resposta = client.get("/sdr", params={"granularidade": "mes", "periodo": "2026-11"})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["evento"] == {"id": "e1", "titulo": "Imersão", "data": "2026-12-02T16:00:00+00:00", "capacidade": 60}
    assert corpo["janela"] == {"inicio": "2026-11-20", "fim": "2026-12-01"}
    sdr = corpo["sdrs"][0]
    assert sdr["id_user"] == "9"
    assert sdr["inscricoes"] == 3
    assert sdr["ligacoes"] == 4
    assert sdr["pontuacao"] == 62
    assert sdr["posicao"] == 1
    assert len(sdr["serie_evento"]) == 10  # 20/11 a 01/12 sem os domingos 22 e 29
    # 3 da planilha (metricas_funil_sdr); meta = 4 × 21 dias seg–sex de novembro (evento em 02/12).
    assert sdr["ranking_mes"] == {"negocios": 40, "inscricoes": 3, "inscricoes_hoje": 0, "meta": 84}
    assert corpo["mes_ranking"] == {"inicio": "2026-11-01", "fim": "2026-11-30"}
    assert corpo["janela_meta"] == {"inicio": "2026-11-01", "fim": "2026-11-30"}
    assert corpo["inscritos_sed_mes"] == 0  # o fake do SED não devolve inscrição no período
    assert pedidos == [(date(2026, 11, 1), date(2026, 11, 30))]


def test_sdr_evento_com_caractere_invalido_400(monkeypatch):
    resposta = _client(monkeypatch).get(
        "/sdr", params={"granularidade": "mes", "periodo": "2026-11", "evento": "a;b"}
    )
    assert resposta.status_code == 400


def test_funil_sdr_eventos_lista_os_proximos_eventos(monkeypatch):
    client = _client(monkeypatch)

    def query_eventos(tabela, filtros=None, *a, **kw):
        if tabela == "events":
            return [{"id": "e1", "title": "Imersão Alta Cadência", "event_date": "2026-11-18T22:00:00"}]
        return _fake_query(tabela, filtros, *a, **kw)

    monkeypatch.setattr(fontes_banco_mod, "query", query_eventos)
    corpo = client.get("/funil-sdr/eventos").json()
    assert corpo["eventos"] == [{"id": "e1", "titulo": "Imersão Alta Cadência", "data": "2026-11-18T22:00:00"}]


def test_funil_evento_eventos_lista_as_imersoes(monkeypatch):
    client = _client(monkeypatch)
    filtros_eventos: list[dict] = []

    def query_imersoes(tabela, filtros=None, *a, **kw):
        if tabela == "events":
            filtros_eventos.append(filtros)
            return [{"id": "i2", "title": "Imersão Alta Cadência", "event_date": "2026-12-02T16:00:00+00:00"}]
        return _fake_query(tabela, filtros, *a, **kw)

    monkeypatch.setattr(fontes_banco_mod, "query", query_imersoes)
    resposta = client.get("/funil-evento/eventos")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["eventos"] == [{"id": "i2", "titulo": "Imersão Alta Cadência", "data": "2026-12-02T16:00:00+00:00"}]
    assert corpo["avisos"] == []
    assert filtros_eventos[0]["title"] == "ilike.*imers*"


def test_funil_evento_sem_escolha_traz_a_proxima_imersao_com_o_retrato_de_agora(monkeypatch):
    client = _client(monkeypatch)
    chamadas_pipedrive: list[date] = []
    filtros_eventos: list[dict] = []

    def fake_pipedrive(data_evento):
        chamadas_pipedrive.append(data_evento)
        return {"inscritos": 5, "onboarding_agendado": 4, "onboarding_realizado": 3, "vendas": 1}

    def query_imersao(tabela, filtros=None, *a, **kw):
        if tabela == "events":
            filtros_eventos.append(filtros)
            return [{"id": "i2", "title": "Imersão Alta Cadência", "event_date": "2026-12-02T16:00:00+00:00", "capacity": 60}]
        if tabela == "registrations" and "attended" in (filtros or {}):
            return [{"id": "r1"}, {"id": "r2"}]
        if tabela == "registrations":
            return [{"event_id": "i2", "status": s} for s in ("pending", "pending", "approved", "approved", "approved", "rejected")]
        return _fake_query(tabela, filtros, *a, **kw)

    monkeypatch.setattr(funil_evento_mod, "buscar_pipedrive_evento", fake_pipedrive)
    monkeypatch.setattr(fontes_banco_mod, "query", query_imersao)
    resposta = client.get("/funil-evento", params={"granularidade": "mes", "periodo": "2026-11"})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["periodo"] == {"granularidade": "mes", "inicio": "2026-11-01", "fim": "2026-11-30"}
    assert corpo["avisos"] == []
    assert corpo["evento"] == {
        "id": "i2", "titulo": "Imersão Alta Cadência", "data": "2026-12-02T16:00:00+00:00",
        "total": 6, "aprovados": 3, "pendentes": 2, "rejeitados": 1,
    }
    assert corpo["funil"] == {
        "inscritos": 5, "onboarding_agendado": 4, "onboarding_realizado": 3, "comparecimento": 2, "vendas": 1,
    }
    assert chamadas_pipedrive == [date(2026, 12, 2)]
    assert filtros_eventos[0]["title"] == "ilike.*imers*"


def test_funil_evento_inscritos_vem_da_coluna_3_do_pipedrive_e_nao_do_sed(monkeypatch):
    client = _client(monkeypatch)

    def query_25_inscritos(tabela, filtros=None, *a, **kw):
        if tabela == "events":
            return [{"id": "i3", "title": "Imersão", "event_date": "2026-12-02T16:00:00+00:00", "capacity": 60}]
        if tabela == "registrations" and "attended" in (filtros or {}):
            return []
        if tabela == "registrations":
            return [{"event_id": "i3", "status": "pending"}] * 15 + [{"event_id": "i3", "status": "approved"}] * 10
        return _fake_query(tabela, filtros, *a, **kw)

    monkeypatch.setattr(
        funil_evento_mod,
        "buscar_pipedrive_evento",
        lambda _d: {"inscritos": 7, "onboarding_agendado": 3, "onboarding_realizado": 2, "vendas": 0},
    )
    monkeypatch.setattr(fontes_banco_mod, "query", query_25_inscritos)
    corpo = client.get("/funil-evento", params={"granularidade": "mes", "periodo": "2026-11"}).json()
    assert corpo["funil"] == {
        "inscritos": 7, "onboarding_agendado": 3, "onboarding_realizado": 2, "comparecimento": 0, "vendas": 0,
    }
    assert corpo["evento"]["pendentes"] == 15
    assert corpo["evento"]["aprovados"] == 10


def test_funil_evento_com_evento_escolhido_usa_a_data_dele(monkeypatch):
    client = _client(monkeypatch)
    chamadas_pipedrive: list[date] = []
    filtros_eventos: list[dict] = []

    def fake_pipedrive(data_evento):
        chamadas_pipedrive.append(data_evento)
        return dict(funil_evento_mod.ZERADO)

    def query_com_evento(tabela, filtros=None, *a, **kw):
        if tabela == "events":
            filtros_eventos.append(filtros)
            return [{"id": "e-antigo", "title": "Imersão Alta Cadência", "event_date": "2026-11-17T12:00:00+00:00", "capacity": None}]
        if tabela == "registrations":
            return []
        return _fake_query(tabela, filtros, *a, **kw)

    monkeypatch.setattr(funil_evento_mod, "buscar_pipedrive_evento", fake_pipedrive)
    monkeypatch.setattr(fontes_banco_mod, "query", query_com_evento)
    resposta = client.get("/funil-evento", params={"granularidade": "semana", "periodo": "2026-W47", "evento": "e-antigo"})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert filtros_eventos[0]["and"] == '(id.eq."e-antigo")'
    assert corpo["evento"]["id"] == "e-antigo"
    assert corpo["periodo"]["inicio"] == "2026-11-16"
    assert corpo["periodo"]["fim"] == "2026-11-22"
    assert chamadas_pipedrive == [date(2026, 11, 17)]


def test_funil_evento_sem_imersao_zera_o_funil(monkeypatch):
    client = _client(monkeypatch)
    chamadas_pipedrive: list[date] = []

    def fake_pipedrive(data_evento):
        chamadas_pipedrive.append(data_evento)
        return dict(funil_evento_mod.ZERADO)

    def query_sem_imersao(tabela, filtros=None, *a, **kw):
        if tabela in ("events", "registrations"):
            return []
        return _fake_query(tabela, filtros, *a, **kw)

    monkeypatch.setattr(funil_evento_mod, "buscar_pipedrive_evento", fake_pipedrive)
    monkeypatch.setattr(fontes_banco_mod, "query", query_sem_imersao)
    resposta = client.get("/funil-evento", params={"granularidade": "mes", "periodo": "2026-11"})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["evento"] is None
    assert corpo["funil"] == {"inscritos": 0, "onboarding_agendado": 0, "onboarding_realizado": 0, "comparecimento": 0, "vendas": 0}
    assert chamadas_pipedrive == []


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

    monkeypatch.setattr(fontes_banco_mod, "query", query_espia)
    resposta = client.get("/funil-sdr", params={"granularidade": "dia", "periodo": "2026-11-16"})
    assert resposta.status_code == 200
    assert filtros_sdr == [{"and": "(data.gte.2026-11-10,data.lte.2026-11-16)"}]


def test_no_stdout_so_saem_as_primeiras_leituras_com_horario_de_sp(monkeypatch):
    import logging
    import sys
    import time

    monkeypatch.setenv("TZ", "UTC")  # como o container do Easypanel
    time.tzset()

    import app.main  # noqa: F401  (configura o logging ao importar)

    log = logging.getLogger("app")
    assert log.getEffectiveLevel() == logging.INFO
    (handler,) = log.handlers
    assert handler.stream is sys.stdout
    registro = logging.LogRecord("app.workers", logging.INFO, "", 0, "Worker teste: primeira leitura ok", None, None)
    registro.created = 1795449600.0  # 2026-11-23 16:00:00 UTC
    try:
        linha = handler.format(registro)
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()
    # horário de São Paulo (UTC-3), não o do container
    assert linha == "2026-11-23 13:00:00 INFO app.workers: Worker teste: primeira leitura ok"

    # no painel só sai o que vem marcado `no_painel` (as "primeiras leituras ok"); avisos e erros não
    registro.no_painel = True
    assert handler.filter(registro)
    aviso = logging.LogRecord("app.workers", logging.WARNING, "", 0, "Planilha sdrs: aba 'SDR3' pulada", None, None)
    assert not handler.filter(aviso)


def test_funil_evento_parametro_invalido_400(monkeypatch):
    client = _client(monkeypatch)
    evento_invalido = client.get(
        "/funil-evento", params={"granularidade": "mes", "periodo": "2026-11", "evento": 'x",title.neq.y'}
    )
    periodo_invalido = client.get("/funil-evento", params={"granularidade": "mes", "periodo": "xx"})
    assert evento_invalido.status_code == 400
    assert periodo_invalido.status_code == 400
