from __future__ import annotations

from datetime import date

from app.dominios.comercial.banco import TotaisCargo
from app.dominios.comercial.calculo import montar_resposta_comercial
from app.dominios.pessoas.banco import Pessoa
from app.metas import Metas
from app.periodo import Periodo

# Metas são por PESSOA: a chave de `Metas` é (id_user, métrica) e o valor é
# a meta diária atual, que vale pra qualquer período.


def _pessoa(id_: str, nome: str, cargo: str, email: str) -> Pessoa:
    return Pessoa(id=id_, nome=nome, cargo=cargo, email=email)


def _totais(realizado: dict, dias_com_lancamento: dict, serie_diaria: dict | None = None) -> TotaisCargo:
    return TotaisCargo(
        realizado=realizado,
        dias_com_lancamento=dias_com_lancamento,
        serie_diaria=serie_diaria or {},
        contas_por_pessoa={},
        linhas_cargo_cruzado=0,
    )


def _periodo_mes():
    # Mês INTEIRO — é o que `resolver_periodo("mes", ...)` devolve pras rotas.
    # A meta de `dash.metricas_metas` é diária e só é recortada quando o período pedido
    # cobre parte do mês (ver `metas.fracao_do_mes`); com o mês todo, vale cheia.
    return Periodo("mes", date(2026, 9, 1), date(2026, 9, 30))


def test_sem_meta_cadastrada_status_e_sem_meta_mas_pontua_igual():
    pessoa = _pessoa("9", "Nathan", "sdr", "nathan@x.com")
    totais = _totais(realizado={(9, "numeros_captados"): 312}, dias_com_lancamento={(9, "numeros_captados"): 8})
    metas = Metas({})

    resposta = montar_resposta_comercial(
        periodo=_periodo_mes(), cargo="sdr", pessoas_cargo=[pessoa], totais=totais,
        metas=metas, emails_filtro=None, hoje=date(2026, 9, 14),
    )
    metrica = next(m for m in resposta.corpo["pessoas"][0]["metricas"] if m["metrica"] == "numeros_captados")
    assert metrica["status"] == "sem_meta"
    assert metrica["meta_periodo"] is None
    # Pontuação não depende de meta: 312 números captados × 7.
    assert resposta.corpo["pessoas"][0]["pontuacao_total"] == 312 * 7
    assert resposta.corpo["pessoas"][0]["posicao"] == 1
    assert "metas_nao_cadastradas" in resposta.corpo["avisos"]


def test_meta_de_um_colega_nao_vaza_pra_quem_nao_tem_a_dele():
    # Não existe mais fallback de "meta do cargo": quem não tem linha em
    # dash.user_metas fica sem meta, mesmo com o colega de cargo tendo uma.
    pessoa = _pessoa("9", "Nathan", "sdr", "nathan@x.com")
    totais = _totais(realizado={(9, "numeros_captados"): 312}, dias_com_lancamento={(9, "numeros_captados"): 8})
    metas = Metas({(2, "numeros_captados"): 20})  # meta do SDR de id 2

    resposta = montar_resposta_comercial(
        periodo=_periodo_mes(), cargo="sdr", pessoas_cargo=[pessoa], totais=totais,
        metas=metas, emails_filtro=None, hoje=date(2026, 9, 14),
    )
    metrica = next(m for m in resposta.corpo["pessoas"][0]["metricas"] if m["metrica"] == "numeros_captados")
    assert metrica["meta_periodo"] is None
    assert metrica["status"] == "sem_meta"


