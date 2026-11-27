"""Carga completa do financeiro: grava em notas_financeiro todas as abas "NFS <mês>" da planilha (ano = PLANILHA_FINANCEIRO_ANO).

Rodar uma vez (e de novo quando um mês antigo for corrigido): .venv/bin/python -m scripts.carga_financeiro
Depois disso o WorkerFinanceiro mantém só o mês corrente e o anterior.
"""
from __future__ import annotations

import logging
import sys

from app.config import settings
from app.workers import WorkerFinanceiro
from app.workers.google_sheets import LeitorSheets, criar_credenciais


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    if not settings.planilha_financeiro_id or not settings.google_service_account_json:
        raise SystemExit("PLANILHA_FINANCEIRO_ID ou GOOGLE_SERVICE_ACCOUNT_JSON ausente no ak_dash/.env")
    leitor = LeitorSheets(criar_credenciais(settings.google_service_account_json))
    worker = WorkerFinanceiro(settings.planilha_financeiro_id, settings.planilha_financeiro_ano, leitor.abas)
    meses = worker.carga_completa()
    print(f"ok: {', '.join(meses)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
