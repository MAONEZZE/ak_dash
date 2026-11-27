"""Leitura de `dash2.notas_financeiro` (uma linha por nota) pro `/financeiro`.

Devolve o formato `NotaFinanceiro` do contrato.
"""
from __future__ import annotations

from datetime import date

from app.fontes import supabase


def buscar_notas(inicio: date, fim: date) -> list[dict]:
    return [
        {
            "chave": r["chave"],
            "mes": r["mes"][:7],
            "data_referencia": r["data_referencia"][:10],
            "cliente": r.get("cliente"),
            "categoria": r.get("categoria"),
            "produto": r.get("produto"),
            "valor_pago": r.get("valor_pago") or 0,
            "valor_venda": r.get("valor_venda") or 0,
            "forma_pagamento": r["forma_pagamento"],
            "canal": r.get("canal"),
        }
        for r in supabase.ler_notas_financeiro_do_periodo(inicio, fim)
    ]
