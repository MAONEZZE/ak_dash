import dataclasses
import logging
import threading
from datetime import date, datetime

import pytest

from app import config
from app import workers
from app.periodo import TZ_SP


@pytest.fixture(autouse=True)
def _limpar_ativos():
    yield
    workers.ATIVOS.clear()
    workers.MOTIVO_INATIVOS = None


class _Banco:
    def __init__(self, tabelas):
        self.tabelas = tabelas            # nome -> list[dict]
        self.consultas = []               # (tabela, filtros, colunas)
        self.upserts = []                 # (tabela, linhas, on_conflict)
        self.apagados = []                # (tabela, filtros)

    def query(self, tabela, filtros=None, schema=None, colunas="*", **kwargs):
        self.consultas.append((tabela, filtros, colunas))
        return [dict(l) for l in self.tabelas.get(tabela, [])]

    def upsert(self, tabela, linhas, on_conflict, schema=None):
        self.upserts.append((tabela, [dict(l) for l in linhas], on_conflict))

    def apagar(self, tabela, filtros, schema=None):
        self.apagados.append((tabela, dict(filtros)))


def _instalar(monkeypatch, banco):
    monkeypatch.setattr(workers.banco, "query", banco.query)
    monkeypatch.setattr(workers.banco, "upsert", banco.upsert)
    monkeypatch.setattr(workers.banco, "apagar", banco.apagar)
    invalidacoes = []
    monkeypatch.setattr(workers.cache, "invalidar", lambda chave=None: invalidacoes.append(chave))
    return invalidacoes


def _sem_carimbo(linhas):
    return [{k: v for k, v in l.items() if k != "atualizado_em"} for l in linhas]


SELLERS = workers.Planilha(nome="sellers", tabela="metricas_sellers", cargo="seller")
CABECALHO = ["Dia", "Follow-ups", "Números Captados", "Indicações Captadas"]


def _worker(abas, hoje=date(2026, 10, 27)):
    fonte = {"abas": abas}
    w = workers.Worker(SELLERS, "ID_SELLERS", lambda _id: fonte["abas"], hoje=lambda: hoje)
    return w, fonte


def test_primeiro_ciclo_grava_metricas_e_metas_no_mes_corrente(monkeypatch):
    banco = _Banco({"users": [{"id": 12, "nome": "Isaque"}], "user_cargos": [{"id_user": 12}]})
    invalidacoes = _instalar(monkeypatch, banco)
    w, _ = _worker([("Isaque", [CABECALHO, ["Meta diária", 50, 3], [5, 10, 2], [6, 4]])])

    w.ciclo()

    assert banco.upserts[0][0] == "metricas_sellers"
    assert banco.upserts[0][2] == "key_data_ref_user"
    assert _sem_carimbo(banco.upserts[0][1]) == [
        {"id_user": 12, "data": "2026-10-05", "key_data_ref_user": "05/10/2026-isaque", "fups": 10, "numeros_captados": 2, "indicacoes": None},
        {"id_user": 12, "data": "2026-10-06", "key_data_ref_user": "06/10/2026-isaque", "fups": 4, "numeros_captados": None, "indicacoes": None},
    ]
    assert all(isinstance(l["atualizado_em"], str) for l in banco.upserts[0][1])
    assert banco.upserts[1][0] == "metas"
    assert banco.upserts[1][2] == "id_user,cargo,metrica"
    assert _sem_carimbo(banco.upserts[1][1]) == [
        {"id_user": 12, "cargo": "seller", "metrica": "fups", "valor_diario": 50},
        {"id_user": 12, "cargo": "seller", "metrica": "numeros_captados", "valor_diario": 3},
    ]
    assert banco.apagados == []
    assert len(invalidacoes) == 1


def test_ciclo_sem_mudanca_nao_grava(monkeypatch):
    banco = _Banco({"users": [{"id": 12, "nome": "Isaque"}], "user_cargos": [{"id_user": 12}]})
    invalidacoes = _instalar(monkeypatch, banco)
    w, _ = _worker([("Isaque", [CABECALHO, ["Meta diária", 50, 3], [5, 10, 2], [6, 4]])])
    w.ciclo()
    banco.upserts.clear()
    invalidacoes.clear()

    w.ciclo()

    assert banco.upserts == []
    assert banco.apagados == []
    assert invalidacoes == []


