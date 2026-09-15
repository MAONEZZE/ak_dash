from __future__ import annotations

from datetime import date

from app.dominios.comercial.banco import TotaisCargo
from app.dominios.geral.banco import EventoInscricoes, Faturamento
from app.dominios.geral.calculo import montar_resposta_geral
from app.dominios.pessoas.banco import Pessoa
from app.metas import Metas
from app.periodo import Periodo

# dash.metricas_cargo: closer=1, sdr=2, empresa=3 (mesmos ids do ambiente
# real). `empresa` é o cargo das metas que não são de ninguém em particular
# (faturamento, liquidado) — ver app/metas.py.
ID_CARGO_CLOSER = 1
ID_CARGO_SDR = 2
ID_CARGO_EMPRESA = 3


def _totais(realizado: dict) -> TotaisCargo:
    return TotaisCargo(realizado=realizado, dias_com_lancamento={}, serie_diaria={}, contas_por_pessoa={}, linhas_cargo_cruzado=0)


def _faturamento_vazio() -> Faturamento:
    vazio = {"faturamento": None, "liquidado": None, "inscritos": None, "aprovados": None}
    return Faturamento(empresa=dict(vazio), por_pessoa={})


# Setembro/2026 (mês completo) capado em 14/09 — o mesmo par que
# `app/dominios/geral/rotas.py` monta pra "mes atual" com hoje=14/09.
def _periodo_metas():
    return Periodo("mes", date(2026, 9, 1), date(2026, 9, 30))


def _periodo_saida():
    return Periodo("mes", date(2026, 9, 1), date(2026, 9, 14))


def _montar(**kwargs):
    return montar_resposta_geral(
        periodo_metas=kwargs.pop("periodo_metas", _periodo_metas()),
        periodo_saida=kwargs.pop("periodo_saida", _periodo_saida()),
        hoje=kwargs.pop("hoje", date(2026, 9, 14)),
        id_cargo_sdr=kwargs.pop("id_cargo_sdr", ID_CARGO_SDR),
        id_cargo_closer=kwargs.pop("id_cargo_closer", ID_CARGO_CLOSER),
        id_cargo_empresa=kwargs.pop("id_cargo_empresa", ID_CARGO_EMPRESA),
        **kwargs,
    )


def test_sem_metas_cadastradas_cards_claros_mostram_realizado_e_meta_none():
    sdr = [Pessoa(id="9", nome="Nathan", cargo="sdr", email="n@x.com")]
    resposta = _montar(
        pessoas_sdr=sdr, pessoas_closer=[],
        totais_sdr=_totais({(9, "numeros_captados"): 312}), totais_closer=_totais({}),
        metas=Metas({}), faturamento=_faturamento_vazio(), eventos=[],
    )
    card_numero = next(c for c in resposta["cards"] if c["metrica"] == "numeros_captados")
    assert card_numero["realizado"] == 312
    assert card_numero["meta"] is None
    assert card_numero["pct"] is None
    assert "metas_nao_cadastradas" in resposta["avisos"]


def test_periodo_de_saida_e_o_capado_nao_o_mes_inteiro():
    resposta = _montar(
        pessoas_sdr=[], pessoas_closer=[],
        totais_sdr=_totais({}), totais_closer=_totais({}),
        metas=Metas({}), faturamento=_faturamento_vazio(), eventos=[],
    )
    assert resposta["periodo"] == {"granularidade": "mes", "inicio": "2026-09-01", "fim": "2026-09-14"}


def test_cards_escuros_none_quando_metricas_faturamento_vazia():
    resposta = _montar(
        pessoas_sdr=[], pessoas_closer=[],
        totais_sdr=_totais({}), totais_closer=_totais({}),
        metas=Metas({}), faturamento=_faturamento_vazio(), eventos=[],
    )
    card_faturamento = next(c for c in resposta["cards"] if c["metrica"] == "faturamento")
    assert card_faturamento["escuro"] is True
    assert card_faturamento["realizado"] is None
    assert card_faturamento["meta"] is None


