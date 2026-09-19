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

# `reunioes_agendadas` e `indicacoes` aparecem nos DOIS cargos: SDR e closer
# agendam reunião e trabalham indicação, cada um com a sua meta (hoje meta é
# por pessoa, em `dash.user_metas`).
METRICAS_SDR: tuple[str, ...] = (
    "conexoes_enviadas",
    "conexoes_aceitas",
    "abordagens",
    "in_mails",
    "fups",
    "numeros_captados",
    "ligacoes_agendadas",
    "reunioes_agendadas",
    "indicacoes",
)

METRICAS_CLOSER: tuple[str, ...] = (
    "ligacoes_realizadas",
    "reunioes_agendadas",
    "reunioes_realizadas",
    "indicacoes",
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
    # Métricas financeiras (fora de vw_metricas, ver dominios/geral/banco.py)
    "faturamento": "Faturamento",
    "liquidado": "Liquidado",
    "inscritos": "Inscritos",
    "aprovados": "Aprovados",
}


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
