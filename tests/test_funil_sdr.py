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


def test_dias_da_janela_do_evento_vao_da_primeira_inscricao_a_vespera_sem_domingo():
    # sex 20 → evento qui 26: sáb 21 entra, dom 22 fica fora, 26 é o evento.
    assert sdr.dias_da_janela_do_evento(date(2026, 11, 20), date(2026, 11, 26)) == [
        date(2026, 11, 20), date(2026, 11, 21), date(2026, 11, 23), date(2026, 11, 24), date(2026, 11, 25),
    ]
    assert sdr.dias_da_janela_do_evento(None, date(2026, 11, 26)) == []
    assert sdr.dias_da_janela_do_evento(date(2026, 11, 26), date(2026, 11, 26)) == []


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


def test_ranking_da_pagina_sdr_pontua_ligacao_8_e_inscricao_10_com_empate_na_mesma_posicao():
    lista = [
        {"id": 14, "ligacoes": 5, "inscricoes": 2},
        {"id": 11, "ligacoes": 0, "inscricoes": 6},
        {"id": 20, "ligacoes": 10, "inscricoes": 0},
        {"id": 30, "ligacoes": 0, "inscricoes": 0},
    ]
    resultado = sdr.ranquear_pagina_sdr(lista)
    assert [(s["id"], s["pontuacao"], s["posicao"]) for s in resultado] == [(20, 80, 1), (11, 60, 2), (14, 60, 2), (30, 0, 3)]
    assert lista[0] == {"id": 14, "ligacoes": 5, "inscricoes": 2}


def test_serie_do_evento_acumula_ate_hoje_e_ritmo_soma_a_meta_diaria_ao_acumulado_do_dia_anterior():
    dias = [date(2026, 11, 20), date(2026, 11, 21), date(2026, 11, 23), date(2026, 11, 24), date(2026, 11, 25)]
    # 22 é domingo: não está na janela, mas entra no acumulado do dia 23.
    por_dia = {date(2026, 11, 20): 2, date(2026, 11, 21): 3, date(2026, 11, 22): 1, date(2026, 11, 23): 1}
    hoje = date(2026, 11, 23)
    assert sdr.serie_do_evento(dias, por_dia, meta_diaria=4, hoje=hoje) == [
        {"data": "2026-11-20", "acumulado": 2, "ritmo": 4},
        {"data": "2026-11-21", "acumulado": 5, "ritmo": 6},
        {"data": "2026-11-23", "acumulado": 7, "ritmo": 9},
        {"data": "2026-11-24", "acumulado": None, "ritmo": 11},
        {"data": "2026-11-25", "acumulado": None, "ritmo": 15},
    ]
    sem_meta = sdr.serie_do_evento(dias, por_dia, meta_diaria=None, hoje=hoje)
    assert [(p["acumulado"], p["ritmo"]) for p in sem_meta] == [(2, None), (5, None), (7, None), (None, None), (None, None)]


def test_previsao_ate_o_evento_projeta_a_media_dos_dias_decorridos_e_compara_com_meta_diaria_vezes_dias():
    dias = [date(2026, 11, 20), date(2026, 11, 21), date(2026, 11, 23), date(2026, 11, 24), date(2026, 11, 25)]
    hoje = date(2026, 11, 23)  # 3 dias decorridos
    assert sdr.previsao_ate_o_evento(dias, acumulado_hoje=7, hoje=hoje, meta_diaria=4) == {"valor": 12, "meta": 20, "pct_meta": 60.0}
    assert sdr.previsao_ate_o_evento(dias, acumulado_hoje=7, hoje=hoje, meta_diaria=None) == {"valor": 12, "meta": None, "pct_meta": None}
    # Janela encerrada: previsão = realizado.
    assert sdr.previsao_ate_o_evento(dias, acumulado_hoje=9, hoje=date(2026, 12, 1), meta_diaria=4) == {"valor": 9, "meta": 20, "pct_meta": 45.0}
    assert sdr.previsao_ate_o_evento([], acumulado_hoje=0, hoje=hoje, meta_diaria=4) is None


