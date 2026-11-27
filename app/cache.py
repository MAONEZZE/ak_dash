"""Cache em memória com TTL — sem dependência externa (Redis etc. não se justifica aqui).

Valor vencido NÃO faz ninguém esperar: a requisição recebe o valor antigo na hora e o
recálculo roda numa thread de fundo (um por chave). Só espera quem pede uma chave que
nunca foi calculada ou que foi invalidada — a TV, que pede as mesmas chaves a cada 60s,
quase nunca cai nesse caso.

Os workers invalidam só as chaves das tabelas que gravaram (`invalidar_prefixos`),
nunca o cache inteiro: uma edição na planilha de SDRs não pode jogar fora o resultado
do Pipedrive.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Iterable, TypeVar

from app.fontes.banco import falhas_na_thread

T = TypeVar("T")

logger = logging.getLogger(__name__)

_armazenamento: dict[str, tuple[float, object]] = {}
_recalculando: set[str] = set()
_travas_por_chave: dict[str, threading.Lock] = {}
_trava = threading.Lock()


def _calcular_e_guardar(chave: str, ttl_segundos: float, calcular: Callable[[], T]) -> T:
    falhas_antes = falhas_na_thread()
    valor = calcular()
    # Consulta que degradou pra vazio não vira cache: senão um timeout de
    # rede deixava o dash sem dado (ou "Meta não cadastrada") pelo TTL inteiro.
    # Sem cache, a próxima requisição tenta de novo.
    if falhas_na_thread() == falhas_antes:
        _armazenamento[chave] = (time.monotonic() + ttl_segundos, valor)
    return valor


def _recalcular_no_fundo(chave: str, ttl_segundos: float, calcular: Callable[[], object]) -> None:
    with _trava:
        if chave in _recalculando:
            return
        _recalculando.add(chave)

    def rodar() -> None:
        try:
            _calcular_e_guardar(chave, ttl_segundos, calcular)
        except Exception:
            logger.warning("Recálculo em segundo plano de '%s' falhou; segue o valor antigo", chave, exc_info=True)
        finally:
            with _trava:
                _recalculando.discard(chave)

    threading.Thread(target=rodar, name=f"cache:{chave}", daemon=True).start()


def obter_ou_calcular(chave: str, ttl_segundos: float, calcular: Callable[[], T]) -> T:
    if ttl_segundos <= 0:  # TTL 0 = cache desligado (dev): sempre o dado fresco
        return calcular()
    entrada = _armazenamento.get(chave)
    if entrada is None:
        # Duas requisições (ou duas tarefas de `em_paralelo`) pedindo a mesma chave ainda vazia:
        # a segunda espera a primeira em vez de repetir a consulta.
        with _trava:
            trava_da_chave = _travas_por_chave.setdefault(chave, threading.Lock())
        with trava_da_chave:
            entrada = _armazenamento.get(chave)
            if entrada is None:
                return _calcular_e_guardar(chave, ttl_segundos, calcular)
    expira_em, valor = entrada
    if time.monotonic() >= expira_em:
        _recalcular_no_fundo(chave, ttl_segundos, calcular)
    return valor  # type: ignore[return-value]


def invalidar(chave: str | None = None) -> None:
    if chave is None:
        _armazenamento.clear()
    else:
        _armazenamento.pop(chave, None)


def invalidar_prefixos(prefixos: Iterable[str]) -> None:
    """Apaga as chaves que começam com algum dos prefixos — a próxima requisição recalcula na hora."""
    prefixos = tuple(prefixos)
    for chave in [c for c in list(_armazenamento) if c.startswith(prefixos)]:
        _armazenamento.pop(chave, None)


def marcar_vencido(prefixos: Iterable[str]) -> None:
    """Vence as chaves dos prefixos sem apagá-las: a próxima requisição recebe o valor atual na hora
    e dispara o recálculo no fundo. Para fonte lenta (Pipedrive), em vez de `invalidar_prefixos`."""
    prefixos = tuple(prefixos)
    for chave, (_, valor) in list(_armazenamento.items()):
        if chave.startswith(prefixos):
            _armazenamento[chave] = (0.0, valor)
