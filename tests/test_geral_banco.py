"""Testes de `dominios/geral/banco.py` — faturamento e o segundo Supabase.

As métricas de atividade saíram daqui: a Geral lê `dash.vw_metricas` pelo
mesmo `buscar_totais` do Comercial (ver tests/test_banco_comercial.py).
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from app.dominios.geral import banco as banco_mod
from app.fontes import sed as sed_mod
from app.fontes import supabase as supabase_mod


# --- buscar_faturamento (dash.metricas_faturamento: uma linha por venda)


def _mockar_vendas(
    monkeypatch,
    linhas: list[dict],
    recebimentos: list[dict] | None = None,
    vendas_por_id: list[dict] | None = None,
) -> list[tuple]:
    chamadas: list[tuple] = []
    catalogo = linhas if vendas_por_id is None else vendas_por_id

    def _ler_vendas_do_periodo(inicio, fim):
        chamadas.append(("ler_vendas_do_periodo", (inicio, fim)))
        return linhas

    def _ler_recebimentos_do_periodo(inicio, fim):
        chamadas.append(("ler_recebimentos_do_periodo", (inicio, fim)))
        return recebimentos or []

    def _ler_vendas_por_id_planilha(ids, colunas="*"):
        chamadas.append(("ler_vendas_por_id_planilha", (ids, colunas)))
        return [v for v in catalogo if v["id_planilha"] in ids]

    monkeypatch.setattr(supabase_mod, "ler_vendas_do_periodo", _ler_vendas_do_periodo)
    monkeypatch.setattr(supabase_mod, "ler_recebimentos_do_periodo", _ler_recebimentos_do_periodo)
    monkeypatch.setattr(supabase_mod, "ler_vendas_por_id_planilha", _ler_vendas_por_id_planilha)
    return chamadas


def test_soma_varias_vendas_no_card_da_empresa(monkeypatch):
    _mockar_vendas(
        monkeypatch,
        [
            {"id_planilha": 1, "user_closer": 8, "valor_bruto_contrato": 400000, "liquido_entrada": 160019.64},
            {"id_planilha": 2, "user_closer": 1, "valor_bruto_contrato": 165000, "liquido_entrada": 21737.70},
            {"id_planilha": 3, "user_closer": 3, "valor_bruto_contrato": 60000, "liquido_entrada": 9000.00},
        ],
        [{"id_planilha_venda": 1, "mes": "2026-08-01", "liquido": 190757.34}],
    )
    resultado = banco_mod.buscar_faturamento(date(2026, 8, 1), date(2026, 8, 31), [1, 3, 8])
    assert resultado.empresa["faturamento"] == 625000
    assert resultado.empresa["liquidado"] == pytest.approx(190757.34)
    assert resultado.empresa["inscritos"] is None
    assert resultado.empresa["aprovados"] is None


def test_agrupa_liquidado_por_user_closer(monkeypatch):
    _mockar_vendas(
        monkeypatch,
        [
            {"id_planilha": 1, "user_closer": 8, "valor_bruto_contrato": 300000, "liquido_entrada": 100000.00},
            {"id_planilha": 2, "user_closer": 8, "valor_bruto_contrato": 100000, "liquido_entrada": 60019.64},
            {"id_planilha": 3, "user_closer": 1, "valor_bruto_contrato": 165000, "liquido_entrada": 21737.70},
        ],
        [
            {"id_planilha_venda": 1, "mes": "2026-08-01", "liquido": 100000.00},
            {"id_planilha_venda": 2, "mes": "2026-08-01", "liquido": 60019.64},
            {"id_planilha_venda": 3, "mes": "2026-08-01", "liquido": 21737.70},
        ],
    )
    resultado = banco_mod.buscar_faturamento(date(2026, 8, 1), date(2026, 8, 31), [1, 8])
    assert resultado.por_pessoa[8]["liquidado"] == 160019.64
    assert resultado.por_pessoa[1]["liquidado"] == 21737.70
    assert resultado.por_pessoa[8]["inscritos"] is None
    assert resultado.por_pessoa[8]["aprovados"] is None


def test_venda_sem_user_closer_entra_na_empresa_e_em_ninguem(monkeypatch):
    _mockar_vendas(
        monkeypatch,
        [
            {"id_planilha": 1, "user_closer": None, "valor_bruto_contrato": 60000, "liquido_entrada": 15000.00},
            {"id_planilha": 2, "user_closer": 1, "valor_bruto_contrato": 20000, "liquido_entrada": 5000.00},
        ],
        [
            {"id_planilha_venda": 1, "mes": "2026-08-01", "liquido": 15000.00},
            {"id_planilha_venda": 2, "mes": "2026-08-01", "liquido": 5000.00},
        ],
    )
    resultado = banco_mod.buscar_faturamento(date(2026, 8, 1), date(2026, 8, 31), [1])
    assert resultado.empresa["faturamento"] == 80000
    assert resultado.empresa["liquidado"] == 20000.00
    assert list(resultado.por_pessoa.keys()) == [1]


def test_periodo_sem_venda_da_zero_e_nao_erro(monkeypatch):
    _mockar_vendas(monkeypatch, [])
    resultado = banco_mod.buscar_faturamento(date(2026, 9, 1), date(2026, 9, 30), [1, 3, 8])
    assert resultado.empresa["faturamento"] == 0
    assert resultado.empresa["liquidado"] == 0
    assert resultado.por_pessoa == {}


def test_liquidado_soma_o_segundo_pagamento_da_venda(monkeypatch):
    # Venda parcelada em duas formas (ex.: entrada no PIX + resto no cartão) —
    # cada pagamento com seu próprio líquido. Faltava somar o segundo: era
    # esse o bug que subestimava o card "Liquidado" da Geral.
    _mockar_vendas(
        monkeypatch,
        [
            {
                "id_planilha": 1,
                "user_closer": 8,
                "valor_bruto_contrato": 60000,
                "liquido_entrada": 27000.00,
                "liquido_pgto_2": 21737.70,
            },
        ],
        [{"id_planilha_venda": 1, "mes": "2026-08-01", "liquido": 48737.70}],
    )
    resultado = banco_mod.buscar_faturamento(date(2026, 8, 1), date(2026, 8, 31), [8])
    assert resultado.empresa["liquidado"] == pytest.approx(48737.70)
    assert resultado.por_pessoa[8]["liquidado"] == pytest.approx(48737.70)


def test_liquidado_sem_segundo_pagamento_nao_muda(monkeypatch):
    _mockar_vendas(
        monkeypatch,
        [{"id_planilha": 1, "user_closer": 8, "valor_bruto_contrato": 60000, "liquido_entrada": 27000.00}],
        [{"id_planilha_venda": 1, "mes": "2026-08-01", "liquido": 27000.00}],
    )
    resultado = banco_mod.buscar_faturamento(date(2026, 8, 1), date(2026, 8, 31), [8])
    assert resultado.empresa["liquidado"] == 27000.00


def test_vendas_sao_lidas_pelo_periodo_pedido(monkeypatch):
    chamadas = _mockar_vendas(monkeypatch, [])
    banco_mod.buscar_faturamento(date(2026, 8, 1), date(2026, 8, 31), [])
    assert chamadas[0] == ("ler_vendas_do_periodo", (date(2026, 8, 1), date(2026, 8, 31)))


def test_liquidado_vem_do_calendario_de_recebimentos_dos_meses_do_periodo(monkeypatch):
    venda_no_periodo = {"id_planilha": 1, "data_venda": "2026-08-05T00:00:00", "valor_bruto_contrato": 10000, "liquido_entrada": 9999, "user_closer": 1}
    venda_fora = {"id_planilha": 2, "data_venda": "2026-03-01T00:00:00", "valor_bruto_contrato": 60000, "user_closer": 3}
    recebimentos = [
        {"id_planilha_venda": 1, "mes": "2026-08-01", "liquido": 4500},
        {"id_planilha_venda": 2, "mes": "2026-08-01", "liquido": 18000},
    ]
    chamadas = _mockar_vendas(monkeypatch, [venda_no_periodo], recebimentos, vendas_por_id=[venda_no_periodo, venda_fora])
    empresa = banco_mod.buscar_faturamento(date(2026, 8, 10), date(2026, 8, 20), [1, 3]).empresa

    assert empresa["faturamento"] == 10000
    assert empresa["liquidado"] == 22500
    assert ("ler_recebimentos_do_periodo", (date(2026, 8, 10), date(2026, 8, 20))) in chamadas


def test_liquidado_por_pessoa_vai_para_o_closer_da_venda_do_recebimento(monkeypatch):
    venda_no_periodo = {"id_planilha": 1, "data_venda": "2026-08-05T00:00:00", "valor_bruto_contrato": 10000, "liquido_entrada": 9999, "user_closer": 1}
    venda_fora = {"id_planilha": 2, "data_venda": "2026-03-01T00:00:00", "valor_bruto_contrato": 60000, "user_closer": 3}
    venda_sem_closer = {"id_planilha": 3, "data_venda": "2026-03-01T00:00:00", "valor_bruto_contrato": 5000, "user_closer": None}
    recebimentos = [
        {"id_planilha_venda": 1, "mes": "2026-08-01", "liquido": 4500},
        {"id_planilha_venda": 2, "mes": "2026-08-01", "liquido": 18000},
        {"id_planilha_venda": 3, "mes": "2026-08-01", "liquido": 700},
    ]
    _mockar_vendas(
        monkeypatch,
        [venda_no_periodo],
        recebimentos,
        vendas_por_id=[venda_no_periodo, venda_fora, venda_sem_closer],
    )
    resultado = banco_mod.buscar_faturamento(date(2026, 8, 1), date(2026, 8, 31), [1, 3])

    assert resultado.por_pessoa[1]["liquidado"] == 4500
    assert resultado.por_pessoa[3]["liquidado"] == 18000
    assert resultado.empresa["liquidado"] == 23200
    assert None not in resultado.por_pessoa


# --- buscar_confrarias_do_mes (segundo Supabase, lido por `app.fontes.sed`)


def _mockar_sed(monkeypatch, eventos: list[dict], inscricoes: list[dict]) -> list[tuple]:
    """Devolve as chamadas feitas em `app.fontes.sed`, como `(nome, args, kwargs)`, pra conferir filtros."""
    chamadas: list[tuple] = []

    def _registra_eventos(nome: str):
        def _fake(*args, **kwargs):
            chamadas.append((nome, args, kwargs))
            return eventos

        return _fake

    def _fake_inscricoes(*args, **kwargs):
        chamadas.append(("ler_inscricoes_dos_eventos", args, kwargs))
        return inscricoes

    for nome in ("ler_eventos_entre", "ler_eventos_a_partir_de", "ler_evento_por_id", "ler_imersoes"):
        monkeypatch.setattr(sed_mod, nome, _registra_eventos(nome))
    monkeypatch.setattr(sed_mod, "ler_inscricoes_dos_eventos", _fake_inscricoes)
    return chamadas


def test_inscritos_conta_toda_inscricao_inclusive_recusada(monkeypatch):
    """Recusado É inscrito: o card mede captação, não ocupação de vaga.

    Regressão do caso real da Imersão Alta Cadência (17/09/2026): 70 linhas no
    banco, 5 delas `rejected`, e a tela mostrava 65.
    """
    _mockar_sed(
        monkeypatch,
        [{"id": "e1", "title": "Imersão", "event_date": "2026-09-20T19:00:00", "capacity": 50}],
        [
            {"event_id": "e1", "status": "pending"},
            {"event_id": "e1", "status": "pending"},
            {"event_id": "e1", "status": "approved"},
            {"event_id": "e1", "status": "rejected"},
        ],
    )
    (evento,) = banco_mod.buscar_confrarias_do_mes(date(2026, 9, 1), date(2026, 9, 30))
    assert evento.inscritos == 4
    assert evento.aprovados == 1
    assert evento.pendentes == 2  # só `pending`: recusado não é pendente
    assert evento.rejeitados == 1
    assert evento.capacidade == 50


def test_evento_sem_inscricao_sai_com_zero_nao_com_erro(monkeypatch):
    _mockar_sed(
        monkeypatch,
        [{"id": "e1", "title": "Imersão", "event_date": "2026-09-20T19:00:00", "capacity": None}],
        [{"event_id": "outro", "status": "approved"}],
    )
    (evento,) = banco_mod.buscar_confrarias_do_mes(date(2026, 9, 1), date(2026, 9, 30))
    assert (evento.inscritos, evento.aprovados, evento.pendentes, evento.rejeitados, evento.capacidade) == (0, 0, 0, 0, None)


def test_filtra_confraria_do_mes_inteiro_e_nao_filtra_status(monkeypatch):
    chamadas = _mockar_sed(
        monkeypatch,
        [{"id": "e1", "title": "x", "event_date": "2026-09-20T19:00:00", "capacity": None}],
        [],
    )
    banco_mod.buscar_confrarias_do_mes(date(2026, 9, 1), date(2026, 9, 30))
    assert chamadas[0] == (
        "ler_eventos_entre",
        (datetime(2026, 9, 1, tzinfo=banco_mod.TZ_SP), datetime(2026, 10, 1, tzinfo=banco_mod.TZ_SP), "confraria akeel", banco_mod.LIMITE_EVENTOS),
        {},
    )
    assert chamadas[1] == ("ler_inscricoes_dos_eventos", (["e1"],), {})


def test_no_maximo_limite_eventos_e_na_ordem_do_banco(monkeypatch):
    limite = banco_mod.LIMITE_EVENTOS
    _mockar_sed(
        monkeypatch,
        [
            {"id": f"e{i}", "title": f"Confraria Akeel {i}", "event_date": "2026-09-20T19:00:00", "capacity": None}
            for i in range(1, limite + 6)
        ],
        [],
    )
    eventos = banco_mod.buscar_confrarias_do_mes(date(2026, 9, 1), date(2026, 9, 30))
    assert [e.id for e in eventos] == [f"e{i}" for i in range(1, limite + 1)]


def test_sem_confraria_no_mes_nao_consulta_inscricoes(monkeypatch):
    chamadas = _mockar_sed(monkeypatch, [], [])
    assert banco_mod.buscar_confrarias_do_mes(date(2026, 9, 1), date(2026, 9, 30)) == []
    assert [c[0] for c in chamadas] == ["ler_eventos_entre"]


def test_evento_sem_titulo_ganha_rotulo_neutro(monkeypatch):
    _mockar_sed(
        monkeypatch,
        [{"id": "e1", "title": None, "event_date": "2026-09-20T19:00:00", "capacity": None}],
        [],
    )
    (evento,) = banco_mod.buscar_confrarias_do_mes(date(2026, 9, 1), date(2026, 9, 30))
    assert evento.titulo == "Sem título"


def test_proximo_evento_busca_a_partir_de_agora_so_um_de_qualquer_titulo_com_inscricoes(monkeypatch):
    agora = datetime(2026, 11, 17, 10, 30, tzinfo=banco_mod.TZ_SP)
    chamadas = _mockar_sed(
        monkeypatch,
        [{"id": "e1", "title": "Confraria Akeel SP", "event_date": "2026-11-20T22:00:00", "capacity": 80}],
        [{"event_id": "e1", "status": "approved"}, {"event_id": "e1", "status": "rejected"}],
    )
    evento = banco_mod.buscar_proximo_evento(agora)
    assert (evento.titulo, evento.data, evento.inscritos, evento.capacidade) == (
        "Confraria Akeel SP", "2026-11-20T22:00:00", 2, 80,
    )
    assert chamadas[0] == ("ler_eventos_a_partir_de", (agora, 1), {})


def test_sem_proximo_evento_devolve_none(monkeypatch):
    _mockar_sed(monkeypatch, [], [])
    assert banco_mod.buscar_proximo_evento(datetime(2026, 11, 17, tzinfo=banco_mod.TZ_SP)) is None


def test_proxima_imersao_filtra_titulo_e_data_a_partir_de_agora(monkeypatch):
    agora = datetime(2026, 11, 17, 10, 30, tzinfo=banco_mod.TZ_SP)
    chamadas = _mockar_sed(
        monkeypatch,
        [{"id": "i2", "title": "Imersão Alta Cadência", "event_date": "2026-12-02T16:00:00+00:00", "capacity": 60}],
        [{"event_id": "i2", "status": "approved"}, {"event_id": "i2", "status": "pending"}, {"event_id": "i2", "status": "rejected"}],
    )
    evento = banco_mod.buscar_proxima_imersao(agora)
    assert (evento.id, evento.inscritos, evento.aprovados, evento.pendentes, evento.rejeitados) == ("i2", 3, 1, 1, 1)
    assert chamadas[0] == ("ler_eventos_a_partir_de", (agora, 1), {"titulo_contem": "imers"})


# --- buscar_logs (dash2.logs_pipedrive, espelho da planilha de logs)


def _mockar_logs(monkeypatch, linhas: list[dict]) -> list[tuple]:
    chamadas: list[tuple] = []

    def _ler_logs_do_periodo(inicio, fim):
        chamadas.append((inicio, fim))
        return list(linhas)

    monkeypatch.setattr(supabase_mod, "ler_logs_do_periodo", _ler_logs_do_periodo)
    return chamadas


def _log(data: str, hora: str | None, usuario: str | None = "Jennifer", atividade: str = "Indicações", cliente: str | None = "Isaque") -> dict:
    return {"data": data, "hora": hora, "usuario_acao": usuario, "atividade": atividade, "cliente_nome": cliente}


def test_logs_filtra_periodo_pela_coluna_data(monkeypatch):
    chamadas = _mockar_logs(monkeypatch, [])
    assert banco_mod.buscar_logs(date(2026, 10, 1), date(2026, 10, 5)) == []
    assert chamadas == [(date(2026, 10, 1), date(2026, 10, 5))]


def test_logs_vem_do_mais_recente_pro_mais_antigo_com_usuario_atividade_e_cliente(monkeypatch):
    _mockar_logs(
        monkeypatch,
        [
            _log("2026-10-01", "09:00:00", cliente="A"),
            _log("2026-10-02", "08:00:00", usuario="Thalyson", atividade="Números Captados", cliente="B"),
            _log("2026-10-01", "18:00:00", cliente="C"),
            _log("2026-10-01", None, usuario=None, cliente=None),
        ],
    )
    logs = banco_mod.buscar_logs(date(2026, 10, 1), date(2026, 10, 31))
    assert [l.cliente for l in logs] == ["B", "C", "A", None]
    assert logs[0] == banco_mod.LogAtividade(
        data="2026-10-02", hora="08:00:00", usuario="Thalyson", atividade="Números Captados", cliente="B"
    )


def test_logs_limita_aos_mais_recentes(monkeypatch):
    total = banco_mod.LIMITE_LOGS + 5
    _mockar_logs(monkeypatch, [_log("2026-10-01", f"{m // 60:02d}:{m % 60:02d}:00", cliente=str(m)) for m in range(total)])
    logs = banco_mod.buscar_logs(date(2026, 10, 1), date(2026, 10, 31))
    assert len(logs) == banco_mod.LIMITE_LOGS
    assert logs[0].cliente == str(total - 1)


def test_lista_os_proximos_eventos_de_qualquer_titulo_do_mais_proximo(monkeypatch):
    agora = datetime(2026, 11, 17, 10, 30, tzinfo=banco_mod.TZ_SP)
    chamadas = _mockar_sed(
        monkeypatch,
        [
            {"id": "e1", "title": "Imersão Alta Cadência", "event_date": "2026-11-18T22:00:00"},
            {"id": "e2", "title": None, "event_date": "2026-11-20T22:00:00"},
        ],
        [],
    )
    eventos = banco_mod.listar_proximos_eventos(agora)
    assert eventos == [
        {"id": "e1", "titulo": "Imersão Alta Cadência", "data": "2026-11-18T22:00:00"},
        {"id": "e2", "titulo": "Sem título", "data": "2026-11-20T22:00:00"},
    ]
    assert chamadas == [("ler_eventos_a_partir_de", (agora, banco_mod.LIMITE_EVENTOS), {"colunas": "id,title,event_date"})]


def test_lista_imersoes_passadas_e_futuras_da_mais_recente(monkeypatch):
    chamadas = _mockar_sed(
        monkeypatch,
        [
            {"id": "i2", "title": "Imersão Alta Cadência", "event_date": "2026-12-02T16:00:00+00:00"},
            {"id": "i1", "title": None, "event_date": "2026-11-17T12:00:00+00:00"},
        ],
        [],
    )
    imersoes = banco_mod.listar_imersoes()
    assert imersoes == [
        {"id": "i2", "titulo": "Imersão Alta Cadência", "data": "2026-12-02T16:00:00+00:00"},
        {"id": "i1", "titulo": "Sem título", "data": "2026-11-17T12:00:00+00:00"},
    ]
    assert chamadas == [("ler_imersoes", ("imers", banco_mod.LIMITE_EVENTOS), {})]


def test_evento_escolhido_e_buscado_pelo_id_sem_filtro_de_titulo(monkeypatch):
    chamadas = _mockar_sed(
        monkeypatch,
        [{"id": "e1", "title": "Imersão", "event_date": "2026-11-18T22:00:00", "capacity": None}],
        [{"event_id": "e1", "status": "pending"}],
    )
    evento = banco_mod.buscar_evento("e1")
    assert (evento.id, evento.pendentes) == ("e1", 1)
    assert chamadas[0] == ("ler_evento_por_id", ("e1",), {})


def test_comparecimento_conta_checkins_do_evento_de_qualquer_status(monkeypatch):
    chamadas: list[tuple] = []

    def _fake_comparecimentos(*args, **kwargs):
        chamadas.append((args, kwargs))
        return [{"id": "r1"}, {"id": "r2"}, {"id": "r3"}]

    monkeypatch.setattr(sed_mod, "ler_comparecimentos", _fake_comparecimentos)
    assert banco_mod.contar_comparecimento("i2") == 3
    assert chamadas == [(("i2",), {})]
