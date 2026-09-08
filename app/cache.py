"""Cache em memória com TTL — sem dependência externa (Redis etc. não se justifica aqui)."""
from __future__ import annotations

import time
from typing import Callable, TypeVar

T = TypeVar("T")

_armazenamento: dict[str, tuple[float, object]] = {}


def obter_ou_calcular(chave: str, ttl_segundos: float, calcular: Callable[[], T]) -> T:
    agora = time.monotonic()
    entrada = _armazenamento.get(chave)
    if entrada is not None:
        expira_em, valor = entrada
        if agora < expira_em:
            return valor  # type: ignore[return-value]
    valor = calcular()
    _armazenamento[chave] = (agora + ttl_segundos, valor)
    return valor


def invalidar(chave: str | None = None) -> None:
    if chave is None:
        _armazenamento.clear()
    else:
        _armazenamento.pop(chave, None)
