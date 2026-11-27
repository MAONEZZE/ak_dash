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
            pipe_id_abordados_pipeline_principal=11,
            pipe_id_respondidos_pipeline_principal=12,
            pipe_id_abordados_pipeline_instagram=21,
            pipe_id_respondidos_pipeline_instagram=22,
            pipe_id_etiqueta_negocio_linkedin=101,
            pipe_id_etiqueta_negocio_indicacao=102,
            pipe_id_oportunidades_pipeline_principal=1,
            pipe_id_etiqueta_negocio_instagram=127,
        ),
    )


def test_criado_no_periodo_com_etiqueta_linkedin_vira_numero_captado_e_pipeline_instagram_nao():
    a = {"id": 1, "add_time": "2026-11-05T15:00:00Z", "pipeline_id": 1, "label_ids": [101], "owner_id": 25564860, "person_id": 501}
    # 23h do dia 04 em SP
    b = {"id": 2, "add_time": "2026-11-05T02:00:00Z", "pipeline_id": 3, "label_ids": [], "owner_id": 28932026, "person_id": 502}
    # sem etiqueta e fora do Instagram
    c = {"id": 3, "add_time": "2026-11-06T12:00:00Z", "pipeline_id": 1, "label_ids": None, "owner_id": 1, "person_id": None}
    # depois do fim
    d = {"id": 4, "add_time": "2026-12-01T12:00:00Z", "pipeline_id": 3, "label_ids": [101], "owner_id": 1, "person_id": 503}

    assert pipedrive.contar([a, b, c, d], date(2026, 11, 1), date(2026, 11, 30)) == [
        Fato("numeros_captados", "linkedin", 25564860, 501, "2026-11-05"),
    ]


def test_entrada_no_estagio_conta_na_data_em_que_entrou_mesmo_se_ja_avancou():
    entradas = [
        {"id_deal": 5, "id_estagio": 11, "entrou_em": "2026-11-10T13:00:00+00:00", "id_dono": 28932026, "id_pessoa": 601},
        # o mesmo negócio avançou para Respondidos: continua contando em Abordados
        {"id_deal": 5, "id_estagio": 12, "entrou_em": "2026-11-12T13:00:00+00:00", "id_dono": 28932026, "id_pessoa": 601},
        # 01h do dia 01/12 em UTC = 22h do dia 30/11 em SP
        {"id_deal": 7, "id_estagio": 22, "entrou_em": "2026-12-01T01:00:00+00:00", "id_dono": 1, "id_pessoa": 603},
        # entrou antes do início
        {"id_deal": 6, "id_estagio": 11, "entrou_em": "2026-10-31T13:00:00+00:00", "id_dono": 28932026, "id_pessoa": 602},
        # estágio não configurado
        {"id_deal": 8, "id_estagio": 99, "entrou_em": "2026-11-11T13:00:00+00:00", "id_dono": 1, "id_pessoa": 604},
    ]

    assert pipedrive.contar_entradas(entradas, date(2026, 11, 1), date(2026, 11, 30)) == [
        Fato("abordagens", "linkedin", 28932026, 601, "2026-11-10"),
        Fato("respondidos", "linkedin", 28932026, 601, "2026-11-12"),
        Fato("abordagens", "instagram", 1, 603, "2026-11-30"),
        Fato("respondidos", "instagram", 1, 603, "2026-11-30"),
    ]


def test_quem_entrou_em_respondido_conta_tambem_como_abordado_uma_vez(monkeypatch):
    monkeypatch.setattr(
        pipedrive,
        "settings",
        dataclasses.replace(pipedrive.settings, pipe_id_abordados_pipeline_principal=2, pipe_id_respondidos_pipeline_principal=3),
    )
    entradas = [
        # negócio 10: só entrou em Respondidos
        {"id_deal": 10, "id_estagio": 3, "entrou_em": "2026-11-05T15:00:00Z", "id_dono": 28932026, "id_pessoa": 10},
        # negócio 11: entrou em Abordados e depois em Respondidos
        {"id_deal": 11, "id_estagio": 2, "entrou_em": "2026-11-03T15:00:00Z", "id_dono": 28932026, "id_pessoa": 11},
        {"id_deal": 11, "id_estagio": 3, "entrou_em": "2026-11-04T15:00:00Z", "id_dono": 28932026, "id_pessoa": 11},
        # negócio 12: entrou em Abordados antes do período; em Respondidos dentro dele
        {"id_deal": 12, "id_estagio": 2, "entrou_em": "2026-10-20T15:00:00Z", "id_dono": 28932026, "id_pessoa": 12},
        {"id_deal": 12, "id_estagio": 3, "entrou_em": "2026-11-06T15:00:00Z", "id_dono": 28932026, "id_pessoa": 12},
    ]

    fatos = pipedrive.contar_entradas(entradas, date(2026, 11, 1), date(2026, 11, 30))

    abordagens = [f for f in fatos if f.metrica == "abordagens"]
    respondidos = [f for f in fatos if f.metrica == "respondidos"]
    assert [(f.canal, f.id_pessoa, f.data) for f in abordagens] == [
        ("linkedin", 11, "2026-11-03"),
        ("linkedin", 10, "2026-11-05"),
        ("linkedin", 12, "2026-11-06"),
    ]
    assert [(f.canal, f.id_pessoa, f.data) for f in respondidos] == [
        ("linkedin", 11, "2026-11-04"),
        ("linkedin", 10, "2026-11-05"),
        ("linkedin", 12, "2026-11-06"),
    ]


