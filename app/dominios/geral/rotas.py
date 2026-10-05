from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import exigir_usuario
from app.cache import obter_ou_calcular
from app.config import settings
from app.dominios.comercial.banco import buscar_totais
from app.dominios.geral.banco import buscar_confrarias_do_mes, buscar_faturamento
from app.dominios.geral.calculo import montar_resposta_geral, montar_termometro
from app.fontes.banco import iniciar_registro_de_falhas, tabelas_com_falha
from app.dominios.pessoas.banco import listar_ativas
from app.metas import buscar_metas
from app.periodo import Periodo, hoje_sp, resolver_periodo, semana_iso

router = APIRouter(tags=["geral"])


def _valor_atual(granularidade: str, hoje: date) -> str:
    if granularidade == "dia":
        return hoje.isoformat()
    if granularidade == "semana":
        return semana_iso(hoje)
    if granularidade == "ano":
        return str(hoje.year)
    return f"{hoje.year:04d}-{hoje.month:02d}"


@router.get("/geral")
def get_geral(
    granularidade: str = Query(default="mes"),
    periodo: str = Query(default="atual"),
    _usuario: dict = Depends(exigir_usuario),
) -> dict:
    iniciar_registro_de_falhas()
    hoje = hoje_sp()
    valor = periodo if periodo != "atual" else _valor_atual(granularidade, hoje)
    try:
        periodo_metas = resolver_periodo(granularidade, valor)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"erro": {"codigo": "parametro_invalido", "mensagem": str(exc)}},
        ) from exc

    # `periodo_saida`/consultas nunca pedem dado do futuro — capado em hoje.
    # A meta ("meta cheia" do período pedido) usa `periodo_metas` por inteiro.
    fim_capado = min(periodo_metas.fim, hoje)
    periodo_saida = Periodo(periodo_metas.granularidade, periodo_metas.inicio, fim_capado)

    todas_ativas = obter_ou_calcular(
        "pessoas:ativas", settings.cache_ttl_pessoas_segundos, listar_ativas
    )
    pessoas_sdr = [p for p in todas_ativas if p.cargo == "sdr"]
    pessoas_closer = [p for p in todas_ativas if p.cargo == "closer"]

    chave_periodo = f"{periodo_saida.inicio.isoformat()}:{periodo_saida.fim.isoformat()}"
    totais_sdr = obter_ou_calcular(
        f"geral_sdr:{chave_periodo}",
        settings.cache_ttl_metricas_segundos,
        lambda: buscar_totais("sdr", [int(p.id) for p in pessoas_sdr], periodo_saida.inicio, periodo_saida.fim),
    )
    totais_closer = obter_ou_calcular(
        f"geral_closer:{chave_periodo}",
        settings.cache_ttl_metricas_segundos,
        lambda: buscar_totais("closer", [int(p.id) for p in pessoas_closer], periodo_saida.inicio, periodo_saida.fim),
    )
    metas = obter_ou_calcular("metas", settings.cache_ttl_metricas_segundos, buscar_metas)
    ids_closer = [int(p.id) for p in pessoas_closer]
    faturamento = obter_ou_calcular(
        f"faturamento:{chave_periodo}",
        settings.cache_ttl_metricas_segundos,
        lambda: buscar_faturamento(periodo_saida.inicio, periodo_saida.fim, ids_closer),
    )

    # Os dois cards ESCUROS (Faturamento/Liquidado) são sempre do MÊS, nunca do
    # recorte pedido: em Dia/Semana/Ano mostram o mês corrente; sob Mês, o mês
    # navegado na pill. Decisão de produto — são o número fechado da empresa, e
    # ninguém lê faturamento "do dia" ou "da semana". O resto da página segue o
    # filtro normalmente, inclusive a coluna Liquidado do closer na tabela,
    # que continua saindo de `faturamento` (período pedido).
    mes_cards = periodo_metas if granularidade == "mes" else resolver_periodo("mes", _valor_atual("mes", hoje))
    inicio_mes, fim_mes = mes_cards.inicio, min(mes_cards.fim, hoje)
    if (inicio_mes, fim_mes) == (periodo_saida.inicio, periodo_saida.fim):
        faturamento_mes = faturamento
    else:
        faturamento_mes = obter_ou_calcular(
            f"faturamento:{inicio_mes.isoformat()}:{fim_mes.isoformat()}",
            settings.cache_ttl_metricas_segundos,
            lambda: buscar_faturamento(inicio_mes, fim_mes, ids_closer),
        )

    # Termômetro e Confrarias são sempre do mês CORRENTE, fora do filtro de
    # data — mesmo sob Mês navegado pra outro mês.
    mes_corrente = resolver_periodo("mes", _valor_atual("mes", hoje))
    if (inicio_mes, fim_mes) == (mes_corrente.inicio, hoje):
        faturamento_mes_corrente = faturamento_mes
    else:
        faturamento_mes_corrente = obter_ou_calcular(
            f"faturamento:{mes_corrente.inicio.isoformat()}:{hoje.isoformat()}",
            settings.cache_ttl_metricas_segundos,
            lambda: buscar_faturamento(mes_corrente.inicio, hoje, ids_closer),
        )
    termometro = montar_termometro(faturamento_mes_corrente)

    eventos = obter_ou_calcular(
        f"confrarias:{mes_corrente.inicio.isoformat()}",
        settings.cache_ttl_metricas_segundos,
        lambda: buscar_confrarias_do_mes(mes_corrente.inicio, mes_corrente.fim),
    )

    resposta = montar_resposta_geral(
        periodo_metas=periodo_metas,
        periodo_saida=periodo_saida,
        hoje=hoje,
        pessoas_sdr=pessoas_sdr,
        pessoas_closer=pessoas_closer,
        totais_sdr=totais_sdr,
        totais_closer=totais_closer,
        metas=metas,
        faturamento=faturamento,
        faturamento_mes=faturamento_mes,
        eventos=eventos,
        termometro=termometro,
    )
    resposta["avisos"] += [f"fonte_indisponivel:{t}" for t in tabelas_com_falha()]
    return resposta
