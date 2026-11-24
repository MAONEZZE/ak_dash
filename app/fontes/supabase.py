"""Leitura e escrita do Supabase principal (schema `NOME_SCHEMA`, hoje `dash_new`), uma função por dado. Leitura degrada para `[]` com aviso `fonte_indisponivel:<tabela>` (via `banco.query`); escrita levanta erro (workers)."""
from __future__ import annotations

from datetime import date, timedelta

from app.fontes import banco
from app.planilhas import COLUNAS_POR_TABELA


def ler_usuarios_ativos() -> list[dict]:
    return banco.query("users", {"active": "eq.true"})


def ler_cargos_dos_usuarios() -> list[dict]:
    return banco.query("user_cargos", colunas="id_user,cargo")


def ler_metas() -> list[dict]:
    return banco.query("metas", colunas="id_user,cargo,metrica,valor_diario")


def ler_metricas_do_cargo(cargo: str, ids: list[int], inicio: date, fim: date) -> list[dict]:
    return banco.query(
        "vw_metricas",
        {
            "id_user": f"in.({','.join(str(i) for i in ids)})",
            "and": f"(data.gte.{inicio.isoformat()},data.lte.{fim.isoformat()})",
            "cargo": f"eq.{cargo}",
        },
        colunas="data,id_user,metrica,valor,conta",
    )


def ler_vendas_do_periodo(inicio: date, fim: date) -> list[dict]:
    return banco.query(
        "metricas_faturamento",
        {"and": f"(data_venda.gte.{inicio.isoformat()},data_venda.lt.{(fim + timedelta(days=1)).isoformat()})"},
    )


def ler_recebimentos_do_periodo(inicio: date, fim: date) -> list[dict]:
    return banco.query(
        "recebimentos_faturamento",
        {"and": f"(mes.gte.{inicio.replace(day=1).isoformat()},mes.lte.{fim.isoformat()})"},
    )


def ler_vendas_por_id_planilha(ids: list[int], colunas: str = "*") -> list[dict]:
    return banco.query(
        "metricas_faturamento",
        {"id_planilha": f"in.({','.join(map(str, ids))})"},
        colunas=colunas,
    )


def ler_clientes_por_id(ids: list[int]) -> list[dict]:
    return banco.query("cliente_faturamento", {"id": f"in.({','.join(str(i) for i in ids)})"})


def ler_usuarios_por_id(ids: list[int]) -> list[dict]:
    return banco.query("users", {"id": f"in.({','.join(str(i) for i in ids)})"})


def ler_logs_do_periodo(inicio: date, fim: date) -> list[dict]:
    return banco.query(
        "logs_pipedrive",
        {"and": f"(data.gte.{inicio.isoformat()},data.lte.{fim.isoformat()})"},
        colunas="data,hora,usuario_acao,atividade,cliente_nome",
    )


def ler_contas_do_canal(canal: str) -> list[dict]:
    return banco.query("contas_funil", {"canal": f"eq.{canal}"}, colunas="id,canal,nome,id_seller")


def ler_metricas_das_contas(inicio: date, fim: date, ids: list[int] | None = None) -> list[dict]:
    filtros = {}
    if ids is not None:
        filtros["id_conta"] = f"in.({','.join(str(i) for i in ids)})"
    filtros["and"] = f"(data.gte.{inicio.isoformat()},data.lte.{fim.isoformat()})"
    return banco.query("metricas_contas", filtros, colunas="id_conta,data," + ",".join(COLUNAS_POR_TABELA["metricas_contas"]))


def ler_metricas_funil_sdr(inicio: date, fim: date) -> list[dict]:
    return banco.query(
        "metricas_funil_sdr",
        {"and": f"(data.gte.{inicio.isoformat()},data.lte.{fim.isoformat()})"},
        colunas="id_user,data," + ",".join(COLUNAS_POR_TABELA["metricas_funil_sdr"]),
    )


def ler_metas_funil_sdr() -> list[dict]:
    return banco.query("metas_funil_sdr", {}, colunas="metrica,periodo,id_user,valor")
