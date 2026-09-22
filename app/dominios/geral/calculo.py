"""Monta a resposta de `GET /geral`: 6 cards (2 escuros de faturamento + 4

claros somados de `dash.vw_metricas`), os próximos eventos que alimentam os
cards de Inscritos/Aprovados, tabela de pessoas (colunas por cargo) e
pontuação/ranking pros dois pódios (SDR e Closer) do frontend.
"""
from __future__ import annotations

from datetime import date

from app.dominios.comercial.banco import TotaisCargo
from app.dominios.geral.banco import EventoInscricoes, Faturamento
from app.dominios.pessoas.banco import Pessoa
from app.metas import Metas
from app.metricas import NOME_EXIBICAO
from app.periodo import Periodo, dias_uteis_decorridos
from app.pontuacao import atribuir_ranking

# Colunas da tabela de pessoas, por cargo (decisão de produto).
_METRICAS_SDR_TABELA = ("numeros_captados", "ligacoes_agendadas", "indicacoes")
_METRICAS_CLOSER_TABELA = ("reunioes_realizadas", "liquidado", "aprovados", "indicacoes")

# Métricas que ENTRAM NA PONTUAÇÃO (e, por consequência, no pódio) — nem toda
# coluna da tabela conta. A pontuação da Geral é a SOMA BRUTA do realizado
# dessas métricas (não depende de meta cadastrada — ver `_pontuacao_por_quantidade`).
# `liquidado` e `aprovados` ficam de fora por decisão de produto: são
# métricas financeiras, não de atividade, e não fazem sentido somadas junto
# com contagens de reunião/indicação numa única pontuação. Elas seguem
# visíveis na tabela, só não pontuam.
# Denominador fixo por cargo: todo closer é medido pelas mesmas métricas,
# senão o ranking compararia somas de tamanhos diferentes.
_METRICAS_PONTUACAO = {
    "sdr": _METRICAS_SDR_TABELA,
    "closer": ("reunioes_realizadas", "indicacoes"),
}

# Inscritos/Aprovados saíram daqui: viraram `eventos` na resposta — não são
# mais um número do período, e sim os próximos eventos girando no card.
#
# Realizado dos escuros vem de `dash.metricas_faturamento` (número fechado da
# empresa) SEMPRE DO MÊS (`faturamento_mes`), nunca do recorte pedido — e SEM
# meta: faturamento e liquidado nunca tiveram (faturamento) ou
# não têm mais (liquidado) uma composição de pessoas que os carregue, então
# ficam sempre com `meta`/`pct`/`pct_ritmo` em `None`. Só os 4 cards claros
# continuam com a meta somada por pessoa.
_COMPOSICAO_CARDS_ESCUROS: tuple[str, ...] = ("faturamento", "liquidado")

# Card claro da empresa -> (cargo, métrica) que o compõem. Uma definição só
# para o realizado E para a meta: era a duplicação entre os dois que fazia
# "Reuniões Agendadas" somar o realizado de 4 closers contra a meta de 7
# pessoas. Reuniões agendadas e indicações são de SDR + Closer; números
# captados e ligações agendadas, só de SDR.
_COMPOSICAO_CARDS_CLAROS: dict[str, tuple[tuple[str, str], ...]] = {
    "numeros_captados": (("sdr", "numeros_captados"),),
    "ligacoes_agendadas": (("sdr", "ligacoes_agendadas"),),
    "reunioes_agendadas": (("sdr", "reunioes_agendadas"), ("closer", "reunioes_agendadas")),
    "indicacoes": (("sdr", "indicacoes"), ("closer", "indicacoes")),
}


def _pct(realizado: float | None, meta: float | None) -> float | None:
    if realizado is None or meta is None or meta <= 0:
        return None
    return round(realizado / meta * 100, 1)


def _pct_ritmo(realizado: float | None, meta: float | None, fracao_decorrida: float) -> float | None:
    if realizado is None or meta is None or meta <= 0 or fracao_decorrida <= 0:
        return None
    return round(realizado / (meta * fracao_decorrida) * 100, 1)


def _rotulo(nome: str, cargo: str, nomes_repetidos: set[str]) -> str:
    if nome in nomes_repetidos:
        return f"{nome} ({'SDR' if cargo == 'sdr' else 'Closer'})"
    return nome


