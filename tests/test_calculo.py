from __future__ import annotations

from datetime import date

from app.dominios.comercial.banco import HistoricoMetrica
from app.dominios.comercial.calculo import calcular_mes_corrente, montar_resposta_comercial
from app.dominios.comercial.planilha import PlanilhaParseada
from app.periodo import Periodo


def _planilha_sdr(arquivo: str, email_sdr: str, meta_conexoes: int, valores_conexoes: dict) -> PlanilhaParseada:
    return PlanilhaParseada(
        arquivo=arquivo,
        email_sdr=email_sdr,
        email_closer="closer@teste.com",
        metas={"conexoes_enviadas": meta_conexoes},
        valores={"conexoes_enviadas": valores_conexoes},
    )


def test_meta_do_periodo_e_meta_diaria_vezes_dias_uteis():
    # Abril/2026 completo (hoje = 30/04) tem 22 dias úteis; meta diária 40 -> 880.
    planilha = _planilha_sdr("p1.csv", "sdr@teste.com", 40, {d: 10 for d in range(1, 31)})
    resultado = calcular_mes_corrente(
        [planilha], "sdr", 2026, 4, dia_inicio=1, dia_fim=30,
        emails_filtro=None, avisos=[],
    )
    totais = resultado["sdr@teste.com"].totais_por_metrica["conexoes_enviadas"]
    assert totais["meta_periodo"] == 40 * 22
    assert totais["realizado"] == 10 * 30


def test_dia_fora_do_calendario_com_valor_gera_aviso_e_e_descartado():
    # Mês de 30 dias (abril), dia 31 com valor não-zero -> aviso, mas não soma no realizado.
    valores = {d: 5 for d in range(1, 31)}
    valores[31] = 99
    planilha = _planilha_sdr("p1.csv", "sdr@teste.com", 40, valores)
    avisos: list[str] = []
    resultado = calcular_mes_corrente(
        [planilha], "sdr", 2026, 4, dia_inicio=1, dia_fim=30,
        emails_filtro=None, avisos=avisos,
    )
    totais = resultado["sdr@teste.com"].totais_por_metrica["conexoes_enviadas"]
    assert totais["realizado"] == 5 * 30  # dia 31 não entrou
    assert any("dia 31 fora do calendário" in a for a in avisos)


def test_dia_fora_do_calendario_com_zero_nao_gera_aviso():
    valores = {d: 5 for d in range(1, 31)}
    valores[31] = 0
    planilha = _planilha_sdr("p1.csv", "sdr@teste.com", 40, valores)
    avisos: list[str] = []
    calcular_mes_corrente(
        [planilha], "sdr", 2026, 4, dia_inicio=1, dia_fim=30,
        emails_filtro=None, avisos=avisos,
    )
    assert avisos == []


def test_lacuna_nunca_vira_status_abaixo_da_meta():
    # Nenhum dia preenchido -> sem_preenchimento, nunca abaixo_da_meta.
    planilha = _planilha_sdr("p1.csv", "sdr@teste.com", 40, {d: None for d in range(1, 31)})
    periodo = Periodo("mes", date(2026, 4, 1), date(2026, 4, 30))
    resposta = montar_resposta_comercial(
        periodo=periodo,
        funcao="sdr",
        planilhas_mes_corrente=[planilha],
        avisos_estruturais=[],
        historico=[],
        cadastro_nomes={},
        emails_filtro=None,
        hoje=date(2026, 4, 30),
    )
    metrica = next(
        m for m in resposta["pessoas"][0]["metricas"] if m["metrica"] == "conexoes_enviadas"
    )
    assert metrica["status"] == "sem_preenchimento"


