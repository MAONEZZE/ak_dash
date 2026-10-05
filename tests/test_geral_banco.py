"""Testes de `dominios/geral/banco.py` — faturamento e o segundo Supabase.

As métricas de atividade saíram daqui: a Geral lê `dash.vw_metricas` pelo
mesmo `buscar_totais` do Comercial (ver tests/test_banco_comercial.py).
"""
from __future__ import annotations

from datetime import date

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


def test_liquidado_soma_o_segundo_pagamento_da_venda(monkeypatch):
    # Venda parcelada em duas formas (ex.: entrada no PIX + resto no cartão) —
    # cada pagamento com seu próprio líquido. Faltava somar o segundo: era
    # esse o bug que subestimava o card "Liquidado" da Geral.
    _mockar_vendas(
        monkeypatch,
        [
            {
                "user_closer": 8,
                "valor_bruto_contrato": 60000,
                "liquido_entrada": 27000.00,
                "liquido_pgto_2": 21737.70,
            },
        ],
    )
    resultado = banco_mod.buscar_faturamento(date(2026, 8, 1), date(2026, 8, 31), [8])
    assert resultado.empresa["liquidado"] == pytest.approx(48737.70)
    assert resultado.por_pessoa[8]["liquidado"] == pytest.approx(48737.70)


def test_liquidado_sem_segundo_pagamento_nao_muda(monkeypatch):
    _mockar_vendas(
        monkeypatch,
        [{"user_closer": 8, "valor_bruto_contrato": 60000, "liquido_entrada": 27000.00}],
    )
    resultado = banco_mod.buscar_faturamento(date(2026, 8, 1), date(2026, 8, 31), [8])
    assert resultado.empresa["liquidado"] == 27000.00


def test_filtro_usa_data_venda_com_lt_no_dia_seguinte(monkeypatch):
    chamadas = _mockar_vendas(monkeypatch, [])
    banco_mod.buscar_faturamento(date(2026, 8, 1), date(2026, 8, 31), [])
    assert chamadas[0]["filtros"]["and"] == "(data_venda.gte.2026-08-01,data_venda.lt.2026-09-01)"


# --- buscar_confrarias_do_mes (segundo Supabase: SED.events/SED.registrations)


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
    (evento,) = banco_mod.buscar_confrarias_do_mes(date(2026, 9, 1), date(2026, 9, 30))
    assert evento.inscritos == 4
    assert evento.aprovados == 1
    assert evento.pendentes == 2  # só `pending`: recusado não é pendente
    assert evento.capacidade == 50


def test_evento_sem_inscricao_sai_com_zero_nao_com_erro(monkeypatch):
    _mockar_duas_queries(
        monkeypatch,
        [{"id": "e1", "title": "Imersão", "event_date": "2026-09-20T19:00:00", "capacity": None}],
        [{"event_id": "outro", "status": "approved"}],
    )
    (evento,) = banco_mod.buscar_confrarias_do_mes(date(2026, 9, 1), date(2026, 9, 30))
    assert (evento.inscritos, evento.aprovados, evento.pendentes, evento.capacidade) == (0, 0, 0, None)


def test_filtra_confraria_do_mes_inteiro_e_nao_filtra_status(monkeypatch):
    chamadas = _mockar_duas_queries(
        monkeypatch,
        [{"id": "e1", "title": "x", "event_date": "2026-09-20T19:00:00", "capacity": None}],
        [],
    )
    banco_mod.buscar_confrarias_do_mes(date(2026, 9, 1), date(2026, 9, 30))
    # Meia-noite de São Paulo em UTC (+3h), com o fim exclusivo no dia seguinte.
    assert chamadas[0]["filtros"]["and"] == '(event_date.gte."2026-09-01T03:00:00Z",event_date.lt."2026-10-01T03:00:00Z")'
    assert chamadas[0]["filtros"]["title"] == "ilike.*confraria akeel*"
    assert chamadas[0]["filtros"]["order"] == "event_date.asc"
    # Sem filtro de status: toda inscrição do evento conta como inscrito.
    assert "status" not in chamadas[1]["filtros"]
    assert chamadas[1]["filtros"]["event_id"] == 'in.("e1")'


