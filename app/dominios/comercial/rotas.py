from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import exigir_usuario
from app.cache import obter_ou_calcular
from app.cargos import buscar_cargos
from app.config import settings
from app.dominios.comercial.banco import buscar_totais
from app.dominios.comercial.calculo import montar_resposta_comercial
from app.dominios.pessoas.banco import listar_ativas
from app.metas import buscar_metas
from app.periodo import hoje_sp, resolver_periodo

router = APIRouter(tags=["comercial"])


def _resolver_periodo_ou_400(granularidade: str, periodo: str):
    try:
        return resolver_periodo(granularidade, periodo)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"erro": {"codigo": "parametro_invalido", "mensagem": str(exc)}},
        ) from exc


def _comercial(granularidade: str, periodo_str: str, pessoas: list[str] | None, cargo: str) -> dict:
    periodo = _resolver_periodo_ou_400(granularidade, periodo_str)
    emails_filtro = set(pessoas) if pessoas else None

    todas_ativas = obter_ou_calcular(
        "pessoas:ativas", settings.cache_ttl_pessoas_segundos, listar_ativas
    )
    pessoas_cargo = [p for p in todas_ativas if p.cargo == cargo]
    ids = [int(p.id) for p in pessoas_cargo]

    chave_periodo = f"{periodo.inicio.isoformat()}:{periodo.fim.isoformat()}"
    totais = obter_ou_calcular(
        f"vw_metricas:{cargo}:{chave_periodo}",
        settings.cache_ttl_metricas_segundos,
        lambda: buscar_totais(cargo, ids, periodo.inicio, periodo.fim),
    )
    metas = obter_ou_calcular(
        f"metas:{chave_periodo}",
        settings.cache_ttl_metricas_segundos,
        lambda: buscar_metas(periodo.inicio, periodo.fim),
    )
    cargos = obter_ou_calcular("cargos", settings.cache_ttl_pessoas_segundos, buscar_cargos)

    resultado = montar_resposta_comercial(
        periodo=periodo,
        cargo=cargo,
        id_cargo=cargos.get(cargo),
        pessoas_cargo=pessoas_cargo,
        totais=totais,
        metas=metas,
        emails_filtro=emails_filtro,
        hoje=hoje_sp(),
    )
    return resultado.corpo


@router.get("/comercial/sdr")
def get_comercial_sdr(
    granularidade: str = Query(...),
    periodo: str = Query(...),
    pessoas: list[str] | None = Query(default=None),
    _usuario: dict = Depends(exigir_usuario),
) -> dict:
    return _comercial(granularidade, periodo, pessoas, cargo="sdr")


@router.get("/comercial/closer")
def get_comercial_closer(
    granularidade: str = Query(...),
    periodo: str = Query(...),
    pessoas: list[str] | None = Query(default=None),
    _usuario: dict = Depends(exigir_usuario),
) -> dict:
    return _comercial(granularidade, periodo, pessoas, cargo="closer")
