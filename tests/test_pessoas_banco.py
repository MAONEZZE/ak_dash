from __future__ import annotations

from app.dominios.pessoas.banco import Pessoa, listar_ativas
from app.fontes import supabase


def test_pessoa_com_dois_cargos_vira_duas_pessoas(monkeypatch):
    monkeypatch.setattr(supabase, "ler_usuarios_ativos", lambda: [{"id": 4, "nome": "Jennifer", "email": "j@x.com", "imagem_url": None, "active": True}])
    monkeypatch.setattr(supabase, "ler_cargos_dos_usuarios", lambda: [{"id_user": 4, "cargo": "sdr"}, {"id_user": 4, "cargo": "seller"}])

    assert listar_ativas() == [
        Pessoa(id="4", nome="Jennifer", cargo="sdr", email="j@x.com", imagem_url=None),
        Pessoa(id="4", nome="Jennifer", cargo="seller", email="j@x.com", imagem_url=None),
    ]


def test_pessoa_sem_email_aparece_com_email_none(monkeypatch):
    monkeypatch.setattr(supabase, "ler_usuarios_ativos", lambda: [{"id": 11, "nome": "Juca", "email": None, "imagem_url": None, "active": True}])
    monkeypatch.setattr(supabase, "ler_cargos_dos_usuarios", lambda: [{"id_user": 11, "cargo": "sdr"}])

    assert listar_ativas() == [Pessoa(id="11", nome="Juca", cargo="sdr", email=None, imagem_url=None)]


def test_usuario_sem_cargo_nao_aparece(monkeypatch):
    monkeypatch.setattr(supabase, "ler_usuarios_ativos", lambda: [{"id": 3, "nome": "Alex", "email": "a@x.com", "imagem_url": None, "active": True}])
    monkeypatch.setattr(supabase, "ler_cargos_dos_usuarios", lambda: [])

    assert listar_ativas() == []
