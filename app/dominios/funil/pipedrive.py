"""Métricas do Pipedrive nos funis LinkedIn, Instagram e SDR. Regras: docs/plans/pipedrive-fonte-de-dados.md."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time

from app.config import settings
from app.fontes import pipedrive as api
from app.fontes.banco import registrar_falha
from app.periodo import TZ_SP

logger = logging.getLogger(__name__)


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


def buscar_pipedrive(inicio: date, fim: date) -> DadosPipedrive:
    """Tudo que os funis precisam do Pipedrive para [inicio, fim]. Pipedrive fora do ar ou sem configuração: VAZIO + falha 'pipedrive' registrada (aviso na tela, sem cache)."""
    desde = datetime.combine(inicio, time.min, tzinfo=TZ_SP)
    try:
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
    except api.PipedriveIndisponivel:
        logger.warning("Pipedrive indisponível — métricas do Pipedrive zeradas", exc_info=True)
        registrar_falha("pipedrive")
        return VAZIO
    return DadosPipedrive(fatos, etiquetas)
