"""Indicadores da aba Dashboard das planilhas (% de atingimento, Falta/Folga, Horas restantes, Média necessária, Previsão), sem I/O."""
from __future__ import annotations


def pct_atingimento(realizado: int, meta: int | None) -> float | None:
    if not meta:
        return None
    return round(realizado / meta * 100, 1)


def falta_folga(realizado: int, meta: int | None) -> dict | None:
    if not meta:
        return None
    if realizado < meta:
        return {"tipo": "falta", "valor": meta - realizado}
    return {"tipo": "folga", "valor": realizado - meta}
