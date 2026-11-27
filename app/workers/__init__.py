"""Workers que espelham as planilhas (SDRs, inclusive o Funil SDR, Closers, funis LinkedIn/Instagram, Financeiro, Logs) no schema dash_new a cada N segundos. Substituem os fluxos n8n de métricas. Cada ciclo é um job independente, agendado a cada WORKER_INTERVALO_SEGUNDOS: lê o estado atual do banco, compara com a planilha e grava só a diferença (o que outro processo mudar no banco é corrigido no job seguinte), no mês corrente em America/Sao_Paulo. Nunca criam usuário nem cargo: aba de quem não está em users/user_cargos é pulada."""
from __future__ import annotations

import logging
import threading
import time
from calendar import monthrange
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable

from app import cache
from app.config import Settings
from app.fontes import banco
from app.fontes import pipedrive as pipedrive_api
from app.fontes import supabase
from app.workers.google_sheets import LeitorSheets, criar_credenciais
from app.periodo import TZ_SP, hoje_sp
from app.workers.planilha_nfs import ler_aba_nfs, mes_da_aba, resolver_vendedor
from app.workers.planilha_logs import COLUNAS_LOG, ler_logs
from app.planilhas import (
    COLUNAS_POR_TABELA,
    Aba,
    ler_linhas,
    ler_metas_dashboard_sdr,
    linhas_metricas,
    normalizar,
    resolver_sdr_do_dashboard,
    resolver_usuario,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Planilha:
    nome: str
    tabela: str
    cargo: str


SDRS = Planilha("sdrs", "metricas_sdrs", "sdr")
CLOSERS = Planilha("closers", "metricas_closers", "closer")


class Worker:
    # Já logou a primeira leitura ok? (na classe: subclasses com __init__ próprio também têm)
    _leu_ok = False
    # Chaves do cache (app/cache.py) que dependem das tabelas que este worker grava: só elas são
    # invalidadas quando ele grava. "metas" pega também "metas-funil-sdr".
    PREFIXOS_CACHE: tuple[str, ...] = ("vw_metricas:", "geral_", "metas")

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
        self.metricas: dict[str, dict] = {}
        self.metas: dict[tuple[int, str], int] = {}
        self.status = {"ultima_leitura_ok": None, "ultimo_erro": None}
        self._puladas: set[str] = set()

    def _exigir(self, rotulo: str, ler: Callable[[], list[dict]]) -> list[dict]:
        antes = banco.falhas_na_thread()
        linhas = ler()
        if banco.falhas_na_thread() != antes:
            raise RuntimeError(f"consulta a {rotulo} falhou")
        return linhas

    def _carregar_estado(self, ano: int, mes: int) -> None:
        inicio = date(ano, mes, 1)
        fim = date(ano, mes, monthrange(ano, mes)[1])
        colunas = COLUNAS_POR_TABELA[self.planilha.tabela]
        self.metricas = {
            l["key_data_ref_user"]: l
            for l in self._exigir(
                self.planilha.tabela,
                lambda: supabase.ler_metricas_planilha(self.planilha.tabela, inicio, fim, colunas),
            )
        }
        self.metas = {
            (l["id_user"], l["metrica"]): l["valor_diario"]
            for l in self._exigir("metas", lambda: supabase.ler_metas_do_cargo(self.planilha.cargo))
        }

    def ciclo(self) -> None:
        hoje = self.hoje()
        self._carregar_estado(hoje.year, hoje.month)  # estado sempre do banco: cada ciclo é um job independente

        abas = [a for titulo, linhas in self.ler_abas(self.planilha_id) if (a := ler_linhas(titulo, linhas)) is not None]
        usuarios = self._exigir("users", supabase.ler_usuarios)
        com_cargo = {l["id_user"] for l in self._exigir("user_cargos", lambda: supabase.ler_ids_com_cargo(self.planilha.cargo))}

        if self._sincronizar(abas, usuarios, com_cargo, hoje):
            cache.invalidar_prefixos(self.PREFIXOS_CACHE)

    def _sincronizar(self, abas: list[Aba], usuarios: list[dict], com_cargo: set[int], hoje: date) -> bool:
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
            supabase.gravar_metricas_planilha(
                self.planilha.tabela,
                [{**l, "atualizado_em": carimbo} for l in sorted(metricas_novas.values(), key=lambda l: (l["id_user"], l["data"]))],
            )
            self.metricas.update(metricas_novas)
            gravou = True

        if metas_novas:
            supabase.gravar_metas(
                [
                    {"id_user": i, "cargo": self.planilha.cargo, "metrica": m, "valor_diario": v, "atualizado_em": carimbo}
                    for (i, m), v in sorted(metas_novas.items())
                ],
            )
            self.metas.update(metas_novas)
            gravou = True

        for i, m in sorted(metas_apagadas):
            supabase.apagar_meta(i, self.planilha.cargo, m)
            self.metas.pop((i, m), None)
            gravou = True

        return gravou

    def executar_ciclo(self) -> None:
        try:
            self.ciclo()
        except Exception as erro:  # rede do Google/Supabase, 429, planilha sem acesso: não derruba o worker
            self.status["ultimo_erro"] = {"em": self.agora().isoformat(), "mensagem": f"{type(erro).__name__}: {erro}"}
            logger.warning("Worker %s: ciclo falhou", self.planilha.nome, exc_info=True)
            return
        self.status["ultima_leitura_ok"] = self.agora().isoformat()
        if not self._leu_ok:
            self._leu_ok = True
            # única linha que aparece no painel do deploy (filtro em app/main.py)
            logger.info("Worker %s: primeira leitura ok", self.planilha.nome, extra={"no_painel": True})

    def rodar(self, parar: threading.Event, intervalo: float) -> None:
        """Agenda um ciclo a cada `intervalo` segundos (WORKER_INTERVALO_SEGUNDOS), contado do início do ciclo anterior. Ciclo mais longo que o intervalo: o próximo começa logo em seguida, sem sobrepor."""
        while True:
            inicio = time.monotonic()
            self.executar_ciclo()
            if parar.wait(max(0.0, intervalo - (time.monotonic() - inicio))):
                return


class WorkerSdr(Worker):
    """Planilha de SDRs: além de metricas_sdrs/metas (Geral e Time), espelha as abas por pessoa em metricas_funil_sdr e as metas da aba "Dashboard SDR" em metas_funil_sdr (página Funil SDR). Uma leitura da planilha por ciclo."""
    PREFIXOS_CACHE = (*Worker.PREFIXOS_CACHE, "funil-sdr:")

    def __init__(
        self,
        planilha_id: str,
        ler_abas: Callable[[str], list[tuple[str, list[list]]]],
        hoje: Callable[[], date] = hoje_sp,
        agora: Callable[[], datetime] = lambda: datetime.now(TZ_SP),
    ):
        super().__init__(SDRS, planilha_id, ler_abas, hoje, agora)
        self.funil: dict[tuple[int, str], dict] = {}
        self.metas_funil: dict[tuple[str, str, int | None], int] = {}

    def _carregar_estado(self, ano: int, mes: int) -> None:
        super()._carregar_estado(ano, mes)
        inicio = date(ano, mes, 1)
        fim = date(ano, mes, monthrange(ano, mes)[1])
        self.funil = {
            (l["id_user"], l["data"]): l
            for l in self._exigir("metricas_funil_sdr", lambda: supabase.ler_metricas_funil_sdr(inicio, fim))
        }
        self.metas_funil = {
            (l["metrica"], l["periodo"], l["id_user"]): l["valor"]
            for l in self._exigir("metas_funil_sdr", supabase.ler_metas_funil_sdr)
        }

    def _sincronizar_funil(self, abas: list[Aba], usuarios: list[dict], com_cargo: set[int], hoje: date) -> bool:
        colunas = COLUNAS_POR_TABELA["metricas_funil_sdr"]
        novas: dict[tuple[int, str], dict] = {}
        for aba in abas:
            u = resolver_usuario(aba.pessoa, usuarios)
            if u is None or u["id"] not in com_cargo:
                continue
            desejadas = {}
            for d, valores in aba.dias.items():
                try:
                    dia = date(hoje.year, hoje.month, d).isoformat()
                except ValueError:
                    continue
                desejadas[(u["id"], dia)] = {"id_user": u["id"], "data": dia, **{c: valores.get(c) for c in colunas}}
            for chave, linha in self.funil.items():
                if linha["id_user"] == u["id"] and chave not in desejadas:
                    desejadas[chave] = {**linha, **{c: None for c in colunas}}
            novas.update({k: l for k, l in desejadas.items() if self.funil.get(k) != l})
        if not novas:
            return False
        supabase.gravar_metricas_funil_sdr(
            [{**l, "atualizado_em": self.agora().isoformat()} for _, l in sorted(novas.items())],
        )
        self.funil.update(novas)
        return True

    def _sincronizar_metas_funil(self, linhas: list[list], usuarios: list[dict], com_cargo: set[int]) -> bool:
        lidas = ler_metas_dashboard_sdr(linhas)
        if not (lidas.diarias or lidas.semanais or lidas.mensais):
            raise RuntimeError("aba Dashboard SDR sem metas reconhecíveis; nada foi apagado")
        sdrs = [u for u in usuarios if u["id"] in com_cargo]
        desejadas: dict[tuple[str, str, int | None], int] = {}
        for nome, metas in lidas.diarias.items():
            u = resolver_sdr_do_dashboard(nome, sdrs)
            if u is None:
                if nome not in self._puladas:
                    self._puladas.add(nome)
                    logger.warning("Planilha sdrs: '%s' da aba Dashboard SDR sem user sdr, meta diária ignorada", nome)
                continue
            desejadas.update({(m, "dia", u["id"]): v for m, v in metas.items()})
        desejadas.update({(m, "semana", None): v for m, v in lidas.semanais.items()})
        desejadas.update({(m, "mes", None): v for m, v in lidas.mensais.items()})

        novas = {k: v for k, v in desejadas.items() if self.metas_funil.get(k) != v}
        apagadas = [k for k in self.metas_funil if k not in desejadas]
        carimbo = self.agora().isoformat()
        if novas:
            supabase.gravar_metas_funil_sdr(
                [
                    {"metrica": m, "periodo": p, "id_user": i, "valor": v, "atualizado_em": carimbo}
                    for (m, p, i), v in sorted(novas.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2] or 0))
                ],
            )
            self.metas_funil.update(novas)
        for m, p, i in apagadas:
            supabase.apagar_meta_funil_sdr(m, p, i)
            self.metas_funil.pop((m, p, i))
        return bool(novas or apagadas)

    def ciclo(self) -> None:
        hoje = self.hoje()
        self._carregar_estado(hoje.year, hoje.month)  # estado sempre do banco: cada ciclo é um job independente

        brutas = self.ler_abas(self.planilha_id)
        abas = [a for titulo, linhas in brutas if (a := ler_linhas(titulo, linhas)) is not None]
        usuarios = self._exigir("users", supabase.ler_usuarios)
        com_cargo = {l["id_user"] for l in self._exigir("user_cargos", lambda: supabase.ler_ids_com_cargo(self.planilha.cargo))}

        gravou = self._sincronizar(abas, usuarios, com_cargo, hoje)
        if self._sincronizar_funil(abas, usuarios, com_cargo, hoje):
            gravou = True
        dashboard = next((linhas for titulo, linhas in brutas if normalizar(titulo) == "dashboard sdr"), None)
        if dashboard is not None and self._sincronizar_metas_funil(dashboard, usuarios, com_cargo):
            gravou = True
        if gravou:
            cache.invalidar_prefixos(self.PREFIXOS_CACHE)


