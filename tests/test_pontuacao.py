from __future__ import annotations

from app.pontuacao import atribuir_ranking, calcular_pontuacao


def test_pontuacao_sdr_soma_realizado_vezes_peso():
    realizado = {
        "inscricoes_realizadas": 1,  # 15
        "ligacoes_realizadas": 2,  # 20
        "numeros_captados": 1,  # 7
        "reunioes_agendadas": 3,  # 21
        "indicacoes": 1,  # 5
        "fups": 50,  # não pontua
    }
    assert calcular_pontuacao("sdr", realizado) == 68


def test_pontuacao_closer_soma_realizado_vezes_peso():
    realizado = {
        "reunioes_realizadas": 1,  # 15
        "inscricoes_realizadas": 1,  # 15
        "ligacoes_realizadas": 1,  # 10
        "reunioes_agendadas": 1,  # 5
        "indicacoes": 1,  # 5
        "ligacoes_agendadas": 1,  # 3
    }
    assert calcular_pontuacao("closer", realizado) == 53


def test_sdr_nao_pontua_ligacao_agendada():
    assert calcular_pontuacao("sdr", {"ligacoes_agendadas": 10}) == 0


def test_metrica_sem_valor_conta_zero():
    assert calcular_pontuacao("closer", {"reunioes_realizadas": None}) == 0
    assert calcular_pontuacao("closer", {}) == 0


def test_ranking_dense_rank_com_empate_e_sem_pontuacao_fica_de_fora():
    pessoas = [
        {"nome": "a", "pontuacao": 80},
        {"nome": "b", "pontuacao": 80},
        {"nome": "c", "pontuacao": 50},
        {"nome": "d", "pontuacao": None},
    ]
    atribuir_ranking(pessoas, "pontuacao")
    por_nome = {p["nome"]: p["posicao"] for p in pessoas}
    assert por_nome["a"] == por_nome["b"] == 1
    assert por_nome["c"] == 2  # dense rank: não pula pro 3º
    assert por_nome["d"] is None
