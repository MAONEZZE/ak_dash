"""Testes de `dominios/geral/banco.py` — faturamento e o segundo Supabase.

As métricas de atividade saíram daqui: a Geral lê `dash.vw_metricas` pelo
mesmo `buscar_totais` do Comercial (ver tests/test_banco_comercial.py).
"""
from __future__ import annotations

from datetime import date, datetime

from app.dominios.geral import banco as banco_mod
from app.fontes import sed as sed_mod
from app.fontes import supabase as supabase_mod


# --- buscar_faturamento (dash.notas_financeiro: uma linha por nota)


def test_faturamento_e_liquidado_vem_de_notas_financeiro(monkeypatch):
    chamadas: list[tuple] = []

    def _ler_notas_financeiro_do_periodo(inicio, fim):
        chamadas.append((inicio, fim))
        return [
            {"mes": "2026-11-01", "data_referencia": "2026-11-10", "valor_venda": 30000, "valor_pago": 5000, "id_vendedor": 1},
            {"mes": "2026-11-01", "data_referencia": "2026-09-30", "valor_venda": 10000, "valor_pago": 2000, "id_vendedor": 3},
            {"mes": "2026-10-01", "data_referencia": "2026-11-05", "valor_venda": 7000, "valor_pago": 999, "id_vendedor": 1},
            {"mes": "2026-11-01", "data_referencia": "2026-11-01", "valor_venda": None, "valor_pago": 1000, "id_vendedor": None},
        ]

    monkeypatch.setattr(supabase_mod, "ler_notas_financeiro_do_periodo", _ler_notas_financeiro_do_periodo)
    resultado = banco_mod.buscar_faturamento(date(2026, 11, 1), date(2026, 11, 27), [1, 3])

    assert chamadas == [(date(2026, 11, 1), date(2026, 11, 27))]
    assert resultado.empresa["faturamento"] == 37000
    assert resultado.empresa["liquidado"] == 8000
    assert resultado.por_pessoa == {
        1: {"faturamento": None, "liquidado": 5000, "inscritos": None, "aprovados": None},
        3: {"faturamento": None, "liquidado": 2000, "inscritos": None, "aprovados": None},
    }


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
