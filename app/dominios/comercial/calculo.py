"""Metas atingidas, dias úteis decorridos e união mês corrente (planilha) + histórico (banco).

Agrupamento por pessoa (email), não por planilha: mesma pessoa em mais de uma
planilha soma realizado E meta (nunca só realizado — isso faria a pessoa
parecer sobre-humana), e sempre gera aviso.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from app.dominios.comercial.banco import HistoricoMetrica
from app.dominios.comercial.planilha import COLUNAS, PlanilhaParseada
from app.periodo import Periodo, dias_uteis_decorridos

_TOTAIS_ZERADOS = {
    "meta_periodo": 0,
    "realizado": 0,
    "dias_com_lacuna": 0,
    "dias_considerados": 0,
}


def _colunas_da_funcao(funcao: str) -> list:
    return [info for info in COLUNAS.values() if info.funcao == funcao]


def _campo_email(funcao: str) -> str:
    return "email_sdr" if funcao == "sdr" else "email_closer"


@dataclass
class _AcumuladorPessoa:
    planilhas_origem: list[str]
    totais_por_metrica: dict[str, dict]  # chave -> {meta_periodo, realizado, dias_com_lacuna, dias_considerados}
    pontos: int = 0


def calcular_mes_corrente(
    planilhas: list[PlanilhaParseada],
    funcao: str,
    ano: int,
    mes: int,
    dia_inicio: int,
    dia_fim: int,
    emails_filtro: set[str] | None,
    avisos: list[str],
) -> dict[str, _AcumuladorPessoa]:
    """Totais do mês corrente (parcial: dias úteis capados em hoje) por pessoa.

    dia_inicio/dia_fim delimitam a fatia do mês pedida (granularidade "dia"
    pede 1 dia; "mes"/"ano" pedem o mês inteiro) — sempre dentro do mês
    corrente, nunca cruzando meses (isso é papel do histórico).
    """
    dias_no_mes = calendar.monthrange(ano, mes)[1]
    dia_fim_no_mes = min(dia_fim, dias_no_mes)
    dias_uteis = dias_uteis_decorridos(date(ano, mes, dia_inicio), date(ano, mes, dia_fim_no_mes))

    campo_email = _campo_email(funcao)
    colunas = _colunas_da_funcao(funcao)

    por_pessoa: dict[str, list[PlanilhaParseada]] = {}
    for pl in planilhas:
        email = getattr(pl, campo_email)
        if email is None:
            continue
        if emails_filtro is not None and email not in emails_filtro:
            continue
        por_pessoa.setdefault(email, []).append(pl)

    resultado: dict[str, _AcumuladorPessoa] = {}
    for email, lista in por_pessoa.items():
        if len(lista) > 1:
            arquivos = ", ".join(p.arquivo for p in lista)
            avisos.append(
                f"Pessoa '{email}' aparece em mais de uma planilha ({arquivos}) — "
                f"realizado e meta somados; confirme se são duas contas reais ou dado desatualizado"
            )

        pontos_pessoa = 0
        totais_por_metrica: dict[str, dict] = {}
        for info in colunas:
            meta_total = 0
            realizado_total = 0
            dias_com_lacuna = 0
            dias_considerados = 0
            for pl in lista:
                meta_diaria = pl.metas.get(info.chave)
                meta_total += (meta_diaria or 0) * dias_uteis
                valores_dia = pl.valores.get(info.chave, {})

                for dia in range(dia_inicio, dia_fim_no_mes + 1):
                    dias_considerados += 1
                    v = valores_dia.get(dia)
                    if v is None:
                        dias_com_lacuna += 1
                    else:
                        realizado_total += v
                        # Gamificação: 1 ponto por dia×métrica em que o
                        # realizado do dia bateu a meta diária daquela
                        # coluna. Só computável sobre a planilha (dado
                        # dia-a-dia) — o histórico do Supabase só guarda
                        # totais do mês fechado, sem granularidade diária,
                        # então não contribui pontos (ver banco.py).
                        if meta_diaria is not None and v >= meta_diaria:
                            pontos_pessoa += 1

                # Dia fora do calendário do mês (planilha sempre tem 31 linhas,
                # mesmo em mês de 30) — nunca entra no cálculo, mas se vier com
                # valor não-zero é dado suspeito e vira aviso.
                for dia, v in valores_dia.items():
                    if dia > dias_no_mes and v not in (None, 0):
                        avisos.append(
                            f"Planilha '{pl.arquivo}': dia {dia} fora do calendário de "
                            f"{mes:02d}/{ano} ({dias_no_mes} dias) com valor '{v}' na "
                            f"coluna '{info.nome_exibicao}'"
                        )

            totais_por_metrica[info.chave] = {
                "meta_periodo": meta_total,
                "realizado": realizado_total,
                "dias_com_lacuna": dias_com_lacuna,
                "dias_considerados": dias_considerados,
            }

        resultado[email] = _AcumuladorPessoa(
            planilhas_origem=[p.arquivo for p in lista],
            totais_por_metrica=totais_por_metrica,
            pontos=pontos_pessoa,
        )
    return resultado


def _somar_historico(
    historico: list[HistoricoMetrica], funcao: str, emails_filtro: set[str] | None
) -> dict[str, dict[str, dict]]:
    somado: dict[str, dict[str, dict]] = {}
    for h in historico:
        if h.funcao != funcao:
            continue
        if emails_filtro is not None and h.email not in emails_filtro:
            continue
        bucket = somado.setdefault(h.email, {})
        totais = bucket.setdefault(h.metrica, dict(_TOTAIS_ZERADOS))
        totais["meta_periodo"] += h.meta_periodo
        totais["realizado"] += h.realizado
        totais["dias_com_lacuna"] += h.dias_com_lacuna
        totais["dias_considerados"] += h.dias_considerados
    return somado


def _status(realizado: int, meta: int, dias_com_lacuna: int, dias_considerados: int) -> str:
    if dias_considerados == 0 or dias_com_lacuna >= dias_considerados:
        return "sem_preenchimento"
    if realizado >= meta:
        return "atingido"
    return "abaixo_da_meta"


def _atribuir_ranking(pessoas_saida: list[dict]) -> None:
    """Dense rank (1-based) de pontuacao_total decrescente, dentro do pool recebido.

    Empate = mesma posição, sem pular número (dois em 1º -> o próximo é 2º).
    """
    pontos_unicos = sorted({p["pontuacao_total"] for p in pessoas_saida}, reverse=True)
    posicao_por_pontos = {pontos: i + 1 for i, pontos in enumerate(pontos_unicos)}
    for p in pessoas_saida:
        p["posicao"] = posicao_por_pontos[p["pontuacao_total"]]


def montar_resposta_comercial(
    periodo: Periodo,
    funcao: str,
    planilhas_mes_corrente: list[PlanilhaParseada],
    avisos_estruturais: list[str],
    historico: list[HistoricoMetrica],
    cadastro_nomes: dict[str, str | None],
    emails_filtro: set[str] | None,
    hoje: date,
) -> dict:
    avisos = list(avisos_estruturais)

    mes_corrente_inicio = date(hoje.year, hoje.month, 1)
    mes_corrente_fim = date(hoje.year, hoje.month, calendar.monthrange(hoje.year, hoje.month)[1])
    periodo_parcial = not (periodo.fim < mes_corrente_inicio or periodo.inicio > mes_corrente_fim)

    dados_mes_corrente: dict[str, _AcumuladorPessoa] = {}
    if periodo_parcial:
        no_mes_corrente = lambda d: (d.year, d.month) == (hoje.year, hoje.month)  # noqa: E731
        dia_inicio = periodo.inicio.day if no_mes_corrente(periodo.inicio) else 1
        dia_fim = (
            periodo.fim.day
            if no_mes_corrente(periodo.fim)
            else calendar.monthrange(hoje.year, hoje.month)[1]
        )
        dados_mes_corrente = calcular_mes_corrente(
            planilhas_mes_corrente,
            funcao,
            hoje.year,
            hoje.month,
            dia_inicio,
            dia_fim,
            emails_filtro,
            avisos,
        )

    historico_somado = _somar_historico(historico, funcao, emails_filtro)

    emails = set(dados_mes_corrente) | set(historico_somado)
    colunas = _colunas_da_funcao(funcao)

    pessoas_saida = []
    for email in sorted(emails):
        acumulador = dados_mes_corrente.get(email)
        planilhas_origem = acumulador.planilhas_origem if acumulador else []
        totais_mc = acumulador.totais_por_metrica if acumulador else {}
        totais_hist = historico_somado.get(email, {})

        metricas_saida = []
        atingidas = 0
        for info in colunas:
            mc = totais_mc.get(info.chave, _TOTAIS_ZERADOS)
            hs = totais_hist.get(info.chave, _TOTAIS_ZERADOS)
            meta_total = mc["meta_periodo"] + hs["meta_periodo"]
            realizado_total = mc["realizado"] + hs["realizado"]
            dias_com_lacuna = mc["dias_com_lacuna"] + hs["dias_com_lacuna"]
            dias_considerados = mc["dias_considerados"] + hs["dias_considerados"]

            status = _status(realizado_total, meta_total, dias_com_lacuna, dias_considerados)
            if status == "atingido":
                atingidas += 1

            metricas_saida.append(
                {
                    "metrica": info.chave,
                    "nome_exibicao": info.nome_exibicao,
                    "meta_periodo": meta_total,
                    "realizado": realizado_total,
                    "status": status,
                    "dias_com_lacuna": dias_com_lacuna,
                }
            )

        pessoas_saida.append(
            {
                "email": email,
                "nome": cadastro_nomes.get(email),
                "metas_atingidas": {"atingidas": atingidas, "total": len(metricas_saida)},
                "metricas": metricas_saida,
                "planilhas_origem": planilhas_origem,
                "pontuacao_total": acumulador.pontos if acumulador else 0,
            }
        )

    _atribuir_ranking(pessoas_saida)

    return {
        "periodo": {
            "granularidade": periodo.granularidade,
            "inicio": periodo.inicio.isoformat(),
            "fim": periodo.fim.isoformat(),
        },
        "periodo_parcial": periodo_parcial,
        "avisos": sorted(set(avisos)),
        "pessoas": pessoas_saida,
    }
