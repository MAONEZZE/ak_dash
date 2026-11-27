from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import exigir_usuario
from app.cache import obter_ou_calcular
from app.config import donos_sdr, etiqueta_pessoa, settings
from app.dominios.funil import evento as funil_evento, pipedrive, sdr, seller
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
from app.fontes.banco import em_paralelo, iniciar_registro_de_falhas, tabelas_com_falha
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
    def contas_da_planilha():
        return obter_ou_calcular(
            f"funil:{canal}:{p.inicio}:{p.fim}",
            settings.cache_ttl_metricas_segundos,
            lambda: buscar_contas(canal, p.inicio, p.fim, _inicio_serie(p)),
        )

    if canal not in pipedrive.METRICAS_POR_CANAL:  # canal só da planilha: nem consulta o Pipedrive
        return contas_da_planilha(), {k: 0 for k in COLUNAS_POR_TABELA["metricas_contas"]}
    contas, dados = em_paralelo(contas_da_planilha, lambda: _pipedrive(p))
    return pipedrive.aplicar_em_contas(contas, dados, canal, p.inicio, lambda nome: etiqueta_pessoa(canal, nome))


def _resolver_periodo_ou_400(granularidade: str, periodo: str):
    try:
        return resolver_periodo(granularidade, periodo)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"erro": {"codigo": "parametro_invalido", "mensagem": str(exc)}},
        ) from exc


def _buscar_evento_da_pagina(evento: str | None, ttl: int):
    """Evento escolhido no filtro ou, sem escolha, o próximo (SED, qualquer título), fora do filtro de período."""
    if evento is None:
        return obter_ou_calcular("evento:proximo", ttl, lambda: buscar_proximo_evento(datetime.now(TZ_SP)))
    return obter_ou_calcular(f"evento:{evento}", ttl, lambda: buscar_evento(evento))


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
    (contas, sem_conta), pessoas, metas = em_paralelo(
        lambda: _contas_do_canal(canal, p),
        lambda: obter_ou_calcular("pessoas:ativas", settings.cache_ttl_pessoas_segundos, listar_ativas),
        lambda: obter_ou_calcular("metas", settings.cache_ttl_metricas_segundos, buscar_metas),
    )

    # Meta de números captados do período: soma das metas dos sellers ativos ligados às contas do canal.
    ids_seller = {c.id_seller for c in contas if c.id_seller is not None}
    ids = [int(pessoa.id) for pessoa in pessoas if pessoa.cargo == "seller" and int(pessoa.id) in ids_seller]
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
    ttl = settings.cache_ttl_metricas_segundos

    # Tudo que não depende de outra consulta vai ao mesmo tempo.
    linhas, metas, pessoas, dados_pipedrive, contas_canais, dados_evento = em_paralelo(
        lambda: obter_ou_calcular(
            f"funil-sdr:{p.inicio}:{p.fim}", ttl, lambda: sdr.buscar_metricas_funil_sdr(_inicio_serie(p), p.fim)
        ),
        lambda: obter_ou_calcular("metas-funil-sdr", ttl, sdr.buscar_metas_funil_sdr),
        lambda: obter_ou_calcular("pessoas:ativas", settings.cache_ttl_pessoas_segundos, listar_ativas),
        lambda: _pipedrive(p),
        lambda: em_paralelo(*(lambda canal=canal: _contas_do_canal(canal, p) for canal in CANAIS)),
        lambda: _buscar_evento_da_pagina(evento, ttl),
    )
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
        for dono, nome in donos_sdr().items()
        for pessoa in pessoas
        if pessoa.cargo == "sdr" and normalizar(pessoa.nome) == nome
    }
    sem_metricas_pipedrive = [{k: v for k, v in l.items() if k not in pipedrive.METRICAS_SDR} for l in linhas]
    linhas = sem_metricas_pipedrive + pipedrive.linhas_sdr(dados_pipedrive, id_dash_por_dono)
    numeros_captados = sum(
        sum(c.metricas["numeros_captados"] for c in contas) + sem_conta["numeros_captados"]
        for contas, sem_conta in contas_canais
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
    hoje = hoje_sp()
    precisa_inscritos_hoje = p.granularidade in ("dia", "semana") and dados_evento is not None and bool(dados_evento.data)
    inscritos_periodo, inscritos_hoje, almocos_pagos = (0, 0, 0) if dados_evento is None else em_paralelo(
        lambda: obter_ou_calcular(
            f"evento:{dados_evento.id}:inscritos:{p.inicio}:{p.fim}",
            ttl,
            lambda: contar_inscritos_no_periodo(dados_evento.id, p.inicio, p.fim),
        ),
        lambda: obter_ou_calcular(
            f"evento:{dados_evento.id}:inscritos:{hoje}:{hoje}",
            ttl,
            lambda: contar_inscritos_no_periodo(dados_evento.id, hoje, hoje),
        )
        if precisa_inscritos_hoje
        else 0,
        lambda: obter_ou_calcular(
            f"pipedrive:almocos:{dados_evento.id}",
            ttl,
            lambda: funil_evento.buscar_almocos_pagos(funil_evento.data_do_evento_sp(dados_evento.data)),
        )
        if dados_evento.data
        else 0,
    )
    # Meta do velocímetro: dia e semana saem do que falta para a capacidade ÷ dias até o evento
    # (sem data do evento, sem meta); mês, ano e custom = a capacidade.
    meta_velocimetro = None if dados_evento is None else dados_evento.capacidade
    if p.granularidade in ("dia", "semana") and dados_evento is not None:
        meta_velocimetro = None
        if dados_evento.data:
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
            # Card Almoços Pagos: coluna Onboarding realizado do Pipedrive agora (ver `funil_evento.buscar_almocos_pagos`).
            "almocos_pagos": almocos_pagos,
            "capacidade": dados_evento.capacidade,
            # Meta do velocímetro no filtro atual (ver `sdr.meta_velocimetro_inscricoes`).
            "meta_velocimetro": meta_velocimetro,
        },
        "avisos": [f"fonte_indisponivel:{t}" for t in tabelas_com_falha()],
    }


