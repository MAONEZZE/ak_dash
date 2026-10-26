from __future__ import annotations

from app.dominios.pessoas import banco as pessoas_banco_mod
from app.dominios.pessoas.banco import Pessoa, listar_ativas


def test_pessoa_com_dois_cargos_vira_duas_pessoas(monkeypatch):
    tabelas = {
        "users": [{"id": 4, "nome": "Jennifer", "email": "j@x.com", "imagem_url": None, "active": True}],
        "user_cargos": [{"id_user": 4, "cargo": "sdr"}, {"id_user": 4, "cargo": "seller"}],
    }

    def fake_query(tabela, filtros=None, schema="dash", colunas="*", **kwargs):
        return tabelas.get(tabela, [])

    monkeypatch.setattr(pessoas_banco_mod, "query", fake_query)

    assert listar_ativas() == [
        Pessoa(id="4", nome="Jennifer", cargo="sdr", email="j@x.com", imagem_url=None),
        Pessoa(id="4", nome="Jennifer", cargo="seller", email="j@x.com", imagem_url=None),
    ]


def test_pessoa_sem_email_aparece_com_email_none(monkeypatch):
    tabelas = {
        "users": [{"id": 11, "nome": "Juca", "email": None, "imagem_url": None, "active": True}],
        "user_cargos": [{"id_user": 11, "cargo": "sdr"}],
    }

    def fake_query(tabela, filtros=None, schema="dash", colunas="*", **kwargs):
        return tabelas.get(tabela, [])

    monkeypatch.setattr(pessoas_banco_mod, "query", fake_query)

    assert listar_ativas() == [Pessoa(id="11", nome="Juca", cargo="sdr", email=None, imagem_url=None)]
