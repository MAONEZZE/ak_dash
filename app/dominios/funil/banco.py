"""Leitura de `contas_funil` e `metricas_contas` (funis LinkedIn/Instagram)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.fontes.banco import query
from app.planilhas import COLUNAS_POR_TABELA


@dataclass(frozen=True)
class ContaFunil:
    id_conta: int
    nome: str
    id_seller: int | None
    metricas: dict[str, int]


def buscar_contas(canal: str, inicio: date, fim: date) -> list[ContaFunil]:
    colunas_metricas = COLUNAS_POR_TABELA["metricas_contas"]

    contas = query("contas_funil", {"canal": f"eq.{canal}"}, colunas="id,nome,id_seller")
    if not contas:
        return []
    contas = sorted(contas, key=lambda c: c["id"])
    ids = [c["id"] for c in contas]

    linhas = query(
        "metricas_contas",
        {
            "id_conta": f"in.({','.join(str(i) for i in ids)})",
            "and": f"(data.gte.{inicio.isoformat()},data.lte.{fim.isoformat()})",
        },
        colunas="id_conta,data," + ",".join(colunas_metricas),
    )

    somas: dict[int, dict[str, int]] = {i: {m: 0 for m in colunas_metricas} for i in ids}
    for linha in linhas:
        acumulado = somas[linha["id_conta"]]
        for m in colunas_metricas:
            acumulado[m] += linha.get(m) or 0

    return [
        ContaFunil(id_conta=c["id"], nome=c["nome"], id_seller=c["id_seller"], metricas=somas[c["id"]])
        for c in contas
    ]