def test_etiqueta_de_indicacao_vira_indicacao_do_dono():
    j = {"id": 10, "add_time": "2026-11-12T15:00:00Z", "pipeline_id": 1, "label_ids": [102, 101], "owner_id": 27369234, "person_id": 701}

    assert pipedrive.contar([j], date(2026, 11, 1), date(2026, 11, 30)) == [
        Fato("numeros_captados", "linkedin", 27369234, 701, "2026-11-12"),
        Fato("indicacoes", None, 27369234, 701, "2026-11-12"),
    ]


def test_buscar_pipedrive_junta_criados_e_entradas_do_historico(monkeypatch):
    A = {"id": 1, "add_time": "2026-11-05T15:00:00Z", "pipeline_id": 1, "label_ids": [101], "owner_id": 25564860, "person_id": 501}
    E = {"id_deal": 5, "id_estagio": 11, "entrou_em": "2026-11-10T13:00:00+00:00", "id_dono": 28932026, "id_pessoa": 601}
    criados = []
    entradas_pedidas = []
    pessoas_pedidas = []

    def etiquetas(ids):
        pessoas_pedidas.extend(ids)
        return {501: (55,)}

    monkeypatch.setattr(pipedrive.api, "negocios_criados_desde", lambda inicio: criados.append(inicio) or [A])
    monkeypatch.setattr(
        pipedrive.supabase,
        "ler_entradas_estagio",
        lambda ids, desde, ate: entradas_pedidas.append((sorted(ids), desde, ate)) or [E],
    )
    monkeypatch.setattr(pipedrive.api, "etiquetas_das_pessoas", etiquetas)

    resultado = pipedrive.buscar_pipedrive(date(2026, 11, 1), date(2026, 11, 30))

    desde = datetime(2026, 11, 1, tzinfo=TZ_SP)
    assert criados == [desde]
    assert entradas_pedidas == [([11, 12, 21, 22], desde, datetime(2026, 12, 1, tzinfo=TZ_SP))]
    # só os números captados precisam da etiqueta da pessoa
    assert pessoas_pedidas == [501]
    assert resultado == pipedrive.DadosPipedrive(
        fatos=[
            Fato("numeros_captados", "linkedin", 25564860, 501, "2026-11-05"),
            Fato("abordagens", "linkedin", 28932026, 601, "2026-11-10"),
        ],
        etiquetas_por_pessoa={501: (55,)},
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


def test_entrada_na_oportunidade_feita_com_prosp_insta_vira_numero_captado_do_instagram(monkeypatch):
    entradas = [
        {"id_deal": 30, "id_estagio": 1, "entrou_em": "2026-11-10T13:00:00+00:00", "id_dono": 5, "id_pessoa": 801},
        # sem a etiqueta
        {"id_deal": 31, "id_estagio": 1, "entrou_em": "2026-11-11T13:00:00+00:00", "id_dono": 5, "id_pessoa": 802},
        # 22h do dia 30/11 em SP
        {"id_deal": 32, "id_estagio": 1, "entrou_em": "2026-12-01T01:00:00+00:00", "id_dono": 6, "id_pessoa": 803},
        # entrou antes do início
        {"id_deal": 33, "id_estagio": 1, "entrou_em": "2026-10-31T13:00:00+00:00", "id_dono": 5, "id_pessoa": 804},
        # outro estágio
        {"id_deal": 34, "id_estagio": 21, "entrou_em": "2026-11-12T13:00:00+00:00", "id_dono": 5, "id_pessoa": 805},
    ]
    etiquetas = {30: (127, 5), 31: (126,), 32: (127,), 33: (127,), 34: (127,)}

    assert pipedrive.contar_oportunidades_instagram(entradas, etiquetas, date(2026, 11, 1), date(2026, 11, 30)) == [
        Fato("numeros_captados", "instagram", 5, 801, "2026-11-10"),
        Fato("numeros_captados", "instagram", 6, 803, "2026-11-30"),
    ]

    monkeypatch.setattr(pipedrive, "settings", dataclasses.replace(pipedrive.settings, pipe_id_etiqueta_negocio_instagram=None))
    assert pipedrive.contar_oportunidades_instagram(entradas, etiquetas, date(2026, 11, 1), date(2026, 11, 30)) == []
