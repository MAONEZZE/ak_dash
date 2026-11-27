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


COLUNAS_NOTA = ["chave", "mes", "linha", "cliente", "categoria", "produto", "valor_pago", "valor_venda", "data_venda", "data_referencia", "forma_pagamento", "canal", "vendedor", "status"]


def ler_aba_nfs(linhas: list[list], ano: int, mes: int) -> list[dict]:
    indices = {normalizar(h): i for i, h in enumerate(linhas[0]) if h} if linhas else {}
    if "cliente" not in indices or "valor pago" not in indices:
        raise ValueError(f"aba NFS {mes:02d}/{ano} sem as colunas Cliente e Valor pago")

    def _cru(linha, nome):
        i = indices.get(nome)
        if i is None or i >= len(linha):
            return None
        return linha[i]

    def _texto(linha, nome):
        valor = _cru(linha, nome)
        if valor is None or not str(valor).strip():
            return None
        return str(valor).strip()

    notas = []
    for n, linha in enumerate(linhas[1:], start=2):
        cliente = _texto(linha, "cliente")
        if cliente is None:
            continue
        data = data_venda(_cru(linha, "data de venda"), ano)
        notas.append({
            "chave": f"{ano:04d}-{mes:02d}:{n}",
            "mes": f"{ano:04d}-{mes:02d}-01",
            "linha": n,
            "cliente": cliente,
            "categoria": categoria(_cru(linha, "categoria")),
            "produto": produto(_cru(linha, "produto")),
            "valor_pago": valor_monetario(_cru(linha, "valor pago")),
            "valor_venda": valor_monetario(_cru(linha, "valor da venda")),
            "data_venda": data.isoformat() if data else None,
            "data_referencia": (data or date(ano, mes, 1)).isoformat(),
            "forma_pagamento": forma_pagamento(_cru(linha, "forma de pagto")),
            "canal": _texto(linha, "origem do lead"),
            "vendedor": _texto(linha, "vendedor"),
            "status": _texto(linha, "status"),
        })
    return notas