def _meta_card_empresa(
    metas: Metas,
    periodo: Periodo,
    composicao: tuple[tuple[str, str], ...],
    pessoas_por_cargo: dict[str, list[Pessoa]],
) -> int | None:
    """Meta do card da empresa = SOMA das metas individuais das pessoas ativas

    dos cargos que compõem o card (ex: reuniões agendadas = as metas dos 3
    SDRs + as dos 4 Closers). `dash.metricas_metas` não guarda linha de
    empresa justamente por isso: o número acompanha o time sem ninguém
    recadastrar quando alguém entra ou sai — e agora acompanha também quem
    tem meta maior que o colega, coisa que a meta por cargo achatava.

    `None` se QUALQUER pessoa da composição estiver sem meta cadastrada (ou
    se a composição for vazia) — nunca a meta de parte do time contra um
    realizado que soma o time inteiro.
    """
    if not composicao:
        return None
    total = 0
    for cargo, metrica in composicao:
        parcial = metas.somar(
            periodo.inicio, periodo.fim, [int(p.id) for p in pessoas_por_cargo[cargo]], metrica
        )
        if parcial is None:
            return None
        total += parcial
    return total


def _pontuacao_por_quantidade(metricas_calc: list[dict], metricas: tuple[str, ...]) -> float:
    """Soma bruta do realizado das métricas de pontuação do cargo — nunca

    `None` (as métricas em `_METRICAS_PONTUACAO` sempre têm `realizado`
    numérico, nunca `None`: vêm de `totais_sdr.realizado.get(..., 0)`/
    `totais_closer.realizado.get(..., 0)`). Diferente de `/comercial/*`
    (`calcular_pontuacao`, % da meta), a pontuação da Geral não depende de
    meta cadastrada — é assim que todo mundo do cargo entra no ranking.
    """
    return sum(m["realizado"] or 0 for m in metricas_calc if m["metrica"] in metricas)


def _montar_pessoa(pessoa: Pessoa, cargo: str, metricas_calc: list[dict], nomes_repetidos: set[str]) -> dict:
    pontuacao = _pontuacao_por_quantidade(metricas_calc, _METRICAS_PONTUACAO[cargo])
    return {
        "id_user": int(pessoa.id),
        "nome": pessoa.nome,
        "cargo": cargo,
        "rotulo": _rotulo(pessoa.nome, cargo, nomes_repetidos),
        "imagem_url": pessoa.imagem_url,
        "pontuacao": pontuacao,
        "posicao": None,  # preenchido por atribuir_ranking, abaixo
        "metricas": [
            {
                "metrica": m["metrica"],
                "nome_exibicao": NOME_EXIBICAO[m["metrica"]],
                "realizado": m["realizado"],
                "meta": m["meta_periodo"],
            }
            for m in metricas_calc
        ],
    }