class WorkerFunil(Worker):
    """Espelha as abas de seller da planilha de um funil (LinkedIn/Instagram) em metricas_sellers e metas, e as abas de conta em metricas_contas."""
    PREFIXOS_CACHE = (*Worker.PREFIXOS_CACHE, "funil:")

    def __init__(
        self,
        canal: str,
        planilha_id: str,
        ler_abas: Callable[[str], list[tuple[str, list[list]]]],
        hoje: Callable[[], date] = hoje_sp,
        agora: Callable[[], datetime] = lambda: datetime.now(TZ_SP),
    ):
        super().__init__(Planilha(f"funil_{canal}", "metricas_sellers", "seller"), planilha_id, ler_abas, hoje, agora)
        self.canal = canal
        self.contas: dict[str, int] = {}
        self.metricas_contas: dict[tuple[int, str], dict] = {}

    def _carregar_estado(self, ano: int, mes: int) -> None:
        super()._carregar_estado(ano, mes)
        inicio = date(ano, mes, 1)
        fim = date(ano, mes, monthrange(ano, mes)[1])
        self.metricas_contas = {
            (l["id_conta"], l["data"]): l
            for l in self._exigir("metricas_contas", lambda: supabase.ler_metricas_das_contas(inicio, fim))
        }

    def _sincronizar_contas(self, abas_conta: list[Aba], hoje: date) -> bool:
        colunas = COLUNAS_POR_TABELA["metricas_contas"]
        metricas_novas: dict[tuple[int, str], dict] = {}

        for aba in abas_conta:
            id_conta = self.contas.get(aba.pessoa)
            if id_conta is None:
                continue

            desejadas = {}
            for d, valores in sorted(aba.dias.items()):
                try:
                    dia = date(hoje.year, hoje.month, d)
                except ValueError:
                    continue
                desejadas[(id_conta, dia.isoformat())] = {
                    "id_conta": id_conta,
                    "data": dia.isoformat(),
                    **{c: valores.get(c) for c in colunas},
                }
            for chave, linha in self.metricas_contas.items():
                if linha["id_conta"] == id_conta and chave not in desejadas:
                    desejadas[chave] = {**linha, **{c: None for c in colunas}}
            for chave, linha in desejadas.items():
                if self.metricas_contas.get(chave) != linha:
                    metricas_novas[chave] = linha

        if not metricas_novas:
            return False

        supabase.gravar_metricas_contas(
            [
                {**l, "atualizado_em": self.agora().isoformat()}
                for l in sorted(metricas_novas.values(), key=lambda l: (l["id_conta"], l["data"]))
            ],
        )
        self.metricas_contas.update(metricas_novas)
        return True

    def ciclo(self) -> None:
        hoje = self.hoje()
        self._carregar_estado(hoje.year, hoje.month)  # estado sempre do banco: cada ciclo é um job independente

        abas = [a for titulo, linhas in self.ler_abas(self.planilha_id) if (a := ler_linhas(titulo, linhas)) is not None]
        usuarios = self._exigir("users", supabase.ler_usuarios)
        com_cargo = {l["id_user"] for l in self._exigir("user_cargos", lambda: supabase.ler_ids_com_cargo(self.planilha.cargo))}

        abas_seller = [a for a in abas if (u := resolver_usuario(a.pessoa, usuarios)) is not None and u["id"] in com_cargo]
        gravou = self._sincronizar(abas_seller, usuarios, com_cargo, hoje)

        abas_conta = [a for a in abas if a not in abas_seller]
        id_seller = resolver_usuario(abas_seller[0].pessoa, usuarios)["id"] if abas_seller else None

        def contas_do_canal() -> dict[str, dict]:
            return {l["nome"]: l for l in self._exigir("contas_funil", lambda: supabase.ler_contas_do_canal(self.canal))}

        existentes = contas_do_canal()
        novas = [
            {"canal": self.canal, "nome": a.pessoa, "id_seller": id_seller}
            for a in abas_conta
            if a.pessoa not in existentes or existentes[a.pessoa]["id_seller"] != id_seller
        ]
        if novas:
            carimbo = self.agora().isoformat()
            supabase.gravar_contas_funil([{**l, "atualizado_em": carimbo} for l in novas])
            existentes = contas_do_canal()
            gravou = True
        self.contas = {nome: l["id"] for nome, l in existentes.items()}
        if self._sincronizar_contas(abas_conta, hoje):
            gravou = True

        if gravou:
            cache.invalidar_prefixos(self.PREFIXOS_CACHE)


