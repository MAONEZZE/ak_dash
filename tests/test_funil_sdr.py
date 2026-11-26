"""Testes de `dominios/funil/sdr.py` — página Funil SDR."""
from __future__ import annotations

from datetime import date, datetime, time

from app.dominios.funil import sdr
from app.fontes import supabase
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


def test_meta_do_sdr_e_a_parte_dele_na_meta_do_time_pela_diaria():
    ids = [11, 14]
    # dia: a própria diária
    assert METAS.da_pessoa(resolver_periodo("dia", "2026-11-16"), ids, 11, "inscricoes_realizadas") == 7
    # mês: 88 × 7/13 e 88 × 6/13
    assert METAS.da_pessoa(resolver_periodo("mes", "2026-11"), ids, 11, "inscricoes_realizadas") == 47
    assert METAS.da_pessoa(resolver_periodo("mes", "2026-11"), ids, 14, "inscricoes_realizadas") == 41
    # custom: diária × dias úteis (16 a 20/11 = 5)
    assert METAS.da_pessoa(resolver_periodo("custom", "2026-11-16..2026-11-20"), ids, 14, "inscricoes_realizadas") == 30
    # sem diária do SDR, sem meta
    assert METAS.da_pessoa(resolver_periodo("mes", "2026-11"), [11, 99], 99, "inscricoes_realizadas") is None


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


def test_meta_diaria_de_inscricoes_e_o_que_falta_pela_capacidade_dividido_pelos_dias_ate_o_evento_sem_domingo():
    evento, hoje = date(2026, 11, 26), date(2026, 11, 23)  # seg 23, ter 24, qua 25: 3 dias
    assert sdr.meta_diaria_inscricoes(80, 68, evento, hoje) == 4
    # Arredonda para cima: 10 em 3 dias = 4.
    assert sdr.meta_diaria_inscricoes(80, 70, evento, hoje) == 4
    # Véspera: tudo o que falta.
    assert sdr.meta_diaria_inscricoes(80, 70, evento, date(2026, 11, 25)) == 10
    # Domingo não conta: de sáb 28 até a véspera de ter 01/12 = sáb + seg = 2 dias.
    assert sdr.meta_diaria_inscricoes(80, 70, date(2026, 12, 1), date(2026, 11, 28)) == 5
    # Só o domingo antes do evento: sem dia de inscrição, sem meta.
    assert sdr.meta_diaria_inscricoes(80, 70, date(2026, 11, 30), date(2026, 11, 29)) is None
    # Capacidade já atingida: 0.
    assert sdr.meta_diaria_inscricoes(80, 80, evento, hoje) == 0
    assert sdr.meta_diaria_inscricoes(80, 95, evento, hoje) == 0
    # Sem capacidade, dia do evento ou depois: sem meta.
    assert sdr.meta_diaria_inscricoes(None, 10, evento, hoje) is None
    assert sdr.meta_diaria_inscricoes(80, 10, evento, evento) is None
    assert sdr.meta_diaria_inscricoes(80, 10, evento, date(2026, 11, 27)) is None


def test_meta_do_velocimetro_de_inscricoes_por_filtro():
    hoje, longe, perto = date(2026, 11, 23), date(2026, 12, 5), date(2026, 11, 26)
    # Longe (11 dias sem domingo): faltam 33 → 3/dia; semana = 3 × 6.
    assert sdr.meta_velocimetro_inscricoes("dia", 80, 47, longe, hoje) == 3
    assert sdr.meta_velocimetro_inscricoes("semana", 80, 47, longe, hoje) == 18
    # Evento no meio da semana: 12 em 3 dias = 4/dia, mas a semana fica no que falta (12), não 24.
    assert sdr.meta_velocimetro_inscricoes("semana", 80, 68, perto, hoje) == 12
    # Capacidade atingida: 0 também na semana.
    assert sdr.meta_velocimetro_inscricoes("semana", 80, 90, perto, hoje) == 0
    # Dia do evento em diante: sem meta.
    assert sdr.meta_velocimetro_inscricoes("semana", 80, 10, perto, perto) is None
    # Mês, ano e custom: a capacidade total.
    for g in ("mes", "ano", "custom"):
        assert sdr.meta_velocimetro_inscricoes(g, 80, 47, longe, hoje) == 80
        assert sdr.meta_velocimetro_inscricoes(g, None, 47, longe, hoje) is None


def test_buscar_metricas_funil_sdr_le_o_intervalo_pela_fonte(monkeypatch):
    chamadas: list[tuple] = []

    def ler_metricas(inicio, fim):
        chamadas.append((inicio, fim))
        return [{"id_user": 9, "data": "2026-11-03"}]

    monkeypatch.setattr(supabase, "ler_metricas_funil_sdr", ler_metricas)
    linhas = sdr.buscar_metricas_funil_sdr(date(2026, 11, 10), date(2026, 11, 16))
    assert linhas == [{"id_user": 9, "data": "2026-11-03"}]
    assert chamadas == [(date(2026, 11, 10), date(2026, 11, 16))]


def test_buscar_metas_funil_sdr_diaria_vem_da_aba_do_sdr_e_semana_mes_do_dashboard(monkeypatch):
    # Diária da tabela "Vendedor" do Dashboard SDR (7) é ignorada: vale a da aba do SDR (4).
    monkeypatch.setattr(
        supabase,
        "ler_metas_funil_sdr",
        lambda: [
            {"metrica": "inscricoes_realizadas", "periodo": "dia", "id_user": 9, "valor": 7},
            {"metrica": "abordagens", "periodo": "semana", "id_user": None, "valor": 50},
            {"metrica": "inscricoes_realizadas", "periodo": "mes", "id_user": None, "valor": 88},
        ],
    )
    cargos = []
    monkeypatch.setattr(
        supabase,
        "ler_metas_do_cargo",
        lambda cargo: cargos.append(cargo) or [{"id_user": 9, "metrica": "inscricoes_realizadas", "valor_diario": 4}],
    )
    metas = sdr.buscar_metas_funil_sdr()
    assert cargos == ["sdr"]
    assert metas.diarias == {(9, "inscricoes_realizadas"): 4}
    assert metas.semanais == {"abordagens": 50}
    assert metas.mensais == {"inscricoes_realizadas": 88}