def test_no_maximo_dez_eventos_e_na_ordem_do_banco(monkeypatch):
    _mockar_duas_queries(
        monkeypatch,
        [
            {"id": f"e{i}", "title": f"Confraria Akeel {i}", "event_date": "2026-09-20T19:00:00", "capacity": None}
            for i in range(1, 26)
        ],
        [],
    )
    eventos = banco_mod.buscar_confrarias_do_mes(date(2026, 9, 1), date(2026, 9, 30))
    assert [e.id for e in eventos] == [f"e{i}" for i in range(1, 11)]


def test_sem_confraria_no_mes_nao_consulta_inscricoes(monkeypatch):
    chamadas = _mockar_duas_queries(monkeypatch, [], [])
    assert banco_mod.buscar_confrarias_do_mes(date(2026, 9, 1), date(2026, 9, 30)) == []
    assert [c["tabela"] for c in chamadas] == ["events"]


def test_evento_sem_titulo_ganha_rotulo_neutro(monkeypatch):
    _mockar_duas_queries(
        monkeypatch,
        [{"id": "e1", "title": None, "event_date": "2026-09-20T19:00:00", "capacity": None}],
        [],
    )
    (evento,) = banco_mod.buscar_confrarias_do_mes(date(2026, 9, 1), date(2026, 9, 30))
    assert evento.titulo == "Sem título"


# Os limites viajam em UTC com `Z`: mandar o relógio de parede de São Paulo
# deslocaria o mês em 3h contra a coluna (que o Prisma grava em UTC), e `+00:00`
# dependeria de percent-encoding correto pra não virar espaço na querystring.
def test_limites_do_mes_nunca_usam_offset_numerico(monkeypatch):
    chamadas = _mockar_duas_queries(monkeypatch, [], [])

    banco_mod.buscar_confrarias_do_mes(date(2026, 12, 1), date(2026, 12, 31))

    valor = chamadas[0]["filtros"]["and"]
    assert '"2027-01-01T03:00:00Z"' in valor
    assert "+" not in valor


# --- buscar_dripify_por_conta (dash.metricas_dripify, uma conta por id_user)


def _mockar_dripify(monkeypatch, linhas: list[dict], usuarios: list[dict]) -> list[dict]:
    chamadas: list[dict] = []

    def _fake_query(tabela, filtros=None, *a, **k):
        chamadas.append({"tabela": tabela, "filtros": filtros or {}})
        return linhas if tabela == "metricas_dripify" else usuarios

    monkeypatch.setattr(banco_mod, "query", _fake_query)
    return chamadas


def _drip(id_user: int, chave: str, aceitas: int | None, captados: int | None) -> dict:
    return {"id_user": id_user, "key_data_ref_user": chave, "conexoes_aceitas": aceitas, "numeros_captados": captados}


def test_dripify_soma_por_conta_so_dentro_do_periodo(monkeypatch):
    _mockar_dripify(
        monkeypatch,
        [
            _drip(1, "01/10/2026-jacob", 20, 10),
            _drip(1, "05/10/2026-jacob", 20, 20),
            _drip(1, "30/09/2026-jacob", 99, 99),  # fora: dia anterior ao início
            _drip(1, "06/10/2026-jacob", 99, 99),  # fora: dia seguinte ao fim
            _drip(3, "02/10/2026-alex", 50, None),
        ],
        [{"id": 1, "nome": "Jacob"}, {"id": 3, "nome": "Alex"}],
    )
    contas = banco_mod.buscar_dripify_por_conta(date(2026, 10, 1), date(2026, 10, 5))
    assert contas == [
        banco_mod.ContaDripify(conta="Alex", conexoes_aceitas=50, numeros_captados=0),
        banco_mod.ContaDripify(conta="Jacob", conexoes_aceitas=40, numeros_captados=30),
    ]


def test_dripify_ignora_chave_sem_data_e_nao_busca_nomes_sem_conta(monkeypatch):
    chamadas = _mockar_dripify(monkeypatch, [_drip(1, "sem-data", 5, 5), _drip(None, "01/10/2026-x", 5, 5)], [])
    assert banco_mod.buscar_dripify_por_conta(date(2026, 10, 1), date(2026, 10, 31)) == []
    assert [c["tabela"] for c in chamadas] == ["metricas_dripify"]


def test_dripify_conta_sem_usuario_ganha_rotulo_neutro(monkeypatch):
    _mockar_dripify(monkeypatch, [_drip(7, "01/10/2026-x", 1, 0)], [])
    [conta] = banco_mod.buscar_dripify_por_conta(date(2026, 10, 1), date(2026, 10, 31))
    assert conta.conta == "Conta 7"