def test_metas_atingidas_conta_status_atingido():
    # Meta diária baixa (1) para bater fácil com realizado alto.
    planilha = _planilha_sdr("p1.csv", "sdr@teste.com", 1, {d: 10 for d in range(1, 31)})
    periodo = Periodo("mes", date(2026, 4, 1), date(2026, 4, 30))
    resposta = montar_resposta_comercial(
        periodo=periodo,
        funcao="sdr",
        planilhas_mes_corrente=[planilha],
        avisos_estruturais=[],
        historico=[],
        cadastro_nomes={},
        emails_filtro=None,
        hoje=date(2026, 4, 30),
    )
    pessoa = resposta["pessoas"][0]
    metrica = next(m for m in pessoa["metricas"] if m["metrica"] == "conexoes_enviadas")
    assert metrica["status"] == "atingido"
    assert pessoa["metas_atingidas"]["atingidas"] == 1


def test_pessoa_duplicada_entre_planilhas_soma_meta_e_realizado_e_avisa():
    p1 = _planilha_sdr("p1.csv", "duplicada@teste.com", 40, {d: 10 for d in range(1, 31)})
    p2 = _planilha_sdr("p2.csv", "duplicada@teste.com", 40, {d: 5 for d in range(1, 31)})
    avisos: list[str] = []
    resultado = calcular_mes_corrente(
        [p1, p2], "sdr", 2026, 4, dia_inicio=1, dia_fim=30,
        emails_filtro=None, avisos=avisos,
    )
    totais = resultado["duplicada@teste.com"].totais_por_metrica["conexoes_enviadas"]
    assert totais["meta_periodo"] == (40 + 40) * 22
    assert totais["realizado"] == (10 + 5) * 30
    assert any("aparece em mais de uma planilha" in a for a in avisos)


def test_uniao_mes_corrente_e_historico_com_sobreposicao():
    planilha = _planilha_sdr("p1.csv", "sdr@teste.com", 40, {d: 10 for d in range(1, 31)})
    historico = [
        HistoricoMetrica(
            email="sdr@teste.com", funcao="sdr", metrica="conexoes_enviadas",
            ano=2026, mes=3, meta_periodo=800, realizado=750,
            dias_com_lacuna=0, dias_considerados=22,
        ),
    ]
    periodo = Periodo("ano", date(2026, 1, 1), date(2026, 12, 31))
    resposta = montar_resposta_comercial(
        periodo=periodo,
        funcao="sdr",
        planilhas_mes_corrente=[planilha],
        avisos_estruturais=[],
        historico=historico,
        cadastro_nomes={},
        emails_filtro=None,
        hoje=date(2026, 4, 30),
    )
    metrica = next(
        m for m in resposta["pessoas"][0]["metricas"] if m["metrica"] == "conexoes_enviadas"
    )
    # Março (histórico) + abril completo (planilha, hoje=30/04): meta e realizado somados.
    assert metrica["meta_periodo"] == 800 + 40 * 22
    assert metrica["realizado"] == 750 + 10 * 30
    assert resposta["periodo_parcial"] is True


def test_uniao_com_mes_sem_dado_nao_quebra():
    # Nenhum histórico para o email (mês sem dado no banco) -> contribui zero, sem exceção.
    planilha = _planilha_sdr("p1.csv", "sdr@teste.com", 40, {d: 10 for d in range(1, 31)})
    periodo = Periodo("ano", date(2026, 1, 1), date(2026, 12, 31))
    resposta = montar_resposta_comercial(
        periodo=periodo,
        funcao="sdr",
        planilhas_mes_corrente=[planilha],
        avisos_estruturais=[],
        historico=[],
        cadastro_nomes={},
        emails_filtro=None,
        hoje=date(2026, 4, 30),
    )
    metrica = next(
        m for m in resposta["pessoas"][0]["metricas"] if m["metrica"] == "conexoes_enviadas"
    )
    assert metrica["meta_periodo"] == 40 * 22
    assert metrica["realizado"] == 10 * 30


