"""Configuração via variáveis de ambiente. Nada de credencial ou ID fixado no código."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

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


settings = Settings()
