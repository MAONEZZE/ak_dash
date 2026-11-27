"""Configuração via variáveis de ambiente. Nada de credencial ou ID fixado no código."""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import time

from dotenv import load_dotenv

load_dotenv()


def _cors_origins() -> list[str]:
    bruto = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    return [origem.strip() for origem in bruto.split(",") if origem.strip()]


def _int_env(nome: str) -> int | None:
    valor = os.getenv(nome)
    if valor is None or not valor.strip():
        return None
    return int(valor)


@dataclass(frozen=True)
class Settings:
    supabase_url: str | None = field(default_factory=lambda: os.getenv("SUPABASE_URL"))
    supabase_service_key: str | None = field(
        default_factory=lambda: os.getenv("SUPABASE_SERVICE_KEY")
    )
    supabase_jwt_secret: str | None = field(
        default_factory=lambda: os.getenv("SUPABASE_JWT_SECRET")
    )
    supabase_schema: str = field(default_factory=lambda: os.getenv("NOME_SCHEMA", "dash_new"))
    # Segundo Supabase (futuro: Inscritos/Aprovados). Em branco = não chama,
    # cards mostram "—", sem erro — nunca derruba o endpoint /geral.
    supabase_inscricoes_url: str | None = field(
        default_factory=lambda: os.getenv("SUPABASE_INSCRICOES_URL")
    )
    supabase_inscricoes_service_key: str | None = field(
        default_factory=lambda: os.getenv("SUPABASE_INSCRICOES_SERVICE_KEY")
    )
    supabase_inscricoes_schema: str | None = field(
        default_factory=lambda: os.getenv("SUPABASE_INSCRICOES_SCHEMA")
    )
    cors_origins: list[str] = field(default_factory=_cors_origins)
    cache_ttl_metricas_segundos: int = field(
        default_factory=lambda: int(os.getenv("CACHE_TTL_METRICAS_SEGUNDOS", "60"))
    )
    # Era 3600 (1h) — alto demais: uma coluna editada em dash.users ou
    # dash.metricas_cargo (nome, cargo, active, imagem_url) ficava até 1h
    # sem aparecer no frontend, apesar do polling de 60s + botão "Atualizar"
    # (a staleness é do cache do BFF, não do frontend). Alinhado aos outros
    # caches — mesma cadência que a decisão de produto já previa.
    cache_ttl_pessoas_segundos: int = field(
        default_factory=lambda: int(os.getenv("CACHE_TTL_PESSOAS_SEGUNDOS", "60"))
    )
    # Workers das planilhas (app/workers.py): só sobem com WORKERS_ATIVOS=true;
    # worker sem ID de planilha não sobe.
    workers_ativos: bool = field(
        default_factory=lambda: os.getenv("WORKERS_ATIVOS", "false").strip().lower() == "true"
    )
    worker_intervalo_segundos: float = field(
        default_factory=lambda: float(os.getenv("WORKER_INTERVALO_SEGUNDOS", "5"))
    )
    # Expediente (America/Sao_Paulo) — base de "Horas restantes" da aba Dashboard.
    expediente_inicio: time = field(
        default_factory=lambda: time.fromisoformat(os.getenv("EXPEDIENTE_INICIO", "10:00"))
    )
    expediente_fim: time = field(
        default_factory=lambda: time.fromisoformat(os.getenv("EXPEDIENTE_FIM", "19:00"))
    )
    google_service_account_json: str | None = field(
        default_factory=lambda: os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or None
    )
    planilha_sdrs_id: str | None = field(
        default_factory=lambda: os.getenv("PLANILHA_SDRS_ID") or None
    )
    planilha_closers_id: str | None = field(
        default_factory=lambda: os.getenv("PLANILHA_CLOSERS_ID") or None
    )
    planilha_funil_linkedin_id: str | None = field(
        default_factory=lambda: os.getenv("PLANILHA_FUNIL_LINKEDIN_ID") or None
    )
    planilha_funil_instagram_id: str | None = field(
        default_factory=lambda: os.getenv("PLANILHA_FUNIL_INSTAGRAM_ID") or None
    )
    planilha_financeiro_id: str | None = field(
        default_factory=lambda: os.getenv("PLANILHA_FINANCEIRO_ID") or None
    )
    planilha_financeiro_ano: int = field(
        default_factory=lambda: int(os.getenv("PLANILHA_FINANCEIRO_ANO", "2026"))
    )
    planilha_logs_id: str | None = field(
        default_factory=lambda: os.getenv("PLANILHA_LOGS_ID") or None
    )
    # Pipedrive (API v2), lido ao vivo pelo BFF — docs/plans/pipedrive-fonte-de-dados.md.
    pipe_token: str | None = field(default_factory=lambda: os.getenv("PIPE_TOKEN") or None)
    pipe_base_url_v2: str | None = field(
        default_factory=lambda: (os.getenv("PIPE_BASE_URL_V2") or "").rstrip("/") or None
    )
    pipe_base_url_v1: str | None = field(
        default_factory=lambda: (os.getenv("PIPE_BASE_URL_V1") or "").rstrip("/") or None
    )
    pipe_id_pipeline_instagram: int | None = field(
        default_factory=lambda: _int_env("PIPE_ID_PIPELINE_INSTAGRAM")
    )
    # Coluna "Oportunidade feita" do pipeline principal (akeel 2.0) — Números Captados do Funil Instagram.
    pipe_id_oportunidades_pipeline_principal: int | None = field(
        default_factory=lambda: _int_env("PIPE_ID_OPORTUNIDADES_PIPELINE_PRINCIPAL")
    )
    pipe_id_abordados_pipeline_principal: int | None = field(
        default_factory=lambda: _int_env("PIPE_ID_ABORDADOS_PIPELINE_PRINCIPAL")
    )
    pipe_id_respondidos_pipeline_principal: int | None = field(
        default_factory=lambda: _int_env("PIPE_ID_RESPONDIDOS_PIPELINE_PRINCIPAL")
    )
    pipe_id_abordados_pipeline_instagram: int | None = field(
        default_factory=lambda: _int_env("PIPE_ID_ABORDADOS_PIPELINE_INSTAGRAM")
    )
    pipe_id_respondidos_pipeline_instagram: int | None = field(
        default_factory=lambda: _int_env("PIPE_ID_RESPONDIDOS_PIPELINE_INSTAGRAM")
    )
    pipe_id_etiqueta_negocio_linkedin: int | None = field(
        default_factory=lambda: _int_env("PIPE_ID_ETIQUETA_NEGOCIO_LINKEDIN")
    )
    # Etiqueta de negócio PROSP_INSTA.
    pipe_id_etiqueta_negocio_instagram: int | None = field(
        default_factory=lambda: _int_env("PIPE_ID_ETIQUETA_NEGOCIO_INSTAGRAM")
    )
    pipe_id_etiqueta_negocio_indicacao: int | None = field(
        default_factory=lambda: _int_env("PIPE_ID_ETIQUETA_NEGOCIO_INDICACAO")
    )
    # Colunas de onboarding do pipeline principal — página Funil Evento (docs/plans/funil-evento.md).
    # Coluna "3. Inscrito" do pipeline akeel 2.0 — etapa Inscritos do Funil Evento.
    pipe_id_inscrito_pipeline_principal: int | None = field(
        default_factory=lambda: _int_env("PIPE_ID_INSCRITO_PIPELINE_PRINCIPAL")
    )
    pipe_id_onboarding_agendado_pipeline_principal: int | None = field(
        default_factory=lambda: _int_env("PIPE_ID_ONBOARDING_AGENDADO_PIPELINE_PRINCIPAL")
    )
    pipe_id_onboarding_realizado_pipeline_principal: int | None = field(
        default_factory=lambda: _int_env("PIPE_ID_ONBOARDING_REALIZADO_PIPELINE_PRINCIPAL")
    )
    # Chave do campo customizado "Almoço" do negócio (tipo set) — card Almoços Pagos do Funil SDR.
    pipe_id_campo_almoco: str | None = field(
        default_factory=lambda: os.getenv("PIPE_ID_CAMPO_ALMOCO") or None
    )


