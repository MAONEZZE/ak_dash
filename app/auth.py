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


def _obter_jwks_por_kid(forcar: bool = False) -> dict[str, PyJWK]:
    """JWKS em cache, mas FALHA NUNCA É CACHEADA.

    Antes, um erro de rede na primeira busca gravava `{}` no cache pra sempre:
    daí em diante todo token caía no fallback HS256, que nunca valida um token
    ES256 — e este projeto assina em ES256. Efeito: um blip de rede no boot do
    BFF fazia 401 em toda requisição até alguém reiniciar o processo. Com o
    dashboard numa TV, isso é a tela de login travada até alguém perceber.

    `forcar=True` refaz a busca ignorando o cache — usado quando chega um `kid`
    desconhecido, que é o que se vê quando o Supabase rotaciona a chave.
    """
    global _jwks_por_kid
    if _jwks_por_kid is not None and not forcar:
        return _jwks_por_kid
    if not settings.supabase_url:
        return {}
    try:
        resposta = httpx.get(f"{settings.supabase_url}/auth/v1/.well-known/jwks.json", timeout=10.0)
        resposta.raise_for_status()
        chaves = resposta.json().get("keys", [])
        _jwks_por_kid = {c["kid"]: PyJWK.from_dict(c) for c in chaves if "kid" in c}
        return _jwks_por_kid
    except httpx.HTTPError as exc:
        # Sem gravar no cache: a próxima requisição tenta de novo.
        logger.warning("Não foi possível buscar o JWKS do Supabase: %s", exc)
        return _jwks_por_kid or {}


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
    if kid and chave_jwks is None:
        # `kid` que o cache não conhece: pode ser rotação de chave no Supabase.
        # Rebusca antes de desistir, senão a rotação derrubaria todo mundo até
        # o próximo restart do BFF.
        chave_jwks = _obter_jwks_por_kid(forcar=True).get(kid)
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