def test_card_indicacoes_soma_captadas_sdr_e_indicacoes_closer():
    sdr = [Pessoa(id="4", nome="Jennifer", cargo="sdr", email="j@x.com")]
    closer = [Pessoa(id="1", nome="Jacob", cargo="closer", email="ja@x.com")]
    resposta = _montar(
        pessoas_sdr=sdr, pessoas_closer=closer,
        totais_sdr=_totais({(4, "indicacoes"): 3}),
        totais_closer=_totais({(1, "indicacoes"): 5}),
        metas=Metas({}), faturamento=_faturamento_vazio(), eventos=[],
    )
    card = next(c for c in resposta["cards"] if c["metrica"] == "indicacoes")
    assert card["realizado"] == 8


def test_pontuacao_pessoa_requer_todas_as_metricas_da_tabela_com_meta():
    # SDR na tabela tem 3 colunas — meta só numa não basta pra pontuação existir.
    sdr = [Pessoa(id="9", nome="Nathan", cargo="sdr", email="n@x.com")]
    metas = Metas({(date(2026, 9, 1), ID_CARGO_SDR, "numeros_captados"): 400})
    resposta = _montar(
        pessoas_sdr=sdr, pessoas_closer=[],
        totais_sdr=_totais({(9, "numeros_captados"): 312}), totais_closer=_totais({}),
        metas=metas, faturamento=_faturamento_vazio(), eventos=[],
    )
    assert resposta["pessoas"][0]["pontuacao"] is None
    assert resposta["pessoas"][0]["posicao"] is None


def test_duas_pessoas_do_mesmo_cargo_compartilham_a_mesma_meta():
    a = Pessoa(id="9", nome="Nathan", cargo="sdr", email="n@x.com")
    b = Pessoa(id="2", nome="Jonathan", cargo="sdr", email="j@x.com")
    metas = Metas({(date(2026, 9, 1), ID_CARGO_SDR, "numeros_captados"): 20})  # diária
    resposta = _montar(
        pessoas_sdr=[a, b], pessoas_closer=[],
        totais_sdr=_totais({(9, "numeros_captados"): 500, (2, "numeros_captados"): 100}), totais_closer=_totais({}),
        metas=metas, faturamento=_faturamento_vazio(), eventos=[],
    )
    por_id = {p["id_user"]: p for p in resposta["pessoas"]}
    meta_nathan = next(m for m in por_id[9]["metricas"] if m["metrica"] == "numeros_captados")
    meta_jonathan = next(m for m in por_id[2]["metricas"] if m["metrica"] == "numeros_captados")
    assert meta_nathan["meta"] == meta_jonathan["meta"] == 440  # 20/dia × 22 dias úteis


def test_id_cargo_none_degrada_pra_meta_none_sem_erro():
    sdr = [Pessoa(id="9", nome="Nathan", cargo="sdr", email="n@x.com")]
    metas = Metas({(date(2026, 9, 1), ID_CARGO_SDR, "numeros_captados"): 400})
    resposta = _montar(
        pessoas_sdr=sdr, pessoas_closer=[],
        totais_sdr=_totais({(9, "numeros_captados"): 312}), totais_closer=_totais({}),
        metas=metas, faturamento=_faturamento_vazio(), eventos=[],
        id_cargo_sdr=None,
    )
    metrica = next(m for m in resposta["pessoas"][0]["metricas"] if m["metrica"] == "numeros_captados")
    assert metrica["meta"] is None


def test_rotulo_distingue_pessoas_com_mesmo_nome():
    sdr = [Pessoa(id="2", nome="Jonathan", cargo="sdr", email="j.sdr@x.com")]
    closer = [Pessoa(id="10", nome="Jonathan", cargo="closer", email="j.closer@x.com")]
    resposta = _montar(
        pessoas_sdr=sdr, pessoas_closer=closer,
        totais_sdr=_totais({}), totais_closer=_totais({}),
        metas=Metas({}), faturamento=_faturamento_vazio(), eventos=[],
    )
    por_id = {p["id_user"]: p["rotulo"] for p in resposta["pessoas"]}
    assert por_id[2] == "Jonathan (SDR)"
    assert por_id[10] == "Jonathan (Closer)"


