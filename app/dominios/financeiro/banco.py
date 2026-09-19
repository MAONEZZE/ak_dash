"""Leitura de `dash.metricas_faturamento` (uma linha por venda) e
`dash.cliente_faturamento` (73 clientes) pra tabela de vendas de `/financeiro`.

Duas consultas, junção em Python — mesmo padrão de `buscar_eventos_proximos`
em `dominios/geral/banco.py`. Não vale a pena um `select` aninhado do
PostgREST aqui: são duas tabelas pequenas e o BFF já faz esse tipo de join
em memória em outro domínio.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.fontes.banco import query


def buscar_clientes(ids: list[int]) -> dict[int, str]:
    if not ids:
        return {}
    ids_str = ",".join(str(i) for i in ids)
    linhas = query("cliente_faturamento", {"id": f"in.({ids_str})"})
    return {int(r["id"]): r["nome"] for r in linhas if r.get("nome")}


def buscar_vendas_detalhadas(inicio: date, fim: date) -> list[dict]:
    fim_exclusivo = fim + timedelta(days=1)
    vendas = query(
        "metricas_faturamento",
        {"and": f"(data_venda.gte.{inicio.isoformat()},data_venda.lt.{fim_exclusivo.isoformat()})"},
    )

    ids_clientes = [int(v["id_cliente"]) for v in vendas if v.get("id_cliente") is not None]
    clientes = buscar_clientes(ids_clientes)

    return [
        {
            "id": v["id"],
            "data_venda": v["data_venda"],
            "cliente": clientes.get(int(v["id_cliente"])) if v.get("id_cliente") is not None else None,
            "produto": v.get("produto"),
            "canal": v.get("canal"),
            "metodo_pagamento": v.get("metodo_pagamento"),
            "num_parcelas": v.get("num_parcelas"),
            "valor_bruto_contrato": v.get("valor_bruto_contrato") or 0,
            "liquido_entrada": v.get("liquido_entrada") or 0,
        }
        for v in vendas
    ]
