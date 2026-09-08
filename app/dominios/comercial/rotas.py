from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import exigir_usuario
from app.cache import obter_ou_calcular
from app.config import settings
from app.dominios.comercial.banco import buscar_historico
from app.dominios.comercial.calculo import montar_resposta_comercial
from app.dominios.comercial.planilha import PlanilhaParseada, parsear_planilha
from app.dominios.pessoas.banco import listar_ativas
from app.fontes.drive import listar_planilhas
from app.fontes.planilha import ler_aba
from app.periodo import hoje_sp, resolver_periodo

router = APIRouter(tags=["comercial"])


@dataclass(frozen=True)
class _CargaPlanilhas:
    planilhas: list[PlanilhaParseada]
    avisos: list[str]


def _carregar_planilhas_mes_corrente() -> _CargaPlanilhas:
    avisos: list[str] = []
    planilhas = []
    for arquivo in listar_planilhas():
        linhas = ler_aba(arquivo.id)
        parseada = parsear_planilha(arquivo.nome, linhas, avisos)
        if parseada:
            planilhas.append(parseada)
    return _CargaPlanilhas(planilhas=planilhas, avisos=avisos)


def _resolver_periodo_ou_400(granularidade: str, periodo: str):
    try:
        return resolver_periodo(granularidade, periodo)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"erro": {"codigo": "parametro_invalido", "mensagem": str(exc)}},
        ) from exc


def _comercial(granularidade: str, periodo_str: str, pessoas: list[str] | None, funcao: str) -> dict:
    periodo = _resolver_periodo_ou_400(granularidade, periodo_str)
    emails_filtro = set(pessoas) if pessoas else None

    carga = obter_ou_calcular(
        "planilhas:mes_corrente",
        settings.cache_ttl_planilha_segundos,
        _carregar_planilhas_mes_corrente,
    )
    hoje = hoje_sp()

    mes_anterior_fim = (hoje.year, hoje.month - 1) if hoje.month > 1 else (hoje.year - 1, 12)
    historico = []
    if (periodo.inicio.year, periodo.inicio.month) <= mes_anterior_fim:
        historico = buscar_historico(
            funcao, periodo.inicio.year, periodo.inicio.month, mes_anterior_fim[0], mes_anterior_fim[1]
        )

    cadastro_nomes = {
        p.email: p.nome
        for p in obter_ou_calcular(
            "pessoas:ativas", settings.cache_ttl_historico_segundos, listar_ativas
        )
    }

    return montar_resposta_comercial(
        periodo=periodo,
        funcao=funcao,
        planilhas_mes_corrente=carga.planilhas,
        avisos_estruturais=list(carga.avisos),
        historico=historico,
        cadastro_nomes=cadastro_nomes,
        emails_filtro=emails_filtro,
        hoje=hoje,
    )


@router.get("/comercial/sdr")
def get_comercial_sdr(
    granularidade: str = Query(...),
    periodo: str = Query(...),
    pessoas: list[str] | None = Query(default=None),
    _usuario: dict = Depends(exigir_usuario),
) -> dict:
    return _comercial(granularidade, periodo, pessoas, funcao="sdr")


@router.get("/comercial/closer")
def get_comercial_closer(
    granularidade: str = Query(...),
    periodo: str = Query(...),
    pessoas: list[str] | None = Query(default=None),
    _usuario: dict = Depends(exigir_usuario),
) -> dict:
    return _comercial(granularidade, periodo, pessoas, funcao="closer")
