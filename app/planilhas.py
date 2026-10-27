"""Leitura das abas das planilhas de métricas (Sellers, SDRs, Closers, Dripify), sem I/O. Usado pelos workers e por scripts/popular_dash2.py."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date


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


def _celula(linha: list, indice: int):
    return linha[indice] if indice < len(linha) else None


def ler_linhas(titulo: str, linhas: list[list]) -> Aba | None:
    if normalizar(titulo).startswith("dashboard"):
        return None
    if not linhas:
        return None
    cabecalho = linhas[0]
    colunas = {
        indice: COLUNA_POR_CABECALHO[normalizar(c)]
        for indice, c in enumerate(cabecalho)
        if indice > 0 and c is not None and normalizar(c) in COLUNA_POR_CABECALHO
    }
    linha_meta = linhas[1] if len(linhas) > 1 else []
    metas = {
        coluna: v
        for indice, coluna in colunas.items()
        if (v := _inteiro(_celula(linha_meta, indice))) is not None
    }
    dias: dict[int, dict[str, int | None]] = {}
    for linha in linhas[2:]:
        dia = _inteiro(_celula(linha, 0))
        if dia is None or not 1 <= dia <= 31:
            continue
        valores = {coluna: _inteiro(_celula(linha, indice)) for indice, coluna in colunas.items()}
        if any(v is not None for v in valores.values()):
            dias[dia] = valores
    return Aba(pessoa=re.sub(r"(?i)^linkedin\s+", "", titulo.strip()), metas=metas, dias=dias)


def linhas_metricas(aba: Aba, id_user: int, nome_user: str, ano: int, mes: int) -> list[dict]:
    linhas: list[dict] = []
    for d, valores in sorted(aba.dias.items()):
        try:
            dia = date(ano, mes, d)
        except ValueError:
            continue
        linhas.append(
            {
                "id_user": id_user,
                "data": dia,
                "key_data_ref_user": f"{dia:%d/%m/%Y}-{nome_user.lower()}",
                **valores,
            }
        )
    return linhas


def resolver_usuario(nome_aba: str, usuarios: list[dict]) -> dict | None:
    alvo = normalizar(nome_aba)
    return next((u for u in sorted(usuarios, key=lambda u: u["id"]) if normalizar(u["nome"]) == alvo), None)


COLUNAS_POR_TABELA: dict[str, list[str]] = {
    "metricas_sellers": ["fups", "numeros_captados", "indicacoes"],
    "metricas_sdrs": ["ligacoes_efetuadas", "ligacoes_realizadas", "inscricoes_realizadas", "indicacoes", "reunioes_agendadas"],
    "metricas_closers": [
        "ligacoes_agendadas",
        "ligacoes_realizadas",
        "reunioes_agendadas",
        "reunioes_realizadas",
        "indicacoes",
        "inscricoes_realizadas",
    ],
    "metricas_dripify": ["conexoes_enviadas", "conexoes_aceitas", "abordagens", "in_mails", "fups", "numeros_captados"],
}