def test_dia_apagado_na_planilha_vira_null(monkeypatch):
    banco = _Banco({"users": [{"id": 12, "nome": "Isaque"}], "user_cargos": [{"id_user": 12}]})
    _instalar(monkeypatch, banco)
    w, fonte = _worker([("Isaque", [CABECALHO, ["Meta diária", 50], [5, 10, 2], [6, 4]])])
    w.ciclo()
    banco.upserts.clear()
    fonte["abas"] = [("Isaque", [CABECALHO, ["Meta diária", 50], [5], [6, 4]])]

    w.ciclo()

    assert len(banco.upserts) == 1
    assert banco.upserts[0][0] == "metricas_sellers"
    assert _sem_carimbo(banco.upserts[0][1]) == [
        {"id_user": 12, "data": "2026-10-05", "key_data_ref_user": "05/10/2026-isaque", "fups": None, "numeros_captados": None, "indicacoes": None},
    ]

    w.ciclo()

    assert len(banco.upserts) == 1


def test_estado_inicial_vem_do_banco(monkeypatch):
    banco = _Banco({
        "users": [{"id": 12, "nome": "Isaque"}],
        "user_cargos": [{"id_user": 12}],
        "metricas_sellers": [
            {"id_user": 12, "data": "2026-10-05", "key_data_ref_user": "05/10/2026-isaque", "fups": 10, "numeros_captados": 2, "indicacoes": None},
            {"id_user": 12, "data": "2026-10-07", "key_data_ref_user": "07/10/2026-isaque", "fups": 8, "numeros_captados": None, "indicacoes": None},
        ],
        "metas": [{"id_user": 12, "metrica": "fups", "valor_diario": 50}],
    })
    _instalar(monkeypatch, banco)
    w, _ = _worker([("Isaque", [CABECALHO, ["Meta diária", 50], [5, 10, 2]])])

    w.ciclo()

    assert ("metricas_sellers", {"and": "(data.gte.2026-10-01,data.lte.2026-10-31)"}, "id_user,data,key_data_ref_user,fups,numeros_captados,indicacoes") in banco.consultas
    assert ("metas", {"cargo": "eq.seller"}, "id_user,metrica,valor_diario") in banco.consultas
    assert len(banco.upserts) == 1
    assert _sem_carimbo(banco.upserts[0][1]) == [
        {"id_user": 12, "data": "2026-10-07", "key_data_ref_user": "07/10/2026-isaque", "fups": None, "numeros_captados": None, "indicacoes": None},
    ]


def test_meta_alterada_regrava_e_meta_apagada_e_removida(monkeypatch):
    banco = _Banco({
        "users": [{"id": 12, "nome": "Isaque"}],
        "user_cargos": [{"id_user": 12}],
        "metas": [{"id_user": 12, "metrica": "fups", "valor_diario": 50}, {"id_user": 12, "metrica": "numeros_captados", "valor_diario": 3}],
    })
    _instalar(monkeypatch, banco)
    w, _ = _worker([("Isaque", [CABECALHO, ["Meta diária", None, 0]])])

    w.ciclo()

    assert banco.apagados == [("metas", {"id_user": "eq.12", "cargo": "eq.seller", "metrica": "eq.fups"})]
    metas_upsert = [u for u in banco.upserts if u[0] == "metas"]
    assert len(metas_upsert) == 1
    assert _sem_carimbo(metas_upsert[0][1]) == [{"id_user": 12, "cargo": "seller", "metrica": "numeros_captados", "valor_diario": 0}]

    banco.upserts.clear()
    banco.apagados.clear()

    w.ciclo()

    assert banco.apagados == []
    assert banco.upserts == []


