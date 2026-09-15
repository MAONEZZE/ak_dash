"""Monta a resposta de `/comercial/{sdr,closer}` a partir de `vw_metricas` + `dash.metricas_metas`.

Pontuação (decisão de produto, substitui a gamificação antiga de "1 ponto
por dia×métrica que bateu a meta diária"): `Σ(realizado/meta × 100) /
qtd_metricas`, escala 0–100, SEM cap, contra a meta cheia do período — só
calculada quando TODAS as métricas do cargo têm meta cadastrada pra aquela
pessoa; caso contrário `None` (nunca uma média parcial disfarçada de total).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.dominios.comercial.banco import TotaisCargo
from app.dominios.pessoas.banco import Pessoa
from app.metas import Metas
from app.metricas import NOME_EXIBICAO, metricas_do_cargo
from app.periodo import Periodo
from app.pontuacao import atribuir_ranking, calcular_pontuacao


def _status(realizado: int, meta_periodo: int | None, dias_com_lancamento: int) -> str:
    if dias_com_lancamento == 0:
        return "sem_preenchimento"
    if meta_periodo is None:
        return "sem_meta"
    return "atingido" if realizado >= meta_periodo else "abaixo_da_meta"


@dataclass(frozen=True)
class RespostaCargo:
    corpo: dict
    linhas_cargo_cruzado: int


def montar_resposta_comercial(
    periodo: Periodo,
    cargo: str,
    id_cargo: int | None,
    pessoas_cargo: list[Pessoa],
    totais: TotaisCargo,
    metas: Metas,
    emails_filtro: set[str] | None,
    hoje: date,
) -> RespostaCargo:
    """`id_cargo` vem de `dash.metricas_cargo` (via `app.cargos.buscar_cargos`) —

    `None` quando o cargo não foi encontrado nessa tabela (degradação: toda
    meta do cargo vira `None`, nunca 0).
    """
    pessoas_alvo = [p for p in pessoas_cargo if emails_filtro is None or p.email in emails_filtro]
    colunas = metricas_do_cargo(cargo)

    pessoas_saida = []
    for pessoa in pessoas_alvo:
        id_user = int(pessoa.id)
        metricas_saida = []
        atingidas = 0
        for chave_metrica in colunas:
            realizado = totais.realizado.get((id_user, chave_metrica), 0)
            dias_com_lancamento = totais.dias_com_lancamento.get((id_user, chave_metrica), 0)
            meta_periodo = (
                metas.por_cargo(periodo.inicio, periodo.fim, id_cargo, chave_metrica)
                if id_cargo is not None
                else None
            )
            status = _status(realizado, meta_periodo, dias_com_lancamento)
            if status == "atingido":
                atingidas += 1
            metricas_saida.append(
                {
                    "metrica": chave_metrica,
                    "nome_exibicao": NOME_EXIBICAO[chave_metrica],
                    "meta_periodo": meta_periodo,
                    "realizado": realizado,
                    "status": status,
                    "dias_com_lacuna": max(
                        0,
                        (periodo.fim - periodo.inicio).days + 1 - dias_com_lancamento,
                    ),
                }
            )

        pessoas_saida.append(
            {
                "id_user": str(id_user),
                "email": pessoa.email,
                "nome": pessoa.nome or None,
                "metas_atingidas": {"atingidas": atingidas, "total": len(metricas_saida)},
                "metricas": metricas_saida,
                "contas_origem": totais.contas_por_pessoa.get(id_user, []),
                "pontuacao_total": calcular_pontuacao(metricas_saida),
            }
        )

    atribuir_ranking(pessoas_saida, "pontuacao_total")

    mes_corrente_inicio = date(hoje.year, hoje.month, 1)
    periodo_parcial = periodo.fim >= mes_corrente_inicio and periodo.inicio <= hoje

    avisos: list[str] = []
    if totais.linhas_cargo_cruzado:
        avisos.append(
            f"{totais.linhas_cargo_cruzado} linha(s) de métrica fora do conjunto do cargo "
            f"'{cargo}' foram ignoradas (dado de outro cargo em vw_metricas)"
        )
    if metas.vazio:
        avisos.append("metas_nao_cadastradas")

    corpo = {
        "periodo": {
            "granularidade": periodo.granularidade,
            "inicio": periodo.inicio.isoformat(),
            "fim": periodo.fim.isoformat(),
        },
        "periodo_parcial": periodo_parcial,
        "avisos": avisos,
        "pessoas": pessoas_saida,
        "serie_diaria": [
            {"dia": dia.isoformat(), "metricas": metricas}
            for dia, metricas in sorted(totais.serie_diaria.items())
        ],
    }
    return RespostaCargo(corpo=corpo, linhas_cargo_cruzado=totais.linhas_cargo_cruzado)
