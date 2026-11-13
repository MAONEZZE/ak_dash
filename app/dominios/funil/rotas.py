from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import exigir_usuario
from app.cache import obter_ou_calcular
from app.config import settings
from app.dominios.funil.banco import buscar_contas
from app.fontes.banco import iniciar_registro_de_falhas, tabelas_com_falha
from app.periodo import resolver_periodo

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
    return {
        "periodo": {"granularidade": p.granularidade, "inicio": p.inicio.isoformat(), "fim": p.fim.isoformat()},
        "avisos": [f"fonte_indisponivel:{t}" for t in tabelas_com_falha()],
        "contas": [{"id_conta": str(c.id_conta), "nome": c.nome, "metricas": c.metricas} for c in contas],
        "dashboard": {"seller": None, "diario": [], "semanal": [], "mensal": []},
    }
