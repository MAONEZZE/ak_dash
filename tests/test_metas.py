"""Testes de `app/metas.py` — `dash.metricas_metas` + `dash.metas_cargo`.

A meta vive numa tabela e o vínculo com o cargo em outra (N:N): a mesma
métrica pode ter meta pra SDR e pra closer, com valores diferentes, e a meta
de empresa (faturamento, liquidado) é só mais um cargo (`empresa`).
"""
from __future__ import annotations

from datetime import date

from app import metas as metas_mod
from app.metas import Metas, buscar_metas, meses_no_intervalo

SDR, CLOSER, EMPRESA = 2, 1, 3


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
    assert metas.por_cargo(date(2026, 9, 1), date(2026, 9, 30), SDR, "numeros_captados") is None


def test_meta_sem_vinculo_em_metas_cargo_nao_vale_pra_ninguem(monkeypatch):
    # Não existe mais fallback de "meta global": meta que ninguém vinculou a
    # um cargo é meta que não existe — nunca é herdada por um cargo qualquer.
    _mockar_banco(
        monkeypatch,
        [{"id": 1, "metrica": "numeros_captados", "periodo": "2026-09-01", "valor": 9}],
        [],
    )
    metas = buscar_metas(date(2026, 9, 1), date(2026, 9, 30))
    assert metas.vazio is True
    assert metas.por_cargo(date(2026, 9, 1), date(2026, 9, 30), SDR, "numeros_captados") is None


def test_uma_meta_vinculada_a_dois_cargos_vale_nos_dois(monkeypatch):
    # `reunioes_agendadas` e `indicacoes` são as métricas que SDR e closer
    # dividem — uma linha de meta, dois vínculos.
    _mockar_banco(
        monkeypatch,
        [{"id": 10, "metrica": "reunioes_agendadas", "periodo": "2026-09-01", "valor": 4}],
        [{"id_meta": 10, "id_cargo": SDR}, {"id_meta": 10, "id_cargo": CLOSER}],
    )
    metas = buscar_metas(date(2026, 9, 15), date(2026, 9, 15))
    assert metas.por_cargo(date(2026, 9, 15), date(2026, 9, 15), SDR, "reunioes_agendadas") == 4
    assert metas.por_cargo(date(2026, 9, 15), date(2026, 9, 15), CLOSER, "reunioes_agendadas") == 4


def test_mesma_metrica_com_valor_diferente_por_cargo(monkeypatch):
    _mockar_banco(
        monkeypatch,
        [
            {"id": 1, "metrica": "indicacoes", "periodo": "2026-09-01", "valor": 4},
            {"id": 2, "metrica": "indicacoes", "periodo": "2026-09-01", "valor": 10},
        ],
        [{"id_meta": 1, "id_cargo": SDR}, {"id_meta": 2, "id_cargo": CLOSER}],
    )
    metas = buscar_metas(date(2026, 9, 15), date(2026, 9, 15))
    assert metas.por_cargo(date(2026, 9, 15), date(2026, 9, 15), SDR, "indicacoes") == 4
    assert metas.por_cargo(date(2026, 9, 15), date(2026, 9, 15), CLOSER, "indicacoes") == 10


def test_meta_de_empresa_e_so_mais_um_cargo(monkeypatch):
    # Faturamento/liquidado penduram no cargo `empresa` (id 3) — e não valem
    # pra SDR nem pra closer.
    _mockar_banco(
        monkeypatch,
        [{"id": 7, "metrica": "faturamento", "periodo": "2026-09-01", "valor": 1000}],
        [{"id_meta": 7, "id_cargo": EMPRESA}],
    )
    metas = buscar_metas(date(2026, 9, 15), date(2026, 9, 15))
    assert metas.por_cargo(date(2026, 9, 15), date(2026, 9, 15), EMPRESA, "faturamento") == 1000
    assert metas.por_cargo(date(2026, 9, 15), date(2026, 9, 15), SDR, "faturamento") is None


def test_meta_por_cargo_soma_varios_meses(monkeypatch):
    # Cada mês entra com os dias úteis DELE (mai/2026: 21, jun: 22).
    _mockar_banco(
        monkeypatch,
        [
            {"id": 1, "metrica": "numeros_captados", "periodo": "2026-05-01", "valor": 10},
            {"id": 2, "metrica": "numeros_captados", "periodo": "2026-06-01", "valor": 15},
        ],
        [{"id_meta": 1, "id_cargo": SDR}, {"id_meta": 2, "id_cargo": SDR}],
    )
    metas = buscar_metas(date(2026, 5, 1), date(2026, 6, 30))
    assert metas.por_cargo(date(2026, 5, 1), date(2026, 6, 30), SDR, "numeros_captados") == 10 * 21 + 15 * 22


def test_meta_por_cargo_none_quando_nenhum_mes_do_intervalo_tem_linha(monkeypatch):
    # Meta cadastrada só pra agosto; pedindo maio-junho não deve inventar 0.
    _mockar_banco(
        monkeypatch,
        [{"id": 1, "metrica": "numeros_captados", "periodo": "2026-08-01", "valor": 100}],
        [{"id_meta": 1, "id_cargo": SDR}],
    )
    metas = buscar_metas(date(2026, 5, 1), date(2026, 6, 30))
    assert metas.por_cargo(date(2026, 5, 1), date(2026, 6, 30), SDR, "numeros_captados") is None


