"""WorkerPipedrive: histórico de estágios do Pipedrive em pipedrive_negocios + pipedrive_entradas_estagio."""
from datetime import datetime, timedelta

from app import workers
from app.periodo import TZ_SP
from tests.test_workers import _Banco, _instalar


def test_entradas_do_estagio_inicial_em_add_time_e_de_cada_mudanca_no_momento_dela():
    negocio = {"id": 13, "add_time": "2026-01-27T04:23:43Z", "stage_id": 3}
    mudancas = [
        {"de": 1, "para": 4, "em": "2026-01-27T04:52:43Z"},
        {"de": 4, "para": 3, "em": "2026-01-27T04:59:57Z"},
        {"de": 3, "para": 4, "em": "2026-02-01T10:00:00Z"},  # reentrada não conta
    ]
    assert workers.entradas_por_estagio(negocio, mudancas) == {
        1: "2026-01-27T04:23:43Z",
        4: "2026-01-27T04:52:43Z",
        3: "2026-01-27T04:59:57Z",
    }


def test_negocio_que_nunca_mudou_de_estagio_entra_no_atual_em_add_time():
    assert workers.entradas_por_estagio({"id": 1, "add_time": "2026-11-02T12:00:00Z", "stage_id": 2}, []) == {2: "2026-11-02T12:00:00Z"}


class _Pipedrive:
    def __init__(self, negocios, historicos):
        self.negocios = negocios
        self.historicos = historicos
        self.desde = []
        self.historicos_pedidos = []

    def atualizados(self, desde):
        self.desde.append(desde)
        return [dict(n) for n in self.negocios]

    def mudancas(self, id_negocio):
        self.historicos_pedidos.append(id_negocio)
        return self.historicos[id_negocio]


def _preparar(monkeypatch, banco, pd):
    _instalar(monkeypatch, banco)
    monkeypatch.setattr(workers.pipedrive_api, "negocios_atualizados_desde", pd.atualizados)
    monkeypatch.setattr(workers.pipedrive_api, "mudancas_de_estagio", pd.mudancas)
    vencidos = []
    monkeypatch.setattr(workers.cache, "marcar_vencido", lambda prefixos: vencidos.append(prefixos))
    return vencidos


def test_ciclo_grava_historico_e_depois_so_rele_quem_mudou_de_estagio(monkeypatch):
    banco = _Banco({})
    a = {"id": 1, "add_time": "2026-11-02T12:00:00Z", "stage_id": 3, "stage_change_time": "2026-11-05T12:00:00Z", "owner_id": 9, "person_id": 50}
    b = {"id": 2, "add_time": "2026-11-03T12:00:00Z", "stage_id": 1, "stage_change_time": None, "owner_id": 9, "person_id": 51}
    pd = _Pipedrive([a, b], {1: [{"de": 1, "para": 2, "em": "2026-11-04T12:00:00Z"}, {"de": 2, "para": 3, "em": "2026-11-05T12:00:00Z"}]})
    vencidos = _preparar(monkeypatch, banco, pd)
    agora = datetime(2026, 11, 25, 10, 0, tzinfo=TZ_SP)
    w = workers.WorkerPipedrive(agora=lambda: agora)

    w.executar_ciclo()

    assert w.status["ultimo_erro"] is None
    assert pd.desde == [workers.INICIO_HISTORICO_PIPEDRIVE]
    assert pd.historicos_pedidos == [1]  # b nunca mudou de estágio: sem chamada de histórico
    assert sorted((l["id_deal"], l["id_estagio"], l["entrou_em"]) for l in banco.tabelas["pipedrive_entradas_estagio"]) == [
        (1, 1, "2026-11-02T12:00:00Z"),
        (1, 2, "2026-11-04T12:00:00Z"),
        (1, 3, "2026-11-05T12:00:00Z"),
        (2, 1, "2026-11-03T12:00:00Z"),
    ]
    assert vencidos == [("pipedrive:",)]

    # 2º ciclo: só o dono de b mudou -> atualiza o negócio, sem reler histórico; cursor avança com margem
    pd.negocios = [a, {**b, "owner_id": 10}]
    w.executar_ciclo()

    assert pd.desde[1] == agora - timedelta(minutes=5)
    assert pd.historicos_pedidos == [1]
    assert next(l for l in banco.tabelas["pipedrive_negocios"] if l["id_deal"] == 2)["id_dono"] == 10

    # 3º ciclo sem mudança: não grava nem vence o cache
    upserts = len(banco.upserts)
    w.executar_ciclo()
    assert len(banco.upserts) == upserts
    assert len(vencidos) == 2


def test_worker_reiniciado_carrega_o_que_ja_foi_sincronizado_e_nao_rele(monkeypatch):
    a = {"id": 1, "add_time": "2026-11-02T12:00:00Z", "stage_id": 3, "stage_change_time": "2026-11-05T12:00:00Z", "owner_id": 9, "person_id": 50}
    banco = _Banco({"pipedrive_negocios": [{"id_deal": 1, "id_dono": 9, "id_pessoa": 50, "stage_change_time": "2026-11-05T12:00:00Z"}]})
    pd = _Pipedrive([a], {})
    _preparar(monkeypatch, banco, pd)

    workers.WorkerPipedrive().executar_ciclo()

    assert pd.historicos_pedidos == []
    assert banco.upserts == []
