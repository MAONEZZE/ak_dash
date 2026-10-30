"""Configuração via variáveis de ambiente. Nada de credencial ou ID fixado no código."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import time

from dotenv import load_dotenv

load_dotenv()


def _cors_origins() -> list[str]:
    bruto = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    return [origem.strip() for origem in bruto.split(",") if origem.strip()]


@dataclass(frozen=True)
class Settings:
    supabase_url: str | None = field(default_factory=lambda: os.getenv("SUPABASE_URL"))
    supabase_service_key: str | None = field(
        default_factory=lambda: os.getenv("SUPABASE_SERVICE_KEY")
    )
    supabase_jwt_secret: str | None = field(
        default_factory=lambda: os.getenv("SUPABASE_JWT_SECRET")
    )
    supabase_schema: str = field(default_factory=lambda: os.getenv("SUPABASE_SCHEMA", "dash2"))
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
    planilha_sellers_id: str | None = field(
        default_factory=lambda: os.getenv("PLANILHA_SELLERS_ID") or None
    )
    planilha_sdrs_id: str | None = field(
        default_factory=lambda: os.getenv("PLANILHA_SDRS_ID") or None
    )
    planilha_closers_id: str | None = field(
        default_factory=lambda: os.getenv("PLANILHA_CLOSERS_ID") or None
    )
    planilha_dripify_id: str | None = field(
        default_factory=lambda: os.getenv("PLANILHA_DRIPIFY_ID") or None
    )
    planilha_financeiro_id: str | None = field(
        default_factory=lambda: os.getenv("PLANILHA_FINANCEIRO_ID") or None
    )
    planilha_financeiro_ano: int = field(
        default_factory=lambda: int(os.getenv("PLANILHA_FINANCEIRO_ANO", "2026"))
    )


settings = Settings()
