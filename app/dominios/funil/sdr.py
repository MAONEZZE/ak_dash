"""Página Funil SDR: soma `metricas_funil_sdr` por SDR no período e calcula as métricas da aba "Dashboard SDR" com as metas de `metas_funil_sdr`."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from app.fontes.banco import query
from app.indicadores import calcular_indicadores
from app.metricas import nome_exibicao
from app.periodo import Periodo, dias_uteis_meta, dias_uteis_totais
from app.planilhas import COLUNAS_POR_TABELA

METRICAS = COLUNAS_POR_TABELA["metricas_funil_sdr"]
# As métricas da aba "Dashboard SDR", na ordem dela.
METRICAS_DASHBOARD = ("inscricoes_realizadas", "indicacoes", "reunioes_agendadas")


@dataclass(frozen=True)
class MetasFunilSdr:
    diarias: dict[tuple[int, str], int]  # (id_user, métrica) -> meta diária
    semanais: dict[str, int]
    mensais: dict[str, int]

    def do_time(self, periodo: Periodo, ids: list[int], metrica: str) -> int | None:
        """Dia: soma das diárias. Semana e mês: metas editáveis da aba. Ano e custom: soma das diárias × dias úteis."""
        if periodo.granularidade == "semana":
            return self.semanais.get(metrica)
        if periodo.granularidade == "mes":
            return self.mensais.get(metrica)
        diarias = [self.diarias[(i, metrica)] for i in ids if (i, metrica) in self.diarias]
        if not diarias:
            return None
        dias = 1 if periodo.granularidade == "dia" else dias_uteis_totais(periodo.inicio, periodo.fim)
        return sum(diarias) * dias


def buscar_metas_funil_sdr() -> MetasFunilSdr:
    diarias: dict[tuple[int, str], int] = {}
    semanais: dict[str, int] = {}
    mensais: dict[str, int] = {}
    for l in query("metas_funil_sdr", colunas="metrica,periodo,id_user,valor"):
        if l["periodo"] == "dia" and l["id_user"] is not None:
            diarias[(int(l["id_user"]), l["metrica"])] = int(l["valor"])
        elif l["periodo"] == "semana":
            semanais[l["metrica"]] = int(l["valor"])
        elif l["periodo"] == "mes":
            mensais[l["metrica"]] = int(l["valor"])
    return MetasFunilSdr(diarias, semanais, mensais)


def buscar_metricas_funil_sdr(inicio: date, fim: date) -> list[dict]:
    return query(
        "metricas_funil_sdr",
        {"and": f"(data.gte.{inicio.isoformat()},data.lte.{fim.isoformat()})"},
        colunas="id_user,data," + ",".join(METRICAS),
    )


def montar_resposta(
    periodo: Periodo,
    sdrs: list[dict],
    linhas: list[dict],
    metas: MetasFunilSdr,
    hoje: date,
    agora: datetime,
    expediente_inicio: time,
    expediente_fim: time,
    numeros_captados: int,
) -> dict:
    """`sdrs`: users ativos com cargo sdr ({id, nome, imagem_url}), na ordem de id.
    `numeros_captados`: soma dos funis LinkedIn + Instagram no período, topo do funil SDR."""
    ids = [s["id"] for s in sdrs]
    somas = {i: {m: 0 for m in METRICAS} for i in ids}
    series: dict[int, list[dict]] = {i: [] for i in ids}
    for l in sorted(linhas, key=lambda l: l["data"]):
        if l["id_user"] not in somas:
            continue
        do_dia = {m: l.get(m) or 0 for m in METRICAS}
        series[l["id_user"]].append({"data": l["data"], "metricas": do_dia})
        # `linhas` pode começar antes do período (série do filtro de dia): só o período soma.
        if l["data"] < periodo.inicio.isoformat():
            continue
        for m in METRICAS:
            somas[l["id_user"]][m] += do_dia[m]

    def total(m: str) -> int:
        return sum(somas[i][m] for i in ids)

    dias_uteis = dias_uteis_meta(periodo.inicio, periodo.fim, hoje)
    metricas_time = []
    for m in METRICAS_DASHBOARD:
        realizado = total(m)
        meta = metas.do_time(periodo, ids, m)
        metricas_time.append(
            {
                "metrica": m,
                "nome_exibicao": nome_exibicao(m, "sdr"),
                "meta_periodo": meta,
                "realizado": realizado,
                **calcular_indicadores(realizado, meta, periodo, dias_uteis, agora, expediente_inicio, expediente_fim),
            }
        )

    funil = {
        "numeros_captados": numeros_captados,
        "indicacoes": total("indicacoes"),
        "oportunidades": numeros_captados + total("indicacoes"),
        "abordados": total("abordagens"),
        "respondidos": total("respondidos"),
        "inscritos": total("inscricoes_realizadas"),
    }

    return {
        "periodo": {"granularidade": periodo.granularidade, "inicio": periodo.inicio.isoformat(), "fim": periodo.fim.isoformat()},
        "dias_uteis": dias_uteis,
        "metricas_time": metricas_time,
        "funil": funil,
        "sdrs": [
            {
                "id_user": str(s["id"]),
                "nome": s["nome"],
                "imagem_url": s.get("imagem_url"),
                "metricas": somas[s["id"]],
                "serie": series[s["id"]],
            }
            for s in sdrs
        ],
    }
