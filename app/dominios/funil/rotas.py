from __future__ import annotations

import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import exigir_usuario
from app.cache import obter_ou_calcular
from app.config import etiqueta_pessoa, settings
from app.dominios.funil import evento as funil_evento, pipedrive, sdr
from app.dominios.funil.banco import buscar_contas
from app.dominios.geral.banco import (
    buscar_evento,
    buscar_proxima_imersao,
    buscar_proximo_evento,
    contar_comparecimento,
    contar_inscritos_no_periodo,
    listar_imersoes,
    listar_proximos_eventos,
)
from app.dominios.pessoas.banco import listar_ativas
from app.fontes.banco import iniciar_registro_de_falhas, tabelas_com_falha
from app.metas import buscar_metas
from app.periodo import TZ_SP, hoje_sp, resolver_periodo
from app.planilhas import COLUNAS_POR_TABELA, normalizar

router = APIRouter(tags=["funil"])

CANAIS = ("linkedin", "instagram")

# Id de evento do SED (uuid): vai dentro do filtro do PostgREST, então só letras, dígitos e hífen.
ID_EVENTO_VALIDO = re.compile(r"^[A-Za-z0-9-]{1,64}$")

# Nos filtros de dia e de semana o gráfico mostra os 7 dias até o fim do filtro (ou até
# hoje, na semana corrente). Sem isso, o dia e a segunda-feira viram um ponto só, sem linha.
# Volta 6 dias antes do início: cobre os 7 dias até qualquer dia da semana.
DIAS_SERIE_CURTA = 7


def _inicio_serie(p):
    if p.granularidade in ("dia", "semana"):
        return p.inicio - timedelta(days=DIAS_SERIE_CURTA - 1)
    return p.inicio


def _pipedrive(p):
    """Dados do Pipedrive do período (com os dias da série), uma busca compartilhada pelas três páginas de funil."""
    inicio = _inicio_serie(p)
    return obter_ou_calcular(
        f"pipedrive:{inicio}:{p.fim}",
        settings.cache_ttl_metricas_segundos,
        lambda: pipedrive.buscar_pipedrive(inicio, p.fim),
    )


def _contas_do_canal(canal: str, p):
    """Contas do canal (planilha) com as métricas do Pipedrive aplicadas, e o que não tem conta (`sem_conta`)."""
    contas = obter_ou_calcular(
        f"funil:{canal}:{p.inicio}:{p.fim}",
        settings.cache_ttl_metricas_segundos,
        lambda: buscar_contas(canal, p.inicio, p.fim, _inicio_serie(p)),
    )
    if canal not in pipedrive.METRICAS_POR_CANAL:  # canal só da planilha: nem consulta o Pipedrive
        return contas, {k: 0 for k in COLUNAS_POR_TABELA["metricas_contas"]}
    return pipedrive.aplicar_em_contas(contas, _pipedrive(p), canal, p.inicio, lambda nome: etiqueta_pessoa(canal, nome))


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
    contas, sem_conta = _contas_do_canal(canal, p)

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
        "sem_conta": sem_conta,
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


