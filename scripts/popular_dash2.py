"""Lê as abas de metas do Excel e devolve os dados por pessoa.

Formato das abas: linha 1 = cabeçalho, linha 2 = "Meta diária", linhas seguintes
com o dia na coluna A. Abas "Dashboard…" são ignoradas.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass


def normalizar(texto) -> str:
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", str(texto)) if not unicodedata.combining(c)
    )
    return " ".join(sem_acento.lower().split())


COLUNA_POR_CABECALHO: dict[str, str] = {
    "follow-ups": "fups",
    "numeros captados": "numeros_captados",
    "indicacoes captadas": "indicacoes",
    "indicacoes": "indicacoes",
    "ligacoes efetuadas": "ligacoes_efetuadas",
    "ligacoes realizadas": "ligacoes_realizadas",
    "inscricoes realizadas": "inscricoes_realizadas",
    "reunioes agendadas": "reunioes_agendadas",
    "ligacoes agendada": "ligacoes_agendadas",
    "ligacoes agendadas": "ligacoes_agendadas",
    "reunioes realizada": "reunioes_realizadas",
    "reunioes realizadas": "reunioes_realizadas",
    "conexoes enviadas": "conexoes_enviadas",
    "conexoes aceitas": "conexoes_aceitas",
    "abordagens": "abordagens",
    "inmails enviados": "in_mails",
}


@dataclass(frozen=True)
class Aba:
    pessoa: str
    metas: dict[str, int]
    dias: dict[int, dict[str, int | None]]


def _inteiro(valor) -> int | None:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    return int(valor)


def ler_aba(ws) -> Aba | None:
    cabecalho = next(ws.iter_rows(min_row=1, max_row=1))
    colunas = {
        indice: COLUNA_POR_CABECALHO[normalizar(c.value)]
        for indice, c in enumerate(cabecalho)
        if indice > 0 and c.value is not None and normalizar(c.value) in COLUNA_POR_CABECALHO
    }
    linha_meta = next(ws.iter_rows(min_row=2, max_row=2))
    metas = {
        coluna: v
        for indice, coluna in colunas.items()
        if (v := _inteiro(linha_meta[indice].value)) is not None
    }
    dias: dict[int, dict[str, int | None]] = {}
    for linha in ws.iter_rows(min_row=3):
        dia = _inteiro(linha[0].value)
        if dia is None or not 1 <= dia <= 31:
            continue
        valores = {coluna: _inteiro(linha[indice].value) for indice, coluna in colunas.items()}
        if any(v is not None for v in valores.values()):
            dias[dia] = valores
    return Aba(pessoa=ws.title.strip(), metas=metas, dias=dias)
