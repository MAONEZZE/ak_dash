"""Testes de `dominios/funil/pipedrive.py` — métricas do Pipedrive nos funis LinkedIn, Instagram e SDR."""
from __future__ import annotations

import dataclasses
from datetime import date, datetime

import pytest

from app.dominios.funil import pipedrive
from app.dominios.funil.banco import ContaFunil
from app.dominios.funil.pipedrive import Fato
from app.fontes import banco
from app.periodo import TZ_SP
from app.planilhas import COLUNAS_POR_TABELA


@pytest.fixture(autouse=True)
def _ids(monkeypatch):
    monkeypatch.setattr(
        pipedrive,
        "settings",
        dataclasses.replace(
            pipedrive.settings,
            pipe_id_pipeline_instagram=3,
            pipe_id_abordados_pipeline_linkedin=11,
            pipe_id_respondidos_pipeline_linkedin=12,
            pipe_id_abordados_pipeline_instagram=21,
            pipe_id_respondidos_pipeline_instagram=22,
            pipe_id_etiqueta_negocio_linkedin=101,
            pipe_id_etiqueta_negocio_indicacao=102,
        ),
    )


def test_criado_no_periodo_vira_numero_captado_do_canal():
    a = {"id": 1, "add_time": "2026-11-05T15:00:00Z", "pipeline_id": 1, "label_ids": [101], "owner_id": 25564860, "person_id": 501}
    # 23h do dia 04 em SP
    b = {"id": 2, "add_time": "2026-11-05T02:00:00Z", "pipeline_id": 3, "label_ids": [], "owner_id": 28932026, "person_id": 502}
    # sem etiqueta e fora do Instagram
    c = {"id": 3, "add_time": "2026-11-06T12:00:00Z", "pipeline_id": 1, "label_ids": None, "owner_id": 1, "person_id": None}
    # depois do fim
    d = {"id": 4, "add_time": "2026-12-01T12:00:00Z", "pipeline_id": 3, "label_ids": [101], "owner_id": 1, "person_id": 503}

    assert pipedrive.contar([a, b, c, d], {}, date(2026, 11, 1), date(2026, 11, 30)) == [
        Fato("numeros_captados", "linkedin", 25564860, 501, "2026-11-05"),
        Fato("numeros_captados", "instagram", 28932026, 502, "2026-11-04"),
    ]


def test_negocio_na_coluna_2_ou_3_conta_pela_data_de_entrada():
    e = {"id": 5, "stage_id": 11, "stage_change_time": "2026-11-10T13:00:00Z", "owner_id": 28932026, "person_id": 601}
    # entrou antes do início
    f = {"id": 6, "stage_id": 11, "stage_change_time": "2026-10-31T13:00:00Z", "owner_id": 28932026, "person_id": 602}
    g = {"id": 7, "stage_id": 22, "stage_change_time": "2026-11-11T13:00:00Z", "owner_id": 1, "person_id": 603}
    # sem data de entrada
    i = {"id": 9, "stage_id": 22, "stage_change_time": None, "owner_id": 1, "person_id": 605}
    # estágio não configurado
    h = {"id": 8, "stage_id": 99, "stage_change_time": "2026-11-11T13:00:00Z", "owner_id": 1, "person_id": 604}
    por_estagio = {11: [e, f], 22: [g, i], 99: [h]}

    assert pipedrive.contar([], por_estagio, date(2026, 11, 1), date(2026, 11, 30)) == [
        Fato("abordagens", "linkedin", 28932026, 601, "2026-11-10"),
        Fato("respondidos", "instagram", 1, 603, "2026-11-11"),
    ]


def test_etiqueta_de_indicacao_vira_indicacao_do_dono():
    j = {"id": 10, "add_time": "2026-11-12T15:00:00Z", "pipeline_id": 1, "label_ids": [102, 101], "owner_id": 27369234, "person_id": 701}

    assert pipedrive.contar([j], {}, date(2026, 11, 1), date(2026, 11, 30)) == [
        Fato("numeros_captados", "linkedin", 27369234, 701, "2026-11-12"),
        Fato("indicacoes", None, 27369234, 701, "2026-11-12"),
    ]


def test_buscar_pipedrive_junta_dados_e_degrada_quando_cai(monkeypatch):
    A = {"id": 1, "add_time": "2026-11-05T15:00:00Z", "pipeline_id": 1, "label_ids": [101], "owner_id": 25564860, "person_id": 501}
    E = {"id": 5, "stage_id": 11, "stage_change_time": "2026-11-10T13:00:00Z", "owner_id": 28932026, "person_id": 601}
    criados = []
    estagios_pedidos = []
    pessoas_pedidas = []

    def no_estagio(id_estagio, desde):
        estagios_pedidos.append((id_estagio, desde))
        return [E] if id_estagio == 11 else []

    def etiquetas(ids):
        pessoas_pedidas.extend(ids)
        return {501: (55,), 601: (66,)}

    monkeypatch.setattr(pipedrive.api, "negocios_criados_desde", lambda inicio: criados.append(inicio) or [A])
    monkeypatch.setattr(pipedrive.api, "negocios_no_estagio", no_estagio)
    monkeypatch.setattr(pipedrive.api, "etiquetas_das_pessoas", etiquetas)

    resultado = pipedrive.buscar_pipedrive(date(2026, 11, 1), date(2026, 11, 30))

    desde = datetime(2026, 11, 1, tzinfo=TZ_SP)
    assert criados == [desde]
    assert sorted(i for i, _ in estagios_pedidos) == [11, 12, 21, 22]
    assert all(d == desde for _, d in estagios_pedidos)
    assert sorted(pessoas_pedidas) == [501, 601]
    assert resultado == pipedrive.DadosPipedrive(
        fatos=[
            Fato("numeros_captados", "linkedin", 25564860, 501, "2026-11-05"),
            Fato("abordagens", "linkedin", 28932026, 601, "2026-11-10"),
        ],
        etiquetas_por_pessoa={501: (55,), 601: (66,)},
    )

    def fora(inicio):
        raise pipedrive.api.PipedriveIndisponivel("fora")

    monkeypatch.setattr(pipedrive.api, "negocios_criados_desde", fora)
    banco.iniciar_registro_de_falhas()
    antes = banco.falhas_na_thread()

    assert pipedrive.buscar_pipedrive(date(2026, 11, 1), date(2026, 11, 30)) is pipedrive.VAZIO
    assert banco.tabelas_com_falha() == ["pipedrive"]
    assert banco.falhas_na_thread() == antes + 1


