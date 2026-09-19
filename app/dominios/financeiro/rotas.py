from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import exigir_usuario
from app.cache import obter_ou_calcular
from app.config import settings
from app.dominios.financeiro.banco import buscar_vendas_detalhadas
from app.dominios.financeiro.calculo import montar_resposta_financeiro
from app.periodo import Periodo, hoje_sp, resolver_periodo, semana_iso

router = APIRouter(tags=["financeiro"])


def _valor_atual(granularidade: str, hoje: date) -> str:
    if granularidade == "dia":
        return hoje.isoformat()
    if granularidade == "semana":
        return semana_iso(hoje)
    if granularidade == "ano":
        return str(hoje.year)
    return f"{hoje.year:04d}-{hoje.month:02d}"


@router.get("/financeiro")
def get_financeiro(
    granularidade: str = Query(default="mes"),
    periodo: str = Query(default="atual"),
    _usuario: dict = Depends(exigir_usuario),
) -> dict:
    hoje = hoje_sp()
    valor = periodo if periodo != "atual" else _valor_atual(granularidade, hoje)
    try:
        periodo_pedido = resolver_periodo(granularidade, valor)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"erro": {"codigo": "parametro_invalido", "mensagem": str(exc)}},
        ) from exc

    fim_capado = min(periodo_pedido.fim, hoje)
    periodo_saida = Periodo(periodo_pedido.granularidade, periodo_pedido.inicio, fim_capado)

    chave_periodo = f"{periodo_saida.inicio.isoformat()}:{periodo_saida.fim.isoformat()}"
    vendas = obter_ou_calcular(
        f"financeiro:{chave_periodo}",
        settings.cache_ttl_metricas_segundos,
        lambda: buscar_vendas_detalhadas(periodo_saida.inicio, periodo_saida.fim),
    )
    return montar_resposta_financeiro(periodo_saida, vendas)
