"""Leitura de `dash2.metricas_faturamento` (uma linha por venda),
`dash2.cliente_faturamento` (73 clientes), `dash2.users` (closer) e
`dash2.recebimentos_faturamento` (um mês de recebimento por venda) pra
tabela de vendas de `/financeiro`.

Quatro consultas, junção em Python — mesmo padrão de `buscar_eventos_proximos`
em `dominios/geral/banco.py`. Não vale a pena um `select` aninhado do
PostgREST aqui: são tabelas pequenas e o BFF já faz esse tipo de join em
memória em outro domínio.
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


def buscar_closers(ids: list[int]) -> dict[int, str]:
    """Nome de `dash.users` pros `user_closer` referenciados nas vendas.

    Sem filtro de `active`: closer que já saiu do time (ex.: Mariana) ainda
    precisa aparecer na venda que fez. `/pessoas` não serve aqui por isso —
    só lista `active = true`.
    """
    if not ids:
        return {}
    ids_str = ",".join(str(i) for i in ids)
    linhas = query("users", {"id": f"in.({ids_str})"})
    return {int(r["id"]): r["nome"] for r in linhas if r.get("nome")}


def buscar_vendas_detalhadas(inicio: date, fim: date) -> list[dict]:
    fim_exclusivo = fim + timedelta(days=1)
    vendas = query(
        "metricas_faturamento",
        {"and": f"(data_venda.gte.{inicio.isoformat()},data_venda.lt.{fim_exclusivo.isoformat()})"},
    )

    receb = query(
        "recebimentos_faturamento",
        {"and": f"(mes.gte.{inicio.replace(day=1).isoformat()},mes.lte.{fim.isoformat()})"},
    )

    # Venda fechada antes do período, mas com recebimento nele, precisa aparecer.
    faltando = sorted(
        {int(r["id_planilha_venda"]) for r in receb}
        - {int(v["id_planilha"]) for v in vendas if v.get("id_planilha") is not None}
    )
    if faltando:
        vendas = vendas + query("metricas_faturamento", {"id_planilha": f"in.({','.join(map(str, faltando))})"})

    ids_clientes = [int(v["id_cliente"]) for v in vendas if v.get("id_cliente") is not None]
    clientes = buscar_clientes(ids_clientes)

    ids_closers = [int(v["user_closer"]) for v in vendas if v.get("user_closer") is not None]
    closers = buscar_closers(ids_closers)

    por_venda: dict[int, list[dict]] = {}
    for r in receb:
        por_venda.setdefault(int(r["id_planilha_venda"]), []).append(
            {"mes": r["mes"][:7], "pago": r.get("pago") or 0, "liquido": r.get("liquido") or 0}
        )
    for lista in por_venda.values():
        lista.sort(key=lambda x: x["mes"])

    return [
        {
            "id": v["id"],
            "id_planilha": v.get("id_planilha"),
            "data_venda": v["data_venda"],
            "cliente": clientes.get(int(v["id_cliente"])) if v.get("id_cliente") is not None else None,
            "produto": v.get("produto"),
            "canal": v.get("canal"),
            "metodo_pagamento": v.get("metodo_pagamento"),
            "num_parcelas": v.get("num_parcelas"),
            "valor_bruto_contrato": v.get("valor_bruto_contrato") or 0,
            "valor_entrada": v.get("valor_entrada") or 0,
            "liquido_entrada": v.get("liquido_entrada") or 0,
            "imposto": v.get("imposto") or 0,
            "taxa": v.get("taxa") or 0,
            # Segundo pagamento de uma venda parcelada em duas formas diferentes
            # (ex.: entrada no PIX + resto no cartão) — mesmo imposto da venda,
            # taxa e forma próprias. "0"/None quando não existe.
            "valor_pgto_2": v.get("valor_pgto_2") or 0,
            "taxa_pgto_2": v.get("taxa_pgto_2") or 0,
            "liquido_pgto_2": v.get("liquido_pgto_2") or 0,
            "forma_pgto_2": v.get("forma_pgto_2"),
            "user_closer": int(v["user_closer"]) if v.get("user_closer") is not None else None,
            "closer": closers.get(int(v["user_closer"])) if v.get("user_closer") is not None else None,
            "recebimentos": por_venda.get(v.get("id_planilha"), []),
        }
        for v in vendas
    ]
