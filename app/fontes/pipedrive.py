"""Cliente mínimo da API v2 do Pipedrive, só leitura. Erro de rede/HTTP ou falta de configuração sobem como PipedriveIndisponivel; quem chama decide como degradar."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.config import settings

TAMANHO_PAGINA = 500


class PipedriveIndisponivel(Exception):
    """Pipedrive fora do ar, recusou a chamada ou não está configurado."""


def _rfc3339(momento: datetime) -> str:
    return momento.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get(caminho: str, params: dict[str, str]) -> dict:
    resposta = httpx.get(
        f"{settings.pipe_base_url_v2}{caminho}",
        params=params,
        headers={"x-api-token": settings.pipe_token},
        timeout=15.0,
    )
    resposta.raise_for_status()
    return resposta.json()


def _paginas(caminho: str, params: dict[str, str]):
    cursor = None
    while True:
        p = {**params, "limit": str(TAMANHO_PAGINA)}
        if cursor:
            p["cursor"] = cursor
        corpo = _get(caminho, p)
        yield corpo.get("data") or []
        cursor = (corpo.get("additional_data") or {}).get("next_cursor")
        if not cursor:
            return


def negocios_no_estagio(id_estagio: int, atualizados_desde: datetime) -> list[dict]:
    """Negócios que estão hoje no estágio e foram atualizados desde `atualizados_desde` (mudar de estágio atualiza update_time)."""
    return [
        negocio
        for pagina in _paginas("/deals", {"stage_id": str(id_estagio), "updated_since": _rfc3339(atualizados_desde)})
        for negocio in pagina
    ]
