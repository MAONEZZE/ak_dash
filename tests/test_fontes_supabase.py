import dataclasses
from datetime import date

import httpx
import pytest

from app.fontes import banco, supabase
from app.planilhas import COLUNAS_POR_TABELA


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


@pytest.mark.parametrize(
    "chamada, tabela, params_esperados",
    [
        (
            lambda: supabase.ler_vendas_do_periodo(date(2026, 8, 1), date(2026, 8, 31)),
            "metricas_faturamento",
            {"select": "*", "and": "(data_venda.gte.2026-08-01,data_venda.lt.2026-09-01)"},
        ),
        (
            lambda: supabase.ler_recebimentos_do_periodo(date(2026, 8, 20), date(2026, 12, 31)),
            "recebimentos_faturamento",
            {"select": "*", "and": "(mes.gte.2026-08-01,mes.lte.2026-12-31)"},
        ),
        (
            lambda: supabase.ler_vendas_por_id_planilha([5, 7]),
            "metricas_faturamento",
            {"select": "*", "id_planilha": "in.(5,7)"},
        ),
        (
            lambda: supabase.ler_vendas_por_id_planilha([5], colunas="id_planilha,user_closer"),
            "metricas_faturamento",
            {"select": "id_planilha,user_closer", "id_planilha": "in.(5)"},
        ),
        (
            lambda: supabase.ler_clientes_por_id([3, 4]),
            "cliente_faturamento",
            {"select": "*", "id": "in.(3,4)"},
        ),
        (
            lambda: supabase.ler_usuarios_por_id([1, 2]),
            "users",
            {"select": "*", "id": "in.(1,2)"},
        ),
        (
            lambda: supabase.ler_logs_do_periodo(date(2026, 11, 1), date(2026, 11, 30)),
            "logs_pipedrive",
            {"select": "data,hora,usuario_acao,atividade,cliente_nome", "and": "(data.gte.2026-11-01,data.lte.2026-11-30)"},
        ),
    ],
)
def test_leituras_de_faturamento_e_logs_mandam_a_requisicao_de_hoje(monkeypatch, chamada, tabela, params_esperados):
    registros = _capturar(monkeypatch)

    chamada()

    assert len(registros) == 1
    requisicao = registros[0]
    assert requisicao["url"] == f"https://sb.test/rest/v1/{tabela}"
    assert _sem_paginacao(requisicao["params"]) == params_esperados


cols_contas = ",".join(COLUNAS_POR_TABELA["metricas_contas"])
cols_sdr = ",".join(COLUNAS_POR_TABELA["metricas_funil_sdr"])


@pytest.mark.parametrize(
    "chamada, tabela, params_esperados",
    [
        (
            lambda: supabase.ler_contas_do_canal("linkedin"),
            "contas_funil",
            {"select": "id,canal,nome,id_seller", "canal": "eq.linkedin"},
        ),
        (
            lambda: supabase.ler_metricas_das_contas(date(2026, 11, 1), date(2026, 11, 30), ids=[1, 2]),
            "metricas_contas",
            {"select": "id_conta,data," + cols_contas, "id_conta": "in.(1,2)", "and": "(data.gte.2026-11-01,data.lte.2026-11-30)"},
        ),
        (
            lambda: supabase.ler_metricas_das_contas(date(2026, 11, 1), date(2026, 11, 30)),
            "metricas_contas",
            {"select": "id_conta,data," + cols_contas, "and": "(data.gte.2026-11-01,data.lte.2026-11-30)"},
        ),
        (
            lambda: supabase.ler_metricas_funil_sdr(date(2026, 11, 10), date(2026, 11, 16)),
            "metricas_funil_sdr",
            {"select": "id_user,data," + cols_sdr, "and": "(data.gte.2026-11-10,data.lte.2026-11-16)"},
        ),
        (
            lambda: supabase.ler_metas_funil_sdr(),
            "metas_funil_sdr",
            {"select": "metrica,periodo,id_user,valor"},
        ),
    ],
)
def test_leituras_dos_funis_mandam_a_requisicao_de_hoje(monkeypatch, chamada, tabela, params_esperados):
    registros = _capturar(monkeypatch)

    chamada()

    assert len(registros) == 1
    requisicao = registros[0]
    assert requisicao["url"] == f"https://sb.test/rest/v1/{tabela}"
    assert _sem_paginacao(requisicao["params"]) == params_esperados


@pytest.mark.parametrize(
    "chamada, metodo, tabela, params_esperados, json_esperado",
    [
        (lambda: supabase.ler_usuarios(), "GET", "users", {"select": "id,nome"}, None),
        (lambda: supabase.ler_ids_com_cargo("sdr"), "GET", "user_cargos", {"select": "id_user", "cargo": "eq.sdr"}, None),
        (lambda: supabase.ler_metas_do_cargo("seller"), "GET", "metas", {"select": "id_user,metrica,valor_diario", "cargo": "eq.seller"}, None),
        (
            lambda: supabase.ler_metricas_planilha("metricas_sellers", date(2026, 10, 1), date(2026, 10, 31), ["fups", "numeros_captados"]),
            "GET",
            "metricas_sellers",
            {"select": "id_user,data,key_data_ref_user,fups,numeros_captados", "and": "(data.gte.2026-10-01,data.lte.2026-10-31)"},
            None,
        ),
        (lambda: supabase.gravar_metricas_planilha("metricas_sdrs", [{"a": 1}]), "POST", "metricas_sdrs", {"on_conflict": "key_data_ref_user"}, [{"a": 1}]),
        (lambda: supabase.gravar_metas([{"a": 1}]), "POST", "metas", {"on_conflict": "id_user,cargo,metrica"}, [{"a": 1}]),
        (lambda: supabase.apagar_meta(9, "sdr", "abordagens"), "DELETE", "metas", {"id_user": "eq.9", "cargo": "eq.sdr", "metrica": "eq.abordagens"}, None),
    ],
)
def test_funcoes_do_worker_base_mandam_a_requisicao_de_hoje(monkeypatch, chamada, metodo, tabela, params_esperados, json_esperado):
    registros = _capturar(monkeypatch)

    chamada()

    assert len(registros) == 1
    requisicao = registros[0]
    assert requisicao["metodo"] == metodo
    assert requisicao["url"] == f"https://sb.test/rest/v1/{tabela}"
    assert _sem_paginacao(requisicao["params"]) == params_esperados
    assert requisicao["json"] == json_esperado
