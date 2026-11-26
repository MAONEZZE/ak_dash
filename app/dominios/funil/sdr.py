"""Página Funil SDR: soma `metricas_funil_sdr` por SDR no período e calcula as métricas da aba "Dashboard SDR" com as metas de `metas_funil_sdr`."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.fontes import supabase
from app.indicadores import calcular_indicadores
from app.metricas import nome_exibicao
from app.periodo import Periodo, dias_uteis_meta, dias_uteis_totais
from app.pontuacao import atribuir_ranking
from app.planilhas import COLUNAS_POR_TABELA

METRICAS = COLUNAS_POR_TABELA["metricas_funil_sdr"]
# As métricas da aba "Dashboard SDR", na ordem dela.
METRICAS_DASHBOARD = ("inscricoes_realizadas", "indicacoes", "reunioes_agendadas")
# Só a página SDR (decisão de 2026-11-26); Geral/Time usam app/pontuacao.py.
PESOS_RANKING_PAGINA_SDR = {"ligacoes": 8, "inscricoes": 10}


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

    def da_pessoa(self, periodo: Periodo, ids: list[int], id_user: int, metrica: str) -> int | None:
        """Parte do SDR na meta do time, na proporção da meta diária dele entre as do time
        (dia/ano/custom: diária × dias úteis; semana/mês: fatia da meta editável). Sem diária, `None`."""
        diaria = self.diarias.get((id_user, metrica))
        soma = sum(self.diarias.get((i, metrica), 0) for i in ids)
        do_time = self.do_time(periodo, ids, metrica)
        if not diaria or not soma or do_time is None:
            return None
        return round(do_time * diaria / soma)


DIAS_DE_INSCRICAO_NA_SEMANA = 6  # domingo não conta


def meta_diaria_inscricoes(capacidade: int | None, inscritos_ate_ontem: int, data_evento: date, hoje: date) -> int | None:
    """Meta do dia do velocímetro de inscrições: o que falta para a capacidade (inscritos até ontem, fixa no dia)
    dividido pelos dias de hoje até a véspera do evento, sem domingos, arredondado para cima.
    Sem capacidade ou sem dia de inscrição até o evento: `None`. Capacidade já atingida: 0."""
    dias = sum(1 for n in range((data_evento - hoje).days) if (hoje + timedelta(days=n)).weekday() != 6)
    if capacidade is None or dias <= 0:
        return None
    falta = capacidade - inscritos_ate_ontem
    if falta <= 0:
        return 0
    return -(-falta // dias)


def meta_velocimetro_inscricoes(
    granularidade: str, capacidade: int | None, inscritos_ate_ontem: int, data_evento: date, hoje: date
) -> int | None:
    """Meta do velocímetro de inscrições do evento por filtro: dia = meta diária; semana = diária × 6,
    limitada ao que falta para a capacidade; mês, ano e custom = a capacidade."""
    if granularidade not in ("dia", "semana"):
        return capacidade
    diaria = meta_diaria_inscricoes(capacidade, inscritos_ate_ontem, data_evento, hoje)
    if diaria is None or granularidade == "dia":
        return diaria
    return max(0, min(diaria * DIAS_DE_INSCRICAO_NA_SEMANA, capacidade - inscritos_ate_ontem))


def buscar_metas_funil_sdr() -> MetasFunilSdr:
    """Diária: linha "Meta diária" da aba de cada SDR (tabela `metas`), a mesma das páginas Geral e Time —
    a tabela "Vendedor" do Dashboard SDR divergia dela (inscrições 7 x 4, 25/11). Semana e mês: metas editáveis do Dashboard SDR."""
    diarias = {
        (int(l["id_user"]), l["metrica"]): int(l["valor_diario"])
        for l in supabase.ler_metas_do_cargo("sdr")
        if l.get("id_user") is not None and l.get("valor_diario") is not None
    }
    semanais: dict[str, int] = {}
    mensais: dict[str, int] = {}
    for l in supabase.ler_metas_funil_sdr():
        if l["periodo"] == "semana":
            semanais[l["metrica"]] = int(l["valor"])
        elif l["periodo"] == "mes":
            mensais[l["metrica"]] = int(l["valor"])
    return MetasFunilSdr(diarias, semanais, mensais)


def buscar_metricas_funil_sdr(inicio: date, fim: date) -> list[dict]:
    return supabase.ler_metricas_funil_sdr(inicio, fim)


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
                # Cards de inscrições por SDR (fundo pisca na cor do atingimento).
                "meta_inscricoes": metas.da_pessoa(periodo, ids, s["id"], "inscricoes_realizadas"),
                "serie": series[s["id"]],
            }
            for s in sdrs
        ],
    }


def ranquear_pagina_sdr(sdrs: list[dict]) -> list[dict]:
    """Pontuação e posição (dense rank) do ranking da página SDR. Não altera a lista de entrada."""
    novas = [
        {**s, "pontuacao": sum((s.get(m) or 0) * peso for m, peso in PESOS_RANKING_PAGINA_SDR.items())}
        for s in sdrs
    ]
    atribuir_ranking(novas, "pontuacao")
    return sorted(novas, key=lambda s: (s["posicao"], s["id"]))