def test_periodo_parcial_falso_quando_mes_fechado_so_historico():
    historico = [
        HistoricoMetrica(
            email="sdr@teste.com", funcao="sdr", metrica="conexoes_enviadas",
            ano=2026, mes=3, meta_periodo=800, realizado=750,
            dias_com_lacuna=0, dias_considerados=22,
        ),
    ]
    periodo = Periodo("mes", date(2026, 3, 1), date(2026, 3, 31))
    resposta = montar_resposta_comercial(
        periodo=periodo,
        funcao="sdr",
        planilhas_mes_corrente=[],
        avisos_estruturais=[],
        historico=historico,
        cadastro_nomes={},
        emails_filtro=None,
        hoje=date(2026, 4, 30),
    )
    assert resposta["periodo_parcial"] is False
    metrica = next(
        m for m in resposta["pessoas"][0]["metricas"] if m["metrica"] == "conexoes_enviadas"
    )
    assert metrica["realizado"] == 750


def test_pontuacao_um_ponto_por_dia_que_bate_meta_lacuna_nao_pontua():
    # Meta diária 10: dias 1-10 batem (>=10), dias 11-20 abaixo, 21-30 lacuna.
    valores = {**{d: 10 for d in range(1, 11)}, **{d: 5 for d in range(11, 21)}, **{d: None for d in range(21, 31)}}
    planilha = _planilha_sdr("p1.csv", "sdr@teste.com", 10, valores)
    periodo = Periodo("mes", date(2026, 4, 1), date(2026, 4, 30))
    resposta = montar_resposta_comercial(
        periodo=periodo,
        funcao="sdr",
        planilhas_mes_corrente=[planilha],
        avisos_estruturais=[],
        historico=[],
        cadastro_nomes={},
        emails_filtro=None,
        hoje=date(2026, 4, 30),
    )
    pessoa = resposta["pessoas"][0]
    assert pessoa["pontuacao_total"] == 10  # só os 10 dias que bateram a meta
    assert pessoa["posicao"] == 1  # única pessoa -> 1º


def test_pontuacao_ranking_dense_rank_com_empate():
    # a e b empatados em pontos altos, c sem nenhum dia batendo meta.
    a = _planilha_sdr("a.csv", "a@teste.com", 10, {d: 10 for d in range(1, 31)})
    b = _planilha_sdr("b.csv", "b@teste.com", 10, {d: 10 for d in range(1, 31)})
    c = _planilha_sdr("c.csv", "c@teste.com", 10, {d: 0 for d in range(1, 31)})
    periodo = Periodo("mes", date(2026, 4, 1), date(2026, 4, 30))
    resposta = montar_resposta_comercial(
        periodo=periodo,
        funcao="sdr",
        planilhas_mes_corrente=[a, b, c],
        avisos_estruturais=[],
        historico=[],
        cadastro_nomes={},
        emails_filtro=None,
        hoje=date(2026, 4, 30),
    )
    por_email = {p["email"]: p for p in resposta["pessoas"]}
    assert por_email["a@teste.com"]["pontuacao_total"] == por_email["b@teste.com"]["pontuacao_total"] == 30
    assert por_email["a@teste.com"]["posicao"] == por_email["b@teste.com"]["posicao"] == 1
    assert por_email["c@teste.com"]["pontuacao_total"] == 0
    assert por_email["c@teste.com"]["posicao"] == 2  # dense rank: não pula pro 3º


def test_filtro_de_pessoas_restringe_saida():
    p1 = _planilha_sdr("p1.csv", "a@teste.com", 40, {d: 10 for d in range(1, 31)})
    p2 = _planilha_sdr("p2.csv", "b@teste.com", 40, {d: 10 for d in range(1, 31)})
    periodo = Periodo("mes", date(2026, 4, 1), date(2026, 4, 30))
    resposta = montar_resposta_comercial(
        periodo=periodo,
        funcao="sdr",
        planilhas_mes_corrente=[p1, p2],
        avisos_estruturais=[],
        historico=[],
        cadastro_nomes={},
        emails_filtro={"a@teste.com"},
        hoje=date(2026, 4, 30),
    )
    emails = [p["email"] for p in resposta["pessoas"]]
    assert emails == ["a@teste.com"]
