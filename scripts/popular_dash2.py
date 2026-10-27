"""Lê as abas de metas do Excel e devolve os dados por pessoa.

Formato das abas: linha 1 = cabeçalho, linha 2 = "Meta diária", linhas seguintes
com o dia na coluna A. Abas "Dashboard…" são ignoradas.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import openpyxl
import psycopg
from dotenv import load_dotenv
from psycopg import sql
from psycopg.rows import dict_row


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
    if normalizar(ws.title).startswith("dashboard"):
        return None
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
    return Aba(pessoa=re.sub(r"(?i)^linkedin\s+", "", ws.title.strip()), metas=metas, dias=dias)


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


PLANILHAS: dict[str, tuple[str, str]] = {
    "Sellers.xlsx": ("metricas_sellers", "seller"),
    "SDRs.xlsx": ("metricas_sdrs", "sdr"),
    "Closers.xlsx": ("metricas_closers", "closer"),
    "Dripify.xlsx": ("metricas_dripify", "dripify"),
}

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


def ler_planilha(caminho: Path) -> list[Aba]:
    wb = openpyxl.load_workbook(caminho, data_only=True)
    return [a for ws in wb.worksheets if (a := ler_aba(ws)) is not None]


def gravar(conn, tabela: str, cargo: str, abas: list[Aba], ano: int, mes: int) -> dict:
    colunas_tabela = COLUNAS_POR_TABELA[tabela]
    totais: dict[str, int] = {}
    n_linhas = 0
    n_metas = 0
    puladas: list[str] = []
    cur = conn.cursor(row_factory=dict_row)
    for aba in abas:
        usuarios = cur.execute("select id, nome from dash2.users").fetchall()
        u = resolver_usuario(aba.pessoa, usuarios)
        if u is None:
            puladas.append(aba.pessoa)
            continue
        cur.execute(
            "insert into dash2.user_cargos (id_user, cargo) values (%s, %s) on conflict do nothing",
            (u["id"], cargo),
        )
        for metrica, valor in aba.metas.items():
            if metrica not in colunas_tabela:
                continue
            cur.execute(
                "insert into dash2.metas (id_user, cargo, metrica, valor_diario) values (%s, %s, %s, %s) "
                "on conflict (id_user, cargo, metrica) do update set valor_diario = excluded.valor_diario, atualizado_em = now()",
                (u["id"], cargo, metrica, valor),
            )
            n_metas += 1
        for linha in linhas_metricas(aba, u["id"], u["nome"], ano, mes):
            linha = {
                k: v for k, v in linha.items() if k in colunas_tabela or k in ("id_user", "data", "key_data_ref_user")
            }
            colunas = list(linha)
            query = sql.SQL(
                "insert into {}.{} ({}) values ({}) on conflict (key_data_ref_user) do update set {}"
            ).format(
                sql.Identifier("dash2"),
                sql.Identifier(tabela),
                sql.SQL(", ").join(sql.Identifier(c) for c in colunas),
                sql.SQL(", ").join(sql.Placeholder(c) for c in colunas),
                sql.SQL(", ").join(
                    [sql.SQL("{0} = excluded.{0}").format(sql.Identifier(c)) for c in colunas if c in colunas_tabela]
                    + [sql.SQL("atualizado_em = now()")]
                ),
            )
            cur.execute(query, linha)
            n_linhas += 1
            for c in colunas:
                if c in colunas_tabela:
                    totais.setdefault(c, 0)
                    if linha[c] is not None:
                        totais[c] += linha[c]
    return {**totais, "linhas": n_linhas, "metas": n_metas, "puladas": puladas}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mes", required=True, help="mês da carga, no formato AAAA-MM")
    parser.add_argument("--pasta", default="seed", help="pasta com as planilhas (padrão: seed)")
    args = parser.parse_args(argv)

    load_dotenv()
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("DATABASE_URL não configurada no ak_dash/.env")

    ano, mes = (int(parte) for parte in args.mes.split("-"))
    pasta = Path(args.pasta)
    for nome in PLANILHAS:
        if not (pasta / nome).exists():
            raise SystemExit(f"arquivo não encontrado: {pasta / nome}")

    resultados: list[str] = []
    with psycopg.connect(dsn) as conn:
        for nome, (tabela, cargo) in PLANILHAS.items():
            abas = ler_planilha(pasta / nome)
            totais = gravar(conn, tabela, cargo, abas, ano, mes)
            for coluna, soma in totais.items():
                if coluna not in ("linhas", "metas", "puladas"):
                    resultados.append(f"{cargo}.{coluna}={soma}")
            for nome_pulada in totais["puladas"]:
                resultados.append(f"{cargo}: aba pulada (sem usuário cadastrado): {nome_pulada}")
            resultados.append(f"{cargo}: {len(abas) - len(totais['puladas'])} abas, {totais['linhas']} linhas, {totais['metas']} metas")
    print("\n".join(resultados))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