def montar_resposta_geral(
    periodo_metas: Periodo,
    periodo_saida: Periodo,
    hoje: date,
    pessoas_sdr: list[Pessoa],
    pessoas_closer: list[Pessoa],
    totais_sdr: TotaisCargo,
    totais_closer: TotaisCargo,
    metas: Metas,
    faturamento: Faturamento,
    faturamento_mes: Faturamento,
    eventos: list[EventoInscricoes],
) -> dict:
    """`periodo_metas` é o período pedido por inteiro (dia/mês/ano completo,

    nunca capado em hoje) — é ele que decide "meta cheia" e o denominador do
    ritmo. `periodo_saida` é o mesmo período capado em hoje (nunca pede dado
    do futuro) — é o que aparece no campo `periodo` da resposta e delimitou
    as consultas de `vw_metricas`/faturamento que já vieram prontas em
    `totais_sdr`/`totais_closer`/`faturamento`.

    `metas` é por PESSOA (`dash.user_metas`): cada card da empresa soma as
    metas de quem o compõe, e cada linha da tabela usa a meta daquela pessoa.
    Quem não tem meta cadastrada fica com `None`, nunca com 0.

    `faturamento` é do período pedido e alimenta as colunas Liquidado/Aprovados
    do closer na tabela. `faturamento_mes` é do MÊS (corrente sob
    dia/semana/ano; o navegado sob mês) e alimenta só os dois cards escuros —
    ver o comentário em `rotas.py`. Sob granularidade Mês os dois são o mesmo
    objeto.

    `eventos` é a única parte da resposta que ignora o período pedido: são os
    próximos eventos (futuro), independentes do recorte de datas da página.
    """
    dias_decorridos = dias_uteis_decorridos(periodo_metas.inicio, periodo_metas.fim, hoje=hoje)
    dias_totais = dias_uteis_decorridos(periodo_metas.inicio, periodo_metas.fim, hoje=periodo_metas.fim)
    fracao_decorrida = dias_decorridos / dias_totais if dias_totais else 0.0

    pessoas_por_cargo = {"sdr": pessoas_sdr, "closer": pessoas_closer}

    cards = []
    for chave in _COMPOSICAO_CARDS_ESCUROS:
        realizado = faturamento_mes.empresa.get(chave)
        cards.append(
            {
                "metrica": chave,
                "nome_exibicao": NOME_EXIBICAO[chave],
                "escuro": True,
                "realizado": realizado,
                "meta": None,
                "pct": None,
                "pct_ritmo": None,
            }
        )

    totais_por_cargo = {"sdr": totais_sdr, "closer": totais_closer}

    for chave, composicao in _COMPOSICAO_CARDS_CLAROS.items():
        realizado = sum(
            totais_por_cargo[cargo].realizado.get((int(pessoa.id), metrica), 0)
            for cargo, metrica in composicao
            for pessoa in pessoas_por_cargo[cargo]
        )
        meta = _meta_card_empresa(metas, periodo_metas, composicao, pessoas_por_cargo)
        cards.append(
            {
                "metrica": chave,
                "nome_exibicao": NOME_EXIBICAO[chave],
                "escuro": False,
                "realizado": realizado,
                "meta": meta,
                "pct": _pct(realizado, meta),
                "pct_ritmo": _pct_ritmo(realizado, meta, fracao_decorrida),
            }
        )

    todos_nomes = [p.nome for p in pessoas_sdr] + [p.nome for p in pessoas_closer]
    nomes_repetidos = {nome for nome in todos_nomes if todos_nomes.count(nome) > 1}

    def meta_de(id_user: int, chave: str) -> int | None:
        return metas.por_usuario(periodo_metas.inicio, periodo_metas.fim, id_user, chave)

    pessoas_saida = []
    for pessoa in pessoas_sdr:
        id_user = int(pessoa.id)
        metricas_calc = [
            {
                "metrica": chave,
                "realizado": totais_sdr.realizado.get((id_user, chave), 0),
                "meta_periodo": meta_de(id_user, chave),
            }
            for chave in _METRICAS_SDR_TABELA
        ]
        pessoas_saida.append(_montar_pessoa(pessoa, "sdr", metricas_calc, nomes_repetidos))

    for pessoa in pessoas_closer:
        id_user = int(pessoa.id)
        financeiro = faturamento.por_pessoa.get(id_user, {})
        metricas_calc = [
            {
                "metrica": "reunioes_realizadas",
                "realizado": totais_closer.realizado.get((id_user, "reunioes_realizadas"), 0),
                "meta_periodo": meta_de(id_user, "reunioes_realizadas"),
            },
            {
                "metrica": "liquidado",
                "realizado": financeiro.get("liquidado"),
                "meta_periodo": meta_de(id_user, "liquidado"),
            },
            {
                "metrica": "aprovados",
                "realizado": financeiro.get("aprovados"),
                "meta_periodo": meta_de(id_user, "aprovados"),
            },
            {
                "metrica": "indicacoes",
                "realizado": totais_closer.realizado.get((id_user, "indicacoes"), 0),
                "meta_periodo": meta_de(id_user, "indicacoes"),
            },
        ]
        pessoas_saida.append(_montar_pessoa(pessoa, "closer", metricas_calc, nomes_repetidos))

    atribuir_ranking(pessoas_saida, "pontuacao")

    avisos: list[str] = []
    if metas.vazio:
        avisos.append("metas_nao_cadastradas")
    if totais_sdr.linhas_cargo_cruzado or totais_closer.linhas_cargo_cruzado:
        avisos.append("linhas_cargo_cruzado_ignoradas")

    return {
        "periodo": {
            "granularidade": periodo_saida.granularidade,
            "inicio": periodo_saida.inicio.isoformat(),
            "fim": periodo_saida.fim.isoformat(),
        },
        "dias_uteis": {"decorridos": dias_decorridos, "total": dias_totais},
        "cards": cards,
        "eventos": [
            {
                "id": e.id,
                "titulo": e.titulo,
                "data": e.data,
                "capacidade": e.capacidade,
                "inscritos": e.inscritos,
                "aprovados": e.aprovados,
            }
            for e in eventos
        ],
        "pessoas": pessoas_saida,
        "avisos": avisos,
    }