def test_rotulo_sem_colisao_e_so_o_nome():
    sdr = [Pessoa(id="9", nome="Nathan", cargo="sdr", email="n@x.com")]
    resposta = _montar(
        pessoas_sdr=sdr, pessoas_closer=[],
        totais_sdr=_totais({}), totais_closer=_totais({}),
        metas=Metas({}), faturamento=_faturamento_vazio(), eventos=[],
    )
    assert resposta["pessoas"][0]["rotulo"] == "Nathan"


def test_pessoas_sdr_vem_antes_dos_closers():
    sdr = [Pessoa(id="9", nome="Nathan", cargo="sdr", email="n@x.com")]
    closer = [Pessoa(id="1", nome="Jacob", cargo="closer", email="ja@x.com")]
    resposta = _montar(
        pessoas_sdr=sdr, pessoas_closer=closer,
        totais_sdr=_totais({}), totais_closer=_totais({}),
        metas=Metas({}), faturamento=_faturamento_vazio(), eventos=[],
    )
    cargos = [p["cargo"] for p in resposta["pessoas"]]
    assert cargos == ["sdr", "closer"]


def test_dias_uteis_decorridos_e_total_refletem_mes_parcial():
    resposta = _montar(
        pessoas_sdr=[], pessoas_closer=[],
        totais_sdr=_totais({}), totais_closer=_totais({}),
        metas=Metas({}), faturamento=_faturamento_vazio(), eventos=[],
    )
    # Setembro/2026: dia 1 é terça. Até 14/09 (segunda) são 10 dias úteis; o mês inteiro tem 22.
    assert resposta["dias_uteis"]["decorridos"] == 10
    assert resposta["dias_uteis"]["total"] == 22


def test_meta_usa_o_mes_inteiro_mesmo_com_periodo_de_saida_capado():
    # Meta cheia do mês (decisão de produto) não diminui só porque o mês
    # ainda não terminou — usa periodo_metas (mês inteiro), não periodo_saida.
    # Card da empresa = meta do cargo × pessoas ativas: 20/dia × 22 × 1 SDR.
    sdr = [Pessoa(id="9", nome="Nathan", cargo="sdr", email="n@x.com")]
    metas = Metas({(date(2026, 9, 1), ID_CARGO_SDR, "numeros_captados"): 20})
    resposta = _montar(
        pessoas_sdr=sdr, pessoas_closer=[],
        totais_sdr=_totais({(9, "numeros_captados"): 312}), totais_closer=_totais({}),
        metas=metas, faturamento=_faturamento_vazio(), eventos=[],
    )
    card = next(c for c in resposta["cards"] if c["metrica"] == "numeros_captados")
    assert card["meta"] == 440


def test_dias_uteis_com_granularidade_dia():
    # "dia" — periodo_metas e periodo_saida são o mesmo único dia (14/09, segunda).
    periodo = Periodo("dia", date(2026, 9, 14), date(2026, 9, 14))
    resposta = _montar(
        periodo_metas=periodo, periodo_saida=periodo,
        pessoas_sdr=[], pessoas_closer=[],
        totais_sdr=_totais({}), totais_closer=_totais({}),
        metas=Metas({}), faturamento=_faturamento_vazio(), eventos=[],
    )
    assert resposta["periodo"]["granularidade"] == "dia"
    assert resposta["dias_uteis"] == {"decorridos": 1, "total": 1}


def test_inscritos_e_aprovados_nao_sao_mais_card_de_periodo():
    # Viraram `eventos` (próximos eventos girando no card); um valor em
    # `metricas_faturamento` com essas chaves não pode ressuscitar o card.
    faturamento = Faturamento(empresa={"faturamento": None, "liquidado": None, "inscritos": 1, "aprovados": 1}, por_pessoa={})
    resposta = _montar(
        pessoas_sdr=[], pessoas_closer=[],
        totais_sdr=_totais({}), totais_closer=_totais({}),
        metas=Metas({}), faturamento=faturamento, eventos=[],
    )
    metricas = {c["metrica"] for c in resposta["cards"]}
    assert "inscritos" not in metricas
    assert "aprovados" not in metricas


