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
    # Um item por dia com linha em metricas_contas, em ordem de data: {"data", "metricas"}.
    serie: list[dict]


def buscar_contas(canal: str, inicio: date, fim: date, inicio_serie: date | None = None) -> list[ContaFunil]:
    """`metricas` soma de `inicio` a `fim`; `serie` começa em `inicio_serie`
    (padrão `inicio`) — no filtro de dia, a série traz os dias anteriores
    pro gráfico ter linha."""
    inicio_serie = inicio_serie or inicio
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
            "and": f"(data.gte.{inicio_serie.isoformat()},data.lte.{fim.isoformat()})",
        },
        colunas="id_conta,data," + ",".join(colunas_metricas),
    )

    somas: dict[int, dict[str, int]] = {i: {m: 0 for m in colunas_metricas} for i in ids}
    series: dict[int, list[dict]] = {i: [] for i in ids}
    for linha in sorted(linhas, key=lambda l: l["data"]):
        do_dia = {m: linha.get(m) or 0 for m in colunas_metricas}
        series[linha["id_conta"]].append({"data": linha["data"], "metricas": do_dia})
        if linha["data"] < inicio.isoformat():
            continue
        acumulado = somas[linha["id_conta"]]
        for m in colunas_metricas:
            acumulado[m] += do_dia[m]

    return [
        ContaFunil(
            id_conta=c["id"], nome=c["nome"], id_seller=c["id_seller"], metricas=somas[c["id"]], serie=series[c["id"]]
        )
        for c in contas
    ]
