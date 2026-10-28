"""Indicadores da aba Dashboard das planilhas (% de atingimento, Falta/Folga, Horas restantes, Média necessária, Previsão), sem I/O."""
from __future__ import annotations


def pct_atingimento(realizado: int, meta: int | None) -> float | None:
    if not meta:
        return None
    return round(realizado / meta * 100, 1)
