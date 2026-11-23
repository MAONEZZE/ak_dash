"""Funil de Evento: etapas do Pipedrive de uma Imersão. Regras: docs/plans/funil-evento.md."""
from __future__ import annotations

from datetime import date, datetime, timezone

from app.periodo import TZ_SP
from app.planilhas import normalizar


def data_do_evento_sp(texto: str) -> date:
    """Dia (em SP) do `event_date` do SED. Sem fuso = UTC (é como o SED grava)."""
    momento = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(TZ_SP).date()


def ids_etiquetas_do_evento(etiquetas: dict[int, str], data_evento: date) -> set[int]:
    """Etiquetas de negócio do evento: `imersao_DD/MM` ou `imersao_DD/MM/AAAA` (sem maiúsculas/acento)."""
    alvo = f"imersao_{data_evento:%d/%m}"
    aceitas = {alvo, f"{alvo}/{data_evento.year}"}
    return {i for i, texto in etiquetas.items() if normalizar(texto) in aceitas}
