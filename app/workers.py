"""Workers que espelham as planilhas (Sellers, SDRs, Closers, Dripify) em dash2 a cada N segundos. Substituem os fluxos n8n de métricas. Gravam só o que mudou (estado em memória, carregado do banco na subida e na virada do mês), no mês corrente em America/Sao_Paulo. Nunca criam usuário nem cargo: aba de quem não está em users/user_cargos é pulada."""
from __future__ import annotations

import logging
import threading
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable

from app import cache
from app.fontes import banco
from app.periodo import TZ_SP, hoje_sp
from app.planilhas import COLUNAS_POR_TABELA, ler_linhas, linhas_metricas, resolver_usuario

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Planilha:
    nome: str
    tabela: str
    cargo: str


PLANILHAS = [
    Planilha("sellers", "metricas_sellers", "seller"),
    Planilha("sdrs", "metricas_sdrs", "sdr"),
    Planilha("closers", "metricas_closers", "closer"),
    Planilha("dripify", "metricas_dripify", "dripify"),
]


class Worker:
    def __init__(
        self,
        planilha: Planilha,
        planilha_id: str,
        ler_abas: Callable[[str], list[tuple[str, list[list]]]],
        hoje: Callable[[], date] = hoje_sp,
        agora: Callable[[], datetime] = lambda: datetime.now(TZ_SP),
    ):
        self.planilha = planilha
        self.planilha_id = planilha_id
        self.ler_abas = ler_abas
        self.hoje = hoje
        self.agora = agora
        self.mes: tuple[int, int] | None = None
        self.metricas: dict[str, dict] = {}
        self.metas: dict[tuple[int, str], int] = {}
        self.status = {"ultima_leitura_ok": None, "ultimo_erro": None}
        self._puladas: set[str] = set()

    def _consultar(self, tabela: str, filtros: dict[str, str], colunas: str) -> list[dict]:
        antes = banco.falhas_na_thread()
        linhas = banco.query(tabela, filtros, colunas=colunas)
        if banco.falhas_na_thread() != antes:
            raise RuntimeError(f"consulta a {tabela} falhou")
        return linhas

    def _carregar_estado(self, ano: int, mes: int) -> None:
        inicio = date(ano, mes, 1)
        fim = date(ano, mes, monthrange(ano, mes)[1])
        colunas = COLUNAS_POR_TABELA[self.planilha.tabela]
        self.metricas = {
            l["key_data_ref_user"]: l
            for l in self._consultar(
                self.planilha.tabela,
                {"and": f"(data.gte.{inicio},data.lte.{fim})"},
                "id_user,data,key_data_ref_user," + ",".join(colunas),
            )
        }
        self.metas = {
            (l["id_user"], l["metrica"]): l["valor_diario"]
            for l in self._consultar("metas", {"cargo": f"eq.{self.planilha.cargo}"}, "id_user,metrica,valor_diario")
        }
        self.mes = (ano, mes)

    def ciclo(self) -> None:
        hoje = self.hoje()
        if (hoje.year, hoje.month) != self.mes:
            self._carregar_estado(hoje.year, hoje.month)

        abas = [a for titulo, linhas in self.ler_abas(self.planilha_id) if (a := ler_linhas(titulo, linhas)) is not None]
        usuarios = self._consultar("users", {}, "id,nome")
        com_cargo = {l["id_user"] for l in self._consultar("user_cargos", {"cargo": f"eq.{self.planilha.cargo}"}, "id_user")}

        colunas = COLUNAS_POR_TABELA[self.planilha.tabela]
        metricas_novas: dict[str, dict] = {}
        metas_novas: dict[tuple[int, str], int] = {}
        metas_apagadas: list[tuple[int, str]] = []

        for aba in abas:
            u = resolver_usuario(aba.pessoa, usuarios)
            if u is None or u["id"] not in com_cargo:
                if aba.pessoa not in self._puladas:
                    self._puladas.add(aba.pessoa)
                    logger.warning(
                        "Planilha %s: aba '%s' pulada (pessoa sem cadastro em users ou sem o cargo %s em user_cargos)",
                        self.planilha.nome,
                        aba.pessoa,
                        self.planilha.cargo,
                    )
                continue

            desejadas = {}
            for l in linhas_metricas(aba, u["id"], u["nome"], hoje.year, hoje.month):
                desejadas[l["key_data_ref_user"]] = {
                    "id_user": u["id"],
                    "data": l["data"].isoformat(),
                    "key_data_ref_user": l["key_data_ref_user"],
                    **{c: l.get(c) for c in colunas},
                }
            for chave, linha in self.metricas.items():
                if linha["id_user"] == u["id"] and chave not in desejadas:
                    desejadas[chave] = {**linha, **{c: None for c in colunas}}
            for chave, linha in desejadas.items():
                if self.metricas.get(chave) != linha:
                    metricas_novas[chave] = linha

            metas_desejadas = {(u["id"], m): v for m, v in aba.metas.items() if m in colunas}
            for chave, v in metas_desejadas.items():
                if self.metas.get(chave) != v:
                    metas_novas[chave] = v
            for i, m in list(self.metas):
                if i == u["id"] and (i, m) not in metas_desejadas:
                    metas_apagadas.append((i, m))

        carimbo = self.agora().isoformat()
        gravou = False

        if metricas_novas:
            banco.upsert(
                self.planilha.tabela,
                [{**l, "atualizado_em": carimbo} for l in sorted(metricas_novas.values(), key=lambda l: (l["id_user"], l["data"]))],
                on_conflict="key_data_ref_user",
            )
            self.metricas.update(metricas_novas)
            gravou = True

        if metas_novas:
            banco.upsert(
                "metas",
                [
                    {"id_user": i, "cargo": self.planilha.cargo, "metrica": m, "valor_diario": v, "atualizado_em": carimbo}
                    for (i, m), v in sorted(metas_novas.items())
                ],
                on_conflict="id_user,cargo,metrica",
            )
            self.metas.update(metas_novas)
            gravou = True

        for i, m in sorted(metas_apagadas):
            banco.apagar(
                "metas",
                {"id_user": f"eq.{i}", "cargo": f"eq.{self.planilha.cargo}", "metrica": f"eq.{m}"},
            )
            self.metas.pop((i, m), None)
            gravou = True

        if gravou:
            cache.invalidar()

    def executar_ciclo(self) -> None:
        try:
            self.ciclo()
        except Exception as erro:  # rede do Google/Supabase, 429, planilha sem acesso: não derruba o worker
            self.status["ultimo_erro"] = {"em": self.agora().isoformat(), "mensagem": f"{type(erro).__name__}: {erro}"}
            logger.warning("Worker %s: ciclo falhou", self.planilha.nome, exc_info=True)
            return
        self.status["ultima_leitura_ok"] = self.agora().isoformat()

    def rodar(self, parar: threading.Event, intervalo: float) -> None:
        while True:
            self.executar_ciclo()
            if parar.wait(intervalo):
                return
