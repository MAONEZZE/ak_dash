from __future__ import annotations

import hashlib
import json

from app import planilha_logs


CABECALHO = ["Data", "Hora", "Usuario da ação", "Atividade feita", "Ação evento", "Nome do Cliente", "Telefone do Cliente", "Quem indicou", "Prospectado por", "Linkedin do Cliente", "instagram do Cliente", "url négocio"]


def test_linha_vira_evento_com_campos_do_banco():
    linha = ["05/08/2026", "18:18", "Jennifer Pamplona", "Números Captados", "adição", "Isaque Costa", " (31) 98713-0727 ", "", "Jennifer", "linkedin.com/in/isaque-costa-41243a62", "", "https://atlaz.pipedrive.com/deal/1803"]

    leitura = planilha_logs.ler_logs([CABECALHO, linha])

    assert leitura.invalidas == []
    assert len(leitura.eventos) == 1
    evento = leitura.eventos[0]
    assert {k: v for k, v in evento.items() if k != "chave"} == {
        "ocorrencias": 1,
        "data": "2026-08-05",
        "hora": "18:18:00",
        "usuario_acao": "Jennifer Pamplona",
        "atividade": "Números Captados",
        "acao_evento": "adição",
        "cliente_nome": "Isaque Costa",
        "telefone": "(31) 98713-0727",
        "telefone_digitos": "31987130727",
        "quem_indicou": None,
        "prospectado_por": "Jennifer",
        "linkedin": "linkedin.com/in/isaque-costa-41243a62",
        "instagram": None,
        "url_negocio": "https://atlaz.pipedrive.com/deal/1803",
    }
    assert evento["chave"] == hashlib.sha1(
        json.dumps(
            ["2026-08-05", "18:18:00", "Jennifer Pamplona", "Números Captados", "adição", "Isaque Costa", "(31) 98713-0727", None, "Jennifer", "linkedin.com/in/isaque-costa-41243a62", None, "https://atlaz.pipedrive.com/deal/1803"],
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def test_data_e_hora_em_numero_serial_viram_iso():
    linha = [46239, 0.7625, "Thalyson", "Indicações", "adição", "Valdir Pandolfi", 5511999998587]

    leitura = planilha_logs.ler_logs([CABECALHO, linha])

    assert len(leitura.eventos) == 1
    evento = leitura.eventos[0]
    assert evento["data"] == "2026-08-05"
    assert evento["hora"] == "18:18:00"
    assert evento["telefone"] == "5511999998587"
    assert evento["telefone_digitos"] == "5511999998587"
    assert evento["url_negocio"] is None


def test_linhas_identicas_viram_um_evento_com_ocorrencias():
    a = ["06/08/2026", "15:20", "Thalyson", "Indicações", "adição", "Valdir Pandolfi"]
    b = ["06/08/2026", "15:20", "Thalyson", "Indicações", "adição", "Aurelio Bud Spencer"]

    leitura = planilha_logs.ler_logs([CABECALHO, a, b, a])

    assert [(e["cliente_nome"], e["ocorrencias"]) for e in leitura.eventos] == [("Valdir Pandolfi", 2), ("Aurelio Bud Spencer", 1)]


def test_linha_sem_data_ou_atividade_vai_para_invalidas_e_vazia_e_ignorada():
    ok = ["06/08/2026", "15:20", "Thalyson", "Indicações"]
    sem_data = ["ontem", "15:20", "Thalyson", "Indicações"]
    sem_atividade = ["06/08/2026", "15:20", "Thalyson", "  "]
    vazia = ["", None, " "]

    leitura = planilha_logs.ler_logs([CABECALHO, ok, sem_data, sem_atividade, vazia, []])

    assert len(leitura.eventos) == 1
    assert leitura.invalidas == [tuple(sem_data), tuple(sem_atividade)]
