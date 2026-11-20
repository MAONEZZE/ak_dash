"""Métricas do Pipedrive nos funis LinkedIn, Instagram e SDR. Regras: docs/plans/pipedrive-fonte-de-dados.md."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from app.config import settings
from app.periodo import TZ_SP


@dataclass(frozen=True)
class Fato:
    metrica: str  # numeros_captados | abordagens | respondidos | indicacoes
    canal: str | None  # linkedin | instagram; None em indicacoes
    id_dono: int | None
    id_pessoa: int | None
    data: str  # AAAA-MM-DD no fuso de SP


def _data_sp(texto: str | None) -> str | None:
    if not texto:
        return None
    return datetime.fromisoformat(texto.replace("Z", "+00:00")).astimezone(TZ_SP).date().isoformat()


def contar(criados: list[dict], por_estagio: dict[int, list[dict]], inicio: date, fim: date) -> list[Fato]:
    """Fatos do período [inicio, fim] (datas em SP). `criados`: negócios por add_time. `por_estagio`: id do estágio → negócios que estão nele hoje."""
    fatos: list[Fato] = []
    for n in criados:
        d = _data_sp(n.get("add_time"))
        if d is None or not (inicio.isoformat() <= d <= fim.isoformat()):
            continue
        etiquetas = n.get("label_ids") or []
        dono, pessoa = n.get("owner_id"), n.get("person_id")
        if settings.pipe_id_etiqueta_negocio_linkedin is not None and settings.pipe_id_etiqueta_negocio_linkedin in etiquetas:
            fatos.append(Fato("numeros_captados", "linkedin", dono, pessoa, d))
        if settings.pipe_id_pipeline_instagram is not None and n.get("pipeline_id") == settings.pipe_id_pipeline_instagram:
            fatos.append(Fato("numeros_captados", "instagram", dono, pessoa, d))
    return fatos