def test_aba_sem_usuario_ou_sem_cargo_e_pulada_com_log_unico(monkeypatch, caplog):
    banco = _Banco({"users": [{"id": 12, "nome": "Isaque"}, {"id": 13, "nome": "Lucas"}], "user_cargos": [{"id_user": 12}]})
    _instalar(monkeypatch, banco)
    w, _ = _worker([("SDR2", [CABECALHO, ["Meta diária", 0], [1, 5]]), ("Lucas", [CABECALHO, ["Meta diária", 10], [1, 7]])])

    with caplog.at_level(logging.WARNING, logger="app.workers"):
        w.ciclo()
        w.ciclo()

    assert banco.upserts == []
    assert banco.apagados == []
    mensagens = [r.getMessage() for r in caplog.records]
    assert len([m for m in mensagens if "SDR2" in m]) == 1
    assert len([m for m in mensagens if "Lucas" in m]) == 1


def test_executar_ciclo_registra_erro_e_sucesso_no_status(monkeypatch):
    contador = {"n": 0}

    class _BancoQueFalha(_Banco):
        falhar = True

        def query(self, tabela, filtros=None, schema=None, colunas="*", **kwargs):
            if tabela == "users" and self.falhar:
                contador["n"] += 1
            return super().query(tabela, filtros, schema=schema, colunas=colunas, **kwargs)

    banco = _BancoQueFalha({"users": [{"id": 12, "nome": "Isaque"}], "user_cargos": [{"id_user": 12}]})
    _instalar(monkeypatch, banco)
    monkeypatch.setattr(workers.banco, "falhas_na_thread", lambda: contador["n"])
    w = workers.Worker(
        SELLERS,
        "ID_SELLERS",
        lambda _id: [("Isaque", [CABECALHO, ["Meta diária", 50], [5, 10]])],
        hoje=lambda: date(2026, 10, 27),
        agora=lambda: datetime(2026, 10, 27, 10, 0, tzinfo=TZ_SP),
    )

    w.executar_ciclo()

    assert w.status["ultima_leitura_ok"] is None
    assert w.status["ultimo_erro"] == {"em": "2026-10-27T10:00:00-03:00", "mensagem": "RuntimeError: consulta a users falhou"}
    assert banco.upserts == []

    banco.falhar = False
    w.executar_ciclo()

    assert w.status["ultima_leitura_ok"] == "2026-10-27T10:00:00-03:00"
    assert w.status["ultimo_erro"] == {"em": "2026-10-27T10:00:00-03:00", "mensagem": "RuntimeError: consulta a users falhou"}
    assert any(tabela == "metricas_sellers" for tabela, _, _ in banco.upserts)


def test_iniciar_sobe_um_worker_por_planilha_configurada(monkeypatch):
    rodados = []
    monkeypatch.setattr(workers.Worker, "rodar", lambda self, parar, intervalo: rodados.append((self.planilha.nome, self.planilha_id, intervalo)))
    monkeypatch.setattr(workers, "criar_credenciais", lambda texto: object())
    base = dataclasses.replace(
        config.settings,
        supabase_url="https://x.supabase.co",
        supabase_service_key="k",
        google_service_account_json="{}",
        planilha_sellers_id="S",
        planilha_sdrs_id=None,
        planilha_closers_id="C",
        planilha_dripify_id=None,
        worker_intervalo_segundos=5.0,
    )

    parar_desligado = workers.iniciar(dataclasses.replace(base, workers_ativos=False))

    assert isinstance(parar_desligado, threading.Event)
    assert workers.ATIVOS == []
    assert rodados == []

    parar = workers.iniciar(dataclasses.replace(base, workers_ativos=True))
    for t in threading.enumerate():
        if t.name.startswith("worker-"):
            t.join(timeout=1)

    assert sorted(w.planilha.nome for w in workers.ATIVOS) == ["closers", "sellers"]
    assert sorted(rodados) == [("closers", "C", 5.0), ("sellers", "S", 5.0)]
    assert isinstance(parar, threading.Event)
    assert parar.is_set() is False


