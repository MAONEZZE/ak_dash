from __future__ import annotations

import csv
import glob
import os

CSV_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "dados_template")


def ler_csv_como_linhas(caminho: str) -> list[list[str]]:
    with open(caminho, newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


def caminhos_csv_reais() -> list[str]:
    return sorted(glob.glob(os.path.join(CSV_DIR, "*.csv")))
