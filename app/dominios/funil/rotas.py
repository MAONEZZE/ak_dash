from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import exigir_usuario
from app.cache import obter_ou_calcular
from app.config import settings
from app.dominios.funil.banco import buscar_contas
from app.dominios.pessoas.banco import listar_ativas
from app.fontes.banco import iniciar_registro_de_falhas, tabelas_com_falha
from app.metas import buscar_metas
from app.periodo import resolver_periodo

router = APIRouter(tags=["funil"])

CANAIS = ("linkedin", "instagram")


def _resolver_periodo_ou_400(granularidade: str, periodo: str):
    try:
        return resolver_periodo(granularidade, periodo)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"erro": {"codigo": "parametro_invalido", "mensagem": str(exc)}},
        ) from exc


@router.get("/funil/{canal}")
def get_funil(
    canal: str,
    granularidade: str = Query(...),
    periodo: str = Query(...),
    _usuario: dict = Depends(exigir_usuario),
) -> dict:
    if canal not in CANAIS:
        raise HTTPException(
            status_code=404,
            detail={"erro": {"codigo": "canal_invalido", "mensagem": "canal deve ser linkedin ou instagram"}},
        )
    iniciar_registro_de_falhas()
    p = _resolver_periodo_ou_400(granularidade, periodo)
    contas = obter_ou_calcular(
        f"funil:{canal}:{p.inicio}:{p.fim}",
        settings.cache_ttl_metricas_segundos,
        lambda: buscar_contas(canal, p.inicio, p.fim),
    )

    # Meta de números captados do período: soma das metas dos sellers ativos ligados às contas do canal.
    ids_seller = {c.id_seller for c in contas if c.id_seller is not None}
    ids = [
        int(pessoa.id)
        for pessoa in obter_ou_calcular("pessoas:ativas", settings.cache_ttl_pessoas_segundos, listar_ativas)
        if pessoa.cargo == "seller" and int(pessoa.id) in ids_seller
    ]
    metas = obter_ou_calcular("metas", settings.cache_ttl_metricas_segundos, buscar_metas)
    meta = metas.somar(p.inicio, p.fim, ids, "seller", "numeros_captados") if ids else None

    return {
        "periodo": {"granularidade": p.granularidade, "inicio": p.inicio.isoformat(), "fim": p.fim.isoformat()},
        "avisos": [f"fonte_indisponivel:{t}" for t in tabelas_com_falha()],
        "contas": [
            {"id_conta": str(c.id_conta), "nome": c.nome, "metricas": c.metricas, "serie": c.serie} for c in contas
        ],
        "meta_numeros_captados": meta,
    }