class WorkerFinanceiro(Worker):
    """Espelha as abas "NFS <mês>" da planilha do financeiro em notas_financeiro (ver sql/2026-11-27-notas-financeiro.sql).

    O ciclo sincroniza só a aba do mês corrente e a do anterior; a carga de todas as abas é `carga_completa`
    (scripts/carga_financeiro.py). Mês sem aba na planilha não apaga nada.
    """
    PREFIXOS_CACHE = ("faturamento:", "financeiro:")

    def __init__(
        self,
        planilha_id: str,
        ano: int,
        ler_abas: Callable[[str], list[tuple[str, list[list]]]],
        hoje: Callable[[], date] = hoje_sp,
        agora: Callable[[], datetime] = lambda: datetime.now(TZ_SP),
    ):
        self.planilha = Planilha("financeiro", "notas_financeiro", "")
        self.planilha_id = planilha_id
        self.ano = ano
        self.ler_abas = ler_abas
        self.hoje = hoje
        self.agora = agora
        self.status = {"ultima_leitura_ok": None, "ultimo_erro": None}
        self._puladas: set[str] = set()

    def sincronizar(self, abas: list[tuple[str, list[list]]], meses: list[tuple[int, int]]) -> None:
        # toda a leitura acontece antes de qualquer escrita: aba com erro não pode gravar parte do ciclo
        presentes: list[str] = []
        desejadas: dict[str, dict] = {}
        for ano, mes in meses:
            linhas = next((l for titulo, l in abas if mes_da_aba(titulo) == mes), None)
            if linhas is None:
                continue
            for nota in ler_aba_nfs(linhas, ano, mes):
                desejadas[nota["chave"]] = nota
            presentes.append(f"{ano:04d}-{mes:02d}-01")
        if not presentes:
            return

        usuarios = self._exigir("users", supabase.ler_usuarios)
        for nota in desejadas.values():
            nota["id_vendedor"] = resolver_vendedor(nota["vendedor"], usuarios)
            if nota["vendedor"] and nota["id_vendedor"] is None and nota["vendedor"] not in self._puladas:
                self._puladas.add(nota["vendedor"])
                logger.warning("Planilha financeiro: vendedor '%s' não está em users, gravado com id_vendedor null", nota["vendedor"])

        atuais = {l["chave"]: l for l in self._exigir("notas_financeiro", lambda: supabase.ler_notas_financeiro_dos_meses(presentes))}
        novas = [d for c, d in sorted(desejadas.items()) if {k: atuais.get(c, {}).get(k) for k in d} != d]
        gravou = False
        if novas:
            supabase.gravar_notas_financeiro([{**d, "atualizado_em": self.agora().isoformat()} for d in novas])
            gravou = True

        removidas = sorted(c for c in atuais if c not in desejadas)
        linhas_por_mes: dict[str, list[int]] = {}
        for c in removidas:
            linhas_por_mes.setdefault(atuais[c]["mes"], []).append(int(atuais[c]["linha"]))
        for mes in sorted(linhas_por_mes):
            supabase.apagar_notas_financeiro(mes, sorted(linhas_por_mes[mes]))
            gravou = True

        if gravou:
            cache.invalidar_prefixos(self.PREFIXOS_CACHE)

    def ciclo(self) -> None:
        h = self.hoje()
        anterior = (h.year, h.month - 1) if h.month > 1 else (h.year - 1, 12)
        self.sincronizar(self.ler_abas(self.planilha_id), [anterior, (h.year, h.month)])

    def carga_completa(self) -> list[str]:
        abas = self.ler_abas(self.planilha_id)
        abas_validas: list[tuple[str, list[list]]] = []
        validas: list[tuple[int, int]] = []
        for titulo, linhas in abas:
            m = mes_da_aba(titulo)
            if m is None:
                continue
            try:
                ler_aba_nfs(linhas, self.ano, m)
            except ValueError as erro:
                logger.warning("Carga financeiro: aba '%s' pulada: %s", titulo, erro)
                continue
            abas_validas.append((titulo, linhas))
            validas.append((self.ano, m))
        self.sincronizar(abas_validas, sorted(validas))
        return [f"{a:04d}-{m:02d}" for a, m in sorted(validas)]


