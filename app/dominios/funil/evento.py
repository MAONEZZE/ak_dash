"""Funil de Evento: etapas do Pipedrive de uma Imersão. Regras: docs/plans/funil-evento.md."""
from __future__ import annotations

from datetime import date, datetime, timezone

from app.periodo import TZ_SP


def data_do_evento_sp(texto: str) -> date:
    """Dia (em SP) do `event_date` do SED. Sem fuso = UTC (é como o SED grava)."""
    momento = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(TZ_SP).date()
