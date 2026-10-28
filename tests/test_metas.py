"""Testes de `app/metas.py` — `dash2.metas`.

Uma linha por (pessoa, cargo, métrica) com o valor DIÁRIO da meta, preenchido
pela planilha. A meta atual vale pra qualquer período (decisão do usuário,
2026-10-05) — não existe mais meta "do mês".
"""
from __future__ import annotations

from datetime import date

from app import metas as metas_mod
from app.metas import Metas, buscar_metas

# ids de dash.users (mesmos do ambiente real: 2 e 9 são SDRs, 1 é closer).
ANA, BRUNO, CLOSER = 2, 9, 1


def _mockar_banco(monkeypatch, linhas: list[dict]) -> None:
    def fake_query(tabela, *a, **k):
        return linhas if tabela == "metas" else []

    monkeypatch.setattr(metas_mod, "query", fake_query)


def test_tabela_vazia_devolve_none_e_vazio_e_true(monkeypatch):
    _mockar_banco(monkeypatch, [])
    metas = buscar_metas()
    assert metas.vazio is True
    assert metas.por_usuario(date(2026, 9, 1), date(2026, 9, 30), ANA, "sdr", "numeros_captados") is None


def test_a_mesma_meta_com_valor_diferente_por_pessoa(monkeypatch):
    _mockar_banco(
        monkeypatch,
        [
            {"id_user": ANA, "cargo": "sdr", "metrica": "numeros_captados", "valor_diario": 4},
            {"id_user": BRUNO, "cargo": "sdr", "metrica": "numeros_captados", "valor_diario": 10},
        ],
    )
    dia = date(2026, 9, 15)
    metas = buscar_metas()
    assert metas.por_usuario(dia, dia, ANA, "sdr", "numeros_captados") == 4
    assert metas.por_usuario(dia, dia, BRUNO, "sdr", "numeros_captados") == 10


def test_pessoa_sem_vinculo_fica_sem_meta_mesmo_com_o_colega_tendo(monkeypatch):
    _mockar_banco(
        monkeypatch,
        [{"id_user": ANA, "cargo": "sdr", "metrica": "numeros_captados", "valor_diario": 4}],
    )
    dia = date(2026, 9, 15)
    metas = buscar_metas()
    assert metas.por_usuario(dia, dia, BRUNO, "sdr", "numeros_captados") is None


def test_meta_zero_cadastrada_e_zero_nao_none(monkeypatch):
    # Meta 0 = métrica aberta pra pessoa (o front pinta a barra de azul).
    _mockar_banco(
        monkeypatch,
        [{"id_user": ANA, "cargo": "sdr", "metrica": "numeros_captados", "valor_diario": 0}],
    )
    assert buscar_metas().por_usuario(date(2026, 9, 1), date(2026, 9, 30), ANA, "sdr", "numeros_captados") == 0


def test_meta_editada_em_outubro_vale_tambem_em_setembro(monkeypatch):
    # Regressão: editar as metas em 05/10 deixava setembro sem meta nenhuma.
    _mockar_banco(
        monkeypatch,
        [{"id_user": ANA, "cargo": "sdr", "metrica": "numeros_captados", "valor_diario": 6}],
    )
    metas = buscar_metas()
    assert metas.por_usuario(date(2026, 9, 1), date(2026, 9, 30), ANA, "sdr", "numeros_captados") == 6 * 22
    assert metas.por_usuario(date(2026, 10, 6), date(2026, 10, 6), ANA, "sdr", "numeros_captados") == 6


def test_mesma_pessoa_e_metrica_tem_meta_diferente_por_cargo(monkeypatch):
    _mockar_banco(
        monkeypatch,
        [
            {"id_user": 4, "cargo": "sdr", "metrica": "indicacoes", "valor_diario": 4},
            {"id_user": 4, "cargo": "seller", "metrica": "indicacoes", "valor_diario": 2},
        ],
    )
    metas = buscar_metas()
    dia = date(2026, 10, 6)
    assert metas.por_usuario(dia, dia, 4, "sdr", "indicacoes") == 4
    assert metas.por_usuario(dia, dia, 4, "seller", "indicacoes") == 2
    assert metas.por_usuario(dia, dia, 4, "closer", "indicacoes") is None


# --- meta diária vira meta do período (dia / semana / mês / ano / custom)


def _metas(diaria: int = 4) -> Metas:
    return Metas({(ANA, "sdr", "numeros_captados"): diaria})


def test_mes_inteiro_multiplica_pelos_dias_uteis_do_mes():
    assert _metas().por_usuario(date(2026, 9, 1), date(2026, 9, 30), ANA, "sdr", "numeros_captados") == 88


def test_mes_inteiro_cobra_22_dias_mesmo_com_20_ou_23_dias_reais():
    # Fevereiro/2026 tem 20 dias úteis e dezembro/2026 tem 23; a regra da planilha cobra 22.
    assert _metas().por_usuario(date(2026, 2, 1), date(2026, 2, 28), ANA, "sdr", "numeros_captados") == 88
    assert _metas().por_usuario(date(2026, 12, 1), date(2026, 12, 31), ANA, "sdr", "numeros_captados") == 88


def test_um_dia_util_devolve_a_propria_diaria():
    assert _metas().por_usuario(date(2026, 9, 15), date(2026, 9, 15), ANA, "sdr", "numeros_captados") == 4


def test_semana_multiplica_pelos_cinco_dias_uteis():
    assert _metas().por_usuario(date(2026, 9, 14), date(2026, 9, 20), ANA, "sdr", "numeros_captados") == 20


def test_sabado_sozinho_nao_cobra_meta():
    assert _metas().por_usuario(date(2026, 9, 19), date(2026, 9, 19), ANA, "sdr", "numeros_captados") == 0


def test_ano_inteiro_multiplica_por_22_vezes_12():
    # Regra da planilha: 22 dias úteis por mês × 12.
    assert _metas().por_usuario(date(2026, 1, 1), date(2026, 12, 31), ANA, "sdr", "numeros_captados") == 4 * 264


def test_intervalo_custom_que_atravessa_meses():
    # 28/09 a 02/10: 5 dias úteis.
    assert _metas().por_usuario(date(2026, 9, 28), date(2026, 10, 2), ANA, "sdr", "numeros_captados") == 20


def test_sem_meta_cadastrada_continua_none():
    assert Metas({}).por_usuario(date(2026, 9, 15), date(2026, 9, 15), ANA, "sdr", "numeros_captados") is None


# --- soma de um grupo: é assim que os cards da empresa acham o denominador


def _metas_do_time() -> Metas:
    return Metas({(ANA, "sdr", "reunioes_agendadas"): 4, (BRUNO, "sdr", "reunioes_agendadas"): 6})


def test_somar_junta_as_metas_individuais_do_grupo():
    dia = date(2026, 9, 15)
    assert _metas_do_time().somar(dia, dia, [ANA, BRUNO], "sdr", "reunioes_agendadas") == 10


def test_somar_ignora_quem_nao_tem_meta():
    dia = date(2026, 9, 15)
    assert _metas_do_time().somar(dia, dia, [ANA, BRUNO, CLOSER], "sdr", "reunioes_agendadas") == 10


def test_somar_devolve_none_se_ninguem_do_grupo_tem_meta():
    dia = date(2026, 9, 15)
    assert _metas_do_time().somar(dia, dia, [CLOSER], "sdr", "reunioes_agendadas") is None


def test_somar_grupo_vazio_e_zero():
    dia = date(2026, 9, 15)
    assert _metas_do_time().somar(dia, dia, [], "sdr", "reunioes_agendadas") == 0
