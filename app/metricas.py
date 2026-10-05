"""Vocabulário de métricas — um nome só, em todo o sistema.

A chave de métrica é o nome da COLUNA nas tabelas de origem
(`dash.metricas_sdrs`, `metricas_closers`, `metricas_dripify`), que é também
o que `dash.metricas_metas.metrica` guarda e o que `dash.vw_metricas` emite.
Não existe tradução em lugar nenhum: banco, BFF e payload da API falam o
mesmo idioma, então não há um segundo lugar pra divergir.

`reuniao_agendado`/`numero`/`follow_up` etc. eram o vocabulário da view
antiga, que não existe mais — ver sql/2026-09-15-view-metricas.sql.
"""
from __future__ import annotations

# `ligacoes_realizadas`, `reunioes_agendadas`, `indicacoes` e
# `inscricoes_realizadas` aparecem nos DOIS cargos, cada pessoa com a sua meta
# (meta é por pessoa, em `dash.user_metas`). `ligacoes_agendadas` saiu de
# `dash.metricas_sdrs` em 02/10/2026 e hoje é só de closer.
METRICAS_SDR: tuple[str, ...] = (
    "conexoes_enviadas",
    "conexoes_aceitas",
    "abordagens",
    "in_mails",
    "fups",
    "numeros_captados",
    "inscricoes_realizadas",
    "ligacoes_realizadas",
    "indicacoes",
    "reunioes_agendadas",
)

METRICAS_CLOSER: tuple[str, ...] = (
    "ligacoes_agendadas",
    "ligacoes_realizadas",
    "reunioes_agendadas",
    "reunioes_realizadas",
    "indicacoes",
    "inscricoes_realizadas",
)

NOME_EXIBICAO: dict[str, str] = {
    "conexoes_enviadas": "Conexões Enviadas",
    "conexoes_aceitas": "Conexões Aceitas",
    "abordagens": "Abordagens",
    "in_mails": "InMails Enviados",
    "fups": "Follow-ups",
    "numeros_captados": "Números Captados",
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


# No SDR a indicação é captada (o closer só "indica"): mesmo nome de coluna,
# rótulo diferente por cargo.
_NOME_EXIBICAO_SDR: dict[str, str] = {"indicacoes": "Indicações Captadas"}


def nome_exibicao(metrica: str, cargo: str | None = None) -> str:
    """Rótulo da métrica na tela. `cargo` só muda o rótulo onde o nome difere

    entre SDR e Closer; sem cargo (cards da empresa que somam os dois) vale o
    nome geral.
    """
    if cargo == "sdr" and metrica in _NOME_EXIBICAO_SDR:
        return _NOME_EXIBICAO_SDR[metrica]
    return NOME_EXIBICAO[metrica]


def metricas_do_cargo(cargo: str) -> tuple[str, ...]:
    """Conjunto de métricas válidas para o cargo — usado pra descartar linha

    de cargo cruzado. A view já filtra por `users.id_cargo`, então isso hoje
    é rede de segurança: se a view voltar a emitir métrica de outro cargo, a
    linha é ignorada e contada, não somada em silêncio.
    """
    if cargo == "sdr":
        return METRICAS_SDR
    if cargo == "closer":
        return METRICAS_CLOSER
    return ()
