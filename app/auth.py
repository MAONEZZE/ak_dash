"""Validação do JWT do Supabase Auth (login email+senha). Sem SSO, sem OAuth de usuário."""
from __future__ import annotations

import jwt
from fastapi import Header, HTTPException

from app.config import settings


def _erro_401(mensagem: str) -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={"erro": {"codigo": "nao_autenticado", "mensagem": mensagem}},
    )


def exigir_usuario(authorization: str = Header(default="")) -> dict:
    if not authorization.startswith("Bearer "):
        raise _erro_401("token ausente")
    token = authorization.removeprefix("Bearer ").strip()
    if not settings.supabase_jwt_secret:
        raise _erro_401("SUPABASE_JWT_SECRET não configurado no BFF")
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.PyJWTError as exc:
        raise _erro_401("token inválido") from exc
    return payload