def test_primeira_inscricao_vira_dia_em_sp_e_ligacoes_somam_por_sdr(monkeypatch):
    monkeypatch.setattr(sdr.sed, "ler_primeira_inscricao", lambda i: [{"created_at": "2026-11-20T02:30:00+00:00"}])
    chamadas: list[tuple] = []

    def fake(tabela, inicio, fim, colunas):
        chamadas.append((tabela, inicio, fim, colunas))
        return [
            {"id_user": 11, "data": "2026-11-03", "ligacoes_realizadas": 4},
            {"id_user": 11, "data": "2026-11-04", "ligacoes_realizadas": None},
            {"id_user": 14, "data": "2026-11-04", "ligacoes_realizadas": 6},
            {"id_user": 11, "data": "2026-11-05", "ligacoes_realizadas": 3},
        ]

    monkeypatch.setattr(sdr.supabase, "ler_metricas_planilha", fake)
    assert sdr.data_primeira_inscricao("e1") == date(2026, 11, 19)  # 02:30 UTC = 23:30 em SP do dia 19
    assert sdr.buscar_ligacoes_sdr(date(2026, 11, 1), date(2026, 11, 30)) == {11: 7, 14: 6}
    assert chamadas == [("metricas_sdrs", date(2026, 11, 1), date(2026, 11, 30), ["ligacoes_realizadas"])]

    monkeypatch.setattr(sdr.sed, "ler_primeira_inscricao", lambda i: [])
    assert sdr.data_primeira_inscricao("e1") is None


def test_montar_resposta_pagina_sdr_junta_card_ranking_previsao_e_serie_por_sdr():
    periodo = resolver_periodo("mes", "2026-11")
    sdrs = [{"id": 11, "nome": "Juca Silva", "imagem_url": None}, {"id": 14, "nome": "Jennifer Souza", "imagem_url": "j.png"}]
    linhas_periodo = [{"id_user": 11, "data": "2026-11-03", "inscricoes_realizadas": 6}, {"id_user": 14, "data": "2026-11-04", "inscricoes_realizadas": 2}]
    linhas_janela = [{"id_user": 11, "data": "2026-11-20", "inscricoes_realizadas": 2}, {"id_user": 11, "data": "2026-11-21", "inscricoes_realizadas": 3}]
    ligacoes = {14: 5}
    evento = {"id": "e1", "titulo": "Imersão", "data": "2026-11-26T16:00:00+00:00", "capacidade": 60}
    dias = sdr.dias_da_janela_do_evento(date(2026, 11, 20), date(2026, 11, 26))

    r = sdr.montar_resposta_pagina_sdr(periodo, sdrs, linhas_periodo, linhas_janela, ligacoes, METAS, evento, dias, date(2026, 11, 21))

    assert r["periodo"] == {"granularidade": "mes", "inicio": "2026-11-01", "fim": "2026-11-30"}
    assert r["evento"] == evento
    assert r["janela"] == {"inicio": "2026-11-20", "fim": "2026-11-25"}
    # Juca 6×10 = 60; Jennifer 5×8 + 2×10 = 60: empatados na posição 1.
    assert [(s["id_user"], s["pontuacao"], s["posicao"]) for s in r["sdrs"]] == [("11", 60, 1), ("14", 60, 1)]
    juca = r["sdrs"][0]
    assert juca["nome"] == "Juca Silva"
    assert juca["inscricoes"] == 6
    assert juca["ligacoes"] == 0
    assert juca["meta_inscricoes"] == METAS.da_pessoa(periodo, [11, 14], 11, "inscricoes_realizadas")
    assert juca["meta_diaria"] == 7
    # 5 em 2 dias × 5 dias da janela = 12,5 → 12; meta 7 × 5 = 35.
    assert juca["previsao"] == {"valor": 12, "meta": 35, "pct_meta": 34.3}
    assert len(juca["serie_evento"]) == 5
    assert juca["serie_evento"][1] == {"data": "2026-11-21", "acumulado": 5, "ritmo": 9}

    r_sem_evento = sdr.montar_resposta_pagina_sdr(periodo, sdrs, linhas_periodo, linhas_janela, ligacoes, METAS, None, [], date(2026, 11, 21))
    assert r_sem_evento["janela"] is None
    assert all(s["previsao"] is None and s["serie_evento"] == [] for s in r_sem_evento["sdrs"])