def test_iniciar_sem_credencial_loga_warning_e_guarda_motivo(monkeypatch, caplog):
    caplog.set_level(logging.WARNING)
    base = dataclasses.replace(
        config.settings,
        workers_ativos=True,
        supabase_url="https://x.supabase.co",
        supabase_service_key="k",
        google_service_account_json=None,
        planilha_sellers_id="S",
    )

    workers.iniciar(base)

    assert workers.ATIVOS == []
    assert workers.MOTIVO_INATIVOS == "GOOGLE_SERVICE_ACCOUNT_JSON ausente ou ilegível no .env"
    assert any("GOOGLE_SERVICE_ACCOUNT_JSON ausente ou ilegível no .env" in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)

    workers.iniciar(dataclasses.replace(base, google_service_account_json="{}", supabase_url=None))

    assert workers.MOTIVO_INATIVOS == "SUPABASE_URL ou SUPABASE_SERVICE_KEY ausente"

    workers.iniciar(dataclasses.replace(base, workers_ativos=False))

    assert workers.MOTIVO_INATIVOS is None


def test_iniciar_com_json_invalido_nao_levanta_e_guarda_motivo(caplog):
    caplog.set_level(logging.WARNING)
    base = dataclasses.replace(
        config.settings,
        workers_ativos=True,
        supabase_url="https://x.supabase.co",
        supabase_service_key="k",
        google_service_account_json="{nao e json",
        planilha_sellers_id="S",
    )

    workers.iniciar(base)

    assert workers.ATIVOS == []
    assert workers.MOTIVO_INATIVOS.startswith("GOOGLE_SERVICE_ACCOUNT_JSON inválido: JSONDecodeError")
    assert any(workers.MOTIVO_INATIVOS in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)


def test_rodar_repete_ate_o_evento_de_parada(monkeypatch):
    parar = threading.Event()
    w = workers.Worker(SELLERS, "ID_SELLERS", lambda _id: [])
    chamadas = {"n": 0}

    def executar_ciclo():
        chamadas["n"] += 1
        if chamadas["n"] == 3:
            parar.set()

    monkeypatch.setattr(w, "executar_ciclo", executar_ciclo)

    w.rodar(parar, 0)

    assert chamadas["n"] == 3


def test_virada_do_mes_recarrega_estado_e_grava_no_mes_novo(monkeypatch):
    banco = _Banco({"users": [{"id": 12, "nome": "Isaque"}], "user_cargos": [{"id_user": 12}]})
    _instalar(monkeypatch, banco)
    dias = {"hoje": date(2026, 10, 31)}
    w = workers.Worker(SELLERS, "ID_SELLERS", lambda _id: [("Isaque", [CABECALHO, ["Meta diária", 50], [1, 9]])], hoje=lambda: dias["hoje"])
    w.ciclo()
    banco.upserts.clear()
    banco.consultas.clear()
    dias["hoje"] = date(2026, 11, 1)

    w.ciclo()

    assert ("metricas_sellers", {"and": "(data.gte.2026-11-01,data.lte.2026-11-30)"}, "id_user,data,key_data_ref_user,fups,numeros_captados,indicacoes") in banco.consultas
    metricas_upsert = [u for u in banco.upserts if u[0] == "metricas_sellers"]
    assert len(metricas_upsert) == 1
    assert _sem_carimbo(metricas_upsert[0][1]) == [
        {"id_user": 12, "data": "2026-11-01", "key_data_ref_user": "01/11/2026-isaque", "fups": 9, "numeros_captados": None, "indicacoes": None},
    ]


