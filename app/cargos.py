"""Leitura de `dash.metricas_cargo` — tabela de referência `id <-> cargo`.

Hoje: closer=1, sdr=2, empresa=3. É ela que liga `users.id_cargo` ao nome do
cargo — é esse o único uso que sobrou (ver `dominios/pessoas/banco.py`).

Meta não passa mais por aqui: era `dash.metas_cargo` que vinculava meta a
cargo, e ela saiu do banco em favor de `dash.user_metas` (meta por pessoa).
O cargo `empresa` virou resquício: os cards da empresa somam as metas das
pessoas que os compõem, ver `dominios/geral/calculo.py`.
"""
from __future__ import annotations

from app.fontes.banco import query


def buscar_cargos() -> dict[str, int]:
    linhas = query("metricas_cargo")
    return {r["cargo"]: int(r["id"]) for r in linhas if r.get("cargo") and r.get("id") is not None}
