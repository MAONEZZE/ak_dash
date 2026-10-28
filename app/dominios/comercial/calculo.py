"""Monta a resposta de `/comercial/{sdr,closer}` a partir de `vw_metricas` + `dash.metricas_metas`.

Pontuação: a mesma do dash inteiro — Σ realizado × peso por cargo, ver
`app/pontuacao.py`. Não depende de meta.

A meta é de cada PESSOA (`dash.user_metas`), não mais do cargo: dois SDRs do
mesmo squad podem ser cobrados por números diferentes, e o ranking continua
comparando percentual de meta, não valor absoluto.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from app.dominios.comercial.banco import TotaisCargo
from app.dominios.pessoas.banco import Pessoa
from app.indicadores import calcular_indicadores
from app.metas import Metas
from app.metricas import metricas_do_cargo, nome_exibicao
from app.periodo import TZ_SP, Periodo, dias_uteis_meta
from app.pontuacao import atribuir_ranking, calcular_pontuacao



def _status(realizado: int, meta_periodo: int | None, dias_com_lancamento: int) -> str:
    # Meta 0 = métrica aberta, sem cobrança: sem isso, `realizado >= 0`
    # sempre bate e a métrica aparece "atingida".
    if dias_com_lancamento == 0:
        return "sem_preenchimento"
    if meta_periodo is None or meta_periodo == 0:
        return "sem_meta"
    return "atingido" if realizado >= meta_periodo else "abaixo_da_meta"


@dataclass(frozen=True)
class RespostaCargo:
    corpo: dict
    linhas_cargo_cruzado: int


def montar_resposta_comercial(
    periodo: Periodo,
    cargo: str,
    pessoas_cargo: list[Pessoa],
    totais: TotaisCargo,
    metas: Metas,
    emails_filtro: set[str] | None,
    hoje: date,
    *,
    agora: datetime | None = None,
    expediente_inicio: time = time(10, 0),
    expediente_fim: time = time(19, 0),
) -> RespostaCargo:
    """`cargo` só decide QUAIS métricas entram nas colunas (`metricas_do_cargo`);

    o valor da meta vem de cada pessoa. Pessoa sem meta cadastrada numa
    métrica fica com `meta_periodo` `None` e status `sem_meta` — nunca 0.
    """
    agora = agora or datetime.combine(hoje, time(0, 0), tzinfo=TZ_SP)
    dias_uteis = dias_uteis_meta(periodo.inicio, periodo.fim, hoje)
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
            meta_periodo = metas.por_usuario(periodo.inicio, periodo.fim, id_user, cargo, chave_metrica)
            status = _status(realizado, meta_periodo, dias_com_lancamento)
            if status == "atingido":
                atingidas += 1
            metricas_saida.append(
                {
                    "metrica": chave_metrica,
                    "nome_exibicao": nome_exibicao(chave_metrica, cargo),
                    "meta_periodo": meta_periodo,
                    "realizado": realizado,
                    "status": status,
                    "dias_com_lacuna": max(
                        0,
                        (periodo.fim - periodo.inicio).days + 1 - dias_com_lancamento,
                    ),
                    **calcular_indicadores(
                        realizado, meta_periodo, periodo, dias_uteis, agora, expediente_inicio, expediente_fim,
                    ),
                }
            )

        pessoas_saida.append(
            {
                "id_user": str(id_user),
                "email": pessoa.email,
                "nome": pessoa.nome or None,
                "imagem_url": pessoa.imagem_url,
                "metas_atingidas": {"atingidas": atingidas, "total": len(metricas_saida)},
                "metricas": metricas_saida,
                "contas_origem": totais.contas_por_pessoa.get(id_user, []),
                "pontuacao_total": calcular_pontuacao(cargo, {m["metrica"]: m["realizado"] for m in metricas_saida}),
            }
        )

    atribuir_ranking(pessoas_saida, "pontuacao_total")

    ids_alvo = [int(p.id) for p in pessoas_alvo]
    metricas_time = []
    for chave_metrica in colunas:
        realizado = sum(totais.realizado.get((i, chave_metrica), 0) for i in ids_alvo)
        meta = metas.somar(periodo.inicio, periodo.fim, ids_alvo, cargo, chave_metrica)
        metricas_time.append(
            {
                "metrica": chave_metrica,
                "nome_exibicao": nome_exibicao(chave_metrica, cargo),
                "meta_periodo": meta,
                "realizado": realizado,
                **calcular_indicadores(
                    realizado, meta, periodo, dias_uteis, agora, expediente_inicio, expediente_fim,
                ),
            }
        )

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
        # Mesmo cálculo de `/geral`: período passado sai decorridos = total,
        # período futuro sai decorridos = 0.
        "dias_uteis": dias_uteis,
        "avisos": avisos,
        "pessoas": pessoas_saida,
        "metricas_time": metricas_time,
        "serie_diaria": [
            {"dia": dia.isoformat(), "metricas": metricas}
            for dia, metricas in sorted(totais.serie_diaria.items())
        ],
    }
    return RespostaCargo(corpo=corpo, linhas_cargo_cruzado=totais.linhas_cargo_cruzado)
