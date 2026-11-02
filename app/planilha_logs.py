"""Leitura da aba Logs da planilha Logs Pipedrive, sem I/O. Usado pelo WorkerLogs."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.planilhas import normalizar

COLUNA_POR_CABECALHO: dict[str, str] = {
    "data": "data",
    "hora": "hora",
    "usuario da acao": "usuario_acao",
    "atividade feita": "atividade",
    "acao evento": "acao_evento",
    "nome do cliente": "cliente_nome",
    "telefone do cliente": "telefone",
    "quem indicou": "quem_indicou",
    "prospectado por": "prospectado_por",
    "linkedin do cliente": "linkedin",
    "instagram do cliente": "instagram",
    "url negocio": "url_negocio",
}

COLUNAS_LOG: list[str] = [
    "data",
    "hora",
    "usuario_acao",
    "atividade",
    "acao_evento",
    "cliente_nome",
    "telefone",
    "telefone_digitos",
    "quem_indicou",
    "prospectado_por",
    "linkedin",
    "instagram",
    "url_negocio",
]


@dataclass(frozen=True)
class LeituraLogs:
    eventos: list[dict]
    invalidas: list[tuple]


def _celula(linha: list, indice: int | None):
    return linha[indice] if indice is not None and indice < len(linha) else None


def _texto(valor) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, bool):
        return str(valor)
    if isinstance(valor, (int, float)):
        return str(int(valor)) if float(valor).is_integer() else str(valor)
    return valor.strip() or None


def _data(valor) -> str | None:
    try:
        if isinstance(valor, str):
            return datetime.strptime(valor.strip(), "%d/%m/%Y").date().isoformat()
        if isinstance(valor, (int, float)) and not isinstance(valor, bool):
            return (date(1899, 12, 30) + timedelta(days=int(valor))).isoformat()
    except ValueError:
        return None
    return None


def _hora(valor) -> str | None:
    try:
        if isinstance(valor, str):
            return time.fromisoformat(valor.strip()).isoformat()
        if isinstance(valor, (int, float)) and not isinstance(valor, bool):
            s = round((valor % 1) * 86400) % 86400
            return time(s // 3600, s % 3600 // 60, s % 60).isoformat()
    except ValueError:
        return None
    return None


def ler_logs(linhas: list[list]) -> LeituraLogs:
    if not linhas:
        return LeituraLogs([], [])
    indices = {
        COLUNA_POR_CABECALHO[normalizar(c)]: i
        for i, c in enumerate(linhas[0])
        if normalizar(c) in COLUNA_POR_CABECALHO
    }
    acumulado: dict[str, dict] = {}
    invalidas: list[tuple] = []
    for linha in linhas[1:]:
        if all(_texto(c) is None for c in linha):
            continue
        evento = {c: _texto(_celula(linha, indices.get(c))) for c in COLUNAS_LOG}
        evento["data"] = _data(_celula(linha, indices.get("data")))
        evento["hora"] = _hora(_celula(linha, indices.get("hora")))
        if evento["data"] is None or evento["atividade"] is None:
            invalidas.append(tuple(linha))
            continue
        evento["telefone_digitos"] = re.sub(r"\D", "", evento["telefone"] or "") or None
        chave = hashlib.sha1(
            json.dumps([evento[c] for c in COLUNAS_LOG if c != "telefone_digitos"], ensure_ascii=False).encode()
        ).hexdigest()
        if chave in acumulado:
            acumulado[chave]["ocorrencias"] += 1
        else:
            acumulado[chave] = {"chave": chave, "ocorrencias": 1, **{c: evento[c] for c in COLUNAS_LOG}}
    return LeituraLogs(list(acumulado.values()), invalidas)
