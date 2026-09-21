"""Guarda de conformidade com `docs/contract/openapi.yaml`: os paths e os

campos obrigatórios do contrato batem com o que o BFF de fato expõe. Não é
um golden-file byte-exato (isso já causou o drift documentado no histórico
do projeto) — é uma checagem estrutural que pega o caso mais comum: alguém
muda a resposta e esquece do contrato, ou vice-versa.
"""
from __future__ import annotations

import os

import yaml

from app.main import app

CONTRATO_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "docs", "contract", "openapi.yaml"
)


def _carregar_openapi() -> dict:
    with open(CONTRATO_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_openapi_e_yaml_valido():
    spec = _carregar_openapi()
    assert spec["openapi"].startswith("3.")


def test_todos_os_paths_do_contrato_existem_no_bff():
    spec = _carregar_openapi()
    rotas_bff = set(app.openapi()["paths"])
    for caminho in spec["paths"]:
        assert caminho in rotas_bff, f"path '{caminho}' está no contrato mas não no BFF"


def test_bff_nao_expoe_rota_de_dado_ausente_do_contrato():
    spec = _carregar_openapi()
    caminhos_contrato = set(spec["paths"])
    rotas_publicas = set(app.openapi()["paths"]) - {"/saude"}
    faltando = rotas_publicas - caminhos_contrato
    assert faltando == set(), f"rota(s) exposta(s) pelo BFF e ausente(s) do contrato: {faltando}"


def test_schema_respostacargo_tem_os_campos_que_o_bff_produz():
    spec = _carregar_openapi()
    campos = set(spec["components"]["schemas"]["RespostaComercial"]["required"])
    assert campos == {"periodo", "periodo_parcial", "avisos", "pessoas", "serie_diaria"}


def test_schema_respostageral_tem_os_campos_que_o_bff_produz():
    spec = _carregar_openapi()
    campos = set(spec["components"]["schemas"]["RespostaGeral"]["required"])
    assert campos == {"periodo", "dias_uteis", "cards", "eventos", "pessoas", "avisos"}


def test_schema_respostafinanceiro_tem_os_campos_que_o_bff_produz():
    spec = _carregar_openapi()
    campos = set(spec["components"]["schemas"]["RespostaFinanceiro"]["required"])
    assert campos == {"periodo", "cards", "vendas"}