class WorkerLogs(Worker):
    """Espelha a aba Logs da planilha Logs Pipedrive em logs_pipedrive (chave = sha1 do conteúdo da linha)."""

    def __init__(
        self,
        planilha_id: str,
        ler_abas: Callable[[str], list[tuple[str, list[list]]]],
        agora: Callable[[], datetime] = lambda: datetime.now(TZ_SP),
    ):
        self.planilha = Planilha("logs", "logs_pipedrive", "")
        self.planilha_id = planilha_id
        self.ler_abas = ler_abas
        self.agora = agora
        self.logs: dict[str, dict] | None = None
        self.status = {"ultima_leitura_ok": None, "ultimo_erro": None}
        self._puladas: set = set()

    def _carregar_estado(self) -> None:
        self.logs = {
            l["chave"]: l
            for l in self._exigir(
                "logs_pipedrive",
                lambda: supabase.ler_logs("chave,ocorrencias,id_user," + ",".join(COLUNAS_LOG)),
            )
        }

    def ciclo(self) -> None:
        self._carregar_estado()  # estado sempre do banco: cada ciclo é um job independente

        abas = dict(self.ler_abas(self.planilha_id))
        if "Logs" not in abas:
            raise RuntimeError("aba Logs não encontrada na planilha de logs")
        leitura = ler_logs(abas["Logs"])
        for numero in leitura.invalidas:
            # só o número da linha: o conteúdo tem nome e telefone de lead
            if ("linha", numero) not in self._puladas:
                self._puladas.add(("linha", numero))
                logger.warning("Planilha logs: linha %d da aba Logs ignorada (sem data válida ou sem atividade)", numero)
        if not leitura.eventos:
            # leitura vazia não pode esvaziar a tabela (mesmo cuidado do financeiro)
            raise RuntimeError("aba Logs sem nenhum evento válido; nada foi apagado")
        usuarios = self._exigir("users", supabase.ler_usuarios)

        desejados: dict[str, dict] = {}
        for e in leitura.eventos:
            # a planilha usa nome completo ("Jennifer Pamplona") e users só o primeiro nome ("Jennifer")
            u = (
                resolver_usuario(e["usuario_acao"], usuarios) or resolver_usuario(e["usuario_acao"].split()[0], usuarios)
                if e["usuario_acao"] else None
            )
            if e["usuario_acao"] and u is None and e["usuario_acao"] not in self._puladas:
                self._puladas.add(e["usuario_acao"])
                logger.warning("Planilha logs: '%s' não está em users, gravado com id_user null", e["usuario_acao"])
            desejados[e["chave"]] = {**e, "id_user": u["id"] if u else None}
        novos = {
            k: d for k, d in sorted(desejados.items())
            if {c: self.logs.get(k, {}).get(c) for c in d} != d
        }
        if novos:
            supabase.gravar_logs([{**l, "atualizado_em": self.agora().isoformat()} for l in novos.values()])
            self.logs.update(novos)

        removidas = sorted(set(self.logs) - set(desejados))
        if removidas:
            supabase.apagar_logs(removidas)
            for k in removidas:
                self.logs.pop(k, None)


