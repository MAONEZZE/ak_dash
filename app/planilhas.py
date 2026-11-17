"""Leitura das abas das planilhas de métricas (Sellers, SDRs, Closers, funis LinkedIn/Instagram), sem I/O. Usado pelos workers."""
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
    "mensagem de abordagem": "mensagens_abordagem",
    "follow de abordagem": "follows_abordagem",
    "respondidos": "respondidos",
    "responderam": "respondidos",
    "abordagens feita": "abordagens",
    "follow up": "fups",
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
    if normalizar(titulo).startswith(("dashboard", "funil")):
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
    # Colunas atuais das abas por SDR. "Oportunidades" da planilha não é lida: na página ela é
    # números captados (funis LinkedIn + Instagram) + indicações captadas.
    "metricas_funil_sdr": ["abordagens", "respondidos", "inscricoes_realizadas", "indicacoes", "reunioes_agendadas"],
    "metricas_closers": [
        "ligacoes_agendadas",
        "ligacoes_realizadas",
        "reunioes_agendadas",
        "reunioes_realizadas",
        "indicacoes",
        "inscricoes_realizadas",
    ],
    "metricas_contas": [
        "conexoes_enviadas",
        "conexoes_aceitas",
        "mensagens_abordagem",
        "abordagens",
        "follows_abordagem",
        "respondidos",
        "in_mails",
        "fups",
        "numeros_captados",
        "indicacoes",
    ],
}


@dataclass(frozen=True)
class MetasDashboardSdr:
    # nome como está na aba ("Juca", "Jenni") -> métrica -> meta diária
    diarias: dict[str, dict[str, int]]
    semanais: dict[str, int]
    mensais: dict[str, int]


def _achar(linhas: list[list], prefixo: str) -> tuple[int, int] | None:
    for i, linha in enumerate(linhas):
        for j, c in enumerate(linha):
            if isinstance(c, str) and normalizar(c).startswith(prefixo):
                return i, j
    return None


def ler_metas_dashboard_sdr(linhas: list[list]) -> MetasDashboardSdr:
    """Metas da aba "Dashboard SDR", achadas pelos rótulos e não por posição fixa.

    Tabela "Vendedor": uma linha por SDR com a meta diária de cada métrica, até
    "META DIÁRIA TOTAL" ou linha vazia. Tabela "Meta Semanal [Editar]" /
    "Meta Mensal [Editar]": uma linha por métrica, rótulo na coluna "Métrica".
    """
    diarias: dict[str, dict[str, int]] = {}
    if (pos := _achar(linhas, "vendedor")) is not None:
        i, j = pos
        cabecalho = linhas[i]
        colunas = {
            k: COLUNA_POR_CABECALHO[normalizar(c)]
            for k, c in enumerate(cabecalho)
            if k > j and isinstance(c, str) and normalizar(c) in COLUNA_POR_CABECALHO
        }
        for linha in linhas[i + 1:]:
            nome = _celula(linha, j)
            if not isinstance(nome, str) or not nome.strip() or normalizar(nome).startswith("meta diaria total"):
                break
            diarias[nome.strip()] = {
                m: v for k, m in colunas.items() if (v := _inteiro(_celula(linha, k))) is not None
            }

    def por_metrica(prefixo: str) -> dict[str, int]:
        pos = _achar(linhas, prefixo)
        if pos is None:
            return {}
        i, j = pos
        # rótulos na coluna "Métrica" do mesmo cabeçalho
        rotulos = next((k for k, c in enumerate(linhas[i]) if isinstance(c, str) and normalizar(c) == "metrica"), None)
        if rotulos is None:
            return {}
        metas: dict[str, int] = {}
        for linha in linhas[i + 1:]:
            rotulo = _celula(linha, rotulos)
            metrica = COLUNA_POR_CABECALHO.get(normalizar(rotulo)) if isinstance(rotulo, str) else None
            if metrica is None:
                break
            if (v := _inteiro(_celula(linha, j))) is not None:
                metas[metrica] = v
        return metas

    return MetasDashboardSdr(diarias=diarias, semanais=por_metrica("meta semanal"), mensais=por_metrica("meta mensal"))


def resolver_sdr_do_dashboard(nome: str, usuarios: list[dict]) -> dict | None:
    """Nome da tabela "Vendedor" -> user. Exato primeiro; senão, o único user cujo nome começa com ele ("Jenni" -> "Jennifer")."""
    if (u := resolver_usuario(nome, usuarios)) is not None:
        return u
    alvo = normalizar(nome)
    candidatos = [u for u in usuarios if normalizar(u["nome"]).startswith(alvo)]
    return candidatos[0] if len(candidatos) == 1 else None
