"""Testes de `app/metas.py` — `dash.metricas_metas` + `dash.user_metas`.

`metricas_metas` diz qual métrica a meta mede; `user_metas` guarda o valor
DIÁRIO de cada pessoa. A meta atual vale pra qualquer período (decisão do
usuário, 2026-10-05) — não existe mais meta "do mês".
"""
from __future__ import annotations

from datetime import date

from app import metas as metas_mod
from app.metas import Metas, buscar_metas

# ids de dash.users (mesmos do ambiente real: 2 e 9 são SDRs, 1 é closer).
ANA, BRUNO, CLOSER = 2, 9, 1


def _mockar_banco(monkeypatch, metas: list[dict], vinculos: list[dict]) -> None:
    def fake_query(tabela, *a, **k):
        return metas if tabela == "metricas_metas" else vinculos

    monkeypatch.setattr(metas_mod, "query", fake_query)


def test_tabela_vazia_devolve_none_e_vazio_e_true(monkeypatch):
    _mockar_banco(monkeypatch, [], [])
    metas = buscar_metas()
    assert metas.vazio is True
    assert metas.por_usuario(date(2026, 9, 1), date(2026, 9, 30), ANA, "numeros_captados") is None


def test_meta_sem_linha_em_user_metas_nao_vale_pra_ninguem(monkeypatch):
    _mockar_banco(monkeypatch, [{"id": 1, "metrica": "numeros_captados", "periodo": "2026-09-01"}], [])
    metas = buscar_metas()
    assert metas.vazio is True


def test_a_mesma_meta_com_valor_diferente_por_pessoa(monkeypatch):
    _mockar_banco(
        monkeypatch,
        [{"id": 2, "metrica": "numeros_captados"}],
        [
            {"id_meta": 2, "id_user": ANA, "valor_meta": 4},
            {"id_meta": 2, "id_user": BRUNO, "valor_meta": 10},
        ],
    )
    dia = date(2026, 9, 15)
    metas = buscar_metas()
    assert metas.por_usuario(dia, dia, ANA, "numeros_captados") == 4
    assert metas.por_usuario(dia, dia, BRUNO, "numeros_captados") == 10


def test_pessoa_sem_vinculo_fica_sem_meta_mesmo_com_o_colega_tendo(monkeypatch):
    _mockar_banco(
        monkeypatch,
        [{"id": 2, "metrica": "numeros_captados"}],
        [{"id_meta": 2, "id_user": ANA, "valor_meta": 4}],
    )
    dia = date(2026, 9, 15)
    metas = buscar_metas()
    assert metas.por_usuario(dia, dia, BRUNO, "numeros_captados") is None


def test_meta_zero_cadastrada_e_zero_nao_none(monkeypatch):
    # Meta 0 = métrica aberta pra pessoa (o front pinta a barra de azul).
    _mockar_banco(
        monkeypatch,
        [{"id": 2, "metrica": "numeros_captados"}],
        [{"id_meta": 2, "id_user": ANA, "valor_meta": 0}],
    )
    assert buscar_metas().por_usuario(date(2026, 9, 1), date(2026, 9, 30), ANA, "numeros_captados") == 0


def test_vinculo_apontando_pra_meta_inexistente_e_ignorado(monkeypatch):
    _mockar_banco(
        monkeypatch,
        [{"id": 2, "metrica": "numeros_captados"}],
        [{"id_meta": 99, "id_user": ANA, "valor_meta": 500}],
    )
    assert buscar_metas().vazio is True


def test_meta_editada_em_outubro_vale_tambem_em_setembro(monkeypatch):
    # Regressão: editar as metas em 05/10 deixava setembro sem meta nenhuma.
    _mockar_banco(
        monkeypatch,
        [{"id": 2, "metrica": "numeros_captados", "periodo": "2026-09-01"}],
        [{"id_meta": 2, "id_user": ANA, "valor_meta": 6, "atualizado_em": "2026-10-05T13:40:23"}],
    )
    metas = buscar_metas()
    assert metas.por_usuario(date(2026, 9, 1), date(2026, 9, 30), ANA, "numeros_captados") == 6 * 22
    assert metas.por_usuario(date(2026, 10, 6), date(2026, 10, 6), ANA, "numeros_captados") == 6


