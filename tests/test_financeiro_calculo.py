from __future__ import annotations

from datetime import date

from app.dominios.financeiro.calculo import montar_resposta_financeiro
from app.periodo import Periodo


def test_resposta_traz_periodo_e_notas_por_data_de_referencia_decrescente():
    periodo = Periodo("ano", date(2026, 1, 1), date(2026, 11, 27))
    setembro = {"chave": "2026-09:1", "data_referencia": "2026-09-01"}
    novembro = {"chave": "2026-11:2", "data_referencia": "2026-11-10"}
    outubro = {"chave": "2026-10:3", "data_referencia": "2026-10-05"}
    resposta = montar_resposta_financeiro(periodo, [setembro, novembro, outubro])
    assert resposta == {
        "periodo": {"granularidade": "ano", "inicio": "2026-01-01", "fim": "2026-11-27"},
        "notas": [novembro, outubro, setembro],
    }
