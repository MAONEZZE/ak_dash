"""Cliente mínimo do Supabase via REST (PostgREST) — só leitura, sem ORM.

Sem credencial configurada, devolve lista vazia (histórico degrada para
"sem dado", nunca quebra o comercial do mês corrente).
"""
from __future__ import annotations

import httpx

from app.config import settings


def query(tabela: str, filtros_eq: dict | None = None) -> list[dict]:
    if not settings.supabase_url or not settings.supabase_service_key:
        return []

    params: dict[str, str] = {"select": "*"}
    for chave, valor in (filtros_eq or {}).items():
        params[chave] = f"eq.{valor}"

    resposta = httpx.get(
        f"{settings.supabase_url}/rest/v1/{tabela}",
        params=params,
        headers={
            "apikey": settings.supabase_service_key,
            "Authorization": f"Bearer {settings.supabase_service_key}",
        },
        timeout=10.0,
    )
    resposta.raise_for_status()
    return resposta.json()