@router.get("/funil-evento/eventos")
def get_eventos_funil_evento(_usuario: dict = Depends(exigir_usuario)) -> dict:
    """Opções do filtro de evento na página Funil Evento: só Imersões, passadas e futuras."""
    iniciar_registro_de_falhas()
    eventos = obter_ou_calcular("eventos:imersoes", settings.cache_ttl_metricas_segundos, listar_imersoes)
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
    pessoas = obter_ou_calcular("pessoas:ativas", settings.cache_ttl_pessoas_segundos, listar_ativas)
    sdrs = sorted(
        (
            {"id": int(pessoa.id), "nome": pessoa.nome, "imagem_url": pessoa.imagem_url}
            for pessoa in pessoas
            if pessoa.cargo == "sdr"
        ),
        key=lambda s: s["id"],
    )
    # Abordagens, respondidos e indicações dos SDRs vêm do Pipedrive, não da planilha.
    id_dash_por_dono = {
        dono: int(pessoa.id)
        for dono, nome in pipedrive.DONOS_SDR.items()
        for pessoa in pessoas
        if pessoa.cargo == "sdr" and normalizar(pessoa.nome) == nome
    }
    sem_metricas_pipedrive = [{k: v for k, v in l.items() if k not in pipedrive.METRICAS_SDR} for l in linhas]
    linhas = sem_metricas_pipedrive + pipedrive.linhas_sdr(_pipedrive(p), id_dash_por_dono)
    numeros_captados = 0
    for canal in CANAIS:
        contas, sem_conta = _contas_do_canal(canal, p)
        numeros_captados += sum(c.metricas["numeros_captados"] for c in contas) + sem_conta["numeros_captados"]
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
    # Meta do velocímetro: dia e semana saem do que falta para a capacidade ÷ dias até o evento
    # (sem data do evento, sem meta); mês, ano e custom = a capacidade.
    meta_velocimetro = None if dados_evento is None else dados_evento.capacidade
    if p.granularidade in ("dia", "semana") and dados_evento is not None:
        meta_velocimetro = None
        if dados_evento.data:
            hoje = hoje_sp()
            inscritos_hoje = obter_ou_calcular(
                f"evento:{dados_evento.id}:inscritos:{hoje}:{hoje}",
                settings.cache_ttl_metricas_segundos,
                lambda: contar_inscritos_no_periodo(dados_evento.id, hoje, hoje),
            )
            meta_velocimetro = sdr.meta_velocimetro_inscricoes(
                p.granularidade,
                dados_evento.capacidade,
                dados_evento.aprovados + dados_evento.pendentes - inscritos_hoje,
                funil_evento.data_do_evento_sp(dados_evento.data),
                hoje,
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
            # Meta do velocímetro no filtro atual (ver `sdr.meta_velocimetro_inscricoes`).
            "meta_velocimetro": meta_velocimetro,
        },
        "avisos": [f"fonte_indisponivel:{t}" for t in tabelas_com_falha()],
    }


FUNIL_EVENTO_ZERADO = {"inscritos": 0, "onboarding_agendado": 0, "onboarding_realizado": 0, "comparecimento": 0, "vendas": 0}


@router.get("/funil-evento")
def get_funil_evento(
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
    ttl = settings.cache_ttl_metricas_segundos
    if evento is None:
        dados = obter_ou_calcular("imersao:proxima", ttl, lambda: buscar_proxima_imersao(datetime.now(TZ_SP)))
    else:
        dados = obter_ou_calcular(f"evento:{evento}", ttl, lambda: buscar_evento(evento))
    funil = dict(FUNIL_EVENTO_ZERADO)
    if dados is not None:
        pipe = dict(funil_evento.ZERADO)
        if dados.data:
            data_evento = funil_evento.data_do_evento_sp(dados.data)
            pipe = obter_ou_calcular(
                f"funil-evento:pipedrive:{dados.id}:{p.inicio}:{p.fim}",
                ttl,
                lambda: funil_evento.buscar_pipedrive_evento(data_evento, p.inicio, p.fim),
            )
        comparecimento = obter_ou_calcular(
            f"evento:{dados.id}:comparecimento", ttl, lambda: contar_comparecimento(dados.id)
        )
        # Etapa 1 = aprovados + pendentes (recusado não conta); o card Total conta todos.
        funil = {"inscritos": dados.aprovados + dados.pendentes, **pipe, "comparecimento": comparecimento}
    return {
        "periodo": {"granularidade": p.granularidade, "inicio": p.inicio.isoformat(), "fim": p.fim.isoformat()},
        "avisos": [f"fonte_indisponivel:{t}" for t in tabelas_com_falha()],
        "evento": None
        if dados is None
        else {
            "id": dados.id,
            "titulo": dados.titulo,
            "data": dados.data,
            "total": dados.inscritos,
            "aprovados": dados.aprovados,
            "pendentes": dados.pendentes,
            "rejeitados": dados.rejeitados,
        },
        "funil": funil,
    }
