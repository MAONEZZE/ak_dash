"""Leitura de `dash2.users` + `dash2.user_cargos`: uma linha por (pessoa, cargo).

Pessoa com vários cargos vira várias `Pessoa`, uma por cargo. Pessoa sem
nenhum cargo não gera linha.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.fontes.banco import query


@dataclass(frozen=True)
class Pessoa:
    id: str
    nome: str
    cargo: str
    email: str
    imagem_url: str | None = None


def listar_ativas() -> list[Pessoa]:
    usuarios = query("users", {"active": "eq.true"})
    vinculos = query("user_cargos", colunas="id_user,cargo")
    cargos_por_user: dict[int, list[str]] = {}
    for v in vinculos:
        cargos_por_user.setdefault(v["id_user"], []).append(v["cargo"])
    for cargos in cargos_por_user.values():
        cargos.sort()
    return [
        Pessoa(
            id=str(r["id"]),
            nome=r.get("nome") or "",
            cargo=cargo,
            email=r["email"],
            imagem_url=r.get("imagem_url"),
        )
        for r in usuarios
        for cargo in cargos_por_user.get(r["id"], [])
        if r.get("email")
    ]
