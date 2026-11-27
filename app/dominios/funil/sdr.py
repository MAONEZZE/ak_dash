"""Página Funil SDR: soma `metricas_funil_sdr` por SDR no período e calcula as métricas da aba "Dashboard SDR" com as metas de `metas_funil_sdr`."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.config import settings
from app.dominios.funil.evento import data_do_evento_sp
from app.fontes import pipedrive as api
from app.fontes import sed, supabase
from app.indicadores import calcular_indicadores
from app.metricas import nome_exibicao
from app.periodo import TZ_SP, Periodo, dias_uteis_meta, dias_uteis_totais
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


def dias_da_janela_do_evento(primeira_inscricao: date | None, data_evento: date) -> list[date]:
    """Dias de inscrição do evento: da primeira inscrição até a véspera, sem domingos. Sem primeira inscrição: `[]`."""
    if primeira_inscricao is None:
        return []
    dias = (data_evento - primeira_inscricao).days
    return [d for d in (primeira_inscricao + timedelta(days=n) for n in range(dias)) if d.weekday() != 6]


def serie_do_evento(dias: list[date], inscricoes_por_dia: dict[date, int], meta_diaria: int | None, hoje: date) -> list[dict]:
    """Série do gráfico do evento por dia da janela. `acumulado`: inscrições da primeira data da janela até o dia,
    só até hoje. `ritmo`: acumulado do dia anterior da janela + meta diária (sem meta, `None`)."""

    def acumulado(d: date) -> int:
        return sum(n for x, n in inscricoes_por_dia.items() if dias[0] <= x <= d)

    pontos: list[dict] = []
    for i, d in enumerate(dias):
        ritmo = None
        if meta_diaria is not None:
            if i == 0:
                ritmo = meta_diaria
            elif dias[i - 1] <= hoje:
                ritmo = acumulado(dias[i - 1]) + meta_diaria
            else:
                ritmo = pontos[i - 1]["ritmo"] + meta_diaria
        pontos.append({"data": d.isoformat(), "acumulado": acumulado(d) if d <= hoje else None, "ritmo": ritmo})
    return pontos


def previsao_ate_o_evento(dias: list[date], acumulado_hoje: int, hoje: date, meta_diaria: int | None) -> dict | None:
    """Previsão do total da janela: média por dia decorrido × dias da janela. Sem dias: `None`.
    Janela encerrada (nenhum dia decorrido): previsão = realizado. Meta = diária × dias da janela."""
    if not dias:
        return None
    decorridos = sum(d <= hoje for d in dias)
    total = len(dias)
    valor = round(acumulado_hoje / decorridos * total) if decorridos > 0 else acumulado_hoje
    meta = meta_diaria * total if meta_diaria else None
    pct_meta = round(valor / meta * 100, 1) if meta else None
    return {"valor": valor, "meta": meta, "pct_meta": pct_meta}


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


def data_primeira_inscricao(id_evento: str) -> date | None:
    """Dia (em SP) da 1ª inscrição approved/pending do evento. Sem inscrição: `None`."""
    linhas = sed.ler_primeira_inscricao(id_evento)
    if not linhas:
        return None
    return data_do_evento_sp(linhas[0]["created_at"])


def buscar_ligacoes_sdr(inicio: date, fim: date) -> dict[int, int]:
    """Ligações realizadas por SDR (id_user) no período, da planilha `metricas_sdrs`."""
    somas: dict[int, int] = {}
    for l in supabase.ler_metricas_planilha("metricas_sdrs", inicio, fim, ["ligacoes_realizadas"]):
        id_user = int(l["id_user"])
        somas[id_user] = somas.get(id_user, 0) + (l["ligacoes_realizadas"] or 0)
    return somas


def contar_negocios_sdr(negocios: list[dict], id_dash_por_dono: dict[int, int]) -> dict[int, int]:
    """Negócios por SDR (id_user do dash): os de dono em `id_dash_por_dono`, cada um uma vez."""
    contagem = {i: 0 for i in id_dash_por_dono.values()}
    for n in negocios:
        id_user = id_dash_por_dono.get(n.get("owner_id"))
        if id_user is not None:
            contagem[id_user] += 1
    return contagem


def contar_inscricoes_pipedrive(
    entradas: list[dict], id_dash_por_dono: dict[int, int], hoje: date
) -> dict[int, dict[str, int]]:
    """Inscrições por SDR: negócios que entraram no estágio Inscrito, cada um uma vez (na primeira entrada), pelo dono
    atual. `mes`: todas as `entradas` (já filtradas no mês); `hoje`: as do dia `hoje` em SP."""
    contagem = {i: {"mes": 0, "hoje": 0} for i in id_dash_por_dono.values()}
    vistos: set[int] = set()
    for e in sorted(entradas, key=lambda e: e["entrou_em"]):
        id_user = id_dash_por_dono.get(e.get("id_dono"))
        if id_user is None or e["id_deal"] in vistos:
            continue
        vistos.add(e["id_deal"])
        contagem[id_user]["mes"] += 1
        if datetime.fromisoformat(e["entrou_em"].replace("Z", "+00:00")).astimezone(TZ_SP).date() == hoje:
            contagem[id_user]["hoje"] += 1
    return contagem


def mes_do_ranking(periodo: Periodo) -> tuple[date, date]:
    """Mês do card de ranking: o que contém o fim do filtro (o run rate é sempre do mês)."""
    inicio = periodo.fim.replace(day=1)
    proximo = (inicio + timedelta(days=32)).replace(day=1)
    return inicio, proximo - timedelta(days=1)


def janela_da_meta(mes: tuple[date, date], data_evento: date | None) -> tuple[date, date] | None:
    """Janela da meta do ranking: do 1º dia do mês até a véspera do evento, no máximo até o fim do mês. Sem evento: o mês. Véspera antes do mês: `None`."""
    fim = mes[1] if data_evento is None else min(mes[1], data_evento - timedelta(days=1))
    if fim < mes[0]:
        return None
    return mes[0], fim


def inscricoes_do_mes(linhas: list[dict], ids: list[int], hoje: date) -> dict[int, dict[str, int]]:
    """Inscrições por SDR (planilha → metricas_funil_sdr): `mes` = soma das `linhas` (já filtradas no mês); `hoje` = as da linha de `hoje`. SDR fora de `ids` é ignorado."""
    contagem = {i: {"mes": 0, "hoje": 0} for i in ids}
    for l in linhas:
        id_user = int(l["id_user"])
        if id_user not in contagem:
            continue
        n = l["inscricoes_realizadas"] or 0
        contagem[id_user]["mes"] += n
        if l["data"] == hoje.isoformat():
            contagem[id_user]["hoje"] += n
    return contagem


def _limites_sp(inicio: date, fim: date) -> tuple[datetime, datetime]:
    return datetime.combine(inicio, time.min, tzinfo=TZ_SP), datetime.combine(fim + timedelta(days=1), time.min, tzinfo=TZ_SP)


def buscar_negocios_sdr(inicio: date, fim: date, id_dash_por_dono: dict[int, int]) -> dict[int, int]:
    """Negócios do Pipedrive criados em [inicio, fim] (SP) de que cada SDR é dono.
    Pipedrive fora do ar: `{}` + aviso na tela (ver `api.ou_vazio`)."""
    desde, ate = _limites_sp(inicio, fim)

    def calcular() -> dict[int, int]:
        negocios = [
            n for n in api.negocios_criados_desde(desde) if datetime.fromisoformat(n["add_time"].replace("Z", "+00:00")) < ate
        ]
        return contar_negocios_sdr(negocios, id_dash_por_dono)

    return api.ou_vazio(calcular, {}, "Pipedrive indisponível — negócios dos SDRs zerados")


def buscar_inscricoes_pipedrive(
    inicio: date, fim: date, id_dash_por_dono: dict[int, int], hoje: date
) -> dict[int, dict[str, int]]:
    """Entradas no estágio Inscrito (histórico do WorkerPipedrive) em [inicio, fim], por SDR. Sem o estágio configurado: `{}`."""
    estagio = settings.pipe_id_inscrito_pipeline_principal
    if estagio is None:
        return {}
    desde, ate = _limites_sp(inicio, fim)
    return contar_inscricoes_pipedrive(supabase.ler_entradas_estagio([estagio], desde, ate), id_dash_por_dono, hoje)


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


def montar_resposta_pagina_sdr(
    periodo: Periodo,
    sdrs: list[dict],
    linhas_periodo: list[dict],
    linhas_janela: list[dict],
    ligacoes: dict[int, int],
    metas: MetasFunilSdr,
    evento: dict | None,
    dias: list[date],
    hoje: date,
    mes_ranking: tuple[date, date] | None = None,
    negocios: dict[int, int] | None = None,
    inscricoes_pipedrive: dict[int, dict[str, int]] | None = None,
    inscritos_sed_mes: int | None = None,
) -> dict:
    """Cards, ranking, previsão e série do evento por SDR. `dias`: janela de inscrição do evento (vazia sem evento).
    Card "Ranking SDR" (mês `mes_ranking`): `negocios` e `inscricoes_pipedrive` por SDR (fora deles, zerado), contra a
    meta mensal de inscrições do SDR; `inscritos_sed_mes` vai no badge."""
    negocios = negocios or {}
    inscricoes_pipedrive = inscricoes_pipedrive or {}
    periodo_mes = Periodo("mes", *mes_ranking) if mes_ranking else None
    ids = [s["id"] for s in sdrs]
    inscricoes = {i: 0 for i in ids}
    for l in linhas_periodo:
        id_user = int(l["id_user"])
        if id_user in inscricoes:
            inscricoes[id_user] += l["inscricoes_realizadas"] or 0

    por_dia: dict[int, dict[date, int]] = {i: {} for i in ids}
    for l in linhas_janela:
        id_user = int(l["id_user"])
        if id_user in por_dia:
            d = date.fromisoformat(l["data"])
            por_dia[id_user][d] = por_dia[id_user].get(d, 0) + (l["inscricoes_realizadas"] or 0)

    def acumulado_hoje(i: int) -> int:
        if not dias:
            return 0
        ate = min(hoje, dias[-1])
        return sum(n for d, n in por_dia[i].items() if dias[0] <= d <= ate)

    ranking = ranquear_pagina_sdr(
        [{"id": i, "ligacoes": ligacoes.get(i, 0), "inscricoes": inscricoes[i]} for i in ids]
    )
    por_id = {s["id"]: s for s in sdrs}
    cards = []
    for r in ranking:
        i = r["id"]
        meta_diaria = metas.diarias.get((i, "inscricoes_realizadas"))
        cards.append(
            {
                "id_user": str(i),
                "nome": por_id[i]["nome"],
                "imagem_url": por_id[i].get("imagem_url"),
                "inscricoes": inscricoes[i],
                "meta_inscricoes": metas.da_pessoa(periodo, ids, i, "inscricoes_realizadas"),
                "ligacoes": ligacoes.get(i, 0),
                "pontuacao": r["pontuacao"],
                "posicao": r["posicao"],
                "meta_diaria": meta_diaria,
                "previsao": previsao_ate_o_evento(dias, acumulado_hoje(i), hoje, meta_diaria),
                "serie_evento": serie_do_evento(dias, por_dia[i], meta_diaria, hoje),
                "ranking_mes": {
                    "negocios": negocios.get(i, 0),
                    "inscricoes": inscricoes_pipedrive.get(i, {}).get("mes", 0),
                    "inscricoes_hoje": inscricoes_pipedrive.get(i, {}).get("hoje", 0),
                    "meta": metas.da_pessoa(periodo_mes, ids, i, "inscricoes_realizadas") if periodo_mes else None,
                },
            }
        )

    return {
        "periodo": {"granularidade": periodo.granularidade, "inicio": periodo.inicio.isoformat(), "fim": periodo.fim.isoformat()},
        "evento": evento,
        "janela": {"inicio": dias[0].isoformat(), "fim": dias[-1].isoformat()} if dias else None,
        "mes_ranking": {"inicio": mes_ranking[0].isoformat(), "fim": mes_ranking[1].isoformat()} if mes_ranking else None,
        "inscritos_sed_mes": inscritos_sed_mes,
        "sdrs": cards,
    }
