"""Roda um arquivo .sql (numa transação) ou uma consulta avulsa no Postgres de DATABASE_URL."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv


def main(argv: list[str]) -> int:
    load_dotenv()
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("DATABASE_URL não configurada no ak_dash/.env")

    parser = argparse.ArgumentParser(description=__doc__)
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("arquivo", nargs="?", help="arquivo .sql a rodar numa transação")
    grupo.add_argument("-c", "--consulta", help="consulta SQL avulsa")
    args = parser.parse_args(argv)

    if args.arquivo is not None:
        sql = Path(args.arquivo).read_text(encoding="utf-8")
        with psycopg.connect(dsn) as conn:
            conn.execute(sql)
        print(f"ok: {args.arquivo}")
    else:
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(args.consulta)
                if cur.description is not None:
                    for linha in cur.fetchall():
                        print("\t".join(str(valor) for valor in linha))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
