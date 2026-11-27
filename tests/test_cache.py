import threading
import time

import pytest

from app import cache


@pytest.fixture(autouse=True)
def _cache_limpo():
    cache.invalidar()
    yield
    cache.invalidar()


def _vencer(chave):
    _, valor = cache._armazenamento[chave]
    cache._armazenamento[chave] = (time.monotonic() - 1, valor)


def _esperar_recalculo(chave, timeout=2.0):
    fim = time.monotonic() + timeout
    while time.monotonic() < fim:
        with cache._trava:
            if chave not in cache._recalculando:
                return
        time.sleep(0.01)
    raise AssertionError("recálculo não terminou")


def test_valor_vencido_volta_na_hora_e_e_recalculado_no_fundo():
    valores = iter([1, 2])
    cache.obter_ou_calcular("k", 60, lambda: next(valores))
    _vencer("k")

    assert cache.obter_ou_calcular("k", 60, lambda: next(valores)) == 1  # não espera o recálculo
    _esperar_recalculo("k")
    assert cache.obter_ou_calcular("k", 60, lambda: 99) == 2


def test_recalculo_no_fundo_roda_uma_vez_por_chave():
    cache.obter_ou_calcular("k", 60, lambda: 1)
    _vencer("k")
    liberar = threading.Event()
    chamadas = []

    def lento():
        chamadas.append(1)
        liberar.wait(1)
        return 2

    for _ in range(5):
        cache.obter_ou_calcular("k", 60, lento)
    liberar.set()
    _esperar_recalculo("k")
    assert len(chamadas) == 1


def test_recalculo_que_falha_mantem_o_valor_antigo():
    cache.obter_ou_calcular("k", 60, lambda: 1)
    _vencer("k")

    def quebra():
        raise RuntimeError("fora do ar")

    assert cache.obter_ou_calcular("k", 60, quebra) == 1
    _esperar_recalculo("k")
    assert cache.obter_ou_calcular("k", 60, lambda: 99) == 1


def test_ttl_zero_desliga_o_cache():
    valores = iter([1, 2])
    assert cache.obter_ou_calcular("k", 0, lambda: next(valores)) == 1
    assert cache.obter_ou_calcular("k", 0, lambda: next(valores)) == 2


def test_invalidar_prefixos_apaga_so_as_chaves_dos_prefixos():
    for chave in ("vw_metricas:sdr:x", "metas", "metas-funil-sdr", "pipedrive:x", "funil:linkedin:x", "funil-sdr:x"):
        cache.obter_ou_calcular(chave, 60, lambda: "antigo")

    cache.invalidar_prefixos(("vw_metricas:", "metas", "funil:"))

    assert set(cache._armazenamento) == {"pipedrive:x", "funil-sdr:x"}


def test_chave_vazia_pedida_ao_mesmo_tempo_calcula_uma_vez():
    chamadas = []
    liberar = threading.Event()

    def lento():
        chamadas.append(1)
        liberar.wait(1)
        return "ok"

    resultados = []
    threads = [threading.Thread(target=lambda: resultados.append(cache.obter_ou_calcular("k", 60, lento))) for _ in range(4)]
    for t in threads:
        t.start()
    time.sleep(0.05)
    liberar.set()
    for t in threads:
        t.join()
    assert resultados == ["ok"] * 4
    assert len(chamadas) == 1


def test_marcar_vencido_mantem_o_valor_e_recalcula_no_fundo():
    cache.obter_ou_calcular("pipedrive:x", 60, lambda: "antigo")
    cache.obter_ou_calcular("metas", 60, lambda: "metas")

    cache.marcar_vencido(("pipedrive:",))

    assert cache.obter_ou_calcular("pipedrive:x", 60, lambda: "novo") == "antigo"
    _esperar_recalculo("pipedrive:x")
    assert cache.obter_ou_calcular("pipedrive:x", 60, lambda: "outro") == "novo"
    assert cache.obter_ou_calcular("metas", 60, lambda: "outro") == "metas"
