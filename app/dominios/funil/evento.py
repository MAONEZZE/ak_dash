"""Funil de Evento: etapas do Pipedrive de uma Imersão. Regras: docs/plans/funil-evento.md."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from app.config import settings
from app.fontes import pipedrive as api
from app.periodo import TZ_SP
from app.planilhas import normalizar

ZERADO = {"inscritos": 0, "onboarding_agendado": 0, "onboarding_realizado": 0, "vendas": 0}
DIAS_VENDAS_ANTES_DO_EVENTO = 180
OPCOES_ALMOCO_PAGO = frozenset({198, 199})  # 198 = Almoço Pago (2 dias), 199 = Almoço Pago (1 dia)


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
    ids_etiqueta: set[int],
    inscritos: list[dict],
    agendados: list[dict],
    realizados: list[dict],
    ganhos: list[dict],
) -> dict[str, int]:
    """Negócios com etiqueta do evento em cada lista, sem filtro de data (retrato de agora)."""
    def conta(negocios: list[dict]) -> int:
        return sum(1 for n in negocios if ids_etiqueta & set(n.get("label_ids") or []))

    return {
        "inscritos": conta(inscritos),
        "onboarding_agendado": conta(agendados),
        "onboarding_realizado": conta(realizados),
        "vendas": conta(ganhos),
    }


def contar_almocos_pagos(ids_etiqueta: set[int], realizados: list[dict], chave_campo: str) -> int:
    """Negócios com etiqueta do evento e opção de almoço pago (198 ou 199) no campo `chave_campo`."""
    return sum(
        1
        for n in realizados
        if ids_etiqueta & set(n.get("label_ids") or [])
        and OPCOES_ALMOCO_PAGO & set((n.get("custom_fields") or {}).get(chave_campo) or [])
    )


def _buscar(data_evento: date) -> dict[str, int]:
    ids = ids_etiquetas_do_evento(api.etiquetas_de_negocio(), data_evento)
    if not ids:
        return dict(ZERADO)
    inscrito = settings.pipe_id_inscrito_pipeline_principal
    agendado = settings.pipe_id_onboarding_agendado_pipeline_principal
    realizado = settings.pipe_id_onboarding_realizado_pipeline_principal
    inscritos = api.negocios_atuais_no_estagio(inscrito) if inscrito is not None else []
    agendados = api.negocios_atuais_no_estagio(agendado) if agendado is not None else []
    realizados = api.negocios_atuais_no_estagio(realizado) if realizado is not None else []
    ganhos = api.negocios_ganhos_desde(
        datetime.combine(data_evento - timedelta(days=DIAS_VENDAS_ANTES_DO_EVENTO), time.min, tzinfo=TZ_SP)
    )
    return contar_pipedrive_evento(ids, inscritos, agendados, realizados, ganhos)


def _buscar_almocos(data_evento: date) -> int:
    if settings.pipe_id_campo_almoco is None or settings.pipe_id_onboarding_realizado_pipeline_principal is None:
        return 0
    ids = ids_etiquetas_do_evento(api.etiquetas_de_negocio(), data_evento)
    if not ids:
        return 0
    return contar_almocos_pagos(
        ids,
        api.negocios_atuais_no_estagio(settings.pipe_id_onboarding_realizado_pipeline_principal),
        settings.pipe_id_campo_almoco,
    )


def buscar_almocos_pagos(data_evento: date) -> int:
    """Almoços pagos do evento agora (card do Funil SDR)."""
    return api.ou_vazio(lambda: _buscar_almocos(data_evento), 0, "Pipedrive indisponível — almoços pagos zerados")


def buscar_pipedrive_evento(data_evento: date) -> dict[str, int]:
    """Retrato de agora: Inscritos, Onboarding Agendado/Realizado e Vendas do evento, sem filtro de data.
    Pipedrive fora do ar ou sem configuração: ZERADO + falha 'pipedrive' registrada (aviso na tela)."""
    return api.ou_vazio(lambda: _buscar(data_evento), dict(ZERADO), "Pipedrive indisponível — etapas do Funil Evento zeradas")
