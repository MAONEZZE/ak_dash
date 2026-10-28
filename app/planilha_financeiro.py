"""Leitura da aba BASE_VENDAS da planilha do financeiro (Isaac Newton2.0), sem I/O. Usado pelo WorkerFinanceiro."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.planilhas import normalizar

# Decisão de 2026-10-28: Jonathan é id 2, Mariana é id 5, Nathan foi removido (None).
APELIDOS: dict[str, int | None] = {
    "jonny": 2,
    "jennifer": 4,
    "jacob": 1,
    "alex": 3,
    "thalyson": 8,
    "mary": 5,
    "nathan": None,
}

COLUNAS_VENDA: list[str] = [
    "id_planilha",
    "data_venda",
    "canal",
    "user_sdr",
    "user_closer",
    "produto",
    "valor_bruto_contrato",
    "condicao_pagamento",
    "valor_entrada",
    "metodo_pagamento",
    "num_parcelas",
    "imposto",
    "taxa",
    "liquido_entrada",
    "valor_pgto_2",
    "forma_pgto_2",
    "num_parcelas_pgto_2",
    "taxa_pgto_2",
    "liquido_pgto_2",
    "observacoes",
]


@dataclass(frozen=True)
class VendaPlanilha:
    venda: dict
    cliente_nome: str | None
    cliente_telefone: int | None
    sdr: str | None
    closer: str | None
    recebimentos: list[dict]


def _celula(linha: list, indice: int):
    if indice >= len(linha):
        return None
    valor = linha[indice]
    if isinstance(valor, str) and not valor.strip():
        return None
    return valor


def _data(valor) -> date:
    if isinstance(valor, str):
        return datetime.strptime(valor.strip(), "%d/%m/%Y").date()
    return date(1899, 12, 30) + timedelta(days=int(valor))


def _inteiro_ou_none(valor) -> int | None:
    return None if valor is None else int(valor)


def _telefone(valor) -> int | None:
    if valor is None:
        return None
    texto = str(int(valor)) if isinstance(valor, (int, float)) else str(valor)
    digitos = re.sub(r"\D", "", texto)
    if not digitos or int(digitos) == 0:
        return None
    return int(digitos)


def ler_base_vendas(linhas: list[list], ano: int) -> list[VendaPlanilha]:
    if (
        not linhas
        or normalizar(_celula(linhas[0], 0) or "") != "id"
        or normalizar(_celula(linhas[0], 1) or "") != "data da venda"
    ):
        raise ValueError("BASE_VENDAS fora do formato esperado (A1=ID, B1=Data da Venda)")
    vendas: list[VendaPlanilha] = []
    for linha in linhas[1:]:
        if _celula(linha, 0) is None:
            continue
        sdr = _celula(linha, 5)
        closer = _celula(linha, 6)
        valores = [
            int(_celula(linha, 0)),
            f"{_data(_celula(linha, 1)).isoformat()}T00:00:00",
            _celula(linha, 4),
            APELIDOS.get(normalizar(sdr)) if sdr else None,
            APELIDOS.get(normalizar(closer)) if closer else None,
            _celula(linha, 7),
            _celula(linha, 8),
            _celula(linha, 9),
            _celula(linha, 10),
            _celula(linha, 11),
            _inteiro_ou_none(_celula(linha, 12)),
            _celula(linha, 13),
            _celula(linha, 14),
            _celula(linha, 15),
            _celula(linha, 16),
            _celula(linha, 17),
            _inteiro_ou_none(_celula(linha, 18)),
            _celula(linha, 19),
            _celula(linha, 20),
            _celula(linha, 21),
        ]
        venda = dict(zip(COLUNAS_VENDA, valores))
        vendas.append(
            VendaPlanilha(
                venda=venda,
                cliente_nome=_celula(linha, 2),
                cliente_telefone=_telefone(_celula(linha, 3)),
                sdr=sdr,
                closer=closer,
                recebimentos=[],
            )
        )
    return vendas
