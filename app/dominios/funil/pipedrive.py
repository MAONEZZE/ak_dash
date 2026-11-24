"""Métricas do Pipedrive nos funis LinkedIn, Instagram e SDR. Regras: docs/plans/pipedrive-fonte-de-dados.md."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time
from typing import Callable

from app.config import settings
from app.dominios.funil.banco import ContaFunil
from app.fontes import pipedrive as api
from app.periodo import TZ_SP
from app.planilhas import COLUNAS_POR_TABELA

# Métricas que o Pipedrive sobrescreve em cada página de canal (o resto vem da planilha).
# Instagram fica 100% na planilha: o pipeline "Prospecção Insta" não é usado (decisão de 20/11/2026).
METRICAS_POR_CANAL: dict[str, tuple[str, ...]] = {
    "linkedin": ("numeros_captados",),
}
# owner_id do Pipedrive que é SDR → normalizar(users.nome) do SDR no dash.
DONOS_SDR: dict[int, str] = {28932026: "juca", 27369234: "jennifer"}
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


def contar(criados: list[dict], por_estagio: dict[int, list[dict]], inicio: date, fim: date) -> list[Fato]:
    """Fatos do período [inicio, fim] (datas em SP). `criados`: negócios por add_time. `por_estagio`: id do estágio → negócios que estão nele hoje."""
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

    estagios = {
        settings.pipe_id_abordados_pipeline_linkedin: ("abordagens", "linkedin"),
        settings.pipe_id_respondidos_pipeline_linkedin: ("respondidos", "linkedin"),
        settings.pipe_id_abordados_pipeline_instagram: ("abordagens", "instagram"),
        settings.pipe_id_respondidos_pipeline_instagram: ("respondidos", "instagram"),
    }
    estagios.pop(None, None)
    for id_estagio, negocios in por_estagio.items():
        if id_estagio not in estagios:
            continue
        metrica, canal = estagios[id_estagio]
        for n in negocios:
            if n.get("stage_id") != id_estagio:
                continue
            d = _data_sp(n.get("stage_change_time"))
            if not _no_periodo(d, inicio, fim):
                continue
            fatos.append(Fato(metrica, canal, n.get("owner_id"), n.get("person_id"), d))
    return fatos


def _buscar(inicio: date, fim: date) -> DadosPipedrive:
    desde = datetime.combine(inicio, time.min, tzinfo=TZ_SP)
    criados = api.negocios_criados_desde(desde)
    ids = [
        i
        for i in (
            settings.pipe_id_abordados_pipeline_linkedin,
            settings.pipe_id_respondidos_pipeline_linkedin,
            settings.pipe_id_abordados_pipeline_instagram,
            settings.pipe_id_respondidos_pipeline_instagram,
        )
        if i is not None
    ]
    por_estagio = {i: api.negocios_no_estagio(i, desde) for i in ids}
    fatos = contar(criados, por_estagio, inicio, fim)
    etiquetas = api.etiquetas_das_pessoas([f.id_pessoa for f in fatos if f.canal is not None and f.id_pessoa is not None])
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