# Desde quando o WorkerPipedrive guarda o histórico de estágios (o filtro de ano do dash começa aqui).
INICIO_HISTORICO_PIPEDRIVE = datetime(2026, 1, 1, tzinfo=TZ_SP)
# O cursor volta essa margem a cada ciclo: negócio atualizado enquanto o ciclo anterior rodava não escapa.
MARGEM_CURSOR_PIPEDRIVE = timedelta(minutes=5)
INTERVALO_PIPEDRIVE_SEGUNDOS = 60.0
LOTE_PIPEDRIVE = 100  # negócios gravados por vez: o preenchimento inicial salva o progresso aos poucos
CONCORRENCIA_HISTORICO = 4  # chamadas de histórico ao mesmo tempo (limite do Pipedrive: 120 a cada 2s)


def entradas_por_estagio(negocio: dict, mudancas: list[dict]) -> dict[int, str]:
    """Primeira entrada (UTC, ISO) do negócio em cada estágio.

    O estágio em que o negócio nasceu (o `de` da primeira mudança; sem mudança, o estágio atual)
    entra em `add_time`; cada mudança entra no estágio `para` no momento `em`. Reentrada não conta.
    """
    if not negocio.get("add_time"):
        return {}
    inicial = mudancas[0]["de"] if mudancas and mudancas[0]["de"] is not None else negocio.get("stage_id")
    entradas: dict[int, str] = {}
    if inicial is not None:
        entradas[int(inicial)] = negocio["add_time"]
    for m in mudancas:
        entradas.setdefault(m["para"], m["em"])
    return entradas


