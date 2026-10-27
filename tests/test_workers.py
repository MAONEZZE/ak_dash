from datetime import date, datetime

from app import workers


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