def test_eventos_saem_na_resposta_na_ordem_recebida():
    eventos = [
        EventoInscricoes(id="a", titulo="Imersão", data="2026-09-20T19:00:00", capacidade=50, inscritos=31, aprovados=12),
        EventoInscricoes(id="b", titulo="Workshop", data="2026-09-27T09:00:00", capacidade=None, inscritos=4, aprovados=0),
    ]
    resposta = _montar(
        pessoas_sdr=[], pessoas_closer=[],
        totais_sdr=_totais({}), totais_closer=_totais({}),
        metas=Metas({}), faturamento=_faturamento_vazio(), eventos=eventos,
    )
    assert resposta["eventos"] == [
        {"id": "a", "titulo": "Imersão", "data": "2026-09-20T19:00:00", "capacidade": 50, "inscritos": 31, "aprovados": 12},
        {"id": "b", "titulo": "Workshop", "data": "2026-09-27T09:00:00", "capacidade": None, "inscritos": 4, "aprovados": 0},
    ]


def test_sem_evento_futuro_a_lista_sai_vazia_sem_derrubar_o_resto():
    resposta = _montar(
        pessoas_sdr=[], pessoas_closer=[],
        totais_sdr=_totais({}), totais_closer=_totais({}),
        metas=Metas({}), faturamento=_faturamento_vazio(), eventos=[],
    )
    assert resposta["eventos"] == []
    assert len(resposta["cards"]) == 6


def test_card_reunioes_agendadas_soma_sdr_e_closer():
    # Meta de 4/dia é das 7 pessoas (3 SDR + 4 Closer), então o realizado do
    # card da empresa tem que somar os dois cargos — não só os closers.
    sdr = [Pessoa(id="2", nome="Jonathan", cargo="sdr", email="jo@x.com")]
    closer = [Pessoa(id="1", nome="Jacob", cargo="closer", email="ja@x.com")]
    resposta = _montar(
        pessoas_sdr=sdr, pessoas_closer=closer,
        totais_sdr=_totais({(2, "reunioes_agendadas"): 6}),
        totais_closer=_totais({(1, "reunioes_agendadas"): 9}),
        metas=Metas({}), faturamento=_faturamento_vazio(), eventos=[],
    )
    card = next(c for c in resposta["cards"] if c["metrica"] == "reunioes_agendadas")
    assert card["realizado"] == 15


def test_closer_pontua_sem_liquidado_e_aprovados_cadastrados():
    # `metricas_faturamento` ainda não tem colunas: liquidado/aprovados voltam
    # None pra todo closer. Isso não pode zerar a pontuação — senão o pódio de
    # Closer nunca aparece, que era o sintoma relatado.
    closer = [Pessoa(id="1", nome="Jacob", cargo="closer", email="ja@x.com")]
    # Diárias: 4 reuniões realizadas/dia (88 no mês) e 15 indicações/dia (330).
    metas = Metas({
        (date(2026, 9, 1), ID_CARGO_CLOSER, "reunioes_realizadas"): 4,
        (date(2026, 9, 1), ID_CARGO_CLOSER, "indicacoes"): 15,
    })
    resposta = _montar(
        pessoas_sdr=[], pessoas_closer=closer,
        totais_sdr=_totais({}),
        totais_closer=_totais({(1, "reunioes_realizadas"): 44, (1, "indicacoes"): 165}),
        metas=metas, faturamento=_faturamento_vazio(), eventos=[],
    )
    pessoa = resposta["pessoas"][0]
    assert pessoa["pontuacao"] == 50.0  # (44/88 + 165/330) / 2 * 100
    assert pessoa["posicao"] == 1
    # As duas colunas continuam na tabela, em branco — só não pontuam.
    assert {m["metrica"] for m in pessoa["metricas"]} == {"reunioes_realizadas", "liquidado", "aprovados", "indicacoes"}