def _campos_negocio(negocio: dict) -> dict:
    return {"id_dono": negocio.get("owner_id"), "id_pessoa": negocio.get("person_id"), "stage_change_time": negocio.get("stage_change_time")}


class WorkerPipedrive(Worker):
    """Espelha o histórico de estágios do Pipedrive em pipedrive_negocios + pipedrive_entradas_estagio.

    A cada ciclo lista os negócios atualizados desde o ciclo anterior (no primeiro, desde
    INICIO_HISTORICO_PIPEDRIVE) e relê o histórico (/v1/deals/{id}/flow) só de quem mudou de estágio
    desde a última leitura (`stage_change_time` diferente do guardado). Dono/pessoa trocados sem
    mudar de estágio só atualizam pipedrive_negocios. Ver sql/2026-11-25-pipedrive-estagios.sql.
    """

    PREFIXOS_CACHE = ("pipedrive:",)

    def __init__(self, agora: Callable[[], datetime] = lambda: datetime.now(TZ_SP)):
        self.planilha = Planilha("pipedrive", "pipedrive_entradas_estagio", "")
        self.planilha_id = ""
        self.agora = agora
        self.status = {"ultima_leitura_ok": None, "ultimo_erro": None}
        self._puladas: set[str] = set()
        self.cursor: datetime | None = None
        self.negocios: dict[int, dict] | None = None

    def ciclo(self) -> None:
        inicio_ciclo = self.agora()
        if self.negocios is None:
            self.negocios = {
                int(l["id_deal"]): {k: l.get(k) for k in ("id_dono", "id_pessoa", "stage_change_time")}
                for l in self._exigir("pipedrive_negocios", supabase.ler_negocios_pipedrive)
            }

        mudaram: list[tuple[dict, bool]] = []  # (negócio, precisa reler o histórico?)
        for n in pipedrive_api.negocios_atualizados_desde(self.cursor or INICIO_HISTORICO_PIPEDRIVE):
            campos = _campos_negocio(n)
            guardado = self.negocios.get(n["id"])
            if guardado != campos:
                mudaram.append((n, guardado is None or guardado["stage_change_time"] != campos["stage_change_time"]))

        for i in range(0, len(mudaram), LOTE_PIPEDRIVE):
            self._gravar_lote(mudaram[i:i + LOTE_PIPEDRIVE])

        self.cursor = inicio_ciclo - MARGEM_CURSOR_PIPEDRIVE
        if mudaram:
            cache.marcar_vencido(self.PREFIXOS_CACHE)

    def _gravar_lote(self, lote: list[tuple[dict, bool]]) -> None:
        reler = [n for n, precisa in lote if precisa]

        def historico(n: dict) -> list[dict]:
            # Sem stage_change_time o negócio nunca mudou de estágio: nem chama a API.
            return pipedrive_api.mudancas_de_estagio(n["id"]) if n.get("stage_change_time") else []

        with ThreadPoolExecutor(max_workers=CONCORRENCIA_HISTORICO) as executor:
            historicos = list(executor.map(historico, reler))

        carimbo = self.agora().isoformat()
        # Negócio antes das entradas: a entrada referencia o negócio (chave estrangeira).
        supabase.gravar_negocios_pipedrive(
            [{"id_deal": n["id"], **_campos_negocio(n), "atualizado_em": carimbo} for n, _ in lote]
        )
        supabase.gravar_entradas_estagio(
            [
                {"id_deal": n["id"], "id_estagio": estagio, "entrou_em": em, "atualizado_em": carimbo}
                for n, mudancas in zip(reler, historicos)
                for estagio, em in sorted(entradas_por_estagio(n, mudancas).items())
            ]
        )
        for n, _ in lote:
            self.negocios[n["id"]] = _campos_negocio(n)


