"""Vocabulário de métricas — um nome só, em todo o sistema.

A chave de métrica é o nome da COLUNA nas tabelas de origem
(`dash.metricas_sdrs`, `metricas_closers`, `metricas_dripify`), que é também
o que `dash.metricas_metas.metrica` guarda e o que `dash.vw_metricas` emite.
Não existe tradução em lugar nenhum: banco, BFF e payload da API falam o
mesmo idioma, então não há um segundo lugar pra divergir.

`reuniao_agendado`/`numero`/`follow_up` etc. eram o vocabulário da view
antiga, que não existe mais — ver sql/2026-09-15-view-metricas.sql.

As listas por cargo seguem as planilhas do dash2 (uma tabela por cargo, na
ordem das colunas da planilha). Não são mais a união de um cargo só.
"""
from __future__ import annotations

# Seller (captação): fups, números captados e indicações.
METRICAS_SELLER: tuple[str, ...] = (
    "fups",
    "numeros_captados",
    "indicacoes",
)

# SDR: ligações e captação de inscrições/indicações/reuniões.
# `ligacoes_realizadas`, `reunioes_agendadas`, `indicacoes` e
# `inscricoes_realizadas` também aparecem no closer, cada pessoa com a sua meta
# (meta é por pessoa, em `dash.user_metas`).
METRICAS_SDR: tuple[str, ...] = (
    "ligacoes_efetuadas",
    "ligacoes_realizadas",
    "inscricoes_realizadas",
    "indicacoes",
    "reunioes_agendadas",
)

# Closer: `ligacoes_agendadas` saiu de `dash.metricas_sdrs` em 02/10/2026 e
# hoje é só de closer.
METRICAS_CLOSER: tuple[str, ...] = (
    "ligacoes_agendadas",
    "ligacoes_realizadas",
    "reunioes_agendadas",
    "reunioes_realizadas",
    "indicacoes",
    "inscricoes_realizadas",
)

# Dripify: conexões, abordagens e captação via LinkedIn.
METRICAS_DRIPIFY: tuple[str, ...] = (
    "conexoes_enviadas",
    "conexoes_aceitas",
    "abordagens",
    "in_mails",
    "fups",
    "numeros_captados",
)

NOME_EXIBICAO: dict[str, str] = {
    "conexoes_enviadas": "Conexões Enviadas",
    "conexoes_aceitas": "Conexões Aceitas",
    "abordagens": "Abordagens",
    "in_mails": "InMails Enviados",
    "fups": "Follow-ups",
    "numeros_captados": "Números Captados",
    "ligacoes_efetuadas": "Ligações Efetuadas",
    "ligacoes_agendadas": "Ligações Agendadas",
    "ligacoes_realizadas": "Ligações Realizadas",
    "reunioes_agendadas": "Reuniões Agendadas",
    "reunioes_realizadas": "Reuniões Realizadas",
    "indicacoes": "Indicações",
    "inscricoes_realizadas": "Inscrições Realizadas",
    # Métricas financeiras (fora de vw_metricas, ver dominios/geral/banco.py)
    "faturamento": "Faturamento",
    "liquidado": "Liquidado",
    "faturamento_base": "Faturamento Base",
    "liquidado_base": "Liquidado Base",
    "oportunidade": "Oportunidade",
    "inscritos": "Inscritos",
    "aprovados": "Aprovados",
}


# Na captação (SDR e seller) a indicação é captada (o closer só "indica"):
# mesmo nome de coluna, rótulo diferente por cargo.
_NOME_EXIBICAO_CAPTACAO: dict[str, str] = {"indicacoes": "Indicações Captadas"}


def nome_exibicao(metrica: str, cargo: str | None = None) -> str:
    """Rótulo da métrica na tela. `cargo` só muda o rótulo onde o nome difere

    entre captação (sdr/seller) e closer; sem cargo (cards da empresa que
    somam os dois) vale o nome geral.
    """
    if cargo in ("sdr", "seller") and metrica in _NOME_EXIBICAO_CAPTACAO:
        return _NOME_EXIBICAO_CAPTACAO[metrica]
    return NOME_EXIBICAO[metrica]


def metricas_do_cargo(cargo: str) -> tuple[str, ...]:
    """Conjunto de métricas válidas para o cargo — usado pra descartar linha

    de cargo cruzado. A view já filtra por `users.id_cargo`, então isso hoje
    é rede de segurança: se a view voltar a emitir métrica de outro cargo, a
    linha é ignorada e contada, não somada em silêncio.
    """
    return {
        "seller": METRICAS_SELLER,
        "sdr": METRICAS_SDR,
        "closer": METRICAS_CLOSER,
        "dripify": METRICAS_DRIPIFY,
    }.get(cargo, ())
