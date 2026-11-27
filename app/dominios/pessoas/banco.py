"""Leitura de `users` + `user_cargos` (via app.fontes.supabase): uma linha por (pessoa, cargo).

Pessoa com vários cargos vira várias `Pessoa`, uma por cargo. Pessoa sem
nenhum cargo não gera linha.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.fontes import supabase
from app.fontes.banco import em_paralelo


@dataclass(frozen=True)
class Pessoa:
    id: str
    nome: str
    cargo: str
    email: str | None
    imagem_url: str | None = None


def listar_ativas() -> list[Pessoa]:
    usuarios, vinculos = em_paralelo(supabase.ler_usuarios_ativos, supabase.ler_cargos_dos_usuarios)
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
            email=r.get("email") or None,
            imagem_url=r.get("imagem_url"),
        )
        for r in usuarios
        for cargo in cargos_por_user.get(r["id"], [])
    ]
