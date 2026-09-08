"""Parser da planilha comercial: cabeçalho + meta diária + identificação + dias.

Agnóstico ao período pedido — não decide o que é "dia fora do calendário",
isso depende do mês-alvo e é responsabilidade de calculo.py. Este módulo só
transforma uma lista de linhas cruas (vinda do Sheets ou de um CSV de teste)
em uma estrutura por coluna conhecida, mapeada por NOME, nunca por posição.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ColunaInfo:
    chave: str
    nome_exibicao: str
    funcao: str  # "sdr" | "closer"


# Coluna mapeada por nome normalizado (sem quebra de linha, sem acento) —
# imune a inserção de coluna no meio ou a variação de posição entre arquivos.
COLUNAS: dict[str, ColunaInfo] = {
    "conexoes enviadas": ColunaInfo("conexoes_enviadas", "Conexões Enviadas", "sdr"),
    "conexoes aceitas": ColunaInfo("conexoes_aceitas", "Conexões Aceitas", "sdr"),
    "abordagens": ColunaInfo("abordagens", "Abordagens", "sdr"),
    "inmails enviados": ColunaInfo("inmails_enviados", "InMails Enviados", "sdr"),
    "follow-ups": ColunaInfo("follow_ups", "Follow-ups", "sdr"),
    "numeros captados": ColunaInfo("numeros_captados", "Números Captados", "sdr"),
    "ligacoes agendadas": ColunaInfo("ligacoes_agendadas", "Ligações Agendadas", "sdr"),
    "indicacoes captadas": ColunaInfo("indicacoes_captadas", "Indicações Captadas", "sdr"),
    "ligacoes realizadas": ColunaInfo("ligacoes_realizadas", "Ligações Realizadas", "closer"),
    "reunioes agendadas": ColunaInfo("reunioes_agendadas", "Reuniões Agendadas", "closer"),
    "reunioes realizadas": ColunaInfo("reunioes_realizadas", "Reuniões Realizadas", "closer"),
    "indicacoes": ColunaInfo("indicacoes", "Indicações", "closer"),
}

_TRANS_ACENTOS = str.maketrans("áàâãéêíóôõúç", "aaaaeeiooouc")
_EMAIL_RE = re.compile(
    r"SDR:\s*([\w.+-]+@[\w.-]+)\s+Closer:\s*([\w.+-]+@[\w.-]+)", re.IGNORECASE
)


def normalizar_cabecalho(texto: str) -> str:
    """"Conexões\\nEnviadas" -> "conexoes enviadas"; "Follow-\\nups" -> "follow-ups"."""
    s = texto.replace("\n", " ").strip()
    s = re.sub(r"-\s+", "-", s)  # "Follow-\nups" normalizado antes vira "Follow- ups" -> "Follow-ups"
    s = re.sub(r"\s+", " ", s)
    return s.lower().translate(_TRANS_ACENTOS)


@dataclass
class PlanilhaParseada:
    arquivo: str
    email_sdr: str | None
    email_closer: str | None
    metas: dict[str, int] = field(default_factory=dict)
    # chave da coluna -> {dia (1..31): valor|None}; None = lacuna, nunca confundir com 0.
    valores: dict[str, dict[int, int | None]] = field(default_factory=dict)


def parsear_planilha(
    nome_arquivo: str, linhas: list[list[str]], avisos: list[str]
) -> PlanilhaParseada | None:
    if not linhas:
        avisos.append(f"Planilha '{nome_arquivo}': vazia")
        return None

    cabecalho_bruto = linhas[0]
    cabecalho_normalizado = [normalizar_cabecalho(c) for c in cabecalho_bruto]

    meta_diaria_bruta = linhas[1] if len(linhas) > 1 else []
    metas: dict[str, int] = {}
    colunas_por_indice: dict[int, ColunaInfo] = {}
    for idx, nome_norm in enumerate(cabecalho_normalizado):
        if idx == 0:
            continue
        info = COLUNAS.get(nome_norm)
        if info is None:
            avisos.append(
                f"Planilha '{nome_arquivo}': coluna desconhecida '{cabecalho_bruto[idx]}'"
            )
            continue
        colunas_por_indice[idx] = info
        bruto = meta_diaria_bruta[idx].strip() if idx < len(meta_diaria_bruta) else ""
        try:
            metas[info.chave] = int(bruto)
        except ValueError:
            avisos.append(
                f"Planilha '{nome_arquivo}': meta diária ausente/inválida na coluna "
                f"'{cabecalho_bruto[idx]}'"
            )

    # Linha de anotação "SDR: <email> Closer: <email>" está em posição de
    # coluna variável entre arquivos — varre a planilha inteira com regex,
    # imune à posição e a espaço extra.
    email_sdr = email_closer = None
    for linha in linhas:
        for celula in linha:
            m = _EMAIL_RE.search(celula)
            if m:
                email_sdr, email_closer = m.group(1), m.group(2)
                break
        if email_sdr:
            break
    if not email_sdr or not email_closer:
        avisos.append(
            f"Planilha '{nome_arquivo}': não foi possível identificar SDR/Closer (emails ausentes)"
        )
        return None

    # Linhas de dado real: primeira célula é inteiro — descarta cabeçalho,
    # meta diária, anotação e TOTAL (nenhum desses tem "Dia" como inteiro).
    valores: dict[str, dict[int, int | None]] = {
        info.chave: {} for info in colunas_por_indice.values()
    }
    for linha in linhas:
        primeira = linha[0].strip() if linha else ""
        if not primeira.isdigit():
            continue
        dia = int(primeira)
        if not (1 <= dia <= 31):
            continue
        for idx, info in colunas_por_indice.items():
            bruto = linha[idx].strip() if idx < len(linha) else ""
            if bruto == "":
                valores[info.chave][dia] = None
                continue
            try:
                valores[info.chave][dia] = int(bruto)
            except ValueError:
                avisos.append(
                    f"Planilha '{nome_arquivo}': dia {dia}, coluna '{info.nome_exibicao}': "
                    f"valor não numérico '{bruto}' — tratado como lacuna"
                )
                valores[info.chave][dia] = None

    return PlanilhaParseada(
        arquivo=nome_arquivo,
        email_sdr=email_sdr,
        email_closer=email_closer,
        metas=metas,
        valores=valores,
    )
