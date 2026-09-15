"""Leitura de `dash.metricas_cargo` — tabela de referência `id <-> cargo`.

Hoje: closer=1, sdr=2, empresa=3. É ela que liga `users.id_cargo` ao nome do
cargo (ver `dominios/pessoas/banco.py`) e que `dash.metas_cargo` usa pra
vincular cada meta aos cargos em que ela vale. `empresa` é o cargo das metas
que não pertencem a ninguém em particular (faturamento, liquidado).
"""
from __future__ import annotations

from app.fontes.banco import query


def buscar_cargos() -> dict[str, int]:
    linhas = query("metricas_cargo")
    return {r["cargo"]: int(r["id"]) for r in linhas if r.get("cargo") and r.get("id") is not None}