ATIVOS: list[Worker] = []
MOTIVO_INATIVOS: str | None = None


def iniciar(config: Settings) -> threading.Event:
    global MOTIVO_INATIVOS
    parar = threading.Event()
    ATIVOS.clear()
    MOTIVO_INATIVOS = None
    if not config.workers_ativos:
        return parar
    # O worker do Pipedrive não depende das planilhas: sobe mesmo sem a conta de serviço do Google.
    if config.pipe_token and config.pipe_base_url_v1 and config.pipe_base_url_v2 and config.supabase_url and config.supabase_service_key:
        pipedrive = WorkerPipedrive()
        ATIVOS.append(pipedrive)
        threading.Thread(target=pipedrive.rodar, args=(parar, INTERVALO_PIPEDRIVE_SEGUNDOS), name="worker-pipedrive", daemon=True).start()
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
    if config.planilha_sdrs_id:
        sdrs = WorkerSdr(config.planilha_sdrs_id, LeitorSheets(credenciais).abas)
        ATIVOS.append(sdrs)
        threading.Thread(target=sdrs.rodar, args=(parar, config.worker_intervalo_segundos), name="worker-sdrs", daemon=True).start()
    if config.planilha_closers_id:
        closers = Worker(CLOSERS, config.planilha_closers_id, LeitorSheets(credenciais).abas)
        ATIVOS.append(closers)
        threading.Thread(target=closers.rodar, args=(parar, config.worker_intervalo_segundos), name="worker-closers", daemon=True).start()
    for canal, planilha_id in (("linkedin", config.planilha_funil_linkedin_id), ("instagram", config.planilha_funil_instagram_id)):
        if not planilha_id:
            continue
        funil = WorkerFunil(canal, planilha_id, LeitorSheets(credenciais).abas)
        ATIVOS.append(funil)
        threading.Thread(target=funil.rodar, args=(parar, config.worker_intervalo_segundos), name=f"worker-funil_{canal}", daemon=True).start()
    if config.planilha_financeiro_id:
        financeiro = WorkerFinanceiro(config.planilha_financeiro_id, config.planilha_financeiro_ano, LeitorSheets(credenciais).abas)
        ATIVOS.append(financeiro)
        threading.Thread(target=financeiro.rodar, args=(parar, config.worker_intervalo_segundos), name="worker-financeiro", daemon=True).start()
    if config.planilha_logs_id:
        logs = WorkerLogs(config.planilha_logs_id, LeitorSheets(credenciais).abas)
        ATIVOS.append(logs)
        threading.Thread(target=logs.rodar, args=(parar, config.worker_intervalo_segundos), name="worker-logs", daemon=True).start()
    logger.info("Workers das planilhas ativos: %s", [w.planilha.nome for w in ATIVOS])
    return parar