def test_metas_de_cargos_diferentes_nao_se_misturam(monkeypatch):
    _mockar_banco(
        monkeypatch,
        [
            {"id": 1, "metrica": "reunioes_realizadas", "periodo": "2026-09-01", "valor": 4},
            {"id": 2, "metrica": "reunioes_realizadas", "periodo": "2026-09-01", "valor": 99},
        ],
        [{"id_meta": 1, "id_cargo": CLOSER}, {"id_meta": 2, "id_cargo": SDR}],
    )
    metas = buscar_metas(date(2026, 9, 1), date(2026, 9, 30))
    assert metas.por_cargo(date(2026, 9, 1), date(2026, 9, 30), CLOSER, "reunioes_realizadas") == 4 * 22
    assert metas.por_cargo(date(2026, 9, 1), date(2026, 9, 30), SDR, "reunioes_realizadas") == 99 * 22


def test_nome_da_metrica_e_o_mesmo_dos_dois_lados(monkeypatch):
    # `metricas_metas.metrica` guarda o nome da COLUNA de origem, que é o
    # mesmo que `vw_metricas.metrica` emite e o mesmo que sai no payload —
    # não existe tradução em lugar nenhum.
    _mockar_banco(
        monkeypatch,
        [
            {"id": 1, "metrica": "numeros_captados", "periodo": "2026-09-01", "valor": 4},
            {"id": 2, "metrica": "fups", "periodo": "2026-09-01", "valor": 150},
            {"id": 3, "metrica": "in_mails", "periodo": "2026-09-01", "valor": 5},
            {"id": 4, "metrica": "ligacoes_realizadas", "periodo": "2026-09-01", "valor": 7},
        ],
        [
            {"id_meta": 1, "id_cargo": SDR},
            {"id_meta": 2, "id_cargo": SDR},
            {"id_meta": 3, "id_cargo": SDR},
            {"id_meta": 4, "id_cargo": CLOSER},
        ],
    )
    dia = date(2026, 9, 15)
    metas = buscar_metas(dia, dia)
    assert metas.por_cargo(dia, dia, SDR, "numeros_captados") == 4
    assert metas.por_cargo(dia, dia, SDR, "fups") == 150
    assert metas.por_cargo(dia, dia, SDR, "in_mails") == 5
    assert metas.por_cargo(dia, dia, CLOSER, "ligacoes_realizadas") == 7


# --- meta diária vira meta do período (dia / semana / mês / ano)
#
# `metricas_metas.valor` é a meta de UM DIA ÚTIL de UMA pessoa do cargo.
# Aqui: 4 números captados/dia por SDR. Setembro/2026 tem 22 dias úteis.


def _metas_setembro(diaria: int = 4) -> Metas:
    return Metas({(date(2026, 9, 1), SDR, "numeros_captados"): diaria})


def test_mes_inteiro_multiplica_pelos_dias_uteis_do_mes():
    assert _metas_setembro().por_cargo(date(2026, 9, 1), date(2026, 9, 30), SDR, "numeros_captados") == 88


def test_um_dia_util_devolve_a_propria_diaria():
    assert _metas_setembro().por_cargo(date(2026, 9, 15), date(2026, 9, 15), SDR, "numeros_captados") == 4


def test_semana_multiplica_pelos_cinco_dias_uteis():
    assert _metas_setembro().por_cargo(date(2026, 9, 14), date(2026, 9, 20), SDR, "numeros_captados") == 20


def test_sabado_sozinho_nao_cobra_meta():
    # Meta é diária de TRABALHO: período sem dia útil dentro dá 0, e `0`
    # desliga a barra — nunca cobra a meta do mês num sábado.
    assert _metas_setembro().por_cargo(date(2026, 9, 19), date(2026, 9, 19), SDR, "numeros_captados") == 0


def test_ano_soma_so_os_meses_cadastrados():
    metas = Metas({
        (date(2026, 9, 1), SDR, "numeros_captados"): 4,   # set/2026: 22 dias úteis
        (date(2026, 10, 1), SDR, "numeros_captados"): 4,  # out/2026: 22 dias úteis
    })
    assert metas.por_cargo(date(2026, 1, 1), date(2026, 12, 31), SDR, "numeros_captados") == 176


def test_periodo_que_atravessa_dois_meses_soma_os_dias_uteis_de_cada_um():
    metas = Metas({
        (date(2026, 9, 1), SDR, "numeros_captados"): 4,
        (date(2026, 10, 1), SDR, "numeros_captados"): 5,
    })
    # 28/09 a 02/10: 3 dias úteis de setembro (28,29,30) + 2 de outubro (1,2).
    assert metas.por_cargo(date(2026, 9, 28), date(2026, 10, 2), SDR, "numeros_captados") == 3 * 4 + 2 * 5


def test_sem_meta_cadastrada_continua_none_e_nao_zero():
    assert Metas({}).por_cargo(date(2026, 9, 15), date(2026, 9, 15), SDR, "numeros_captados") is None