settings = Settings()


def etiqueta_pessoa(canal: str, conta: str) -> int | None:
    """Id da etiqueta de pessoa que marca a conta no Pipedrive: env PIPE_ID_ETIQUETA_PESSOA_<CANAL>_<CONTA> (conta sem acento, maiúscula, o que não é letra/dígito vira _). Lida na hora, para contas novas não exigirem restart."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", conta) if not unicodedata.combining(c)
    )
    sufixo = re.sub(r"[^A-Z0-9]+", "_", sem_acento.upper()).strip("_")
    return _int_env(f"PIPE_ID_ETIQUETA_PESSOA_{canal.upper()}_{sufixo}")


PREFIXO_DONO_SDR = "PIPE_ID_USUARIO_SDR_"


def donos_sdr() -> dict[int, str]:
    """owner_id do Pipedrive de cada SDR → nome em minúsculas, das envs PIPE_ID_USUARIO_SDR_<NOME> (ex.: _JUCA=28932026 → "juca",
    comparado com `normalizar(users.nome)`). Lida na hora, para SDR novo não exigir restart."""
    return {
        int(valor): nome[len(PREFIXO_DONO_SDR):].lower()
        for nome, valor in os.environ.items()
        if nome.startswith(PREFIXO_DONO_SDR) and valor.strip()
    }
