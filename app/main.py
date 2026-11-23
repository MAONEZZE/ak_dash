from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import workers
from app.config import settings
from app.dominios.comercial.rotas import router as comercial_router
from app.dominios.financeiro.rotas import router as financeiro_router
from app.dominios.funil.rotas import router as funil_router
from app.dominios.geral.rotas import router as geral_router
from app.dominios.pessoas.rotas import router as pessoas_router
from app.periodo import TZ_SP

# Painel do Easypanel (stdout): só as linhas marcadas `no_painel` (as "primeiras leituras ok" dos workers),
# com horário de SP. Os demais logs do app ficam fora; erros dos workers seguem no /saude.
_log_app = logging.getLogger("app")
if not _log_app.handlers:
    _saida = logging.StreamHandler(sys.stdout)
    _formato = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    # horário de São Paulo, não o do container (UTC no Easypanel)
    _formato.converter = lambda segundos: datetime.fromtimestamp(segundos, TZ_SP).timetuple()
    _saida.setFormatter(_formato)
    _saida.addFilter(lambda registro: getattr(registro, "no_painel", False))
    _log_app.addHandler(_saida)
_log_app.setLevel(logging.INFO)

@asynccontextmanager
async def _ciclo_de_vida(_app: FastAPI):
    parar = workers.iniciar(settings)
    yield
    parar.set()


app = FastAPI(title="Dashboard Akeel — BFF", version="0.1.0", lifespan=_ciclo_de_vida)


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
app.include_router(funil_router)


@app.get("/saude", tags=["infra"])
def saude() -> dict:
    return {
        "status": "ok",
        "workers": {w.planilha.nome: w.status for w in workers.ATIVOS},
        "workers_motivo": workers.MOTIVO_INATIVOS,
    }
