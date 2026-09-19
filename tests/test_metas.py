"""Testes de `app/metas.py` — `dash.metricas_metas` + `dash.user_metas`.

A meta vive em duas tabelas: `metricas_metas` declara QUE a métrica tem meta
naquele mês (é ela que data a meta) e `user_metas` guarda O VALOR de cada
pessoa. Meta é de PESSOA, não de cargo: dois SDRs podem ter valores
diferentes da mesma métrica no mesmo mês, e quem não tem linha não tem meta.
"""
from __future__ import annotations

from datetime import date

from app import metas as metas_mod
from app.metas import Metas, buscar_metas, meses_no_intervalo

# ids de dash.users (mesmos do ambiente real: 2 e 9 são SDRs, 1 é closer).
ANA, BRUNO, CLOSER = 2, 9, 1


def _mockar_banco(monkeypatch, metas: list[dict], vinculos: list[dict]) -> None:
    def fake_query(tabela, *a, **k):
        return metas if tabela == "metricas_metas" else vinculos

    monkeypatch.setattr(metas_mod, "query", fake_query)


def test_meses_no_intervalo_um_mes():
    assert meses_no_intervalo(date(2026, 9, 1), date(2026, 9, 14)) == [date(2026, 9, 1)]


def test_meses_no_intervalo_varios_meses():
    meses = meses_no_intervalo(date(2026, 5, 15), date(2026, 8, 3))
    assert meses == [date(2026, 5, 1), date(2026, 6, 1), date(2026, 7, 1), date(2026, 8, 1)]


def test_tabela_vazia_devolve_none_e_vazio_e_true(monkeypatch):
    _mockar_banco(monkeypatch, [], [])
    metas = buscar_metas(date(2026, 9, 1), date(2026, 9, 30))
    assert metas.vazio is True
    assert metas.por_usuario(date(2026, 9, 1), date(2026, 9, 30), ANA, "numeros_captados") is None


def test_meta_sem_linha_em_user_metas_nao_vale_pra_ninguem(monkeypatch):
    # `metricas_metas` sozinha só diz que a métrica É metrificada no mês; sem
    # `user_metas` ninguém tem número nenhum pra cumprir. Não existe fallback
    # de "meta do cargo" nem de "meta global".
    _mockar_banco(
        monkeypatch,
        [{"id": 1, "metrica": "numeros_captados", "periodo": "2026-09-01"}],
        [],
    )
    metas = buscar_metas(date(2026, 9, 1), date(2026, 9, 30))
    assert metas.vazio is True
    assert metas.por_usuario(date(2026, 9, 1), date(2026, 9, 30), ANA, "numeros_captados") is None


def test_a_mesma_meta_com_valor_diferente_por_pessoa(monkeypatch):
    # O que a modelagem antiga (meta por cargo) não conseguia expressar: uma
    # linha de métrica, valores próprios de cada um.
    _mockar_banco(
        monkeypatch,
        [{"id": 2, "metrica": "numeros_captados", "periodo": "2026-09-01"}],
        [
            {"id_meta": 2, "id_user": ANA, "valor_meta": 4},
            {"id_meta": 2, "id_user": BRUNO, "valor_meta": 10},
        ],
    )
    dia = date(2026, 9, 15)
    metas = buscar_metas(dia, dia)
    assert metas.por_usuario(dia, dia, ANA, "numeros_captados") == 4
    assert metas.por_usuario(dia, dia, BRUNO, "numeros_captados") == 10


def test_pessoa_sem_vinculo_fica_sem_meta_mesmo_com_o_colega_tendo(monkeypatch):
    _mockar_banco(
        monkeypatch,
        [{"id": 2, "metrica": "numeros_captados", "periodo": "2026-09-01"}],
        [{"id_meta": 2, "id_user": ANA, "valor_meta": 4}],
    )
    dia = date(2026, 9, 15)
    metas = buscar_metas(dia, dia)
    assert metas.por_usuario(dia, dia, ANA, "numeros_captados") == 4
    assert metas.por_usuario(dia, dia, BRUNO, "numeros_captados") is None


