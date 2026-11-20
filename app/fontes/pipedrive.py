"""Cliente mínimo da API v2 do Pipedrive, só leitura. Erro de rede/HTTP ou falta de configuração sobem como PipedriveIndisponivel; quem chama decide como degradar."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.config import settings

TAMANHO_PAGINA = 500
LOTE_PESSOAS = 100


class PipedriveIndisponivel(Exception):
    """Pipedrive fora do ar, recusou a chamada ou não está configurado."""


def _rfc3339(momento: datetime) -> str:
    return momento.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get(caminho: str, params: dict[str, str]) -> dict:
    if not settings.pipe_token or not settings.pipe_base_url_v2:
        raise PipedriveIndisponivel("Pipedrive não configurado (PIPE_TOKEN/PIPE_BASE_URL_V2)")
    try:
        resposta = httpx.get(
            f"{settings.pipe_base_url_v2}{caminho}",
            params=params,
            headers={"x-api-token": settings.pipe_token},
            timeout=15.0,
        )
        resposta.raise_for_status()
        return resposta.json()
    except httpx.HTTPError as exc:
        raise PipedriveIndisponivel(str(exc)) from exc


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


def _momento(texto: str) -> datetime:
    return datetime.fromisoformat(texto.replace("Z", "+00:00"))


def negocios_criados_desde(inicio: datetime) -> list[dict]:
    """Negócios criados a partir de `inicio` (tz-aware), do mais novo ao mais antigo. A v2 não filtra por add_time: ordena por ele e para no primeiro mais antigo que `inicio`."""
    resultado = []
    for pagina in _paginas("/deals", {"sort_by": "add_time", "sort_direction": "desc"}):
        for n in pagina:
            if _momento(n["add_time"]) < inicio:
                return resultado
            resultado.append(n)
    return resultado


def etiquetas_das_pessoas(ids: list[int]) -> dict[int, tuple[int, ...]]:
    """Etiquetas (label_ids) de cada pessoa. Ids repetidos são pedidos uma vez só."""
    unicos = sorted(set(ids))
    resultado = {}
    for i in range(0, len(unicos), LOTE_PESSOAS):
        lote = unicos[i:i + LOTE_PESSOAS]
        for pagina in _paginas("/persons", {"ids": ",".join(str(x) for x in lote)}):
            for p in pagina:
                resultado[p["id"]] = tuple(p.get("label_ids") or [])
    return resultado
