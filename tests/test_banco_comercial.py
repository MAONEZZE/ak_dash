"""Testes de `dominios/comercial/banco.py` contra `dash.vw_metricas` (formato longo)."""
from __future__ import annotations

from datetime import date

from app.dominios.comercial import banco as banco_mod


def _mockar_query(monkeypatch, linhas: list[dict]) -> None:
    monkeypatch.setattr(banco_mod, "query", lambda *a, **k: linhas)


def test_soma_realizado_e_conta_dias_distintos(monkeypatch):
    _mockar_query(
        monkeypatch,
        [
            {"data": "2026-09-01", "id_user": 9, "metrica": "numeros_captados", "valor": 10, "conta": "jonathan"},
            {"data": "2026-09-02", "id_user": 9, "metrica": "numeros_captados", "valor": 20, "conta": "jonathan"},
        ],
    )
    totais = banco_mod.buscar_totais("sdr", [9], date(2026, 9, 1), date(2026, 9, 3))
    assert totais.realizado[(9, "numeros_captados")] == 30
    assert totais.dias_com_lancamento[(9, "numeros_captados")] == 2
    assert totais.contas_por_pessoa[9] == ["jonathan"]


def test_metrica_fora_do_conjunto_do_cargo_e_descartada_e_contada(monkeypatch):
    # "ligacoes_realizadas" é métrica de closer — não deve aparecer num
    # relatório de sdr. (`indicacoes` e `reunioes_agendadas` não servem de
    # exemplo: valem pros dois cargos.)
    _mockar_query(
        monkeypatch,
        [
            {"data": "2026-09-01", "id_user": 2, "metrica": "ligacoes_realizadas", "valor": 5, "conta": "x"},
            {"data": "2026-09-01", "id_user": 2, "metrica": "numeros_captados", "valor": 3, "conta": "x"},
        ],
    )
    totais = banco_mod.buscar_totais("sdr", [2], date(2026, 9, 1), date(2026, 9, 1))
    assert (2, "ligacoes_realizadas") not in totais.realizado
    assert totais.realizado[(2, "numeros_captados")] == 3
    assert totais.linhas_cargo_cruzado == 1


def test_serie_diaria_pre_populada_com_zero_em_todo_dia_do_intervalo(monkeypatch):
    _mockar_query(monkeypatch, [{"data": "2026-09-02", "id_user": 9, "metrica": "numeros_captados", "valor": 7, "conta": "x"}])
    totais = banco_mod.buscar_totais("sdr", [9], date(2026, 9, 1), date(2026, 9, 3))
    assert set(totais.serie_diaria) == {date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)}
    assert totais.serie_diaria[date(2026, 9, 1)]["numeros_captados"] == 0
    assert totais.serie_diaria[date(2026, 9, 2)]["numeros_captados"] == 7
    assert totais.serie_diaria[date(2026, 9, 3)]["numeros_captados"] == 0


def test_sem_ids_devolve_vazio_sem_consultar(monkeypatch):
    chamado = False

    def _fake_query(*a, **k):
        nonlocal chamado
        chamado = True
        return []

    monkeypatch.setattr(banco_mod, "query", _fake_query)
    totais = banco_mod.buscar_totais("sdr", [], date(2026, 9, 1), date(2026, 9, 1))
    assert totais.realizado == {}
    assert chamado is False


def test_pessoa_sem_nenhuma_linha_fica_de_fora_dos_dicionarios(monkeypatch):
    _mockar_query(monkeypatch, [])
    totais = banco_mod.buscar_totais("closer", [10], date(2026, 9, 1), date(2026, 9, 1))
    assert (10, "indicacoes") not in totais.realizado
    assert (10, "indicacoes") not in totais.dias_com_lancamento