def test_numeros_captados_do_linkedin_vao_para_a_conta_da_etiqueta():
    COLUNAS = COLUNAS_POR_TABELA["metricas_contas"]

    def _m(**kw):
        return {c: kw.get(c, 0) for c in COLUNAS}

    jacob = ContaFunil(1, "Jacob", None, _m(conexoes_enviadas=40, numeros_captados=9), [{"data": "2026-11-03", "metricas": _m(conexoes_enviadas=40, numeros_captados=9)}])
    mary = ContaFunil(2, "Mary", None, _m(numeros_captados=4), [])
    dados = pipedrive.DadosPipedrive(
        [
            Fato("numeros_captados", "linkedin", 1, 501, "2026-11-03"),
            Fato("numeros_captados", "linkedin", 1, 501, "2026-11-05"),
            Fato("numeros_captados", "linkedin", 1, 502, "2026-11-05"),
            Fato("numeros_captados", "linkedin", 1, 501, "2026-10-29"),
            Fato("abordagens", "linkedin", 28932026, 501, "2026-11-05"),
            Fato("numeros_captados", "instagram", 1, 501, "2026-11-05"),
        ],
        {501: (55,), 502: (77,)},
    )
    etiqueta = {"Jacob": 55}.get

    contas, sem_conta = pipedrive.aplicar_em_contas([jacob, mary], dados, "linkedin", date(2026, 11, 1), etiqueta)

    assert contas[0].metricas == _m(conexoes_enviadas=40, numeros_captados=2)
    assert contas[0].serie == [
        {"data": "2026-10-29", "metricas": _m(numeros_captados=1)},
        {"data": "2026-11-03", "metricas": _m(conexoes_enviadas=40, numeros_captados=1)},
        {"data": "2026-11-05", "metricas": _m(numeros_captados=1)},
    ]
    assert contas[1].metricas == _m()
    assert sem_conta == _m(numeros_captados=1)
    assert jacob.metricas["numeros_captados"] == 9
    assert jacob.serie[0]["metricas"]["numeros_captados"] == 9


def test_instagram_troca_abordagens_respondidos_e_numeros_captados():
    COLUNAS = COLUNAS_POR_TABELA["metricas_contas"]

    def _m(**kw):
        return {c: kw.get(c, 0) for c in COLUNAS}

    lucas = ContaFunil(3, "Lucas", None, _m(abordagens=50, respondidos=20, numeros_captados=8, fups=7), [])
    dados = pipedrive.DadosPipedrive(
        [
            Fato("abordagens", "instagram", 28932026, 801, "2026-11-10"),
            Fato("abordagens", "instagram", 1, 801, "2026-11-10"),
            Fato("respondidos", "instagram", 1, 801, "2026-11-11"),
            Fato("numeros_captados", "instagram", 1, 801, "2026-11-09"),
            Fato("respondidos", "linkedin", 1, 801, "2026-11-11"),
        ],
        {801: (90,)},
    )
    etiqueta = {"Lucas": 90}.get

    contas, sem_conta = pipedrive.aplicar_em_contas([lucas], dados, "instagram", date(2026, 11, 1), etiqueta)

    assert contas[0].metricas == _m(abordagens=2, respondidos=1, numeros_captados=1, fups=7)
    assert sem_conta == _m()


def test_linhas_sdr_somam_por_sdr_e_dia_so_dos_donos_sdr():
    dados = pipedrive.DadosPipedrive(
        [
            Fato("abordagens", "linkedin", 28932026, 1, "2026-11-10"),
            Fato("abordagens", "instagram", 28932026, 2, "2026-11-10"),
            Fato("respondidos", "linkedin", 27369234, 3, "2026-11-11"),
            Fato("indicacoes", None, 27369234, 4, "2026-11-10"),
            Fato("abordagens", "linkedin", 25564860, 5, "2026-11-10"),
            Fato("numeros_captados", "linkedin", 28932026, 6, "2026-11-10"),
        ],
        {},
    )
    id_dash_por_dono = {28932026: 11, 27369234: 14}

    assert pipedrive.linhas_sdr(dados, id_dash_por_dono) == [
        {"id_user": 11, "data": "2026-11-10", "abordagens": 2, "respondidos": 0, "indicacoes": 0},
        {"id_user": 14, "data": "2026-11-10", "abordagens": 0, "respondidos": 0, "indicacoes": 1},
        {"id_user": 14, "data": "2026-11-11", "abordagens": 0, "respondidos": 1, "indicacoes": 0},
    ]
