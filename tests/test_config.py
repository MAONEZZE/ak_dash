"""Configuração: defaults dos workers das planilhas."""
from datetime import time

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


def test_settings_le_envs_dos_workers(monkeypatch):
    monkeypatch.setenv("WORKERS_ATIVOS", " TRUE ")
    monkeypatch.setenv("WORKER_INTERVALO_SEGUNDOS", "2.5")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", '{"type": "service_account"}')
    monkeypatch.setenv("PLANILHA_SELLERS_ID", "abc")
    monkeypatch.setenv("PLANILHA_DRIPIFY_ID", "")
    monkeypatch.delenv("PLANILHA_SDRS_ID", raising=False)
    monkeypatch.delenv("PLANILHA_CLOSERS_ID", raising=False)

    s = config.Settings()

    assert s.workers_ativos is True
    assert s.worker_intervalo_segundos == 2.5
    assert s.google_service_account_json == '{"type": "service_account"}'
    assert s.planilha_sellers_id == "abc"
    assert s.planilha_dripify_id is None
    assert s.planilha_sdrs_id is None


def test_settings_le_envs_do_worker_financeiro(monkeypatch):
    monkeypatch.setenv("PLANILHA_FINANCEIRO_ID", "fin")
    monkeypatch.setenv("PLANILHA_FINANCEIRO_ANO", "2027")

    s = config.Settings()

    assert s.planilha_financeiro_id == "fin"
    assert s.planilha_financeiro_ano == 2027

    monkeypatch.delenv("PLANILHA_FINANCEIRO_ID", raising=False)
    monkeypatch.delenv("PLANILHA_FINANCEIRO_ANO", raising=False)

    s = config.Settings()

    assert s.planilha_financeiro_id is None
    assert s.planilha_financeiro_ano == 2026


def test_expediente_padrao_10_as_19_e_lido_das_envs(monkeypatch):
    monkeypatch.delenv("EXPEDIENTE_INICIO", raising=False)
    monkeypatch.delenv("EXPEDIENTE_FIM", raising=False)

    s = config.Settings()

    assert s.expediente_inicio == time(10, 0)
    assert s.expediente_fim == time(19, 0)

    monkeypatch.setenv("EXPEDIENTE_INICIO", "09:30")
    monkeypatch.setenv("EXPEDIENTE_FIM", "18:00")

    s = config.Settings()

    assert s.expediente_inicio == time(9, 30)
    assert s.expediente_fim == time(18, 0)
