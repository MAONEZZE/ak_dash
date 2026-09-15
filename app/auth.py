"""Validação do JWT do Supabase Auth (login email+senha). Sem SSO, sem OAuth de usuário.

Projetos Supabase mais novos assinam tokens com chaves assimétricas (ES256,
publicadas em /.well-known/jwks.json) em vez do segredo legado HS256 —
tenta JWKS primeiro (chave pública, sem segredo pra rotacionar) e cai pro
segredo HS256 só quando o projeto não tem chave JWKS pro token recebido.

O JWKS é buscado com `httpx` (não com `jwt.PyJWKClient`, que usa `urllib` por
baixo — em algumas instalações de Python no macOS o `urllib` não enxerga o
certificado raiz do sistema e toda busca falha com CERTIFICATE_VERIFY_FAILED,
mesmo com o resto do BFF, via httpx, conectando normalmente).
"""
from __future__ import annotations

import logging

import httpx
import jwt
from jwt import PyJWK

from fastapi import Header, HTTPException

from app.config import settings

logger = logging.getLogger(__name__)

_ALGORITMOS_JWKS = ["ES256", "RS256"]
_jwks_por_kid: dict[str, PyJWK] | None = None


def _erro_401(mensagem: str) -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={"erro": {"codigo": "nao_autenticado", "mensagem": mensagem}},
    )


def _obter_jwks_por_kid() -> dict[str, PyJWK]:
    global _jwks_por_kid
    if _jwks_por_kid is not None:
        return _jwks_por_kid
    if not settings.supabase_url:
        _jwks_por_kid = {}
        return _jwks_por_kid
    try:
        resposta = httpx.get(f"{settings.supabase_url}/auth/v1/.well-known/jwks.json", timeout=10.0)
        resposta.raise_for_status()
        chaves = resposta.json().get("keys", [])
        _jwks_por_kid = {c["kid"]: PyJWK.from_dict(c) for c in chaves if "kid" in c}
    except httpx.HTTPError as exc:
        logger.warning("Não foi possível buscar o JWKS do Supabase: %s", exc)
        _jwks_por_kid = {}
    return _jwks_por_kid


def exigir_usuario(authorization: str = Header(default="")) -> dict:
    if not authorization.startswith("Bearer "):
        raise _erro_401("token ausente")
    token = authorization.removeprefix("Bearer ").strip()

    try:
        cabecalho = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise _erro_401("token inválido") from exc

    kid = cabecalho.get("kid")
    chave_jwks = _obter_jwks_por_kid().get(kid) if kid else None
    if chave_jwks is not None:
        try:
            return jwt.decode(token, chave_jwks.key, algorithms=_ALGORITMOS_JWKS, audience="authenticated")
        except jwt.PyJWTError as exc:
            logger.warning("Falha ao validar token via JWKS: %s: %s", type(exc).__name__, exc)
            raise _erro_401("token inválido") from exc

    # Sem chave JWKS pro kid recebido (projeto sem JWKS, ou kid desconhecido) — tenta o segredo legado.
    if not settings.supabase_jwt_secret:
        raise _erro_401("token não corresponde a nenhuma chave JWKS e SUPABASE_JWT_SECRET não está configurado")
    try:
        return jwt.decode(
            token, settings.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated"
        )
    except jwt.PyJWTError as exc:
        logger.warning("Falha ao validar token via segredo HS256 legado: %s: %s", type(exc).__name__, exc)
        raise _erro_401("token inválido") from exc