def test_duas_pessoas_do_mesmo_cargo_podem_ter_metas_diferentes():
    # O ponto da mudança pra dash.user_metas: dois SDRs, metas diferentes no
    # mesmo mês. Com meta por cargo os dois seriam cobrados pelos mesmos 440.
    a = _pessoa("2", "A", "sdr", "a@x.com")
    b = _pessoa("4", "B", "sdr", "b@x.com")
    totais = _totais(
        realizado={(2, "numeros_captados"): 500, (4, "numeros_captados"): 500},
        dias_com_lancamento={(2, "numeros_captados"): 8, (4, "numeros_captados"): 8},
    )
    # Diárias × 22 dias úteis de set/2026: A cobra 440, B cobra 660.
    metas = Metas({
        (2, "numeros_captados"): 20,
        (4, "numeros_captados"): 30,
    })

    resposta = montar_resposta_comercial(
        periodo=_periodo_mes(), cargo="sdr", pessoas_cargo=[a, b], totais=totais,
        metas=metas, emails_filtro=None, hoje=date(2026, 9, 14),
    )
    por_email = {p["email"]: p for p in resposta.corpo["pessoas"]}
    meta_a = next(m for m in por_email["a@x.com"]["metricas"] if m["metrica"] == "numeros_captados")
    meta_b = next(m for m in por_email["b@x.com"]["metricas"] if m["metrica"] == "numeros_captados")
    assert meta_a["meta_periodo"] == 440
    assert meta_b["meta_periodo"] == 660
    # Mesmo realizado, status diferente — é a meta de cada um que decide.
    assert meta_a["status"] == "atingido"
    assert meta_b["status"] == "abaixo_da_meta"


def test_zero_dias_com_lancamento_e_sem_preenchimento_mesmo_com_meta():
    pessoa = _pessoa("9", "Nathan", "sdr", "nathan@x.com")
    totais = _totais(realizado={}, dias_com_lancamento={})
    # Meta cadastrada é DIÁRIA: 20/dia × 22 dias úteis de set/2026 = 440 no mês.
    metas = Metas({(9, "numeros_captados"): 20})

    resposta = montar_resposta_comercial(
        periodo=_periodo_mes(), cargo="sdr", pessoas_cargo=[pessoa], totais=totais,
        metas=metas, emails_filtro=None, hoje=date(2026, 9, 14),
    )
    metrica = next(m for m in resposta.corpo["pessoas"][0]["metricas"] if m["metrica"] == "numeros_captados")
    assert metrica["status"] == "sem_preenchimento"


def test_status_atingido_e_abaixo_da_meta():
    pessoa = _pessoa("9", "Nathan", "sdr", "nathan@x.com")
    totais = _totais(
        realizado={(9, "numeros_captados"): 500, (9, "ligacoes_realizadas"): 10},
        dias_com_lancamento={(9, "numeros_captados"): 8, (9, "ligacoes_realizadas"): 8},
    )
    # Diárias: numero 20/dia (440 no mês, realizado 500 -> atingido) e
    # ligações realizadas 5/dia (110 no mês, realizado 10 -> abaixo).
    metas = Metas({
        (9, "numeros_captados"): 20,
        (9, "ligacoes_realizadas"): 5,
    })

    resposta = montar_resposta_comercial(
        periodo=_periodo_mes(), cargo="sdr", pessoas_cargo=[pessoa], totais=totais,
        metas=metas, emails_filtro=None, hoje=date(2026, 9, 14),
    )
    por_metrica = {m["metrica"]: m for m in resposta.corpo["pessoas"][0]["metricas"]}
    assert por_metrica["numeros_captados"]["status"] == "atingido"
    assert por_metrica["ligacoes_realizadas"]["status"] == "abaixo_da_meta"


def test_meta_zero_e_sem_meta_nao_atingido():
    # Meta zero = não é cobrado nesta métrica (mesma regra de pontuacao.py):
    # `realizado >= 0` sempre bate, então sem essa regra viraria "atingido" à toa.
    pessoa = _pessoa("9", "Nathan", "sdr", "nathan@x.com")
    totais = _totais(realizado={(9, "numeros_captados"): 0}, dias_com_lancamento={(9, "numeros_captados"): 8})
    metas = Metas({(9, "numeros_captados"): 0})

    resposta = montar_resposta_comercial(
        periodo=_periodo_mes(), cargo="sdr", pessoas_cargo=[pessoa], totais=totais,
        metas=metas, emails_filtro=None, hoje=date(2026, 9, 14),
    )
    metrica = next(m for m in resposta.corpo["pessoas"][0]["metricas"] if m["metrica"] == "numeros_captados")
    assert metrica["meta_periodo"] == 0
    assert metrica["status"] == "sem_meta"


