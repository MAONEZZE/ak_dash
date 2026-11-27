"""Leitura das planilhas de métricas pela Google Sheets API (service account, só leitura). Uma chamada `spreadsheets.get` por ciclo traz todas as abas, o que cabe na cota de 60 leituras/min com 4 planilhas a cada 5s."""
from __future__ import annotations

import json

import google.auth.transport.requests
import httpx
from google.oauth2 import service_account

ESCOPO = "https://www.googleapis.com/auth/spreadsheets.readonly"
_URL = "https://sheets.googleapis.com/v4/spreadsheets/{}"
_CAMPOS = "sheets(properties(title),data(rowData(values(effectiveValue))))"


def criar_credenciais(json_texto: str):
    return service_account.Credentials.from_service_account_info(json.loads(json_texto), scopes=[ESCOPO])


def _valor(celula: dict):
    ev = celula.get("effectiveValue") or {}
    if "numberValue" in ev:
        n = ev["numberValue"]
        return int(n) if float(n).is_integer() else float(n)
    if "stringValue" in ev:
        return ev["stringValue"]
    if "boolValue" in ev:
        return ev["boolValue"]
    return None


class LeitorSheets:
    def __init__(self, credenciais):
        self._credenciais = credenciais

    def abas(self, planilha_id: str) -> list[tuple[str, list[list]]]:
        if not self._credenciais.valid:
            self._credenciais.refresh(google.auth.transport.requests.Request())
        resposta = httpx.get(
            _URL.format(planilha_id),
            params={"includeGridData": "true", "fields": _CAMPOS},
            headers={"Authorization": f"Bearer {self._credenciais.token}"},
            timeout=10.0,
        )
        resposta.raise_for_status()
        abas = []
        for sheet in resposta.json().get("sheets", []):
            titulo = sheet["properties"]["title"]
            dados = (sheet.get("data") or [{}])[0]
            linhas = [[_valor(c) for c in linha.get("values", [])] for linha in dados.get("rowData", [])]
            abas.append((titulo, linhas))
        return abas
