"""Workers que espelham as planilhas (Sellers, SDRs, Closers, Dripify) em dash2 a cada N segundos. Substituem os fluxos n8n de métricas. Gravam só o que mudou (estado em memória, carregado do banco na subida e na virada do mês), no mês corrente em America/Sao_Paulo. Nunca criam usuário nem cargo: aba de quem não está em users/user_cargos é pulada."""
from __future__ import annotations

import logging
import threading
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable

from app import cache
from app.config import Settings
from app.fontes import banco
from app.fontes.google_sheets import LeitorSheets, criar_credenciais
from app.periodo import TZ_SP, hoje_sp
from app.planilha_financeiro import COLUNAS_VENDA, ler_base_vendas
from app.planilhas import COLUNAS_POR_TABELA, ler_linhas, linhas_metricas, normalizar, resolver_usuario

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


class WorkerFinanceiro(Worker):
    """Espelha a aba BASE_VENDAS da Isaac Newton2.0 em metricas_faturamento + recebimentos_faturamento."""

    def __init__(
        self,
        planilha_id: str,
        ano: int,
        ler_abas: Callable[[str], list[tuple[str, list[list]]]],
        agora: Callable[[], datetime] = lambda: datetime.now(TZ_SP),
    ):
        self.planilha = Planilha("financeiro", "metricas_faturamento", "")
        self.planilha_id = planilha_id
        self.ano = ano
        self.ler_abas = ler_abas
        self.agora = agora
        self.vendas: dict[int, dict] | None = None
        self.recebimentos: dict[tuple[int, str], dict] = {}
        self.status = {"ultima_leitura_ok": None, "ultimo_erro": None}
        self._puladas: set[str] = set()

    def _carregar_estado(self) -> None:
        self.vendas = {
            l["id_planilha"]: l
            for l in self._consultar(
                "metricas_faturamento",
                {"id_planilha": "not.is.null"},
                "id_planilha,id_cliente," + ",".join(c for c in COLUNAS_VENDA if c != "id_planilha"),
            )
        }
        self.recebimentos = {
            (l["id_planilha_venda"], l["mes"]): l
            for l in self._consultar("recebimentos_faturamento", {}, "id_planilha_venda,mes,pago,liquido")
        }

    def _resolver_clientes(self, lidas: list) -> dict[int, int | None]:
        clientes = self._consultar("cliente_faturamento", {}, "id,nome,telefone")
        por_telefone = {c["telefone"]: c["id"] for c in clientes if c["telefone"]}
        por_nome = {normalizar(c["nome"]): c["id"] for c in clientes}
        resolvidos: dict[int, int | None] = {}
        for v in lidas:
            if v.cliente_telefone is not None:
                resolvidos[v.venda["id_planilha"]] = por_telefone.get(v.cliente_telefone)
            else:
                resolvidos[v.venda["id_planilha"]] = por_nome.get(normalizar(v.cliente_nome)) if v.cliente_nome else None
        return resolvidos

    def ciclo(self) -> None:
        if self.vendas is None:
            self._carregar_estado()

        abas = dict(self.ler_abas(self.planilha_id))
        lidas = ler_base_vendas(abas["BASE_VENDAS"], self.ano)
        ids_cliente = self._resolver_clientes(lidas)

        desejadas = {v.venda["id_planilha"]: {**v.venda, "id_cliente": ids_cliente[v.venda["id_planilha"]]} for v in lidas}
        vendas_novas = {
            i: d for i, d in sorted(desejadas.items())
            if {k: self.vendas.get(i, {}).get(k) for k in d} != d
        }
        receb_desejados = {(r["id_planilha_venda"], r["mes"]): r for v in lidas for r in v.recebimentos}
        receb_novos = {
            k: r for k, r in sorted(receb_desejados.items())
            if {c: self.recebimentos.get(k, {}).get(c) for c in r} != r
        }

        carimbo = self.agora().isoformat()
        gravou = False

        if vendas_novas:
            banco.upsert(
                self.planilha.tabela,
                [{**l, "atualizado_em": carimbo} for l in vendas_novas.values()],
                on_conflict="id_planilha",
            )
            self.vendas.update(vendas_novas)
            gravou = True

        if receb_novos:
            banco.upsert(
                "recebimentos_faturamento",
                [{**l, "atualizado_em": carimbo} for l in receb_novos.values()],
                on_conflict="id_planilha_venda,mes",
            )
            self.recebimentos.update(receb_novos)
            gravou = True

        if gravou:
            cache.invalidar()


ATIVOS: list[Worker] = []
MOTIVO_INATIVOS: str | None = None


def iniciar(config: Settings) -> threading.Event:
    global MOTIVO_INATIVOS
    parar = threading.Event()
    ATIVOS.clear()
    MOTIVO_INATIVOS = None
    if not config.workers_ativos:
        return parar
    if not config.google_service_account_json:
        motivo = "GOOGLE_SERVICE_ACCOUNT_JSON ausente ou ilegível no .env"
    elif not (config.supabase_url and config.supabase_service_key):
        motivo = "SUPABASE_URL ou SUPABASE_SERVICE_KEY ausente"
    else:
        motivo = None
    if motivo:
        MOTIVO_INATIVOS = motivo
        logger.warning("Workers das planilhas não subiram: %s", motivo)
        return parar
    try:
        credenciais = criar_credenciais(config.google_service_account_json)
    except Exception as erro:  # o texto da exceção pode conter trecho da chave: só o tipo vai para o motivo
        MOTIVO_INATIVOS = f"GOOGLE_SERVICE_ACCOUNT_JSON inválido: {type(erro).__name__}"
        logger.warning("Workers das planilhas não subiram: %s", MOTIVO_INATIVOS)
        return parar
    ids = {
        "sellers": config.planilha_sellers_id,
        "sdrs": config.planilha_sdrs_id,
        "closers": config.planilha_closers_id,
        "dripify": config.planilha_dripify_id,
    }
    for p in PLANILHAS:
        if not ids[p.nome]:
            continue
        w = Worker(p, ids[p.nome], LeitorSheets(credenciais).abas)
        ATIVOS.append(w)
        threading.Thread(target=w.rodar, args=(parar, config.worker_intervalo_segundos), name=f"worker-{p.nome}", daemon=True).start()
    logger.info("Workers das planilhas ativos: %s", [w.planilha.nome for w in ATIVOS])
    return parar
