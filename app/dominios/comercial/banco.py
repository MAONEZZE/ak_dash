"""Histórico comercial (meses fechados) vindo do Supabase.

Schema assumido — tabela `metricas_comerciais_mensais`:
  email (text), funcao ('sdr'|'closer'), metrica (chave estável),
  ano (int), mes (int), meta_periodo (int), realizado (int),
  dias_com_lacuna (int), dias_considerados (int)

Schema real ainda não confirmado (ver "aguardando você" em
docs/plans/dashboard-akeel.md) — ajustar nomes de coluna quando o processo
de fechamento de mês externo definir a tabela de verdade.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.fontes.banco import query


@dataclass(frozen=True)
class HistoricoMetrica:
    email: str
    funcao: str
    metrica: str
    ano: int
    mes: int
    meta_periodo: int
    realizado: int
    dias_com_lacuna: int
    dias_considerados: int


def buscar_historico(
    funcao: str, ano_inicio: int, mes_inicio: int, ano_fim: int, mes_fim: int
) -> list[HistoricoMetrica]:
    """Meses fechados no intervalo [ano_inicio-mes_inicio, ano_fim-mes_fim], inclusive."""
    linhas = query("metricas_comerciais_mensais", {"funcao": funcao})
    resultado = []
    for r in linhas:
        chave_mes = (int(r["ano"]), int(r["mes"]))
        if (ano_inicio, mes_inicio) <= chave_mes <= (ano_fim, mes_fim):
            resultado.append(
                HistoricoMetrica(
                    email=r["email"],
                    funcao=r["funcao"],
                    metrica=r["metrica"],
                    ano=int(r["ano"]),
                    mes=int(r["mes"]),
                    meta_periodo=int(r["meta_periodo"]),
                    realizado=int(r["realizado"]),
                    dias_com_lacuna=int(r["dias_com_lacuna"]),
                    dias_considerados=int(r["dias_considerados"]),
                )
            )
    return resultado