def test_filtro_de_pessoas_por_email_restringe_saida():
    a = _pessoa("2", "A", "sdr", "a@x.com")
    b = _pessoa("4", "B", "sdr", "b@x.com")
    totais = _totais(realizado={}, dias_com_lancamento={})
    resposta = montar_resposta_comercial(
        periodo=_periodo_mes(), cargo="sdr", pessoas_cargo=[a, b], totais=totais,
        metas=Metas({}), emails_filtro={"a@x.com"}, hoje=date(2026, 9, 14),
    )
    emails = [p["email"] for p in resposta.corpo["pessoas"]]
    assert emails == ["a@x.com"]


def test_ranking_dense_rank_entre_pessoas_com_pontuacao():
    a = _pessoa("2", "A", "sdr", "a@x.com")
    b = _pessoa("4", "B", "sdr", "b@x.com")
    # Todas as métricas de SDR com meta (de cada um) pra pontuação existir.
    from app.metricas import METRICAS_SDR

    # Pesos do SDR somam 44 (15+10+7+7+5): 2200 em cada -> 96800, 1100 -> 48400.
    valores_meta = {(pid, m): 100 for pid in (2, 4) for m in METRICAS_SDR}
    metas = Metas(valores_meta)
    realizado = {(2, m): 2200 for m in METRICAS_SDR} | {(4, m): 1100 for m in METRICAS_SDR}
    dias = {(pid, m): 8 for pid in (2, 4) for m in METRICAS_SDR}
    totais = _totais(realizado=realizado, dias_com_lancamento=dias)

    resposta = montar_resposta_comercial(
        periodo=_periodo_mes(), cargo="sdr", pessoas_cargo=[a, b], totais=totais,
        metas=metas, emails_filtro=None, hoje=date(2026, 9, 14),
    )
    por_email = {p["email"]: p for p in resposta.corpo["pessoas"]}
    assert por_email["a@x.com"]["pontuacao_total"] == 2200 * 44
    assert por_email["a@x.com"]["posicao"] == 1
    assert por_email["b@x.com"]["posicao"] == 2


def test_linhas_cargo_cruzado_gera_aviso():
    pessoa = _pessoa("9", "Nathan", "sdr", "nathan@x.com")
    totais = TotaisCargo(realizado={}, dias_com_lancamento={}, serie_diaria={}, contas_por_pessoa={}, linhas_cargo_cruzado=3)
    resposta = montar_resposta_comercial(
        periodo=_periodo_mes(), cargo="sdr", pessoas_cargo=[pessoa], totais=totais,
        metas=Metas({(9, "x"): 1}), emails_filtro=None, hoje=date(2026, 9, 14),
    )
    assert any("3 linha" in a for a in resposta.corpo["avisos"])


def test_serie_diaria_convertida_para_lista_ordenada_por_dia():
    pessoa = _pessoa("9", "Nathan", "sdr", "nathan@x.com")
    serie = {date(2026, 9, 2): {"numeros_captados": 5}, date(2026, 9, 1): {"numeros_captados": 3}}
    totais = _totais(realizado={}, dias_com_lancamento={}, serie_diaria=serie)
    resposta = montar_resposta_comercial(
        periodo=_periodo_mes(), cargo="sdr", pessoas_cargo=[pessoa], totais=totais,
        metas=Metas({}), emails_filtro=None, hoje=date(2026, 9, 14),
    )
    dias = [d["dia"] for d in resposta.corpo["serie_diaria"]]
    assert dias == ["2026-09-01", "2026-09-02"]


def test_colunas_do_sdr_trocam_ligacoes_agendadas_por_realizadas_e_ganham_inscricoes():
    # `ligacoes_agendadas` saiu de `dash.metricas_sdrs` (02/10/2026).
    pessoa = _pessoa("9", "Nathan", "sdr", "nathan@x.com")
    resposta = montar_resposta_comercial(
        periodo=_periodo_mes(), cargo="sdr", pessoas_cargo=[pessoa], totais=_totais({}, {}),
        metas=Metas({}), emails_filtro=None, hoje=date(2026, 9, 14),
    )
    colunas = [m["metrica"] for m in resposta.corpo["pessoas"][0]["metricas"]]
    assert colunas == [
        "conexoes_enviadas", "conexoes_aceitas", "abordagens", "in_mails",
        "fups", "numeros_captados", "inscricoes_realizadas", "ligacoes_realizadas", "indicacoes",
        "reunioes_agendadas",
    ]


