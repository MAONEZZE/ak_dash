"""Configuração via variáveis de ambiente. Nada de credencial ou ID fixado no código."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _cors_origins() -> list[str]:
    bruto = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    return [origem.strip() for origem in bruto.split(",") if origem.strip()]


@dataclass(frozen=True)
class Settings:
    google_service_account_json: str | None = field(
        default_factory=lambda: os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    )
    drive_pasta_id: str | None = field(default_factory=lambda: os.getenv("DRIVE_PASTA_ID"))
    planilhas_local_dir: str | None = field(
        default_factory=lambda: os.getenv("PLANILHAS_LOCAL_DIR")
    )
    supabase_url: str | None = field(default_factory=lambda: os.getenv("SUPABASE_URL"))
    supabase_service_key: str | None = field(
        default_factory=lambda: os.getenv("SUPABASE_SERVICE_KEY")
    )
    supabase_jwt_secret: str | None = field(
        default_factory=lambda: os.getenv("SUPABASE_JWT_SECRET")
    )
    cors_origins: list[str] = field(default_factory=_cors_origins)
    cache_ttl_planilha_segundos: int = field(
        default_factory=lambda: int(os.getenv("CACHE_TTL_PLANILHA_SEGUNDOS", "300"))
    )
    cache_ttl_historico_segundos: int = field(
        default_factory=lambda: int(os.getenv("CACHE_TTL_HISTORICO_SEGUNDOS", "3600"))
    )


settings = Settings()
