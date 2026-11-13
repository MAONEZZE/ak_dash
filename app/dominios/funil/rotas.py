from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import exigir_usuario
from app.cache import obter_ou_calcular
from app.config import settings
from app.dominios.comercial.banco import buscar_totais
from app.dominios.comercial.calculo import montar_resposta_comercial
from app.dominios.funil.banco import buscar_contas
from app.dominios.funil.calculo import METRICAS_DASHBOARD_FUNIL, recortes_dashboard
from app.dominios.pessoas.banco import listar_ativas
from app.fontes.banco import iniciar_registro_de_falhas, tabelas_com_falha
from app.metas import buscar_metas
from app.periodo import TZ_SP, hoje_sp, resolver_periodo

router = APIRouter(tags=["funil"])


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
    iniciar_registro_de_falhas()
    p = _resolver_periodo_ou_400(granularidade, periodo)
    contas = obter_ou_calcular(
        f"funil:{canal}:{p.inicio}:{p.fim}",
        settings.cache_ttl_metricas_segundos,
        lambda: buscar_contas(canal, p.inicio, p.fim),
    )
    ids_seller = sorted({c.id_seller for c in contas if c.id_seller is not None})
    pessoas_seller = [
        p
        for p in obter_ou_calcular("pessoas:ativas", settings.cache_ttl_pessoas_segundos, listar_ativas)
        if p.cargo == "seller" and int(p.id) in ids_seller
    ]
    ids = [int(p.id) for p in pessoas_seller]
    metas = obter_ou_calcular("metas", settings.cache_ttl_metricas_segundos, buscar_metas)
    seller = {"id_user": pessoas_seller[0].id, "nome": pessoas_seller[0].nome} if pessoas_seller else None
    dashboard: dict = {"seller": seller}
    for chave, rec in recortes_dashboard(hoje_sp()).items():
        totais = obter_ou_calcular(
            f"funil_dashboard:{ids}:{rec.inicio}:{rec.fim}",
            settings.cache_ttl_metricas_segundos,
            lambda rec=rec: buscar_totais("seller", ids, rec.inicio, rec.fim),
        )
        corpo = montar_resposta_comercial(
            periodo=rec,
            cargo="seller",
            pessoas_cargo=pessoas_seller,
            totais=totais,
            metas=metas,
            emails_filtro=None,
            hoje=hoje_sp(),
            agora=datetime.now(TZ_SP),
            expediente_inicio=settings.expediente_inicio,
            expediente_fim=settings.expediente_fim,
        ).corpo
        dashboard[chave] = [
            m for k in METRICAS_DASHBOARD_FUNIL[canal] for m in corpo["metricas_time"] if m["metrica"] == k
        ]
    return {
        "periodo": {"granularidade": p.granularidade, "inicio": p.inicio.isoformat(), "fim": p.fim.isoformat()},
        "avisos": [f"fonte_indisponivel:{t}" for t in tabelas_com_falha()],
        "contas": [{"id_conta": str(c.id_conta), "nome": c.nome, "metricas": c.metricas} for c in contas],
        "dashboard": dashboard,
    }
