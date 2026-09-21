"""Testes de `dominios/financeiro/banco.py` — vendas detalhadas + junção com

cliente. Mesmo padrão de mock de `tests/test_geral_banco.py`.
"""
from __future__ import annotations

from datetime import date

from app.dominios.financeiro import banco as banco_mod


def _mockar(monkeypatch, respostas: dict[str, list[dict]]) -> list[dict]:
    chamadas: list[dict] = []

    def _fake_query(tabela, filtros=None, *a, **k):
        chamadas.append({"tabela": tabela, "filtros": filtros or {}})
        return respostas.get(tabela, [])

    monkeypatch.setattr(banco_mod, "query", _fake_query)
    return chamadas


def test_soma_de_vendas_junta_nome_do_cliente_por_id_cliente(monkeypatch):
    _mockar(
        monkeypatch,
        {
            "metricas_faturamento": [
                {
                    "id": 1,
                    "data_venda": "2026-08-05T00:00:00",
                    "id_cliente": 42,
                    "produto": "Mentoria",
                    "canal": "Instagram",
                    "metodo_pagamento": "Pix",
                    "num_parcelas": 1,
                    "valor_bruto_contrato": 10000,
                    "liquido_entrada": 9500,
                },
            ],
            "cliente_faturamento": [{"id": 42, "nome": "Maria Silva"}],
        },
    )
    vendas = banco_mod.buscar_vendas_detalhadas(date(2026, 8, 1), date(2026, 8, 31))
    assert len(vendas) == 1
    assert vendas[0]["cliente"] == "Maria Silva"
    assert vendas[0]["valor_bruto_contrato"] == 10000
    assert vendas[0]["liquido_entrada"] == 9500


def test_venda_com_id_cliente_sem_cliente_correspondente_fica_com_cliente_none(monkeypatch):
    _mockar(
        monkeypatch,
        {
            "metricas_faturamento": [
                {
                    "id": 2,
                    "data_venda": "2026-08-06T00:00:00",
                    "id_cliente": 999,
                    "produto": None,
                    "canal": None,
                    "metodo_pagamento": None,
                    "num_parcelas": None,
                    "valor_bruto_contrato": 5000,
                    "liquido_entrada": 1000,
                },
            ],
            "cliente_faturamento": [],
        },
    )
    vendas = banco_mod.buscar_vendas_detalhadas(date(2026, 8, 1), date(2026, 8, 31))
    assert vendas[0]["cliente"] is None


def test_venda_sem_id_cliente_fica_com_cliente_none_sem_consultar_a_toa(monkeypatch):
    chamadas = _mockar(
        monkeypatch,
        {
            "metricas_faturamento": [
                {
                    "id": 3,
                    "data_venda": "2026-08-07T00:00:00",
                    "id_cliente": None,
                    "produto": None,
                    "canal": None,
                    "metodo_pagamento": None,
                    "num_parcelas": None,
                    "valor_bruto_contrato": 3000,
                    "liquido_entrada": 500,
                },
            ],
        },
    )
    vendas = banco_mod.buscar_vendas_detalhadas(date(2026, 8, 1), date(2026, 8, 31))
    assert vendas[0]["cliente"] is None
    # buscar_clientes([]) não dispara consulta — só a de metricas_faturamento.
    assert [c["tabela"] for c in chamadas] == ["metricas_faturamento"]


def test_periodo_sem_venda_devolve_lista_vazia(monkeypatch):
    _mockar(monkeypatch, {"metricas_faturamento": []})
    vendas = banco_mod.buscar_vendas_detalhadas(date(2026, 9, 1), date(2026, 9, 30))
    assert vendas == []


def test_venda_com_user_closer_junta_nome_do_closer(monkeypatch):
    _mockar(
        monkeypatch,
        {
            "metricas_faturamento": [
                {
                    "id": 4,
                    "data_venda": "2026-08-10T00:00:00",
                    "id_cliente": None,
                    "produto": "KeepSide",
                    "canal": "LinkedIn",
                    "metodo_pagamento": "PIX",
                    "num_parcelas": 1,
                    "valor_bruto_contrato": 60000,
                    "valor_entrada": 60000,
                    "liquido_entrada": 43475.40,
                    "imposto": 0.1,
                    "taxa": 0.1949,
                    "user_closer": 5,
                },
            ],
            "users": [{"id": 5, "nome": "Mariana"}],
        },
    )
    vendas = banco_mod.buscar_vendas_detalhadas(date(2026, 8, 1), date(2026, 8, 31))
    assert vendas[0]["user_closer"] == 5
    assert vendas[0]["closer"] == "Mariana"
    assert vendas[0]["valor_entrada"] == 60000
    assert vendas[0]["imposto"] == 0.1
    assert vendas[0]["taxa"] == 0.1949


def test_venda_com_user_closer_sem_correspondente_fica_com_closer_none(monkeypatch):
    _mockar(
        monkeypatch,
        {
            "metricas_faturamento": [
                {
                    "id": 5,
                    "data_venda": "2026-08-11T00:00:00",
                    "id_cliente": None,
                    "produto": None,
                    "canal": None,
                    "metodo_pagamento": None,
                    "num_parcelas": None,
                    "valor_bruto_contrato": 1000,
                    "liquido_entrada": 900,
                    "user_closer": 999,
                },
            ],
            "users": [],
        },
    )
    vendas = banco_mod.buscar_vendas_detalhadas(date(2026, 8, 1), date(2026, 8, 31))
    assert vendas[0]["closer"] is None


def test_venda_sem_user_closer_fica_com_closer_none_sem_consultar_users(monkeypatch):
    chamadas = _mockar(
        monkeypatch,
        {
            "metricas_faturamento": [
                {
                    "id": 6,
                    "data_venda": "2026-08-12T00:00:00",
                    "id_cliente": None,
                    "produto": None,
                    "canal": None,
                    "metodo_pagamento": None,
                    "num_parcelas": None,
                    "valor_bruto_contrato": 1000,
                    "liquido_entrada": 900,
                    "user_closer": None,
                },
            ],
        },
    )
    vendas = banco_mod.buscar_vendas_detalhadas(date(2026, 8, 1), date(2026, 8, 31))
    assert vendas[0]["user_closer"] is None
    assert vendas[0]["closer"] is None
    assert [c["tabela"] for c in chamadas] == ["metricas_faturamento"]


def test_buscar_closers_com_lista_vazia_nao_consulta():
    assert banco_mod.buscar_closers([]) == {}


def test_filtro_de_data_usa_lt_no_dia_seguinte_ao_fim(monkeypatch):
    chamadas = _mockar(monkeypatch, {"metricas_faturamento": []})
    banco_mod.buscar_vendas_detalhadas(date(2026, 8, 1), date(2026, 8, 31))
    filtros = chamadas[0]["filtros"]
    assert filtros["and"] == "(data_venda.gte.2026-08-01,data_venda.lt.2026-09-01)"


def test_buscar_clientes_com_lista_vazia_nao_consulta():
    assert banco_mod.buscar_clientes([]) == {}
