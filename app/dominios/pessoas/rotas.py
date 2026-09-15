from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import exigir_usuario
from app.cache import obter_ou_calcular
from app.config import settings
from app.dominios.pessoas.banco import listar_ativas

router = APIRouter(tags=["pessoas"])


@router.get("/pessoas")
def get_pessoas(_usuario: dict = Depends(exigir_usuario)) -> list[dict]:
    pessoas = obter_ou_calcular(
        "pessoas:ativas", settings.cache_ttl_pessoas_segundos, listar_ativas
    )
    return [
        {"id": p.id, "nome": p.nome, "cargo": p.cargo, "email": p.email, "imagem_url": p.imagem_url}
        for p in pessoas
    ]