@router.get("/sdr")
def get_pagina_sdr(
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

    linhas, metas, pessoas, ligacoes, dados_evento = em_paralelo(
        lambda: obter_ou_calcular(
            f"pagina-sdr:linhas:{p.inicio}:{p.fim}", ttl, lambda: sdr.buscar_metricas_funil_sdr(p.inicio, p.fim)
        ),
        lambda: obter_ou_calcular("metas-funil-sdr", ttl, sdr.buscar_metas_funil_sdr),
        lambda: obter_ou_calcular("pessoas:ativas", settings.cache_ttl_pessoas_segundos, listar_ativas),
        lambda: obter_ou_calcular(
            f"pagina-sdr:ligacoes:{p.inicio}:{p.fim}", ttl, lambda: sdr.buscar_ligacoes_sdr(p.inicio, p.fim)
        ),
        lambda: _buscar_evento_da_pagina(evento, ttl),
    )

    # Janela de inscrição do evento: da primeira inscrição até a véspera, sem domingos.
    dias: list[date] = []
    if dados_evento is not None and dados_evento.data:
        primeira = obter_ou_calcular(
            f"evento:{dados_evento.id}:primeira-inscricao", ttl, lambda: sdr.data_primeira_inscricao(dados_evento.id)
        )
        dias = sdr.dias_da_janela_do_evento(primeira, funil_evento.data_do_evento_sp(dados_evento.data))
    linhas_janela = (
        obter_ou_calcular(
            f"pagina-sdr:linhas:{dias[0]}:{dias[-1]}", ttl, lambda: sdr.buscar_metricas_funil_sdr(dias[0], dias[-1])
        )
        if dias
        else []
    )

    sdrs = sorted(
        (
            {"id": int(pessoa.id), "nome": pessoa.nome, "imagem_url": pessoa.imagem_url}
            for pessoa in pessoas
            if pessoa.cargo == "sdr"
        ),
        key=lambda s: s["id"],
    )
    evento_dict = (
        None
        if dados_evento is None
        else {"id": dados_evento.id, "titulo": dados_evento.titulo, "data": dados_evento.data, "capacidade": dados_evento.capacidade}
    )
    # Card "Ranking SDR" (mês do fim do filtro): inscrições da planilha (metricas_funil_sdr); negócios do Pipedrive;
    # badge = inscritos do evento no SED. Donos nas envs PIPE_ID_USUARIO_SDR_*.
    id_dash_por_dono = {
        dono: s["id"] for dono, nome in donos_sdr().items() for s in sdrs if normalizar(s["nome"]) == nome
    }
    inicio_mes, fim_mes = sdr.mes_do_ranking(p)
    hoje = hoje_sp()
    chave_donos = sorted(id_dash_por_dono.items())
    negocios, linhas_mes, inscritos_sed_mes = em_paralelo(
        lambda: obter_ou_calcular(
            f"pagina-sdr:negocios:{inicio_mes}:{chave_donos}",
            ttl,
            lambda: sdr.buscar_negocios_sdr(inicio_mes, fim_mes, id_dash_por_dono),
        ),
        lambda: obter_ou_calcular(
            f"pagina-sdr:linhas:{inicio_mes}:{fim_mes}", ttl, lambda: sdr.buscar_metricas_funil_sdr(inicio_mes, fim_mes)
        ),
        lambda: None
        if dados_evento is None
        else obter_ou_calcular(
            f"pagina-sdr:inscritos-sed:{dados_evento.id}:{inicio_mes}",
            ttl,
            lambda: contar_inscritos_no_periodo(dados_evento.id, inicio_mes, fim_mes),
        ),
    )
    inscricoes_mes = sdr.inscricoes_do_mes(linhas_mes, [s["id"] for s in sdrs], hoje)
    data_evento = funil_evento.data_do_evento_sp(dados_evento.data) if dados_evento is not None and dados_evento.data else None
    janela_meta = sdr.janela_da_meta((inicio_mes, fim_mes), data_evento)
    return {
        **sdr.montar_resposta_pagina_sdr(
            p, sdrs, linhas, linhas_janela, ligacoes, metas, evento_dict, dias, hoje=hoje,
            mes_ranking=(inicio_mes, fim_mes),
            janela_meta=janela_meta,
            negocios=negocios,
            inscricoes_mes=inscricoes_mes,
            inscritos_sed_mes=inscritos_sed_mes,
        ),
        "avisos": [f"fonte_indisponivel:{t}" for t in tabelas_com_falha()],
    }


@router.get("/seller")
def get_pagina_seller(
    granularidade: str = Query(...),
    periodo: str = Query(...),
    _usuario: dict = Depends(exigir_usuario),
) -> dict:
    iniciar_registro_de_falhas()
    p = _resolver_periodo_ou_400(granularidade, periodo)
    (linkedin, instagram), pessoas, metas = em_paralelo(
        lambda: em_paralelo(lambda: _contas_do_canal("linkedin", p), lambda: _contas_do_canal("instagram", p)),
        lambda: obter_ou_calcular("pessoas:ativas", settings.cache_ttl_pessoas_segundos, listar_ativas),
        lambda: obter_ou_calcular("metas", settings.cache_ttl_metricas_segundos, buscar_metas),
    )
    sellers = sorted(
        ({"id": int(x.id), "nome": x.nome, "imagem_url": x.imagem_url} for x in pessoas if x.cargo == "seller"),
        key=lambda s: s["id"],
    )
    return {
        **seller.montar_resposta_pagina_seller(p, sellers, {"linkedin": linkedin, "instagram": instagram}, metas, hoje_sp()),
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
                f"pipedrive:evento:{dados.id}",
                ttl,
                lambda: funil_evento.buscar_pipedrive_evento(data_evento),
            )
        comparecimento = obter_ou_calcular(
            f"evento:{dados.id}:comparecimento", ttl, lambda: contar_comparecimento(dados.id)
        )
        funil = {**pipe, "comparecimento": comparecimento}
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
