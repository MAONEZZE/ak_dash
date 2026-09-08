"""Leitura da tabela `pessoas` (Supabase): id, nome, cargo, ativo, email, role."""
from __future__ import annotations

from dataclasses import dataclass

from app.fontes.banco import query


@dataclass(frozen=True)
class Pessoa:
    id: str
    nome: str
    cargo: str
    email: str


def listar_ativas() -> list[Pessoa]:
    linhas = query("pessoas", {"ativo": "true"})
    return [
        Pessoa(id=str(r["id"]), nome=r["nome"], cargo=r["cargo"], email=r["email"])
        for r in linhas
    ]
