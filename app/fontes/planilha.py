"""Cliente Google Sheets: aba -> lista de linhas (cru, sem parsing de negócio).

O parser de negócio (app/dominios/comercial/planilha.py) recebe exatamente
esse formato — lista de listas de string — e é por isso testável direto
contra os CSVs de dados_template/ sem precisar desta função.

Dev local (`PLANILHAS_LOCAL_DIR`): quando ativo, `listar_planilhas()` (em
`fontes/drive.py`) passa o caminho do arquivo local como `spreadsheet_id` —
aqui isso vira leitura de CSV em vez de chamada ao Sheets.
"""
from __future__ import annotations

import csv
import json

from app.config import settings


def ler_aba(spreadsheet_id: str, aba: str = "A1:Z100") -> list[list[str]]:
    if settings.planilhas_local_dir:
        with open(spreadsheet_id, newline="", encoding="utf-8") as f:
            return list(csv.reader(f))

    if not settings.google_service_account_json:
        return []

    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    credenciais = service_account.Credentials.from_service_account_info(
        json.loads(settings.google_service_account_json),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    servico = build("sheets", "v4", credentials=credenciais)
    resposta = (
        servico.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=aba)
        .execute()
    )
    return resposta.get("values", [])
