"""Funil de Evento: etapas do Pipedrive de uma Imersão. Regras: docs/plans/funil-evento.md."""
from __future__ import annotations

from datetime import date, datetime, time, timezone

from app.config import settings
from app.dominios.funil.pipedrive import _data_sp, _no_periodo
from app.fontes import pipedrive as api
from app.periodo import TZ_SP
from app.planilhas import normalizar

ZERADO = {"onboarding_agendado": 0, "onboarding_realizado": 0, "vendas": 0}


def data_do_evento_sp(texto: str) -> date:
    """Dia (em SP) do `event_date` do SED. Sem fuso = UTC (é como o SED grava)."""
    momento = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(TZ_SP).date()


def ids_etiquetas_do_evento(etiquetas: dict[int, str], data_evento: date) -> set[int]:
    """Etiquetas de negócio do evento: `imersao_DD/MM` ou `imersao_DD/MM/AAAA` (sem maiúsculas/acento)."""
    alvo = f"imersao_{data_evento:%d/%m}"
    aceitas = {alvo, f"{alvo}/{data_evento.year}"}
    return {i for i, texto in etiquetas.items() if normalizar(texto) in aceitas}


def contar_pipedrive_evento(
    ids_etiqueta: set[int], agendados: list[dict], realizados: list[dict], ganhos: list[dict], inicio: date, fim: date
) -> dict[str, int]:
    """Negócios com etiqueta do evento: nas colunas de onboarding pela data de entrada (stage_change_time),
    ganhos pela data de ganho (won_time). Datas em dias de SP, [inicio, fim]."""
    def conta(negocios: list[dict], campo: str) -> int:
        return sum(
            1
            for n in negocios
            if ids_etiqueta & set(n.get("label_ids") or []) and _no_periodo(_data_sp(n.get(campo)), inicio, fim)
        )

    return {
        "onboarding_agendado": conta(agendados, "stage_change_time"),
        "onboarding_realizado": conta(realizados, "stage_change_time"),
        "vendas": conta(ganhos, "won_time"),
    }


def _buscar(data_evento: date, inicio: date, fim: date) -> dict[str, int]:
    desde = datetime.combine(inicio, time.min, tzinfo=TZ_SP)
    ids = ids_etiquetas_do_evento(api.etiquetas_de_negocio(), data_evento)
    if not ids:
        return dict(ZERADO)
    agendado = settings.pipe_id_onboarding_agendado_pipeline_linkedin
    realizado = settings.pipe_id_onboarding_realizado_pipeline_linkedin
    agendados = api.negocios_no_estagio(agendado, desde) if agendado is not None else []
    realizados = api.negocios_no_estagio(realizado, desde) if realizado is not None else []
    ganhos = api.negocios_ganhos_desde(desde)
    return contar_pipedrive_evento(ids, agendados, realizados, ganhos, inicio, fim)


def buscar_pipedrive_evento(data_evento: date, inicio: date, fim: date) -> dict[str, int]:
    """Onboarding Agendado/Realizado e Vendas do evento em [inicio, fim]. Pipedrive fora do ar ou sem
    configuração: ZERADO + falha 'pipedrive' registrada (aviso na tela)."""
    return api.ou_vazio(lambda: _buscar(data_evento, inicio, fim), dict(ZERADO), "Pipedrive indisponível — etapas do Funil Evento zeradas")