def test_closer_sem_meta_operacional_continua_sem_pontuacao():
    # A regra "sem meta = sem pontuação" segue valendo pras métricas que pontuam.
    closer = [Pessoa(id="1", nome="Jacob", cargo="closer", email="ja@x.com")]
    metas = Metas({(date(2026, 9, 1), ID_CARGO_CLOSER, "reunioes_realizadas"): 4})
    resposta = _montar(
        pessoas_sdr=[], pessoas_closer=closer,
        totais_sdr=_totais({}), totais_closer=_totais({(1, "reunioes_realizadas"): 44}),
        metas=metas, faturamento=_faturamento_vazio(), eventos=[],
    )
    assert resposta["pessoas"][0]["pontuacao"] is None
    assert resposta["pessoas"][0]["posicao"] is None


def test_meta_do_card_da_empresa_e_a_do_cargo_vezes_o_time():
    # Reuniões agendadas: 4/dia por pessoa, 2 SDRs + 1 Closer = 12/dia -> 264
    # no mês (22 dias úteis). `dash.metricas_metas` não guarda linha de empresa; o
    # número acompanha o time sozinho.
    sdr = [
        Pessoa(id="9", nome="Nathan", cargo="sdr", email="n@x.com"),
        Pessoa(id="2", nome="Jonathan", cargo="sdr", email="j@x.com"),
    ]
    closer = [Pessoa(id="1", nome="Jacob", cargo="closer", email="ja@x.com")]
    metas = Metas({
        (date(2026, 9, 1), ID_CARGO_SDR, "reunioes_agendadas"): 4,
        (date(2026, 9, 1), ID_CARGO_CLOSER, "reunioes_agendadas"): 4,
    })
    resposta = _montar(
        pessoas_sdr=sdr, pessoas_closer=closer,
        totais_sdr=_totais({}), totais_closer=_totais({}),
        metas=metas, faturamento=_faturamento_vazio(), eventos=[],
    )
    card = next(c for c in resposta["cards"] if c["metrica"] == "reunioes_agendadas")
    assert card["meta"] == 4 * 22 * 3


def test_card_de_dois_cargos_sem_meta_num_deles_fica_sem_meta():
    # Só o Closer tem meta de reuniões agendadas: o card não pode mostrar a meta
    # de 4 closers contra um realizado que soma SDR + Closer.
    sdr = [Pessoa(id="9", nome="Nathan", cargo="sdr", email="n@x.com")]
    closer = [Pessoa(id="1", nome="Jacob", cargo="closer", email="ja@x.com")]
    metas = Metas({(date(2026, 9, 1), ID_CARGO_CLOSER, "reunioes_agendadas"): 4})
    resposta = _montar(
        pessoas_sdr=sdr, pessoas_closer=closer,
        totais_sdr=_totais({}), totais_closer=_totais({}),
        metas=metas, faturamento=_faturamento_vazio(), eventos=[],
    )
    card = next(c for c in resposta["cards"] if c["metrica"] == "reunioes_agendadas")
    assert card["meta"] is None


def test_card_de_indicacoes_junta_captadas_do_sdr_com_indicacoes_do_closer():
    sdr = [Pessoa(id="9", nome="Nathan", cargo="sdr", email="n@x.com")]
    closer = [Pessoa(id="1", nome="Jacob", cargo="closer", email="ja@x.com")]
    metas = Metas({
        (date(2026, 9, 1), ID_CARGO_SDR, "indicacoes"): 4,
        (date(2026, 9, 1), ID_CARGO_CLOSER, "indicacoes"): 10,
    })
    resposta = _montar(
        pessoas_sdr=sdr, pessoas_closer=closer,
        totais_sdr=_totais({(9, "indicacoes"): 3}),
        totais_closer=_totais({(1, "indicacoes"): 5}),
        metas=metas, faturamento=_faturamento_vazio(), eventos=[],
    )
    card = next(c for c in resposta["cards"] if c["metrica"] == "indicacoes")
    assert card["realizado"] == 8
    assert card["meta"] == (4 * 22) + (10 * 22)
