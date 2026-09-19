"""Testes de `dominios/geral/banco.py` — faturamento e o segundo Supabase.

As métricas de atividade saíram daqui: a Geral lê `dash.vw_metricas` pelo
mesmo `buscar_totais` do Comercial (ver tests/test_banco_comercial.py).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.dominios.geral import banco as banco_mod


# --- buscar_faturamento (dash.metricas_faturamento: uma linha por venda)


def _mockar_vendas(monkeypatch, linhas: list[dict]) -> list[dict]:
    chamadas: list[dict] = []

    def _fake_query(tabela, filtros=None, *a, **k):
        chamadas.append({"tabela": tabela, "filtros": filtros or {}})
        return linhas

    monkeypatch.setattr(banco_mod, "query", _fake_query)
    return chamadas


def test_soma_varias_vendas_no_card_da_empresa(monkeypatch):
    _mockar_vendas(
        monkeypatch,
        [
            {"user_closer": 8, "valor_bruto_contrato": 400000, "liquido_entrada": 160019.64},
            {"user_closer": 1, "valor_bruto_contrato": 165000, "liquido_entrada": 21737.70},
            {"user_closer": 3, "valor_bruto_contrato": 60000, "liquido_entrada": 9000.00},
        ],
    )
    resultado = banco_mod.buscar_faturamento(date(2026, 8, 1), date(2026, 8, 31), [1, 3, 8])
    assert resultado.empresa["faturamento"] == 625000
    assert resultado.empresa["liquidado"] == pytest.approx(190757.34)
    assert resultado.empresa["inscritos"] is None
    assert resultado.empresa["aprovados"] is None


def test_agrupa_liquidado_por_user_closer(monkeypatch):
    _mockar_vendas(
        monkeypatch,
        [
            {"user_closer": 8, "valor_bruto_contrato": 300000, "liquido_entrada": 100000.00},
            {"user_closer": 8, "valor_bruto_contrato": 100000, "liquido_entrada": 60019.64},
            {"user_closer": 1, "valor_bruto_contrato": 165000, "liquido_entrada": 21737.70},
        ],
    )
    resultado = banco_mod.buscar_faturamento(date(2026, 8, 1), date(2026, 8, 31), [1, 8])
    assert resultado.por_pessoa[8]["liquidado"] == 160019.64
    assert resultado.por_pessoa[1]["liquidado"] == 21737.70
    assert resultado.por_pessoa[8]["inscritos"] is None
    assert resultado.por_pessoa[8]["aprovados"] is None


def test_venda_sem_user_closer_entra_na_empresa_e_em_ninguem(monkeypatch):
    _mockar_vendas(
        monkeypatch,
        [
            {"user_closer": None, "valor_bruto_contrato": 60000, "liquido_entrada": 15000.00},
            {"user_closer": 1, "valor_bruto_contrato": 20000, "liquido_entrada": 5000.00},
        ],
    )
    resultado = banco_mod.buscar_faturamento(date(2026, 8, 1), date(2026, 8, 31), [1])
    assert resultado.empresa["faturamento"] == 80000
    assert resultado.empresa["liquidado"] == 20000.00
    assert list(resultado.por_pessoa.keys()) == [1]


def test_periodo_sem_venda_da_zero_e_nao_erro(monkeypatch):
    _mockar_vendas(monkeypatch, [])
    resultado = banco_mod.buscar_faturamento(date(2026, 9, 1), date(2026, 9, 30), [1, 3, 8])
    assert resultado.empresa["faturamento"] == 0
    assert resultado.empresa["liquidado"] == 0
    assert resultado.por_pessoa == {}


def test_filtro_usa_data_venda_com_lt_no_dia_seguinte(monkeypatch):
    chamadas = _mockar_vendas(monkeypatch, [])
    banco_mod.buscar_faturamento(date(2026, 8, 1), date(2026, 8, 31), [])
    assert chamadas[0]["filtros"]["and"] == "(data_venda.gte.2026-08-01,data_venda.lt.2026-09-01)"


# --- buscar_eventos_proximos (segundo Supabase: SED.events/SED.registrations)


def _mockar_duas_queries(monkeypatch, eventos: list[dict], inscricoes: list[dict]) -> list[dict]:
    """Devolve a lista de chamadas feitas, pra conferir filtros enviados ao PostgREST."""
    chamadas: list[dict] = []

    def _fake_query(tabela, filtros=None, *a, **k):
        chamadas.append({"tabela": tabela, "filtros": filtros or {}})
        return eventos if tabela == "events" else inscricoes

    monkeypatch.setattr(banco_mod, "query", _fake_query)
    return chamadas


def test_inscritos_conta_toda_inscricao_inclusive_recusada(monkeypatch):
    """Recusado É inscrito: o card mede captação, não ocupação de vaga.

    Regressão do caso real da Imersão Alta Cadência (17/09/2026): 70 linhas no
    banco, 5 delas `rejected`, e a tela mostrava 65.
    """
    _mockar_duas_queries(
        monkeypatch,
        [{"id": "e1", "title": "Imersão", "event_date": "2026-09-20T19:00:00", "capacity": 50}],
        [
            {"event_id": "e1", "status": "pending"},
            {"event_id": "e1", "status": "pending"},
            {"event_id": "e1", "status": "approved"},
            {"event_id": "e1", "status": "rejected"},
        ],
    )
    (evento,) = banco_mod.buscar_eventos_proximos(datetime(2026, 9, 15, 10, 0))
    assert evento.inscritos == 4
    assert evento.aprovados == 1
    assert evento.capacidade == 50


def test_evento_sem_inscricao_sai_com_zero_nao_com_erro(monkeypatch):
    _mockar_duas_queries(
        monkeypatch,
        [{"id": "e1", "title": "Imersão", "event_date": "2026-09-20T19:00:00", "capacity": None}],
        [{"event_id": "outro", "status": "approved"}],
    )
    (evento,) = banco_mod.buscar_eventos_proximos(datetime(2026, 9, 15, 10, 0))
    assert (evento.inscritos, evento.aprovados, evento.capacidade) == (0, 0, None)


def test_filtra_por_data_futura_e_nao_filtra_status(monkeypatch):
    chamadas = _mockar_duas_queries(
        monkeypatch,
        [{"id": "e1", "title": "x", "event_date": "2026-09-20T19:00:00", "capacity": None}],
        [],
    )
    banco_mod.buscar_eventos_proximos(datetime(2026, 9, 15, 10, 30, 0))
    # Ingênuo é assumido como UTC: só ganha o sufixo `Z`, sem deslocar nada.
    assert chamadas[0]["filtros"]["event_date"] == "gte.2026-09-15T10:30:00Z"
    assert chamadas[0]["filtros"]["order"] == "event_date.asc"
    # Sem filtro de status: toda inscrição do evento conta como inscrito.
    assert "status" not in chamadas[1]["filtros"]
    assert chamadas[1]["filtros"]["event_id"] == 'in.("e1")'


def test_no_maximo_tres_eventos_e_na_ordem_do_banco(monkeypatch):
    _mockar_duas_queries(
        monkeypatch,
        [
            {"id": f"e{i}", "title": f"Evento {i}", "event_date": f"2026-09-2{i}T19:00:00", "capacity": None}
            for i in range(1, 6)
        ],
        [],
    )
    eventos = banco_mod.buscar_eventos_proximos(datetime(2026, 9, 15, 10, 0))
    assert [e.id for e in eventos] == ["e1", "e2", "e3"]


def test_sem_evento_futuro_nao_consulta_inscricoes(monkeypatch):
    chamadas = _mockar_duas_queries(monkeypatch, [], [])
    assert banco_mod.buscar_eventos_proximos(datetime(2026, 9, 15, 10, 0)) == []
    assert [c["tabela"] for c in chamadas] == ["events"]


def test_evento_sem_titulo_ganha_rotulo_neutro(monkeypatch):
    _mockar_duas_queries(
        monkeypatch,
        [{"id": "e1", "title": None, "event_date": "2026-09-20T19:00:00", "capacity": None}],
        [],
    )
    (evento,) = banco_mod.buscar_eventos_proximos(datetime(2026, 9, 15, 10, 0))
    assert evento.titulo == "Sem título"


# O corte tem que viajar em UTC. Mandar o relógio de parede de São Paulo
# adiantava o filtro em 3h contra a coluna (que o Prisma grava em UTC), e
# eventos já começados apareciam como "próximos".
def test_corte_vai_em_utc_quando_agora_tem_fuso(monkeypatch):
    chamadas = _mockar_duas_queries(monkeypatch, [], [])
    sp = timezone(timedelta(hours=-3))

    banco_mod.buscar_eventos_proximos(datetime(2026, 9, 15, 10, 30, 0, tzinfo=sp))

    assert chamadas[0]["filtros"]["event_date"] == "gte.2026-09-15T13:30:00Z"


# `+00:00` dependeria de percent-encoding correto para não virar espaço na
# querystring do PostgREST; `Z` não tem essa armadilha.
def test_corte_nunca_usa_offset_numerico(monkeypatch):
    chamadas = _mockar_duas_queries(monkeypatch, [], [])

    banco_mod.buscar_eventos_proximos(datetime(2026, 9, 15, 10, 30, 0, tzinfo=timezone.utc))

    valor = chamadas[0]["filtros"]["event_date"]
    assert valor.endswith("Z")
    assert "+" not in valor
