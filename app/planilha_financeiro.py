"""Leitura da aba BASE_VENDAS da planilha do financeiro (Isaac Newton2.0), sem I/O. Usado pelo WorkerFinanceiro."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

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


def ler_base_vendas(linhas: list[list], ano: int) -> list[VendaPlanilha]:
    vendas: list[VendaPlanilha] = []
    for linha in linhas[1:]:
        valores = [
            _celula(linha, 0),
            f"{_data(_celula(linha, 1)).isoformat()}T00:00:00",
            _celula(linha, 4),
            None,
            None,
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
                cliente_telefone=None,
                sdr=_celula(linha, 5),
                closer=_celula(linha, 6),
                recebimentos=[],
            )
        )
    return vendas
