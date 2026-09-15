"""Leitura de `dash.vw_metricas` — granularidade diária, formato longo

(`data, id_user, nome, cargo, conta, metrica, valor`). Fonte única das duas
páginas: a view lê as tabelas de origem em tempo real
(`metricas_sdrs`/`metricas_closers`/`metricas_dripify`), com a data extraída
de `key_data_ref_user` e o cargo vindo de `users.id_cargo` — ver
sql/2026-09-15-view-metricas.sql.

A view já filtra por cargo, então métrica fora do conjunto do cargo não
deveria aparecer. Se aparecer, a linha é descartada aqui via
`metricas_do_cargo`, contada (não usuário-a-usuário, senão o aviso vira
ruído) e reportada em bloco pra quem monta a resposta decidir se avisa.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.fontes.banco import query
from app.metricas import metricas_do_cargo


@dataclass(frozen=True)
class TotaisCargo:
    # (id_user, metrica) -> soma de `valor` no período
    realizado: dict[tuple[int, str], int]
    # (id_user, metrica) -> quantidade de DIAS DISTINTOS com linha no período
    # (nunca confundir com o valor somado: um dia com valor 0 lançado conta
    # aqui, um dia sem linha nenhuma não conta).
    dias_com_lancamento: dict[tuple[int, str], int]
    # dia -> {metrica: soma do squad inteiro naquele dia} — todo dia do
    # intervalo pré-populado com zero, pra série de gráfico nunca ter buraco.
    serie_diaria: dict[date, dict[str, int]]
    # id_user -> contas (slugs de conta em vw_metricas) que contribuíram
    contas_por_pessoa: dict[int, list[str]]
    linhas_cargo_cruzado: int


def buscar_totais(cargo: str, ids: list[int], inicio: date, fim: date) -> TotaisCargo:
    metricas_validas = set(metricas_do_cargo(cargo))

    serie_diaria: dict[date, dict[str, int]] = {}
    dia_cursor = inicio
    while dia_cursor <= fim:
        serie_diaria[dia_cursor] = {m: 0 for m in metricas_validas}
        dia_cursor += timedelta(days=1)

    if not ids:
        return TotaisCargo({}, {}, serie_diaria, {}, 0)

    linhas = query(
        "vw_metricas",
        {
            "id_user": f"in.({','.join(str(i) for i in ids)})",
            "and": f"(data.gte.{inicio.isoformat()},data.lte.{fim.isoformat()})",
        },
        colunas="data,id_user,metrica,valor,conta",
    )

    realizado: dict[tuple[int, str], int] = {}
    dias_vistos: dict[tuple[int, str], set[date]] = {}
    contas_por_pessoa: dict[int, set[str]] = {}
    linhas_cargo_cruzado = 0

    for r in linhas:
        metrica = r.get("metrica")
        if metrica not in metricas_validas:
            linhas_cargo_cruzado += 1
            continue
        try:
            id_user = int(r["id_user"])
            dia = date.fromisoformat(str(r["data"])[:10])
            valor = int(r["valor"])
        except (KeyError, TypeError, ValueError):
            continue

        chave = (id_user, metrica)
        realizado[chave] = realizado.get(chave, 0) + valor
        dias_vistos.setdefault(chave, set()).add(dia)
        serie_diaria.setdefault(dia, {m: 0 for m in metricas_validas})
        serie_diaria[dia][metrica] = serie_diaria[dia].get(metrica, 0) + valor
        conta = r.get("conta")
        if conta:
            contas_por_pessoa.setdefault(id_user, set()).add(conta)

    return TotaisCargo(
        realizado=realizado,
        dias_com_lancamento={chave: len(dias) for chave, dias in dias_vistos.items()},
        serie_diaria=serie_diaria,
        contas_por_pessoa={id_user: sorted(contas) for id_user, contas in contas_por_pessoa.items()},
        linhas_cargo_cruzado=linhas_cargo_cruzado,
    )
