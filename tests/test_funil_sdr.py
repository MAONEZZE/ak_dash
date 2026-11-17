"""Testes de `dominios/funil/sdr.py` — página Funil SDR."""
from __future__ import annotations

from datetime import date, datetime, time

from app.dominios.funil import sdr
from app.periodo import TZ_SP, resolver_periodo

METAS = sdr.MetasFunilSdr(
    diarias={(11, "inscricoes_realizadas"): 7, (14, "inscricoes_realizadas"): 6, (11, "reunioes_agendadas"): 2},
    semanais={"inscricoes_realizadas": 55},
    mensais={"inscricoes_realizadas": 88, "reunioes_agendadas": 44},
)


def test_meta_do_time_segue_a_granularidade():
    ids = [11, 14]
    assert METAS.do_time(resolver_periodo("dia", "2026-11-16"), ids, "inscricoes_realizadas") == 13
    assert METAS.do_time(resolver_periodo("semana", "2026-W47"), ids, "inscricoes_realizadas") == 55
    assert METAS.do_time(resolver_periodo("mes", "2026-11"), ids, "inscricoes_realizadas") == 88
    # custom: diárias × dias úteis (16 a 20/11 = 5)
    assert METAS.do_time(resolver_periodo("custom", "2026-11-16..2026-11-20"), ids, "inscricoes_realizadas") == 65
    assert METAS.do_time(resolver_periodo("semana", "2026-W47"), ids, "indicacoes") is None
    assert METAS.do_time(resolver_periodo("dia", "2026-11-16"), [14], "reunioes_agendadas") is None


def test_montar_resposta_soma_por_sdr_e_calcula_metricas_do_time():
    periodo = resolver_periodo("mes", "2026-11")
    sdrs = [{"id": 11, "nome": "Juca", "imagem_url": None}, {"id": 14, "nome": "Jennifer", "imagem_url": "j.png"}]
    linhas = [
        {"id_user": 14, "data": "2026-11-04", "abordagens": None, "respondidos": 34, "inscricoes_realizadas": 2, "indicacoes": 1, "reunioes_agendadas": 0},
        {"id_user": 11, "data": "2026-11-03", "abordagens": 20, "respondidos": 0, "inscricoes_realizadas": 3, "indicacoes": 1, "reunioes_agendadas": 1},
        {"id_user": 11, "data": "2026-11-05", "abordagens": 10, "respondidos": 8, "inscricoes_realizadas": 1, "indicacoes": None, "reunioes_agendadas": 2},
        {"id_user": 99, "data": "2026-11-05", "inscricoes_realizadas": 50},  # inativo / sem cargo sdr
    ]

    corpo = sdr.montar_resposta(
        periodo, sdrs, linhas, METAS,
        hoje=date(2026, 11, 16), agora=datetime(2026, 11, 16, 12, tzinfo=TZ_SP),
        expediente_inicio=time(10), expediente_fim=time(19), numeros_captados=40,
    )

    assert [s["nome"] for s in corpo["sdrs"]] == ["Juca", "Jennifer"]
    assert corpo["sdrs"][0]["metricas"] == {
        "abordagens": 30, "respondidos": 8, "inscricoes_realizadas": 4, "indicacoes": 1, "reunioes_agendadas": 3,
    }
    assert [d["data"] for d in corpo["sdrs"][0]["serie"]] == ["2026-11-03", "2026-11-05"]
    assert corpo["sdrs"][1]["metricas"]["respondidos"] == 34
    # Funil do time: oportunidades = números captados (LinkedIn + Instagram) + indicações dos SDRs.
    assert corpo["funil"] == {
        "numeros_captados": 40, "indicacoes": 2, "oportunidades": 42, "abordados": 30, "respondidos": 42, "inscritos": 6,
    }
    assert corpo["sdrs"][1]["id_user"] == "14"

    inscricoes, indicacoes, reunioes = corpo["metricas_time"]
    assert inscricoes["metrica"] == "inscricoes_realizadas"
    assert (inscricoes["realizado"], inscricoes["meta_periodo"]) == (6, 88)
    assert inscricoes["falta_folga"] == {"tipo": "falta", "valor": 82}
    assert inscricoes["pct_atingimento"] == 6.8
    assert inscricoes["previsao"] is not None  # só no mês
    assert (indicacoes["realizado"], indicacoes["meta_periodo"], indicacoes["pct_atingimento"]) == (2, None, None)
    assert (reunioes["realizado"], reunioes["meta_periodo"]) == (3, 44)


def test_montar_resposta_linhas_antes_do_periodo_so_entram_na_serie():
    """Filtro de dia: a rota manda a semana até o dia pro gráfico; os totais são só do dia."""
    periodo = resolver_periodo("dia", "2026-11-16")
    linhas = [
        {"id_user": 11, "data": "2026-11-12", "abordagens": 9, "respondidos": 0, "inscricoes_realizadas": 4, "indicacoes": 0, "reunioes_agendadas": 3},
        {"id_user": 11, "data": "2026-11-16", "abordagens": 2, "respondidos": 1, "inscricoes_realizadas": 1, "indicacoes": 0, "reunioes_agendadas": 1},
    ]
    corpo = sdr.montar_resposta(
        periodo, [{"id": 11, "nome": "Juca", "imagem_url": None}], linhas, METAS,
        hoje=date(2026, 11, 16), agora=datetime(2026, 11, 16, 12, tzinfo=TZ_SP),
        expediente_inicio=time(10), expediente_fim=time(19), numeros_captados=0,
    )
    (juca,) = corpo["sdrs"]
    assert [d["data"] for d in juca["serie"]] == ["2026-11-12", "2026-11-16"]
    assert juca["metricas"]["abordagens"] == 2
    assert corpo["funil"]["inscritos"] == 1
    assert corpo["metricas_time"][2]["realizado"] == 1  # reuniões agendadas só do dia
