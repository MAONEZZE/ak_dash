"""Leitura e escrita do Supabase principal (schema `NOME_SCHEMA`, hoje `dash_new`), uma função por dado. Leitura degrada para `[]` com aviso `fonte_indisponivel:<tabela>` (via `banco.query`); escrita levanta erro (workers)."""
from __future__ import annotations

from datetime import date, timedelta

from app.fontes import banco


def ler_usuarios_ativos() -> list[dict]:
    return banco.query("users", {"active": "eq.true"})


def ler_cargos_dos_usuarios() -> list[dict]:
    return banco.query("user_cargos", colunas="id_user,cargo")


def ler_metas() -> list[dict]:
    return banco.query("metas", colunas="id_user,cargo,metrica,valor_diario")
