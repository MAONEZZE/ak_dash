"""Lista as planilhas comerciais na pasta do Google Drive (DRIVE_PASTA_ID).

Incluir pessoa nova = jogar a planilha na pasta — nenhum cadastro, nenhum código.
Sem credencial configurada, devolve lista vazia (o domínio comercial degrada
para "sem dado do mês corrente", sem quebrar).

Dev local (`PLANILHAS_LOCAL_DIR`): antes da credencial do Google existir, lista
os CSVs de um diretório local no lugar da pasta do Drive — mesma forma
(`ArquivoDrive`), mesmo contrato para `dominios/comercial/rotas.py`.
"""
from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass

from app.config import settings


@dataclass(frozen=True)
class ArquivoDrive:
    id: str
    nome: str


def listar_planilhas() -> list[ArquivoDrive]:
    if settings.planilhas_local_dir:
        caminhos = sorted(glob.glob(os.path.join(settings.planilhas_local_dir, "*.csv")))
        return [ArquivoDrive(id=caminho, nome=os.path.basename(caminho)) for caminho in caminhos]

    if not settings.drive_pasta_id or not settings.google_service_account_json:
        return []

    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    credenciais = service_account.Credentials.from_service_account_info(
        json.loads(settings.google_service_account_json),
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    servico = build("drive", "v3", credentials=credenciais)
    resposta = (
        servico.files()
        .list(
            q=f"'{settings.drive_pasta_id}' in parents and trashed = false",
            fields="files(id, name)",
        )
        .execute()
    )
    return [ArquivoDrive(id=a["id"], nome=a["name"]) for a in resposta.get("files", [])]
