"""Leitura das abas "NFS <mês>" da planilha do financeiro, sem I/O. Usado pelo WorkerFinanceiro e por scripts/carga_financeiro.py."""
from __future__ import annotations

from app.planilhas import normalizar

MESES = ["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def mes_da_aba(titulo: str) -> int | None:
    n = normalizar(titulo)
    if n.startswith("nfs ") and n[4:] in MESES:
        return MESES.index(n[4:]) + 1
    return None


def valor_monetario(valor) -> float | None:
    if valor is None:
        return None
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return float(valor)
    t = valor.replace("R$", "").replace(" ", "").strip()
    if not t:
        return None
    t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None
