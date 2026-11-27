"""Leitura e escrita do Supabase principal (schema `NOME_SCHEMA`, hoje `dash_new`), uma função por dado. Leitura degrada para `[]` com aviso `fonte_indisponivel:<tabela>` (via `banco.query`); escrita levanta erro (workers)."""
from __future__ import annotations

from datetime import date, datetime

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


def ler_usuarios() -> list[dict]:
    return banco.query("users", {}, colunas="id,nome")


def ler_ids_com_cargo(cargo: str) -> list[dict]:
    return banco.query("user_cargos", {"cargo": f"eq.{cargo}"}, colunas="id_user")


def ler_metas_do_cargo(cargo: str) -> list[dict]:
    return banco.query("metas", {"cargo": f"eq.{cargo}"}, colunas="id_user,metrica,valor_diario")


def ler_metricas_planilha(tabela: str, inicio: date, fim: date, colunas: list[str]) -> list[dict]:
    return banco.query(
        tabela,
        {"and": f"(data.gte.{inicio.isoformat()},data.lte.{fim.isoformat()})"},
        colunas="id_user,data,key_data_ref_user," + ",".join(colunas),
    )


def gravar_metricas_planilha(tabela: str, linhas: list[dict]) -> None:
    banco.upsert(tabela, linhas, on_conflict="key_data_ref_user")


def gravar_metas(linhas: list[dict]) -> None:
    banco.upsert("metas", linhas, on_conflict="id_user,cargo,metrica")


def apagar_meta(id_user: int, cargo: str, metrica: str) -> None:
    banco.apagar("metas", {"id_user": f"eq.{id_user}", "cargo": f"eq.{cargo}", "metrica": f"eq.{metrica}"})


def gravar_metricas_funil_sdr(linhas: list[dict]) -> None:
    banco.upsert("metricas_funil_sdr", linhas, on_conflict="id_user,data")


def gravar_metas_funil_sdr(linhas: list[dict]) -> None:
    banco.upsert("metas_funil_sdr", linhas, on_conflict="metrica,periodo,id_user")


def apagar_meta_funil_sdr(metrica: str, periodo: str, id_user: int | None) -> None:
    banco.apagar(
        "metas_funil_sdr",
        {"metrica": f"eq.{metrica}", "periodo": f"eq.{periodo}", "id_user": "is.null" if id_user is None else f"eq.{id_user}"},
    )


def gravar_metricas_contas(linhas: list[dict]) -> None:
    banco.upsert("metricas_contas", linhas, on_conflict="id_conta,data")


def gravar_contas_funil(linhas: list[dict]) -> None:
    banco.upsert("contas_funil", linhas, on_conflict="canal,nome")


def ler_notas_financeiro_dos_meses(meses: list[str]) -> list[dict]:
    return banco.query("notas_financeiro", {"mes": f"in.({','.join(meses)})"})


def ler_notas_financeiro_do_periodo(inicio: date, fim: date) -> list[dict]:
    return banco.query(
        "notas_financeiro",
        {"or": f"(and(mes.gte.{inicio.replace(day=1).isoformat()},mes.lte.{fim.isoformat()}),and(data_referencia.gte.{inicio.isoformat()},data_referencia.lte.{fim.isoformat()}))"},
    )


def gravar_notas_financeiro(linhas: list[dict]) -> None:
    banco.upsert("notas_financeiro", linhas, on_conflict="chave")


def apagar_notas_financeiro(mes: str, linhas: list[int]) -> None:
    banco.apagar("notas_financeiro", {"mes": f"eq.{mes}", "linha": f"in.({','.join(map(str, linhas))})"})


def ler_logs(colunas: str) -> list[dict]:
    return banco.query("logs_pipedrive", {}, colunas=colunas)


def gravar_logs(linhas: list[dict]) -> None:
    banco.upsert("logs_pipedrive", linhas, on_conflict="chave")


def apagar_logs(chaves: list[str]) -> None:
    banco.apagar("logs_pipedrive", {"chave": f"in.({','.join(chaves)})"})


def ler_negocios_pipedrive() -> list[dict]:
    return banco.query("pipedrive_negocios", {}, colunas="id_deal,id_dono,id_pessoa,stage_change_time")


def gravar_negocios_pipedrive(linhas: list[dict]) -> None:
    banco.upsert("pipedrive_negocios", linhas, on_conflict="id_deal")


def gravar_entradas_estagio(linhas: list[dict]) -> None:
    banco.upsert("pipedrive_entradas_estagio", linhas, on_conflict="id_deal,id_estagio")


def ler_entradas_estagio(ids_estagio: list[int], desde: datetime, ate: datetime) -> list[dict]:
    """Entradas nos estágios com `desde <= entrou_em < ate`, com o dono e a pessoa atuais do negócio."""
    return banco.query(
        "vw_pipedrive_entradas_estagio",
        {
            "id_estagio": f"in.({','.join(str(i) for i in ids_estagio)})",
            "and": f"(entrou_em.gte.{desde.isoformat()},entrou_em.lt.{ate.isoformat()})",
        },
        colunas="id_deal,id_estagio,entrou_em,id_dono,id_pessoa",
    )
