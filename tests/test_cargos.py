from __future__ import annotations

from app import cargos as cargos_mod
from app.cargos import buscar_cargos


def test_buscar_cargos_mapeia_nome_para_id(monkeypatch):
    monkeypatch.setattr(
        cargos_mod,
        "query",
        lambda *a, **k: [{"id": 1, "cargo": "closer"}, {"id": 2, "cargo": "sdr"}],
    )
    assert buscar_cargos() == {"closer": 1, "sdr": 2}


def test_buscar_cargos_vazio_quando_tabela_vazia(monkeypatch):
    monkeypatch.setattr(cargos_mod, "query", lambda *a, **k: [])
    assert buscar_cargos() == {}
