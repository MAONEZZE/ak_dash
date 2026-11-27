"""Cliente mínimo da API v2 do Pipedrive, só leitura. Erro de rede/HTTP ou falta de configuração sobem como PipedriveIndisponivel; quem chama decide como degradar."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Callable, TypeVar

import httpx

from app.config import settings
from app.fontes import banco

logger = logging.getLogger(__name__)

T = TypeVar("T")

TAMANHO_PAGINA = 500
LOTE_PESSOAS = 100
# Espera antes de repetir uma chamada recusada por limite de taxa (429); a janela do Pipedrive é de 2s.
ESPERA_429_SEGUNDOS = 2.0
TENTATIVAS_429 = 4


class PipedriveIndisponivel(Exception):
    """Pipedrive fora do ar, recusou a chamada ou não está configurado."""


def _rfc3339(momento: datetime) -> str:
    return momento.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get(caminho: str, params: dict[str, str], versao: str = "v2") -> dict:
    base = settings.pipe_base_url_v1 if versao == "v1" else settings.pipe_base_url_v2
    if not settings.pipe_token or not base:
        raise PipedriveIndisponivel(f"Pipedrive não configurado (PIPE_TOKEN/PIPE_BASE_URL_{versao.upper()})")
    try:
        resposta = httpx.get(
            f"{base}{caminho}",
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


def negocios_atuais_no_estagio(id_estagio: int) -> list[dict]:
    """Negócios que estão hoje no estágio (abertos, ganhos e perdidos; não excluídos), sem filtro de data."""
    return [n for pagina in _paginas("/deals", {"stage_id": str(id_estagio)}) for n in pagina]


def negocios_ganhos_desde(inicio: datetime) -> list[dict]:
    """Negócios ganhos atualizados desde `inicio` (ganhar atualiza update_time, então todo ganho no período vem)."""
    return [
        negocio
        for pagina in _paginas("/deals", {"status": "won", "updated_since": _rfc3339(inicio)})
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


def negocios_atualizados_desde(desde: datetime) -> list[dict]:
    """Todos os negócios (qualquer pipeline e status) atualizados desde `desde`. Mudar de estágio atualiza update_time."""
    return [n for pagina in _paginas("/deals", {"updated_since": _rfc3339(desde)}) for n in pagina]


def _get_esperando_limite(caminho: str, params: dict[str, str], versao: str) -> dict:
    """`_get` que, recusado por limite de taxa (429), espera a janela e tenta de novo. Uso do worker, que faz milhares de chamadas."""
    for tentativa in range(1, TENTATIVAS_429 + 1):
        try:
            return _get(caminho, params, versao)
        except PipedriveIndisponivel as exc:
            causa = exc.__cause__
            limite = isinstance(causa, httpx.HTTPStatusError) and causa.response.status_code == 429
            if not limite or tentativa == TENTATIVAS_429:
                raise
            time.sleep(ESPERA_429_SEGUNDOS)
    raise AssertionError("inalcançável")


def mudancas_de_estagio(id_negocio: int) -> list[dict]:
    """Mudanças de `stage_id` do negócio (histórico /v1/deals/{id}/flow), da mais antiga à mais nova.

    Cada uma: {"de": id do estágio anterior, "para": id do novo, "em": "AAAA-MM-DDTHH:MM:SSZ"} — o
    `log_time` do Pipedrive vem em UTC, sem fuso.
    """
    mudancas: list[dict] = []
    inicio = 0
    while True:
        corpo = _get_esperando_limite(
            f"/deals/{id_negocio}/flow", {"items": "dealChange", "limit": str(TAMANHO_PAGINA), "start": str(inicio)}, "v1"
        )
        for item in corpo.get("data") or []:
            dados = item.get("data") or {}
            if item.get("object") == "dealChange" and dados.get("field_key") == "stage_id" and dados.get("log_time"):
                mudancas.append({
                    "de": int(dados["old_value"]) if dados.get("old_value") else None,
                    "para": int(dados["new_value"]),
                    "em": dados["log_time"].replace(" ", "T") + "Z",
                })
        paginacao = (corpo.get("additional_data") or {}).get("pagination") or {}
        if not paginacao.get("more_items_in_collection"):
            break
        inicio = paginacao.get("next_start") or inicio + TAMANHO_PAGINA
    return sorted(mudancas, key=lambda m: m["em"])


def etiquetas_de_negocio() -> dict[int, str]:
    """Id → texto de cada etiqueta de negócio (campo `label` de /v1/dealFields)."""
    corpo = _get("/dealFields", {"limit": "500"}, versao="v1")
    for campo in corpo.get("data") or []:
        if campo.get("key") == "label":
            return {int(o["id"]): o["label"] for o in campo.get("options") or []}
    return {}


def _etiquetas_por_id(caminho: str, ids: list[int]) -> dict[int, tuple[int, ...]]:
    unicos = sorted(set(ids))
    resultado = {}
    for i in range(0, len(unicos), LOTE_PESSOAS):
        lote = unicos[i:i + LOTE_PESSOAS]
        for pagina in _paginas(caminho, {"ids": ",".join(str(x) for x in lote)}):
            for p in pagina:
                resultado[p["id"]] = tuple(p.get("label_ids") or [])
    return resultado


def etiquetas_das_pessoas(ids: list[int]) -> dict[int, tuple[int, ...]]:
    """Etiquetas (label_ids) de cada pessoa. Ids repetidos são pedidos uma vez só."""
    return _etiquetas_por_id("/persons", ids)


def etiquetas_dos_negocios(ids: list[int]) -> dict[int, tuple[int, ...]]:
    """Etiquetas (label_ids) de cada negócio. Ids repetidos são pedidos uma vez só."""
    return _etiquetas_por_id("/deals", ids)


def ou_vazio(calcular: Callable[[], T], vazio: T, mensagem: str) -> T:
    """Roda `calcular`; Pipedrive fora do ar ou sem configuração → loga `mensagem`, registra a falha 'pipedrive' (aviso na tela, sem cache) e devolve `vazio`."""
    try:
        return calcular()
    except PipedriveIndisponivel:
        logger.warning(mensagem, exc_info=True)
        banco.registrar_falha("pipedrive")
        return vazio
