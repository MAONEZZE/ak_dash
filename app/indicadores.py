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


def media_necessaria(realizado: int, meta: int | None, restantes: float, unidade: str) -> dict | None:
    if not meta:
        return None
    if realizado >= meta:
        return {"valor": None, "unidade": unidade, "situacao": "meta_batida"}
    if restantes <= 0:
        situacao = "expediente_encerrado" if unidade == "hora" else "periodo_encerrado"
        return {"valor": None, "unidade": unidade, "situacao": situacao}
    valor = round((meta - realizado) / restantes, 1)
    return {"valor": valor, "unidade": unidade, "situacao": "pendente"}


def previsao(realizado: int, decorridos: int, total: int) -> float | None:
    if decorridos <= 0:
        return None
    return round(realizado / decorridos * total, 1)
