"""Recortes de período do dashboard de funil (LinkedIn/Instagram)."""
from __future__ import annotations

from datetime import date

from app.periodo import Periodo, resolver_periodo, semana_iso

METRICAS_DASHBOARD_FUNIL: dict[str, tuple[str, ...]] = {
    "linkedin": ("fups", "numeros_captados"),
    "instagram": ("fups", "numeros_captados", "indicacoes"),
}


def recortes_dashboard(hoje: date) -> dict[str, Periodo]:
    return {
        "diario": resolver_periodo("dia", hoje.isoformat()),
        "semanal": resolver_periodo("semana", semana_iso(hoje)),
        "mensal": resolver_periodo("mes", f"{hoje.year:04d}-{hoje.month:02d}"),
    }
