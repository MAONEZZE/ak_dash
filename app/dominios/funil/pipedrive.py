"""Métricas do Pipedrive nos funis LinkedIn, Instagram e SDR. Regras: docs/plans/pipedrive-fonte-de-dados.md."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from typing import Callable

from app.config import settings
from app.dominios.funil.banco import ContaFunil
from app.fontes import pipedrive as api
from app.fontes import supabase
from app.fontes.banco import em_paralelo
from app.periodo import TZ_SP
from app.planilhas import COLUNAS_POR_TABELA

# Métricas que o Pipedrive sobrescreve em cada página de canal (o resto vem da planilha).
# Instagram fica 100% na planilha: o pipeline "Prospecção Insta" não é usado (decisão de 20/11/2026).
METRICAS_POR_CANAL: dict[str, tuple[str, ...]] = {
    "linkedin": ("numeros_captados",),
}
# Colunas de metricas_funil_sdr que vêm do Pipedrive.
METRICAS_SDR = ("abordagens", "respondidos", "indicacoes")


@dataclass(frozen=True)
class Fato:
    metrica: str  # numeros_captados | abordagens | respondidos | indicacoes
    canal: str | None  # linkedin | instagram; None em indicacoes
    id_dono: int | None
    id_pessoa: int | None
    data: str  # AAAA-MM-DD no fuso de SP


@dataclass(frozen=True)
class DadosPipedrive:
    fatos: list[Fato]
    etiquetas_por_pessoa: dict[int, tuple[int, ...]]


VAZIO = DadosPipedrive([], {})


def _data_sp(texto: str | None) -> str | None:
    if not texto:
        return None
    return datetime.fromisoformat(texto.replace("Z", "+00:00")).astimezone(TZ_SP).date().isoformat()


def _no_periodo(d: str | None, inicio: date, fim: date) -> bool:
    return d is not None and inicio.isoformat() <= d <= fim.isoformat()


def contar(criados: list[dict], inicio: date, fim: date) -> list[Fato]:
    """Fatos dos negócios criados no período [inicio, fim] (datas em SP), por add_time: números captados e indicações."""
    fatos: list[Fato] = []
    for n in criados:
        d = _data_sp(n.get("add_time"))
        if not _no_periodo(d, inicio, fim):
            continue
        etiquetas = n.get("label_ids") or []
        dono, pessoa = n.get("owner_id"), n.get("person_id")
        if settings.pipe_id_etiqueta_negocio_linkedin is not None and settings.pipe_id_etiqueta_negocio_linkedin in etiquetas:
            fatos.append(Fato("numeros_captados", "linkedin", dono, pessoa, d))
        if settings.pipe_id_pipeline_instagram is not None and n.get("pipeline_id") == settings.pipe_id_pipeline_instagram:
            fatos.append(Fato("numeros_captados", "instagram", dono, pessoa, d))
        if settings.pipe_id_etiqueta_negocio_indicacao is not None and settings.pipe_id_etiqueta_negocio_indicacao in etiquetas:
            fatos.append(Fato("indicacoes", None, dono, pessoa, d))
    return fatos


def _estagios() -> dict[int, tuple[str, str]]:
    """Id do estágio no Pipedrive -> (métrica, canal), só dos configurados."""
    estagios = {
        settings.pipe_id_abordados_pipeline_principal: ("abordagens", "linkedin"),
        settings.pipe_id_respondidos_pipeline_principal: ("respondidos", "linkedin"),
        settings.pipe_id_abordados_pipeline_instagram: ("abordagens", "instagram"),
        settings.pipe_id_respondidos_pipeline_instagram: ("respondidos", "instagram"),
    }
    estagios.pop(None, None)
    return estagios


def contar_entradas(entradas: list[dict], inicio: date, fim: date) -> list[Fato]:
    """Abordagens: cada negócio uma vez, na primeira entrada no período em Abordados ou Respondido do canal.
    Respondidos: cada entrada no período em Respondido (data em SP), mesmo que o negócio já tenha avançado.
    `entradas` vem do histórico gravado pelo WorkerPipedrive."""
    estagios = _estagios()
    fatos: list[Fato] = []
    abordados_vistos: set[tuple[int, str]] = set()
    for e in sorted(entradas, key=lambda e: (e["entrou_em"], e["id_deal"])):
        if e["id_estagio"] not in estagios:
            continue
        d = _data_sp(e["entrou_em"])
        if not _no_periodo(d, inicio, fim):
            continue
        metrica, canal = estagios[e["id_estagio"]]
        if (e["id_deal"], canal) not in abordados_vistos:
            abordados_vistos.add((e["id_deal"], canal))
            fatos.append(Fato("abordagens", canal, e.get("id_dono"), e.get("id_pessoa"), d))
        if metrica == "respondidos":
            fatos.append(Fato("respondidos", canal, e.get("id_dono"), e.get("id_pessoa"), d))
    return fatos


def _buscar(inicio: date, fim: date) -> DadosPipedrive:
    desde = datetime.combine(inicio, time.min, tzinfo=TZ_SP)
    ate = datetime.combine(fim + timedelta(days=1), time.min, tzinfo=TZ_SP)
    criados, entradas = em_paralelo(
        lambda: api.negocios_criados_desde(desde),
        lambda: supabase.ler_entradas_estagio(list(_estagios()), desde, ate) if _estagios() else [],
    )
    fatos = contar(criados, inicio, fim) + contar_entradas(entradas, inicio, fim)
    # Só os números captados vão para a conta pela etiqueta da pessoa (`aplicar_em_contas`).
    etiquetas = api.etiquetas_das_pessoas(
        [f.id_pessoa for f in fatos if f.metrica == "numeros_captados" and f.id_pessoa is not None]
    )
    return DadosPipedrive(fatos, etiquetas)


def buscar_pipedrive(inicio: date, fim: date) -> DadosPipedrive:
    """Tudo que os funis precisam do Pipedrive para [inicio, fim]. Pipedrive fora do ar ou sem configuração: VAZIO + falha 'pipedrive' registrada (aviso na tela, sem cache)."""
    return api.ou_vazio(lambda: _buscar(inicio, fim), VAZIO, "Pipedrive indisponível — métricas do Pipedrive zeradas")


def aplicar_em_contas(
    contas: list[ContaFunil], dados: DadosPipedrive, canal: str, inicio: date, etiqueta_da_conta: Callable[[str], int | None]
) -> tuple[list[ContaFunil], dict[str, int]]:
    """Troca as métricas do Pipedrive do canal em cada conta (soma e série) e devolve o que não tem conta em `sem_conta` (só dias a partir de `inicio`). Não altera `contas`."""
    colunas = COLUNAS_POR_TABELA["metricas_contas"]
    metricas = METRICAS_POR_CANAL[canal]
    zerar = {m: 0 for m in metricas}

    somas = {c.id_conta: {**c.metricas, **zerar} for c in contas}
    series = {c.id_conta: {d["data"]: {**d["metricas"], **zerar} for d in c.serie} for c in contas}
    sem_conta = {k: 0 for k in colunas}
    etiquetas = [(c.id_conta, etiqueta_da_conta(c.nome)) for c in contas]

    for f in dados.fatos:
        if f.canal != canal or f.metrica not in metricas:
            continue
        da_pessoa = dados.etiquetas_por_pessoa.get(f.id_pessoa, ())
        conta = next((i for i, e in etiquetas if e is not None and e in da_pessoa), None)
        no_periodo = f.data >= inicio.isoformat()
        if conta is None:
            if no_periodo:
                sem_conta[f.metrica] += 1
            continue
        series[conta].setdefault(f.data, {k: 0 for k in colunas})[f.metrica] += 1
        if no_periodo:
            somas[conta][f.metrica] += 1

    return (
        [
            replace(c, metricas=somas[c.id_conta], serie=[{"data": d, "metricas": series[c.id_conta][d]} for d in sorted(series[c.id_conta])])
            for c in contas
        ],
        sem_conta,
    )


def linhas_sdr(dados: DadosPipedrive, id_dash_por_dono: dict[int, int]) -> list[dict]:
    """Linhas no formato de metricas_funil_sdr (id_user, data + METRICAS_SDR), uma por SDR e dia, só de donos em `id_dash_por_dono`."""
    linhas: dict[tuple[str, int], dict] = {}
    for f in dados.fatos:
        if f.metrica in METRICAS_SDR and f.id_dono in id_dash_por_dono:
            id_user = id_dash_por_dono[f.id_dono]
            linha = linhas.setdefault((f.data, id_user), {"id_user": id_user, "data": f.data, **{m: 0 for m in METRICAS_SDR}})
            linha[f.metrica] += 1
    return [linhas[k] for k in sorted(linhas)]
