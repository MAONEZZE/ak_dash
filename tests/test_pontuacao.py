from __future__ import annotations

from app.pontuacao import atribuir_ranking, calcular_pontuacao


def test_pontuacao_none_quando_lista_vazia():
    assert calcular_pontuacao([]) is None


def test_pontuacao_none_quando_qualquer_metrica_sem_meta():
    metricas = [
        {"realizado": 100, "meta_periodo": 200},
        {"realizado": 50, "meta_periodo": None},
    ]
    assert calcular_pontuacao(metricas) is None


def test_pontuacao_none_quando_qualquer_metrica_sem_realizado():
    metricas = [
        {"realizado": 100, "meta_periodo": 200},
        {"realizado": None, "meta_periodo": 50},
    ]
    assert calcular_pontuacao(metricas) is None


def test_pontuacao_media_sem_cap():
    # 312/400*100=78; 200/100*100=200 (sem cap) -> média 139.
    metricas = [
        {"realizado": 312, "meta_periodo": 400},
        {"realizado": 200, "meta_periodo": 100},
    ]
    assert calcular_pontuacao(metricas) == 139.0


def test_pontuacao_meta_zero_conta_como_100_por_cento():
    metricas = [{"realizado": 0, "meta_periodo": 0}]
    assert calcular_pontuacao(metricas) == 100.0


def test_ranking_dense_rank_com_empate_e_sem_pontuacao_fica_de_fora():
    pessoas = [
        {"nome": "a", "pontuacao": 80.0},
        {"nome": "b", "pontuacao": 80.0},
        {"nome": "c", "pontuacao": 50.0},
        {"nome": "d", "pontuacao": None},
    ]
    atribuir_ranking(pessoas, "pontuacao")
    por_nome = {p["nome"]: p["posicao"] for p in pessoas}
    assert por_nome["a"] == por_nome["b"] == 1
    assert por_nome["c"] == 2  # dense rank: não pula pro 3º
    assert por_nome["d"] is None