def test_metrica_compartilhada_entre_cargos_e_so_mais_uma_meta_por_pessoa(monkeypatch):
    # `reunioes_agendadas` é de SDR e de closer. Antes isso exigia N:N
    # meta<->cargo; agora é só cada pessoa com o valor dela.
    _mockar_banco(
        monkeypatch,
        [{"id": 10, "metrica": "reunioes_agendadas", "periodo": "2026-09-01"}],
        [
            {"id_meta": 10, "id_user": ANA, "valor_meta": 4},
            {"id_meta": 10, "id_user": CLOSER, "valor_meta": 6},
        ],
    )
    dia = date(2026, 9, 15)
    metas = buscar_metas(dia, dia)
    assert metas.por_usuario(dia, dia, ANA, "reunioes_agendadas") == 4
    assert metas.por_usuario(dia, dia, CLOSER, "reunioes_agendadas") == 6


def test_a_data_da_meta_vem_de_metricas_metas_nao_de_user_metas(monkeypatch):
    # `user_metas` não tem coluna de data: quem data o vínculo é a linha de
    # `metricas_metas` pra qual ele aponta. Meta de agosto não vale em setembro.
    _mockar_banco(
        monkeypatch,
        [
            {"id": 1, "metrica": "numeros_captados", "periodo": "2026-08-01"},
            {"id": 2, "metrica": "numeros_captados", "periodo": "2026-09-01"},
        ],
        [
            {"id_meta": 1, "id_user": ANA, "valor_meta": 3},
            {"id_meta": 2, "id_user": ANA, "valor_meta": 7},
        ],
    )
    metas = buscar_metas(date(2026, 8, 1), date(2026, 9, 30))
    assert metas.por_usuario(date(2026, 8, 3), date(2026, 8, 3), ANA, "numeros_captados") == 3
    assert metas.por_usuario(date(2026, 9, 15), date(2026, 9, 15), ANA, "numeros_captados") == 7


def test_vinculo_apontando_pra_meta_fora_do_intervalo_e_ignorado(monkeypatch):
    _mockar_banco(
        monkeypatch,
        [{"id": 2, "metrica": "numeros_captados", "periodo": "2026-09-01"}],
        [{"id_meta": 99, "id_user": ANA, "valor_meta": 500}],
    )
    metas = buscar_metas(date(2026, 9, 1), date(2026, 9, 30))
    assert metas.vazio is True


def test_meta_soma_varios_meses(monkeypatch):
    # Cada mês entra com os dias úteis DELE (mai/2026: 21, jun: 22).
    _mockar_banco(
        monkeypatch,
        [
            {"id": 1, "metrica": "numeros_captados", "periodo": "2026-05-01"},
            {"id": 2, "metrica": "numeros_captados", "periodo": "2026-06-01"},
        ],
        [
            {"id_meta": 1, "id_user": ANA, "valor_meta": 10},
            {"id_meta": 2, "id_user": ANA, "valor_meta": 15},
        ],
    )
    metas = buscar_metas(date(2026, 5, 1), date(2026, 6, 30))
    assert metas.por_usuario(date(2026, 5, 1), date(2026, 6, 30), ANA, "numeros_captados") == 10 * 21 + 15 * 22


def test_none_quando_nenhum_mes_do_intervalo_tem_linha(monkeypatch):
    # Meta cadastrada só pra agosto; pedindo maio-junho não deve inventar 0.
    _mockar_banco(
        monkeypatch,
        [{"id": 1, "metrica": "numeros_captados", "periodo": "2026-08-01"}],
        [{"id_meta": 1, "id_user": ANA, "valor_meta": 100}],
    )
    metas = buscar_metas(date(2026, 5, 1), date(2026, 6, 30))
    assert metas.por_usuario(date(2026, 5, 1), date(2026, 6, 30), ANA, "numeros_captados") is None


def test_nome_da_metrica_e_o_mesmo_dos_dois_lados(monkeypatch):
    # `metricas_metas.metrica` guarda o nome da COLUNA de origem, que é o
    # mesmo que `vw_metricas.metrica` emite e o mesmo que sai no payload —
    # não existe tradução em lugar nenhum.
    _mockar_banco(
        monkeypatch,
        [
            {"id": 1, "metrica": "numeros_captados", "periodo": "2026-09-01"},
            {"id": 2, "metrica": "fups", "periodo": "2026-09-01"},
            {"id": 3, "metrica": "in_mails", "periodo": "2026-09-01"},
            {"id": 4, "metrica": "ligacoes_realizadas", "periodo": "2026-09-01"},
        ],
        [
            {"id_meta": 1, "id_user": ANA, "valor_meta": 4},
            {"id_meta": 2, "id_user": ANA, "valor_meta": 150},
            {"id_meta": 3, "id_user": ANA, "valor_meta": 5},
            {"id_meta": 4, "id_user": CLOSER, "valor_meta": 7},
        ],
    )
    dia = date(2026, 9, 15)
    metas = buscar_metas(dia, dia)
    assert metas.por_usuario(dia, dia, ANA, "numeros_captados") == 4
    assert metas.por_usuario(dia, dia, ANA, "fups") == 150
    assert metas.por_usuario(dia, dia, ANA, "in_mails") == 5
    assert metas.por_usuario(dia, dia, CLOSER, "ligacoes_realizadas") == 7