def test_financeiro_primeiro_ciclo_grava_vendas_com_cliente_e_recebimentos(monkeypatch):
    banco = _Banco({
        "cliente_faturamento": [{"id": 84, "nome": "Fernando Seguim", "telefone": 11942556237}],
        "metricas_faturamento": [],
        "recebimentos_faturamento": [],
    })
    invalidacoes = _instalar(monkeypatch, banco)
    cab_fin = ["ID", "Data da Venda"] + [""] * 44
    linha = [8, 46037, "Fernando Seguim", "11 942556237", "", "", "Jacob", "", 9893.8, "", 9893.8, "PIX", "", 0.1, 0, 8904.42] + [""] * 6 + [9893.8, 8904.42]
    w = workers.WorkerFinanceiro("ID_FIN", 2026, lambda _id: [("BASE_VENDAS", [cab_fin, linha])])

    w.ciclo()

    venda = banco.upserts[0]
    assert venda[0] == "metricas_faturamento"
    assert venda[2] == "id_planilha"
    sem_carimbo = _sem_carimbo(venda[1])[0]
    assert sem_carimbo["id_cliente"] == 84
    assert sem_carimbo["id_planilha"] == 8
    assert sem_carimbo["user_closer"] == 1
    assert isinstance(venda[1][0]["atualizado_em"], str)
    recebimentos = banco.upserts[1]
    assert recebimentos[0] == "recebimentos_faturamento"
    assert recebimentos[2] == "id_planilha_venda,mes"
    assert _sem_carimbo(recebimentos[1]) == [
        {"id_planilha_venda": 8, "mes": "2026-01-01", "pago": 9893.8, "liquido": 8904.42},
    ]
    assert banco.apagados == []
    assert len(invalidacoes) == 1
    assert w.planilha.nome == "financeiro"


def test_financeiro_ciclo_sem_mudanca_nao_grava(monkeypatch):
    banco = _Banco({
        "cliente_faturamento": [{"id": 84, "nome": "Fernando Seguim", "telefone": 11942556237}],
        "metricas_faturamento": [],
        "recebimentos_faturamento": [],
    })
    invalidacoes = _instalar(monkeypatch, banco)
    cab_fin = ["ID", "Data da Venda"] + [""] * 44
    linha = [8, 46037, "Fernando Seguim", "11 942556237", "", "", "Jacob", "", 9893.8, "", 9893.8, "PIX", "", 0.1, 0, 8904.42] + [""] * 6 + [9893.8, 8904.42]
    w = workers.WorkerFinanceiro("ID_FIN", 2026, lambda _id: [("BASE_VENDAS", [cab_fin, linha])])
    w.ciclo()
    banco.upserts.clear()
    invalidacoes.clear()

    w.ciclo()

    assert banco.upserts == []
    assert banco.apagados == []
    assert invalidacoes == []


def test_financeiro_cria_cliente_novo_e_reaproveita_cliente_sem_telefone_pelo_nome(monkeypatch):
    class _BancoClientes(_Banco):
        def upsert(self, tabela, linhas, on_conflict, schema=None):
            if not linhas:
                return
            super().upsert(tabela, linhas, on_conflict, schema)
            if tabela == "cliente_faturamento":
                for l in linhas:
                    self.tabelas[tabela].append({"telefone": None, **l, "id": 900 + len(self.tabelas[tabela])})

    banco = _BancoClientes({
        "cliente_faturamento": [{"id": 90, "nome": "Renata Perri", "telefone": 0}],
        "metricas_faturamento": [],
        "recebimentos_faturamento": [],
    })
    _instalar(monkeypatch, banco)
    cab_fin = ["ID", "Data da Venda"] + [""] * 44
    def linha(id_, nome, telefone):
        return [id_, 46037, nome, telefone, "", "", "Jacob", "", 9893.8, "", 9893.8, "PIX", "", 0.1, 0, 8904.42] + [""] * 6 + [9893.8, 8904.42]
    abas = [("BASE_VENDAS", [cab_fin, linha(1, "Ana Nova", "11 91111-1111"), linha(2, "renata perri", ""), linha(3, "Sem Fone", "")])]
    w = workers.WorkerFinanceiro("ID_FIN", 2026, lambda _id: abas)

    w.ciclo()

    clientes = [(t, _sem_carimbo(l), c) for t, l, c in banco.upserts if t == "cliente_faturamento"]
    assert clientes == [
        ("cliente_faturamento", [{"nome": "Ana Nova", "telefone": 11911111111}], "telefone"),
        ("cliente_faturamento", [{"nome": "Sem Fone"}], "id"),
    ]
    venda = next(l for t, l, _ in banco.upserts if t == "metricas_faturamento")
    assert {l["id_planilha"]: l["id_cliente"] for l in _sem_carimbo(venda)} == {1: 901, 2: 90, 3: 902}
