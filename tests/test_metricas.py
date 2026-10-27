"""Testes de `app/metricas.py` — vocabulário de métricas por cargo."""
from __future__ import annotations

from app.metricas import metricas_do_cargo, nome_exibicao


def test_metricas_do_cargo_seguem_as_planilhas():
    assert metricas_do_cargo("seller") == ("fups", "numeros_captados", "indicacoes")
    assert metricas_do_cargo("sdr") == (
        "ligacoes_efetuadas", "ligacoes_realizadas", "inscricoes_realizadas", "indicacoes", "reunioes_agendadas",
    )
    assert metricas_do_cargo("closer") == (
        "ligacoes_agendadas", "ligacoes_realizadas", "reunioes_agendadas", "reunioes_realizadas",
        "indicacoes", "inscricoes_realizadas",
    )
    assert metricas_do_cargo("dripify") == (
        "conexoes_enviadas", "conexoes_aceitas", "abordagens", "in_mails", "fups", "numeros_captados",
    )
    assert metricas_do_cargo("empresa") == ()
    assert nome_exibicao("ligacoes_efetuadas") == "Ligações Efetuadas"
    assert nome_exibicao("indicacoes", "seller") == "Indicações Captadas"
