"""Leitura das abas "NFS <mês>" da planilha do financeiro, sem I/O. Usado pelo WorkerFinanceiro e por scripts/carga_financeiro.py."""
from __future__ import annotations

from datetime import date, datetime, timedelta

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


CATEGORIAS = ("venda nova", "mensalidade cliente", "upsell")
PRODUTOS = {"ativacao": "Ativação", "tracao": "Tração", "aceleracao": "Aceleração", "the green house": "The Green House"}


def categoria(valor) -> str | None:
    n = normalizar(valor) if valor else ""
    return n if n in CATEGORIAS else None


def produto(valor) -> str | None:
    if valor is None or not str(valor).strip():
        return None
    return PRODUTOS.get(normalizar(valor), str(valor).strip())


def forma_pagamento(valor) -> str:
    n = normalizar(valor) if valor else ""
    if not n:
        return "Outros"
    if "pix" in n and "cart" in n:
        return "Outros"
    if "cartao" in n or n == "link":
        return "Cartão"
    if n.startswith("pix"):
        return "PIX"
    if "boleto" in n:
        return "Boleto"
    return "Outros"


def data_venda(valor, ano: int) -> date | None:
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        data = date(1899, 12, 30) + timedelta(days=int(valor))
    elif isinstance(valor, str):
        try:
            data = datetime.strptime(valor.strip(), "%d/%m/%Y").date()
        except ValueError:
            return None
    else:
        return None
    return data if data.year == ano else None
