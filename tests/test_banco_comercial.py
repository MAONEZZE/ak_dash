"""Testes de `dominios/comercial/banco.py` contra `dash.vw_metricas` (formato longo)."""
from __future__ import annotations

from datetime import date

from app.dominios.comercial import banco as banco_mod
from app.fontes import supabase


def _mockar_query(monkeypatch, linhas: list[dict]) -> None:
    monkeypatch.setattr(supabase, "ler_metricas_do_cargo", lambda cargo, ids, inicio, fim: linhas)


def test_soma_realizado_e_conta_dias_distintos(monkeypatch):
    _mockar_query(
        monkeypatch,
        [
            {"data": "2026-09-01", "id_user": 9, "metrica": "ligacoes_efetuadas", "valor": 10, "conta": "jonathan"},
            {"data": "2026-09-02", "id_user": 9, "metrica": "ligacoes_efetuadas", "valor": 20, "conta": "jonathan"},
        ],
    )
    totais = banco_mod.buscar_totais("sdr", [9], date(2026, 9, 1), date(2026, 9, 3))
    assert totais.realizado[(9, "ligacoes_efetuadas")] == 30
    assert totais.dias_com_lancamento[(9, "ligacoes_efetuadas")] == 2
    assert totais.contas_por_pessoa[9] == ["jonathan"]


def test_metrica_fora_do_conjunto_do_cargo_e_descartada_e_contada(monkeypatch):
    # "reunioes_realizadas" é métrica só de closer — não deve aparecer num
    # relatório de sdr. (`indicacoes`, `reunioes_agendadas`, `ligacoes_realizadas`
    # e `inscricoes_realizadas` não servem de exemplo: valem pros dois cargos.)
    _mockar_query(
        monkeypatch,
        [
            {"data": "2026-09-01", "id_user": 2, "metrica": "reunioes_realizadas", "valor": 5, "conta": "x"},
            {"data": "2026-09-01", "id_user": 2, "metrica": "ligacoes_efetuadas", "valor": 3, "conta": "x"},
        ],
    )
    totais = banco_mod.buscar_totais("sdr", [2], date(2026, 9, 1), date(2026, 9, 1))
    assert (2, "reunioes_realizadas") not in totais.realizado
    assert totais.realizado[(2, "ligacoes_efetuadas")] == 3
    assert totais.linhas_cargo_cruzado == 1


def test_sdr_soma_ligacoes_realizadas_e_inscricoes_e_descarta_ligacoes_agendadas(monkeypatch):
    # `ligacoes_agendadas` saiu de `dash.metricas_sdrs`: hoje é só de closer.
    _mockar_query(
        monkeypatch,
        [
            {"data": "2026-09-01", "id_user": 2, "metrica": "ligacoes_realizadas", "valor": 4, "conta": None},
            {"data": "2026-09-01", "id_user": 2, "metrica": "inscricoes_realizadas", "valor": 2, "conta": None},
            {"data": "2026-09-01", "id_user": 2, "metrica": "ligacoes_agendadas", "valor": 7, "conta": None},
        ],
    )
    totais = banco_mod.buscar_totais("sdr", [2], date(2026, 9, 1), date(2026, 9, 1))
    assert totais.realizado[(2, "ligacoes_realizadas")] == 4
    assert totais.realizado[(2, "inscricoes_realizadas")] == 2
    assert (2, "ligacoes_agendadas") not in totais.realizado
    assert totais.linhas_cargo_cruzado == 1


def test_closer_soma_ligacoes_agendadas_e_inscricoes(monkeypatch):
    _mockar_query(
        monkeypatch,
        [
            {"data": "2026-09-01", "id_user": 1, "metrica": "ligacoes_agendadas", "valor": 3, "conta": None},
            {"data": "2026-09-01", "id_user": 1, "metrica": "inscricoes_realizadas", "valor": 1, "conta": None},
        ],
    )
    totais = banco_mod.buscar_totais("closer", [1], date(2026, 9, 1), date(2026, 9, 1))
    assert totais.realizado[(1, "ligacoes_agendadas")] == 3
    assert totais.realizado[(1, "inscricoes_realizadas")] == 1
    assert totais.linhas_cargo_cruzado == 0


def test_serie_diaria_pre_populada_com_zero_em_todo_dia_do_intervalo(monkeypatch):
    _mockar_query(monkeypatch, [{"data": "2026-09-02", "id_user": 9, "metrica": "ligacoes_efetuadas", "valor": 7, "conta": "x"}])
    totais = banco_mod.buscar_totais("sdr", [9], date(2026, 9, 1), date(2026, 9, 3))
    assert set(totais.serie_diaria) == {date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)}
    assert totais.serie_diaria[date(2026, 9, 1)]["ligacoes_efetuadas"] == 0
    assert totais.serie_diaria[date(2026, 9, 2)]["ligacoes_efetuadas"] == 7
    assert totais.serie_diaria[date(2026, 9, 3)]["ligacoes_efetuadas"] == 0


def test_sem_ids_devolve_vazio_sem_consultar(monkeypatch):
    def _fake_ler(cargo, ids, inicio, fim):
        raise AssertionError("não devia consultar")

    monkeypatch.setattr(supabase, "ler_metricas_do_cargo", _fake_ler)
    totais = banco_mod.buscar_totais("sdr", [], date(2026, 9, 1), date(2026, 9, 1))
    assert totais.realizado == {}


def test_pessoa_sem_nenhuma_linha_fica_de_fora_dos_dicionarios(monkeypatch):
    _mockar_query(monkeypatch, [])
    totais = banco_mod.buscar_totais("closer", [10], date(2026, 9, 1), date(2026, 9, 1))
    assert (10, "indicacoes") not in totais.realizado
    assert (10, "indicacoes") not in totais.dias_com_lancamento


def test_consulta_pede_o_cargo_as_pessoas_e_o_intervalo(monkeypatch):
    chamadas = []

    def _fake_ler(cargo, ids, inicio, fim):
        chamadas.append((cargo, ids, inicio, fim))
        return []

    monkeypatch.setattr(supabase, "ler_metricas_do_cargo", _fake_ler)
    banco_mod.buscar_totais("sdr", [4], date(2026, 10, 1), date(2026, 10, 2))
    assert chamadas == [("sdr", [4], date(2026, 10, 1), date(2026, 10, 2))]
