"""Configuração: defaults dos workers das planilhas."""
from datetime import time

from app import config


def test_workers_desligados_por_padrao(monkeypatch):
    for nome in (
        "WORKERS_ATIVOS",
        "WORKER_INTERVALO_SEGUNDOS",
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        "PLANILHA_SDRS_ID",
        "PLANILHA_CLOSERS_ID",
        "PLANILHA_FUNIL_LINKEDIN_ID",
        "PLANILHA_FUNIL_INSTAGRAM_ID",
    ):
        monkeypatch.delenv(nome, raising=False)

    s = config.Settings()

    assert s.workers_ativos is False
    assert s.worker_intervalo_segundos == 5.0
    assert s.google_service_account_json is None
    assert s.planilha_sdrs_id is None
    assert s.planilha_closers_id is None
    assert s.planilha_funil_linkedin_id is None
    assert s.planilha_funil_instagram_id is None


def test_settings_le_envs_dos_workers(monkeypatch):
    monkeypatch.setenv("WORKERS_ATIVOS", " TRUE ")
    monkeypatch.setenv("WORKER_INTERVALO_SEGUNDOS", "2.5")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", '{"type": "service_account"}')
    monkeypatch.setenv("PLANILHA_FUNIL_LINKEDIN_ID", "abc")
    monkeypatch.setenv("PLANILHA_FUNIL_INSTAGRAM_ID", "")
    monkeypatch.delenv("PLANILHA_SDRS_ID", raising=False)
    monkeypatch.delenv("PLANILHA_CLOSERS_ID", raising=False)

    s = config.Settings()

    assert s.workers_ativos is True
    assert s.worker_intervalo_segundos == 2.5
    assert s.google_service_account_json == '{"type": "service_account"}'
    assert s.planilha_funil_linkedin_id == "abc"
    assert s.planilha_funil_instagram_id is None
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


def test_settings_le_env_do_worker_de_logs(monkeypatch):
    monkeypatch.setenv("PLANILHA_LOGS_ID", "logs")

    s = config.Settings()

    assert s.planilha_logs_id == "logs"

    monkeypatch.setenv("PLANILHA_LOGS_ID", "")

    s = config.Settings()

    assert s.planilha_logs_id is None


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


def test_settings_le_envs_do_pipedrive(monkeypatch):
    monkeypatch.setenv("PIPE_TOKEN", "tok")
    monkeypatch.setenv("PIPE_BASE_URL_V2", "https://x.pipedrive.com/api/v2/")
    monkeypatch.setenv("PIPE_ID_PIPELINE_INSTAGRAM", "3")
    monkeypatch.setenv("PIPE_ID_ABORDADOS_PIPELINE_LINKEDIN", "11")
    monkeypatch.setenv("PIPE_ID_RESPONDIDOS_PIPELINE_LINKEDIN", "12")
    monkeypatch.setenv("PIPE_ID_ABORDADOS_PIPELINE_INSTAGRAM", "21")
    monkeypatch.setenv("PIPE_ID_RESPONDIDOS_PIPELINE_INSTAGRAM", "22")
    monkeypatch.setenv("PIPE_ID_ETIQUETA_NEGOCIO_LINKEDIN", "101")
    monkeypatch.setenv("PIPE_ID_ETIQUETA_NEGOCIO_INDICACAO", "102")

    s = config.Settings()

    assert s.pipe_token == "tok"
    assert s.pipe_base_url_v2 == "https://x.pipedrive.com/api/v2"
    assert s.pipe_id_pipeline_instagram == 3
    assert s.pipe_id_abordados_pipeline_linkedin == 11
    assert s.pipe_id_respondidos_pipeline_linkedin == 12
    assert s.pipe_id_abordados_pipeline_instagram == 21
    assert s.pipe_id_respondidos_pipeline_instagram == 22
    assert s.pipe_id_etiqueta_negocio_linkedin == 101
    assert s.pipe_id_etiqueta_negocio_indicacao == 102

    monkeypatch.setenv("PIPE_TOKEN", "")
    monkeypatch.delenv("PIPE_ID_PIPELINE_INSTAGRAM", raising=False)

    s = config.Settings()

    assert s.pipe_token is None
    assert s.pipe_id_pipeline_instagram is None


def test_pipe_id_inscrito_pipeline_linkedin_vem_do_env(monkeypatch):
    monkeypatch.setenv("PIPE_ID_INSCRITO_PIPELINE_LINKEDIN", "7")

    s = config.Settings()

    assert s.pipe_id_inscrito_pipeline_linkedin == 7

    monkeypatch.delenv("PIPE_ID_INSCRITO_PIPELINE_LINKEDIN", raising=False)

    assert config.Settings().pipe_id_inscrito_pipeline_linkedin is None


def test_schema_vem_de_nome_schema(monkeypatch):
    monkeypatch.setenv("NOME_SCHEMA", "dash_x")
    monkeypatch.setenv("SUPABASE_SCHEMA", "dash2")

    s = config.Settings()

    assert s.supabase_schema == "dash_x"

    monkeypatch.delenv("NOME_SCHEMA", raising=False)

    assert config.Settings().supabase_schema == "dash_new"


def test_etiqueta_pessoa_le_env_pelo_canal_e_nome_da_conta(monkeypatch):
    monkeypatch.setenv("PIPE_ID_ETIQUETA_PESSOA_LINKEDIN_LETICIA_SOUZA", "55")
    monkeypatch.setenv("PIPE_ID_ETIQUETA_PESSOA_INSTAGRAM_JACOB", "66")
    monkeypatch.delenv("PIPE_ID_ETIQUETA_PESSOA_LINKEDIN_MARY", raising=False)

    assert config.etiqueta_pessoa("linkedin", "Letícia Souza") == 55
    assert config.etiqueta_pessoa("instagram", "jacob") == 66
    assert config.etiqueta_pessoa("linkedin", "Mary") is None
