"""Cliente mínimo do Supabase via REST (PostgREST) — só leitura, sem ORM.

Tabelas reais vivem no schema `dash` (não `public`) — daí o header
`Accept-Profile`, que o PostgREST exige pra selecionar schema fora do padrão.

Sem credencial configurada, ou se a consulta falhar (tabela ainda não
existe, coluna ainda não existe, rede fora, RLS bloqueando), devolve lista
vazia — todo domínio decide sozinho como degradar "sem dado" a partir daí.
Isso agora é o caminho comum, não a exceção: todo o BFF lê do Supabase.

PostgREST devolve no máximo 1000 linhas por request por padrão — `query()`
pagina sozinho com `limit`/`offset` até a página vir incompleta, então quem
chama nunca precisa se preocupar com truncamento silencioso.

Falha de rede (timeout, conexão caída) ganha UMA nova tentativa antes de
degradar — o Supabase às vezes passa de 10s numa consulta que normalmente
leva 0,3s. Toda degradação conta em `falhas_na_thread()`, que o cache usa
pra não guardar um resultado vazio por falha como se fosse dado real.
"""
from __future__ import annotations

import logging
import threading

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_TAMANHO_PAGINA = 1000
_TENTATIVAS = 2

_local = threading.local()


def falhas_na_thread() -> int:
    """Quantas consultas degradaram pra vazio nesta thread desde que ela subiu.

    Por thread porque o FastAPI roda endpoint síncrono num pool de threads:
    um contador global pegaria a falha de outra requisição.
    """
    return getattr(_local, "falhas", 0)


def _get(url: str, params: dict[str, str], headers: dict[str, str]) -> httpx.Response:
    for tentativa in range(1, _TENTATIVAS + 1):
        try:
            return httpx.get(url, params=params, headers=headers, timeout=10.0)
        except httpx.TransportError:
            if tentativa == _TENTATIVAS:
                raise
            logger.info("Consulta Supabase %s falhou na tentativa %d — tentando de novo", url, tentativa)
    raise AssertionError("inalcançável")


def query(
    tabela: str,
    filtros: dict[str, str] | None = None,
    schema: str = "dash",
    colunas: str = "*",
    *,
    url_base: str | None = None,
    service_key: str | None = None,
) -> list[dict]:
    """`filtros` é passado direto pro PostgREST — cada valor já inclui o operador

    (ex: `{"active": "eq.true"}`, `{"id_user": "in.(1,2,3)"}`), sem prefixo
    automático de `eq.`. Duas condições no mesmo campo (ex: `data` com
    `gte.`/`lte.`) vão juntas em `{"and": "(data.gte.X,data.lte.Y)"}` — chave
    de dict não repete.

    `url_base`/`service_key` permitem apontar pra um segundo projeto Supabase
    (ver `settings.supabase_inscricoes_*`); por padrão usa o projeto principal.
    """
    url_base = url_base if url_base is not None else settings.supabase_url
    service_key = service_key if service_key is not None else settings.supabase_service_key
    if not url_base or not service_key:
        return []

    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Accept-Profile": schema,
    }

    linhas: list[dict] = []
    offset = 0
    try:
        while True:
            params: dict[str, str] = {
                "select": colunas,
                **(filtros or {}),
                "limit": str(_TAMANHO_PAGINA),
                "offset": str(offset),
            }
            resposta = _get(f"{url_base}/rest/v1/{tabela}", params, headers)
            resposta.raise_for_status()
            pagina = resposta.json()
            linhas.extend(pagina)
            if len(pagina) < _TAMANHO_PAGINA:
                break
            offset += _TAMANHO_PAGINA
        return linhas
    except httpx.HTTPError:
        _local.falhas = falhas_na_thread() + 1
        logger.warning("Consulta Supabase à tabela '%s' falhou — degradando para vazio", tabela, exc_info=True)
        return []
