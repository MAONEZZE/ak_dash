"""Configuração: defaults dos workers das planilhas."""
from app import config


def test_workers_desligados_por_padrao(monkeypatch):
    for nome in (
        "WORKERS_ATIVOS",
        "WORKER_INTERVALO_SEGUNDOS",
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        "PLANILHA_SELLERS_ID",
        "PLANILHA_SDRS_ID",
        "PLANILHA_CLOSERS_ID",
        "PLANILHA_DRIPIFY_ID",
    ):
        monkeypatch.delenv(nome, raising=False)

    s = config.Settings()

    assert s.workers_ativos is False
    assert s.worker_intervalo_segundos == 5.0
    assert s.google_service_account_json is None
    assert s.planilha_sellers_id is None
    assert s.planilha_sdrs_id is None
    assert s.planilha_closers_id is None
    assert s.planilha_dripify_id is None
