"""Leitura de `dash.users`: id, nome, cargo, email, active, role.

O cargo saiu de `users` (era uma coluna de texto) e virou `users.id_cargo`,
FK pra `dash.metricas_cargo` — a mesma tabela que `dash.metas_cargo` usa pra
vincular meta a cargo. Aqui ele é resolvido de volta pro nome ('sdr',
'closer', 'empresa'), que é o que o resto do BFF e o contrato da API usam.
Pessoa com `id_cargo` nulo ou apontando pra cargo inexistente fica com cargo
`""` — some dos filtros por cargo em vez de ser chutada pra um deles.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.cargos import buscar_cargos
from app.fontes.banco import query


@dataclass(frozen=True)
class Pessoa:
    id: str
    nome: str
    cargo: str
    email: str
    imagem_url: str | None = None


def listar_ativas() -> list[Pessoa]:
    cargo_por_id = {id_cargo: cargo for cargo, id_cargo in buscar_cargos().items()}
    linhas = query("users", {"active": "eq.true"})
    return [
        Pessoa(
            id=str(r["id"]),
            nome=r.get("nome") or "",
            cargo=cargo_por_id.get(r.get("id_cargo"), ""),
            email=r["email"],
            imagem_url=r.get("imagem_url"),
        )
        for r in linhas
        if r.get("email")
    ]
