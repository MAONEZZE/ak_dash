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
from app.pontuacao import atribuir_ranking, calcular_pontuacao

# Colunas da tabela de pessoas, por cargo (decisão de produto).
_METRICAS_SDR_TABELA = ("numeros_captados", "ligacoes_agendadas", "indicacoes")
_METRICAS_CLOSER_TABELA = ("reunioes_realizadas", "liquidado", "aprovados", "indicacoes")

# Métricas que ENTRAM NA PONTUAÇÃO (e, por consequência, no pódio) — nem toda
# coluna da tabela conta. `liquidado` e `aprovados` ficam de fora enquanto
# `dash.metricas_faturamento` não tiver as colunas de negócio: elas voltam
# `None` pra todo closer, e uma métrica sem realizado zera a pontuação inteira
# (regra de `pontuacao.py`) — era exatamente isso que deixava o pódio de
# Closer vazio enquanto o de SDR aparecia. Elas seguem visíveis na tabela,
# só não pontuam. Denominador fixo por cargo: todo closer é medido pelas
# mesmas métricas, senão o ranking compararia médias de tamanhos diferentes.
_METRICAS_PONTUACAO = {
    "sdr": _METRICAS_SDR_TABELA,
    "closer": ("reunioes_realizadas", "indicacoes"),
}

# Inscritos/Aprovados saíram daqui: viraram `eventos` na resposta — não são
# mais um número do período, e sim os próximos eventos girando no card.
_CARDS_ESCUROS = ("faturamento", "liquidado")

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
    id_por_cargo: dict[str, int | None],
    pessoas_por_cargo: dict[str, list[Pessoa]],
) -> int | None:
    """Meta do card da empresa = meta do CARGO × pessoas ativas daquele cargo,

    somada sobre os cargos que compõem o card (ex: reuniões agendadas = 4/dia
    × 3 SDRs + 4/dia × 4 Closers = 28/dia). `dash.metricas_metas` não guarda linha de
    empresa pras métricas de cargo justamente por isso: o número acompanha o
    time sem ninguém recadastrar quando alguém entra ou sai.

    `None` se QUALQUER parte não tiver meta cadastrada — nunca meta de um
    cargo só contra um realizado que soma os dois.
    """
    total = 0
    for cargo, metrica in composicao:
        id_cargo = id_por_cargo.get(cargo)
        if id_cargo is None:
            return None
        meta_por_pessoa = metas.por_cargo(periodo.inicio, periodo.fim, id_cargo, metrica)
        if meta_por_pessoa is None:
            return None
        total += meta_por_pessoa * len(pessoas_por_cargo[cargo])
    return total


def _montar_pessoa(pessoa: Pessoa, cargo: str, metricas_calc: list[dict], nomes_repetidos: set[str]) -> dict:
    pontuacao = calcular_pontuacao(
        [m for m in metricas_calc if m["metrica"] in _METRICAS_PONTUACAO[cargo]]
    )
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
    id_cargo_sdr: int | None,
    id_cargo_closer: int | None,
    id_cargo_empresa: int | None,
    faturamento: Faturamento,
    eventos: list[EventoInscricoes],
) -> dict:
    """`periodo_metas` é o período pedido por inteiro (dia/mês/ano completo,

    nunca capado em hoje) — é ele que decide "meta cheia" e o denominador do
    ritmo. `periodo_saida` é o mesmo período capado em hoje (nunca pede dado
    do futuro) — é o que aparece no campo `periodo` da resposta e delimitou
    as consultas de `vw_metricas`/faturamento que já vieram prontas em
    `totais_sdr`/`totais_closer`/`faturamento`.

    `id_cargo_empresa` é o cargo `empresa` de `dash.metricas_cargo` — é nele
    que ficam penduradas as metas que não são de ninguém em particular
    (faturamento, liquidado). `None` (cargo ausente da tabela) degrada pra
    meta `None`, nunca pra 0.

    `eventos` é a única parte da resposta que ignora o período pedido: são os
    próximos eventos (futuro), independentes do recorte de datas da página.
    """
    dias_decorridos = dias_uteis_decorridos(periodo_metas.inicio, periodo_metas.fim, hoje=hoje)
    dias_totais = dias_uteis_decorridos(periodo_metas.inicio, periodo_metas.fim, hoje=periodo_metas.fim)
    fracao_decorrida = dias_decorridos / dias_totais if dias_totais else 0.0

    cards = []
    for chave in _CARDS_ESCUROS:
        realizado = faturamento.empresa.get(chave)
        meta = (
            metas.por_cargo(periodo_metas.inicio, periodo_metas.fim, id_cargo_empresa, chave)
            if id_cargo_empresa is not None
            else None
        )
        cards.append(
            {
                "metrica": chave,
                "nome_exibicao": NOME_EXIBICAO[chave],
                "escuro": True,
                "realizado": realizado,
                "meta": meta,
                "pct": _pct(realizado, meta),
                "pct_ritmo": _pct_ritmo(realizado, meta, fracao_decorrida),
            }
        )

    totais_por_cargo = {"sdr": totais_sdr, "closer": totais_closer}
    pessoas_por_cargo = {"sdr": pessoas_sdr, "closer": pessoas_closer}
    id_por_cargo = {"sdr": id_cargo_sdr, "closer": id_cargo_closer}

    for chave, composicao in _COMPOSICAO_CARDS_CLAROS.items():
        realizado = sum(
            totais_por_cargo[cargo].realizado.get((int(pessoa.id), metrica), 0)
            for cargo, metrica in composicao
            for pessoa in pessoas_por_cargo[cargo]
        )
        meta = _meta_card_empresa(metas, periodo_metas, composicao, id_por_cargo, pessoas_por_cargo)
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

    pessoas_saida = []
    meta_sdr = {
        chave: metas.por_cargo(periodo_metas.inicio, periodo_metas.fim, id_cargo_sdr, chave) if id_cargo_sdr is not None else None
        for chave in _METRICAS_SDR_TABELA
    }
    for pessoa in pessoas_sdr:
        id_user = int(pessoa.id)
        metricas_calc = [
            {
                "metrica": chave,
                "realizado": totais_sdr.realizado.get((id_user, chave), 0),
                "meta_periodo": meta_sdr[chave],
            }
            for chave in _METRICAS_SDR_TABELA
        ]
        pessoas_saida.append(_montar_pessoa(pessoa, "sdr", metricas_calc, nomes_repetidos))

    meta_closer = {
        chave: metas.por_cargo(periodo_metas.inicio, periodo_metas.fim, id_cargo_closer, chave) if id_cargo_closer is not None else None
        for chave in _METRICAS_CLOSER_TABELA
    }
    for pessoa in pessoas_closer:
        id_user = int(pessoa.id)
        financeiro = faturamento.por_pessoa.get(id_user, {})
        metricas_calc = [
            {
                "metrica": "reunioes_realizadas",
                "realizado": totais_closer.realizado.get((id_user, "reunioes_realizadas"), 0),
                "meta_periodo": meta_closer["reunioes_realizadas"],
            },
            {
                "metrica": "liquidado",
                "realizado": financeiro.get("liquidado"),
                "meta_periodo": meta_closer["liquidado"],
            },
            {
                "metrica": "aprovados",
                "realizado": financeiro.get("aprovados"),
                "meta_periodo": meta_closer["aprovados"],
            },
            {
                "metrica": "indicacoes",
                "realizado": totais_closer.realizado.get((id_user, "indicacoes"), 0),
                "meta_periodo": meta_closer["indicacoes"],
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