def test_contar_negocios_sdr_so_de_donos_sdr():
    negocios = [{"owner_id": 100}, {"owner_id": 100}, {"owner_id": 200}, {"owner_id": 999}]

    assert sdr.contar_negocios_sdr(negocios, {100: 11, 200: 14, 300: 15}) == {11: 2, 14: 1, 15: 0}


def test_inscricoes_pipedrive_contam_cada_negocio_uma_vez_e_separam_o_dia():
    entradas = [
        {"id_deal": 1, "id_dono": 100, "entrou_em": "2026-11-03T15:00:00+00:00"},
        {"id_deal": 1, "id_dono": 100, "entrou_em": "2026-11-25T15:00:00+00:00"},  # reentrada: não conta de novo
        {"id_deal": 2, "id_dono": 100, "entrou_em": "2026-11-25T14:00:00+00:00"},  # hoje em SP
        {"id_deal": 3, "id_dono": 100, "entrou_em": "2026-11-26T02:00:00+00:00"},  # 25/11 23h em SP: hoje
        {"id_deal": 4, "id_dono": 200, "entrou_em": "2026-11-26T12:00:00+00:00"},
        {"id_deal": 5, "id_dono": 999, "entrou_em": "2026-11-25T12:00:00+00:00"},  # não é SDR
    ]

    contagem = sdr.contar_inscricoes_pipedrive(entradas, {100: 11, 200: 14}, date(2026, 11, 25))

    assert contagem == {11: {"mes": 3, "hoje": 2}, 14: {"mes": 1, "hoje": 0}}


def test_mes_do_ranking_e_o_mes_do_fim_do_filtro():
    assert sdr.mes_do_ranking(resolver_periodo("dia", "2026-02-10")) == (date(2026, 2, 1), date(2026, 2, 28))
    assert sdr.mes_do_ranking(resolver_periodo("mes", "2026-12")) == (date(2026, 12, 1), date(2026, 12, 31))


def test_janela_da_meta_vai_do_dia_1_a_vespera_do_evento_no_maximo_o_fim_do_mes():
    mes = (date(2026, 11, 1), date(2026, 11, 30))
    assert sdr.janela_da_meta(mes, date(2026, 11, 26)) == (date(2026, 11, 1), date(2026, 11, 25))
    assert sdr.janela_da_meta(mes, date(2026, 12, 2)) == (date(2026, 11, 1), date(2026, 11, 30))
    assert sdr.janela_da_meta(mes, None) == (date(2026, 11, 1), date(2026, 11, 30))
    assert sdr.janela_da_meta(mes, date(2026, 11, 1)) is None
    assert sdr.janela_da_meta(mes, date(2026, 10, 20)) is None


def test_ranking_do_mes_entra_no_card_de_cada_sdr_com_a_meta_mensal_de_inscricoes():
    p = resolver_periodo("dia", "2026-11-25")
    sdrs = [{"id": 11, "nome": "Juca", "imagem_url": None}, {"id": 14, "nome": "Jennifer", "imagem_url": None}]

    corpo = sdr.montar_resposta_pagina_sdr(
        p, sdrs, [], [], {}, METAS, None, [], date(2026, 11, 25),
        mes_ranking=sdr.mes_do_ranking(p),
        negocios={11: 295},
        inscricoes_pipedrive={11: {"mes": 10, "hoje": 2}},
        inscritos_sed_mes=120,
    )

    por_id = {c["id_user"]: c["ranking_mes"] for c in corpo["sdrs"]}
    # meta mensal do time (88) na proporção das diárias (7 de 13), mesmo no filtro de dia
    assert por_id["11"] == {"negocios": 295, "inscricoes": 10, "inscricoes_hoje": 2, "meta": 47}
    assert por_id["14"] == {"negocios": 0, "inscricoes": 0, "inscricoes_hoje": 0, "meta": 41}
    assert corpo["mes_ranking"] == {"inicio": "2026-11-01", "fim": "2026-11-30"}
    assert corpo["inscritos_sed_mes"] == 120
