from __future__ import annotations

from datetime import date

from app.dominios.comercial.banco import TotaisCargo
from app.dominios.comercial.calculo import montar_resposta_comercial
from app.dominios.pessoas.banco import Pessoa
from app.metas import Metas
from app.periodo import Periodo

# Metas são por PESSOA: `dash.metricas_metas` diz que a métrica tem meta
# naquele mês e `dash.user_metas` guarda o valor de cada um. A chave de
# `Metas` é (mês, id_user, métrica) — não existe mais chave por cargo.


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


def test_sem_meta_cadastrada_status_e_sem_meta_e_pontuacao_none():
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
    assert resposta.corpo["pessoas"][0]["pontuacao_total"] is None
    assert resposta.corpo["pessoas"][0]["posicao"] is None
    assert "metas_nao_cadastradas" in resposta.corpo["avisos"]


def test_meta_de_um_colega_nao_vaza_pra_quem_nao_tem_a_dele():
    # Não existe mais fallback de "meta do cargo": quem não tem linha em
    # dash.user_metas fica sem meta, mesmo com o colega de cargo tendo uma.
    pessoa = _pessoa("9", "Nathan", "sdr", "nathan@x.com")
    totais = _totais(realizado={(9, "numeros_captados"): 312}, dias_com_lancamento={(9, "numeros_captados"): 8})
    metas = Metas({(date(2026, 9, 1), 2, "numeros_captados"): 20})  # meta do SDR de id 2

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
        (date(2026, 9, 1), 2, "numeros_captados"): 20,
        (date(2026, 9, 1), 4, "numeros_captados"): 30,
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
    metas = Metas({(date(2026, 9, 1), 9, "numeros_captados"): 20})

    resposta = montar_resposta_comercial(
        periodo=_periodo_mes(), cargo="sdr", pessoas_cargo=[pessoa], totais=totais,
        metas=metas, emails_filtro=None, hoje=date(2026, 9, 14),
    )
    metrica = next(m for m in resposta.corpo["pessoas"][0]["metricas"] if m["metrica"] == "numeros_captados")
    assert metrica["status"] == "sem_preenchimento"


def test_status_atingido_e_abaixo_da_meta():
    pessoa = _pessoa("9", "Nathan", "sdr", "nathan@x.com")
    totais = _totais(
        realizado={(9, "numeros_captados"): 500, (9, "ligacoes_agendadas"): 10},
        dias_com_lancamento={(9, "numeros_captados"): 8, (9, "ligacoes_agendadas"): 8},
    )
    # Diárias: numero 20/dia (440 no mês, realizado 500 -> atingido) e
    # lig_agendado 5/dia (110 no mês, realizado 10 -> abaixo).
    metas = Metas({
        (date(2026, 9, 1), 9, "numeros_captados"): 20,
        (date(2026, 9, 1), 9, "ligacoes_agendadas"): 5,
    })

    resposta = montar_resposta_comercial(
        periodo=_periodo_mes(), cargo="sdr", pessoas_cargo=[pessoa], totais=totais,
        metas=metas, emails_filtro=None, hoje=date(2026, 9, 14),
    )
    por_metrica = {m["metrica"]: m for m in resposta.corpo["pessoas"][0]["metricas"]}
    assert por_metrica["numeros_captados"]["status"] == "atingido"
    assert por_metrica["ligacoes_agendadas"]["status"] == "abaixo_da_meta"


def test_meta_zero_e_sem_meta_nao_atingido():
    # Meta zero = não é cobrado nesta métrica (mesma regra de pontuacao.py):
    # `realizado >= 0` sempre bate, então sem essa regra viraria "atingido" à toa.
    pessoa = _pessoa("9", "Nathan", "sdr", "nathan@x.com")
    totais = _totais(realizado={(9, "numeros_captados"): 0}, dias_com_lancamento={(9, "numeros_captados"): 8})
    metas = Metas({(date(2026, 9, 1), 9, "numeros_captados"): 0})

    resposta = montar_resposta_comercial(
        periodo=_periodo_mes(), cargo="sdr", pessoas_cargo=[pessoa], totais=totais,
        metas=metas, emails_filtro=None, hoje=date(2026, 9, 14),
    )
    metrica = next(m for m in resposta.corpo["pessoas"][0]["metricas"] if m["metrica"] == "numeros_captados")
    assert metrica["meta_periodo"] == 0
    assert metrica["status"] == "sem_meta"


def test_pontuacao_so_quando_todas_as_metricas_do_cargo_tem_meta():
    # SDR tem 8 métricas — meta só pra "numeros_captados" não basta.
    pessoa = _pessoa("9", "Nathan", "sdr", "nathan@x.com")
    totais = _totais(realizado={(9, "numeros_captados"): 400}, dias_com_lancamento={(9, "numeros_captados"): 8})
    # Meta cadastrada é DIÁRIA: 20/dia × 22 dias úteis de set/2026 = 440 no mês.
    metas = Metas({(date(2026, 9, 1), 9, "numeros_captados"): 20})

    resposta = montar_resposta_comercial(
        periodo=_periodo_mes(), cargo="sdr", pessoas_cargo=[pessoa], totais=totais,
        metas=metas, emails_filtro=None, hoje=date(2026, 9, 14),
    )
    assert resposta.corpo["pessoas"][0]["pontuacao_total"] is None


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
    # As 8 métricas de SDR precisam de meta (de cada um) pra pontuação existir.
    from app.metricas import METRICAS_SDR

    # 100/dia × 22 = 2200 no mês; realizado 2200 -> 100 pts, 1100 -> 50 pts.
    valores_meta = {(date(2026, 9, 1), pid, m): 100 for pid in (2, 4) for m in METRICAS_SDR}
    metas = Metas(valores_meta)
    realizado = {(2, m): 2200 for m in METRICAS_SDR} | {(4, m): 1100 for m in METRICAS_SDR}
    dias = {(pid, m): 8 for pid in (2, 4) for m in METRICAS_SDR}
    totais = _totais(realizado=realizado, dias_com_lancamento=dias)

    resposta = montar_resposta_comercial(
        periodo=_periodo_mes(), cargo="sdr", pessoas_cargo=[a, b], totais=totais,
        metas=metas, emails_filtro=None, hoje=date(2026, 9, 14),
    )
    por_email = {p["email"]: p for p in resposta.corpo["pessoas"]}
    assert por_email["a@x.com"]["pontuacao_total"] == 100.0
    assert por_email["a@x.com"]["posicao"] == 1
    assert por_email["b@x.com"]["posicao"] == 2


def test_linhas_cargo_cruzado_gera_aviso():
    pessoa = _pessoa("9", "Nathan", "sdr", "nathan@x.com")
    totais = TotaisCargo(realizado={}, dias_com_lancamento={}, serie_diaria={}, contas_por_pessoa={}, linhas_cargo_cruzado=3)
    resposta = montar_resposta_comercial(
        periodo=_periodo_mes(), cargo="sdr", pessoas_cargo=[pessoa], totais=totais,
        metas=Metas({(date(2026, 9, 1), 9, "x"): 1}), emails_filtro=None, hoje=date(2026, 9, 14),
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
