"""Testes de `dominios/financeiro/banco.py` — notas do período no formato do contrato."""
from __future__ import annotations

from datetime import date

from app.dominios.financeiro import banco as banco_mod
from app.fontes import supabase


def test_buscar_notas_devolve_notas_no_formato_do_contrato(monkeypatch):
    chamadas: list[tuple] = []

    def fake(inicio, fim):
        chamadas.append((inicio, fim))
        return [
            {
                "chave": "2026-11:2",
                "mes": "2026-11-01",
                "linha": 2,
                "cliente": "Ana",
                "categoria": "venda nova",
                "produto": "Aceleração",
                "valor_pago": 5000,
                "valor_venda": None,
                "data_venda": None,
                "data_referencia": "2026-11-01",
                "forma_pagamento": "PIX",
                "canal": None,
                "vendedor": "Jacob",
                "id_vendedor": 1,
                "status": "Emitida",
                "atualizado_em": "x",
            }
        ]

    monkeypatch.setattr(supabase, "ler_notas_financeiro_do_periodo", fake)

    notas = banco_mod.buscar_notas(date(2026, 1, 1), date(2026, 11, 27))

    assert chamadas == [(date(2026, 1, 1), date(2026, 11, 27))]
    assert notas == [
        {
            "chave": "2026-11:2",
            "mes": "2026-11",
            "data_referencia": "2026-11-01",
            "cliente": "Ana",
            "categoria": "venda nova",
            "produto": "Aceleração",
            "valor_pago": 5000,
            "valor_venda": 0,
            "forma_pagamento": "PIX",
            "canal": None,
        }
    ]
