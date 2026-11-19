from __future__ import annotations

import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import exigir_usuario
from app.cache import obter_ou_calcular
from app.config import settings
from app.dominios.funil import sdr
from app.dominios.funil.banco import buscar_contas
from app.dominios.geral.banco import (
    buscar_evento,
    buscar_proximo_evento,
    contar_inscritos_no_periodo,
    listar_proximos_eventos,
)
from app.dominios.pessoas.banco import listar_ativas
from app.fontes.banco import iniciar_registro_de_falhas, tabelas_com_falha
from app.metas import buscar_metas
from app.periodo import TZ_SP, hoje_sp, resolver_periodo

router = APIRouter(tags=["funil"])

CANAIS = ("linkedin", "instagram")

# Id de evento do SED (uuid): vai dentro do filtro do PostgREST, então só letras, dígitos e hífen.
ID_EVENTO_VALIDO = re.compile(r"^[A-Za-z0-9-]{1,64}$")

# No filtro de dia o gráfico de linhas teria um ponto só; a série traz a semana até o dia.
DIAS_SERIE_FILTRO_DIA = 7


def _inicio_serie(p):
    return p.inicio - timedelta(days=DIAS_SERIE_FILTRO_DIA - 1) if p.granularidade == "dia" else p.inicio


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
        lambda: buscar_contas(canal, p.inicio, p.fim, _inicio_serie(p)),
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


@router.get("/funil-sdr/eventos")
def get_eventos_funil_sdr(_usuario: dict = Depends(exigir_usuario)) -> dict:
    """Opções do filtro de evento (header, só habilitado na página Funil SDR)."""
    iniciar_registro_de_falhas()
    eventos = obter_ou_calcular(
        "eventos:proximos", settings.cache_ttl_metricas_segundos, lambda: listar_proximos_eventos(datetime.now(TZ_SP))
    )
    return {"eventos": eventos, "avisos": [f"fonte_indisponivel:{t}" for t in tabelas_com_falha()]}


@router.get("/funil-sdr")
def get_funil_sdr(
    granularidade: str = Query(...),
    periodo: str = Query(...),
    evento: str | None = Query(None),
    _usuario: dict = Depends(exigir_usuario),
) -> dict:
    if evento is not None and not ID_EVENTO_VALIDO.match(evento):
        raise HTTPException(
            status_code=400,
            detail={"erro": {"codigo": "parametro_invalido", "mensagem": "evento inválido"}},
        )
    iniciar_registro_de_falhas()
    p = _resolver_periodo_ou_400(granularidade, periodo)
    linhas = obter_ou_calcular(
        f"funil-sdr:{p.inicio}:{p.fim}",
        settings.cache_ttl_metricas_segundos,
        lambda: sdr.buscar_metricas_funil_sdr(_inicio_serie(p), p.fim),
    )
    metas = obter_ou_calcular("metas-funil-sdr", settings.cache_ttl_metricas_segundos, sdr.buscar_metas_funil_sdr)
    sdrs = sorted(
        (
            {"id": int(pessoa.id), "nome": pessoa.nome, "imagem_url": pessoa.imagem_url}
            for pessoa in obter_ou_calcular("pessoas:ativas", settings.cache_ttl_pessoas_segundos, listar_ativas)
            if pessoa.cargo == "sdr"
        ),
        key=lambda s: s["id"],
    )
    numeros_captados = sum(
        c.metricas["numeros_captados"]
        for canal in CANAIS
        for c in obter_ou_calcular(
            f"funil:{canal}:{p.inicio}:{p.fim}",
            settings.cache_ttl_metricas_segundos,
            lambda canal=canal: buscar_contas(canal, p.inicio, p.fim, _inicio_serie(p)),
        )
    )
    corpo = sdr.montar_resposta(
        p,
        sdrs,
        linhas,
        metas,
        hoje=hoje_sp(),
        agora=datetime.now(TZ_SP),
        expediente_inicio=settings.expediente_inicio,
        expediente_fim=settings.expediente_fim,
        numeros_captados=numeros_captados,
    )
    # Velocímetro e cards do evento: o evento escolhido no filtro ou, sem
    # escolha, o próximo (SED, qualquer título), fora do filtro de período.
    if evento is None:
        dados_evento = obter_ou_calcular(
            "evento:proximo",
            settings.cache_ttl_metricas_segundos,
            lambda: buscar_proximo_evento(datetime.now(TZ_SP)),
        )
    else:
        dados_evento = obter_ou_calcular(
            f"evento:{evento}", settings.cache_ttl_metricas_segundos, lambda: buscar_evento(evento)
        )
    inscritos_periodo = (
        0
        if dados_evento is None
        else obter_ou_calcular(
            f"evento:{dados_evento.id}:inscritos:{p.inicio}:{p.fim}",
            settings.cache_ttl_metricas_segundos,
            lambda: contar_inscritos_no_periodo(dados_evento.id, p.inicio, p.fim),
        )
    )
    return {
        **corpo,
        "evento": None
        if dados_evento is None
        else {
            "id": dados_evento.id,
            "titulo": dados_evento.titulo,
            "data": dados_evento.data,
            # Aqui inscrito = aprovado + pendente (recusado não conta), diferente da Geral.
            "inscritos": dados_evento.aprovados + dados_evento.pendentes,
            # Os mesmos inscritos, só os feitos dentro do filtro de data (velocímetro).
            "inscritos_periodo": inscritos_periodo,
            "aprovados": dados_evento.aprovados,
            "pendentes": dados_evento.pendentes,
            "rejeitados": dados_evento.rejeitados,
            "capacidade": dados_evento.capacidade,
        },
        "avisos": [f"fonte_indisponivel:{t}" for t in tabelas_com_falha()],
    }