def test_duas_linhas_da_mesma_pessoa_e_metrica_vale_a_atualizada_por_ultimo(monkeypatch):
    _mockar_banco(
        monkeypatch,
        [
            {"id": 2, "metrica": "numeros_captados"},
            {"id": 20, "metrica": "numeros_captados"},
        ],
        [
            {"id_meta": 20, "id_user": ANA, "valor_meta": 8, "atualizado_em": "2026-10-05T09:00:00"},
            {"id_meta": 2, "id_user": ANA, "valor_meta": 6, "atualizado_em": "2026-10-01T10:40:28"},
        ],
    )
    dia = date(2026, 10, 6)
    assert buscar_metas().por_usuario(dia, dia, ANA, "numeros_captados") == 8


# --- meta diária vira meta do período (dia / semana / mês / ano / custom)


def _metas(diaria: int = 4) -> Metas:
    return Metas({(ANA, "numeros_captados"): diaria})


def test_mes_inteiro_multiplica_pelos_dias_uteis_do_mes():
    assert _metas().por_usuario(date(2026, 9, 1), date(2026, 9, 30), ANA, "numeros_captados") == 88


def test_um_dia_util_devolve_a_propria_diaria():
    assert _metas().por_usuario(date(2026, 9, 15), date(2026, 9, 15), ANA, "numeros_captados") == 4


def test_semana_multiplica_pelos_cinco_dias_uteis():
    assert _metas().por_usuario(date(2026, 9, 14), date(2026, 9, 20), ANA, "numeros_captados") == 20


def test_sabado_sozinho_nao_cobra_meta():
    assert _metas().por_usuario(date(2026, 9, 19), date(2026, 9, 19), ANA, "numeros_captados") == 0


def test_ano_inteiro_multiplica_pelos_dias_uteis_do_ano():
    # 2026 tem 261 dias úteis (seg-sex, sem feriado).
    assert _metas().por_usuario(date(2026, 1, 1), date(2026, 12, 31), ANA, "numeros_captados") == 4 * 261


def test_intervalo_custom_que_atravessa_meses():
    # 28/09 a 02/10: 5 dias úteis.
    assert _metas().por_usuario(date(2026, 9, 28), date(2026, 10, 2), ANA, "numeros_captados") == 20


def test_sem_meta_cadastrada_continua_none():
    assert Metas({}).por_usuario(date(2026, 9, 15), date(2026, 9, 15), ANA, "numeros_captados") is None


# --- soma de um grupo: é assim que os cards da empresa acham o denominador


def _metas_do_time() -> Metas:
    return Metas({(ANA, "reunioes_agendadas"): 4, (BRUNO, "reunioes_agendadas"): 6})


def test_somar_junta_as_metas_individuais_do_grupo():
    dia = date(2026, 9, 15)
    assert _metas_do_time().somar(dia, dia, [ANA, BRUNO], "reunioes_agendadas") == 10


def test_somar_ignora_quem_nao_tem_meta():
    dia = date(2026, 9, 15)
    assert _metas_do_time().somar(dia, dia, [ANA, BRUNO, CLOSER], "reunioes_agendadas") == 10


def test_somar_devolve_none_se_ninguem_do_grupo_tem_meta():
    dia = date(2026, 9, 15)
    assert _metas_do_time().somar(dia, dia, [CLOSER], "reunioes_agendadas") is None


def test_somar_grupo_vazio_e_zero():
    dia = date(2026, 9, 15)
    assert _metas_do_time().somar(dia, dia, [], "reunioes_agendadas") == 0