# --- meta diária vira meta do período (dia / semana / mês / ano)
#
# `user_metas.valor_meta` é a meta de UM DIA ÚTIL daquela pessoa.
# Aqui: 4 números captados/dia. Setembro/2026 tem 22 dias úteis.


def _metas_setembro(diaria: int = 4) -> Metas:
    return Metas({(date(2026, 9, 1), ANA, "numeros_captados"): diaria})


def test_mes_inteiro_multiplica_pelos_dias_uteis_do_mes():
    assert _metas_setembro().por_usuario(date(2026, 9, 1), date(2026, 9, 30), ANA, "numeros_captados") == 88


def test_um_dia_util_devolve_a_propria_diaria():
    assert _metas_setembro().por_usuario(date(2026, 9, 15), date(2026, 9, 15), ANA, "numeros_captados") == 4


def test_semana_multiplica_pelos_cinco_dias_uteis():
    assert _metas_setembro().por_usuario(date(2026, 9, 14), date(2026, 9, 20), ANA, "numeros_captados") == 20


def test_sabado_sozinho_nao_cobra_meta():
    # Meta é diária de TRABALHO: período sem dia útil dentro dá 0, e `0`
    # desliga a barra — nunca cobra a meta do mês num sábado.
    assert _metas_setembro().por_usuario(date(2026, 9, 19), date(2026, 9, 19), ANA, "numeros_captados") == 0


def test_ano_soma_so_os_meses_cadastrados():
    metas = Metas({
        (date(2026, 9, 1), ANA, "numeros_captados"): 4,   # set/2026: 22 dias úteis
        (date(2026, 10, 1), ANA, "numeros_captados"): 4,  # out/2026: 22 dias úteis
    })
    assert metas.por_usuario(date(2026, 1, 1), date(2026, 12, 31), ANA, "numeros_captados") == 176


def test_periodo_que_atravessa_dois_meses_soma_os_dias_uteis_de_cada_um():
    metas = Metas({
        (date(2026, 9, 1), ANA, "numeros_captados"): 4,
        (date(2026, 10, 1), ANA, "numeros_captados"): 5,
    })
    # 28/09 a 02/10: 3 dias úteis de setembro (28,29,30) + 2 de outubro (1,2).
    assert metas.por_usuario(date(2026, 9, 28), date(2026, 10, 2), ANA, "numeros_captados") == 3 * 4 + 2 * 5


def test_sem_meta_cadastrada_continua_none_e_nao_zero():
    assert Metas({}).por_usuario(date(2026, 9, 15), date(2026, 9, 15), ANA, "numeros_captados") is None


# --- soma de um grupo: é assim que os cards da empresa acham o denominador


def _metas_do_time() -> Metas:
    return Metas({
        (date(2026, 9, 1), ANA, "reunioes_agendadas"): 4,
        (date(2026, 9, 1), BRUNO, "reunioes_agendadas"): 6,
    })


def test_somar_junta_as_metas_individuais_do_grupo():
    dia = date(2026, 9, 15)
    assert _metas_do_time().somar(dia, dia, [ANA, BRUNO], "reunioes_agendadas") == 10


def test_somar_devolve_none_se_alguem_do_grupo_nao_tem_meta():
    # O realizado do card soma o time inteiro; meta de parte do time daria um
    # percentual inflado. Melhor "Meta não cadastrada" do que um número errado.
    dia = date(2026, 9, 15)
    assert _metas_do_time().somar(dia, dia, [ANA, BRUNO, CLOSER], "reunioes_agendadas") is None


def test_somar_grupo_vazio_e_zero():
    # Cargo sem ninguém ativo contribui 0 pro card — mesmo resultado que o
    # modelo antigo dava multiplicando a meta do cargo por zero pessoas.
    dia = date(2026, 9, 15)
    assert _metas_do_time().somar(dia, dia, [], "reunioes_agendadas") == 0
