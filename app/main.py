from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.dominios.comercial.rotas import router as comercial_router
from app.dominios.financeiro.rotas import router as financeiro_router
from app.dominios.geral.rotas import router as geral_router
from app.dominios.pessoas.rotas import router as pessoas_router

app = FastAPI(title="Dashboard Akeel — BFF", version="0.1.0")


@app.exception_handler(HTTPException)
async def erro_no_formato_do_contrato(_request: Request, exc: HTTPException) -> JSONResponse:
    """Contrato exige `{"erro": {...}}` na raiz — sem o `{"detail": ...}` padrão do FastAPI."""
    corpo = exc.detail if isinstance(exc.detail, dict) and "erro" in exc.detail else {
        "erro": {"codigo": "erro", "mensagem": str(exc.detail)}
    }
    return JSONResponse(status_code=exc.status_code, content=corpo, headers=exc.headers)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(pessoas_router)
app.include_router(comercial_router)
app.include_router(geral_router)
app.include_router(financeiro_router)


@app.get("/saude", tags=["infra"])
def saude() -> dict:
    return {"status": "ok"}
