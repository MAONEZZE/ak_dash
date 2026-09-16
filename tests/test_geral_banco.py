"""Testes de `dominios/geral/banco.py` — faturamento e o segundo Supabase.

As métricas de atividade saíram daqui: a Geral lê `dash.vw_metricas` pelo
mesmo `buscar_totais` do Comercial (ver tests/test_banco_comercial.py).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.dominios.geral import banco as banco_mod


# --- buscar_eventos_proximos (segundo Supabase: SED.events/SED.registrations)


def _mockar_duas_queries(monkeypatch, eventos: list[dict], inscricoes: list[dict]) -> list[dict]:
    """Devolve a lista de chamadas feitas, pra conferir filtros enviados ao PostgREST."""
    chamadas: list[dict] = []

    def _fake_query(tabela, filtros=None, *a, **k):
        chamadas.append({"tabela": tabela, "filtros": filtros or {}})
        return eventos if tabela == "events" else inscricoes

    monkeypatch.setattr(banco_mod, "query", _fake_query)
    return chamadas


def test_conta_inscritos_como_pendentes_mais_aprovados(monkeypatch):
    _mockar_duas_queries(
        monkeypatch,
        [{"id": "e1", "title": "Imersão", "event_date": "2026-09-20T19:00:00", "capacity": 50}],
        [
            {"event_id": "e1", "status": "pending"},
            {"event_id": "e1", "status": "pending"},
            {"event_id": "e1", "status": "approved"},
        ],
    )
    (evento,) = banco_mod.buscar_eventos_proximos(datetime(2026, 9, 15, 10, 0))
    assert evento.inscritos == 3
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


def test_filtra_por_data_futura_e_so_status_pending_approved(monkeypatch):
    chamadas = _mockar_duas_queries(
        monkeypatch,
        [{"id": "e1", "title": "x", "event_date": "2026-09-20T19:00:00", "capacity": None}],
        [],
    )
    banco_mod.buscar_eventos_proximos(datetime(2026, 9, 15, 10, 30, 0))
    # Ingênuo é assumido como UTC: só ganha o sufixo `Z`, sem deslocar nada.
    assert chamadas[0]["filtros"]["event_date"] == "gte.2026-09-15T10:30:00Z"
    assert chamadas[0]["filtros"]["order"] == "event_date.asc"
    assert chamadas[1]["filtros"]["status"] == "in.(pending,approved)"
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