def test_indicacoes_do_sdr_se_chamam_indicacoes_captadas_e_do_closer_so_indicacoes():
    sdr = montar_resposta_comercial(
        periodo=_periodo_mes(), cargo="sdr", pessoas_cargo=[_pessoa("9", "Nathan", "sdr", "nathan@x.com")],
        totais=_totais({}, {}), metas=Metas({}), emails_filtro=None, hoje=date(2026, 9, 14),
    )
    closer = montar_resposta_comercial(
        periodo=_periodo_mes(), cargo="closer", pessoas_cargo=[_pessoa("1", "Jacob", "closer", "jacob@x.com")],
        totais=_totais({}, {}), metas=Metas({}), emails_filtro=None, hoje=date(2026, 9, 14),
    )
    nome = lambda r: next(m["nome_exibicao"] for m in r.corpo["pessoas"][0]["metricas"] if m["metrica"] == "indicacoes")
    assert nome(sdr) == "Indicações Captadas"
    assert nome(closer) == "Indicações"


def test_colunas_do_closer_ganham_ligacoes_agendadas_e_inscricoes():
    pessoa = _pessoa("1", "Jacob", "closer", "jacob@x.com")
    resposta = montar_resposta_comercial(
        periodo=_periodo_mes(), cargo="closer", pessoas_cargo=[pessoa], totais=_totais({}, {}),
        metas=Metas({}), emails_filtro=None, hoje=date(2026, 9, 14),
    )
    metricas = resposta.corpo["pessoas"][0]["metricas"]
    assert [m["metrica"] for m in metricas] == [
        "ligacoes_agendadas", "ligacoes_realizadas", "reunioes_agendadas", "reunioes_realizadas",
        "indicacoes", "inscricoes_realizadas",
    ]
    nomes = {m["metrica"]: m["nome_exibicao"] for m in metricas}
    assert nomes["inscricoes_realizadas"] == "Inscrições Realizadas"
    assert nomes["ligacoes_realizadas"] == "Ligações Realizadas"


def test_dias_uteis_do_mes_parcial():
    # Setembro/2026: dia 1 é terça. Até 14/09 (segunda) são 10 dias úteis; o mês inteiro tem 22.
    resposta = montar_resposta_comercial(
        periodo=_periodo_mes(), cargo="sdr", pessoas_cargo=[], totais=_totais({}, {}),
        metas=Metas({}), emails_filtro=None, hoje=date(2026, 9, 14),
    )
    assert resposta.corpo["dias_uteis"] == {"decorridos": 10, "total": 22}


def test_dias_uteis_de_mes_passado_decorridos_igual_total():
    resposta = montar_resposta_comercial(
        periodo=_periodo_mes(), cargo="closer", pessoas_cargo=[], totais=_totais({}, {}),
        metas=Metas({}), emails_filtro=None, hoje=date(2026, 10, 2),
    )
    assert resposta.corpo["dias_uteis"] == {"decorridos": 22, "total": 22}


def test_dias_uteis_de_mes_futuro_decorridos_zero():
    resposta = montar_resposta_comercial(
        periodo=_periodo_mes(), cargo="sdr", pessoas_cargo=[], totais=_totais({}, {}),
        metas=Metas({}), emails_filtro=None, hoje=date(2026, 8, 20),
    )
    assert resposta.corpo["dias_uteis"] == {"decorridos": 0, "total": 22}


def test_pontuacao_da_comercial_usa_os_pesos_do_cargo():
    pessoa = _pessoa("1", "Jacob", "closer", "jacob@x.com")
    realizado = {(1, "reunioes_realizadas"): 2, (1, "ligacoes_agendadas"): 1, (1, "inscricoes_realizadas"): 1}
    totais = _totais(realizado=realizado, dias_com_lancamento={k: 1 for k in realizado})
    resposta = montar_resposta_comercial(
        periodo=_periodo_mes(), cargo="closer", pessoas_cargo=[pessoa], totais=totais,
        metas=Metas({}), emails_filtro=None, hoje=date(2026, 9, 14),
    )
    assert resposta.corpo["pessoas"][0]["pontuacao_total"] == 2 * 15 + 3 + 15
