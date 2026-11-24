"""Workers que espelham as planilhas (SDRs, inclusive o Funil SDR, Closers, funis LinkedIn/Instagram, Financeiro, Logs) no schema dash_new a cada N segundos. Substituem os fluxos n8n de métricas. Cada ciclo é um job independente, agendado a cada WORKER_INTERVALO_SEGUNDOS: lê o estado atual do banco, compara com a planilha e grava só a diferença (o que outro processo mudar no banco é corrigido no job seguinte), no mês corrente em America/Sao_Paulo. Nunca criam usuário nem cargo: aba de quem não está em users/user_cargos é pulada."""
from __future__ import annotations

import logging
import threading
import time
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable

from app import cache
from app.config import Settings
from app.fontes import banco
from app.fontes import supabase
from app.workers.google_sheets import LeitorSheets, criar_credenciais
from app.periodo import TZ_SP, hoje_sp
from app.workers.planilha_financeiro import APELIDOS, COLUNAS_VENDA, ler_base_vendas
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

    def _consultar(self, tabela: str, filtros: dict[str, str], colunas: str) -> list[dict]:
        antes = banco.falhas_na_thread()
        linhas = banco.query(tabela, filtros, colunas=colunas)
        if banco.falhas_na_thread() != antes:
            raise RuntimeError(f"consulta a {tabela} falhou")
        return linhas

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
            cache.invalidar()

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
            cache.invalidar()


class WorkerFunil(Worker):
    """Espelha as abas de seller da planilha de um funil (LinkedIn/Instagram) em metricas_sellers e metas, e as abas de conta em metricas_contas."""

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
        colunas = COLUNAS_POR_TABELA["metricas_contas"]
        self.metricas_contas = {
            (l["id_conta"], l["data"]): l
            for l in self._consultar(
                "metricas_contas",
                {"and": f"(data.gte.{inicio},data.lte.{fim})"},
                "id_conta,data," + ",".join(colunas),
            )
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

        banco.upsert(
            "metricas_contas",
            [
                {**l, "atualizado_em": self.agora().isoformat()}
                for l in sorted(metricas_novas.values(), key=lambda l: (l["id_conta"], l["data"]))
            ],
            on_conflict="id_conta,data",
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
            return {l["nome"]: l for l in self._consultar("contas_funil", {"canal": f"eq.{self.canal}"}, "id,canal,nome,id_seller")}

        existentes = contas_do_canal()
        novas = [
            {"canal": self.canal, "nome": a.pessoa, "id_seller": id_seller}
            for a in abas_conta
            if a.pessoa not in existentes or existentes[a.pessoa]["id_seller"] != id_seller
        ]
        if novas:
            carimbo = self.agora().isoformat()
            banco.upsert("contas_funil", [{**l, "atualizado_em": carimbo} for l in novas], on_conflict="canal,nome")
            existentes = contas_do_canal()
            gravou = True
        self.contas = {nome: l["id"] for nome, l in existentes.items()}
        if self._sincronizar_contas(abas_conta, hoje):
            gravou = True

        if gravou:
            cache.invalidar()


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
        # linhas do n8n antes do worker (backup em metricas_faturamento_bkp_20261028): apagadas uma vez por processo
        self._apagar_legado = True

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
        def casar() -> dict[int, int | None]:
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

        resolvidos = casar()
        com_telefone: dict[int, dict] = {}
        sem_telefone: dict[str, dict] = {}
        for v in lidas:
            if resolvidos[v.venda["id_planilha"]] is not None:
                continue
            if v.cliente_telefone is not None:
                com_telefone.setdefault(v.cliente_telefone, {"nome": v.cliente_nome, "telefone": v.cliente_telefone})
            elif v.cliente_nome:
                sem_telefone.setdefault(normalizar(v.cliente_nome), {"nome": v.cliente_nome})
        if com_telefone or sem_telefone:
            banco.upsert("cliente_faturamento", list(com_telefone.values()), on_conflict="telefone")
            banco.upsert("cliente_faturamento", list(sem_telefone.values()), on_conflict="id")
            resolvidos = casar()
        return resolvidos

    def ciclo(self) -> None:
        self._carregar_estado()  # estado sempre do banco: cada ciclo é um job independente

        abas = dict(self.ler_abas(self.planilha_id))
        if "BASE_VENDAS" not in abas:
            raise RuntimeError("aba BASE_VENDAS não encontrada na planilha do financeiro")
        lidas = ler_base_vendas(abas["BASE_VENDAS"], self.ano)
        for v in lidas:
            for nome in (v.sdr, v.closer):
                if nome and normalizar(nome) not in APELIDOS and nome not in self._puladas:
                    self._puladas.add(nome)
                    logger.warning(
                        "Planilha financeiro: '%s' não está nos apelidos de SDR/Closer (venda %s), gravado como null",
                        nome,
                        v.venda["id_planilha"],
                    )
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

        # só depois de ler e gravar a planilha: uma leitura que falha não pode esvaziar o faturamento
        if self._apagar_legado and desejadas:
            banco.apagar("metricas_faturamento", {"id_planilha": "is.null"})
            self._apagar_legado = False
            gravou = True

        meses_apagados = [k for k in sorted(self.recebimentos) if k not in receb_desejados and k[0] in desejadas]
        for i, mes in meses_apagados:
            banco.apagar("recebimentos_faturamento", {"id_planilha_venda": f"eq.{i}", "mes": f"eq.{mes}"})
            self.recebimentos.pop((i, mes))
            gravou = True

        removidas = sorted(set(self.vendas) - set(desejadas))
        if removidas:
            banco.apagar("metricas_faturamento", {"id_planilha": f"in.({','.join(map(str, removidas))})"})
            for i in removidas:
                self.vendas.pop(i, None)
            for k in [k for k in self.recebimentos if k[0] in removidas]:
                del self.recebimentos[k]
            gravou = True

        if gravou:
            cache.invalidar()


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
            for l in self._consultar("logs_pipedrive", {}, "chave,ocorrencias,id_user," + ",".join(COLUNAS_LOG))
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
            banco.upsert(
                "logs_pipedrive",
                [{**l, "atualizado_em": self.agora().isoformat()} for l in novos.values()],
                on_conflict="chave",
            )
            self.logs.update(novos)

        removidas = sorted(set(self.logs) - set(desejados))
        if removidas:
            banco.apagar("logs_pipedrive", {"chave": f"in.({','.join(removidas)})"})
            for k in removidas:
                self.logs.pop(k, None)


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
