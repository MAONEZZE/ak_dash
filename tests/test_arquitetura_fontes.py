import pathlib
import re

RAIZ = pathlib.Path(__file__).parent.parent
APP = RAIZ / "app"

PERMITIDO_HTTPX = {"app/auth.py", "app/workers/google_sheets.py"}

_RE_HTTPX = re.compile(r"^\s*(import httpx|from httpx\b)", re.M)
_RE_IMPORT_BANCO = re.compile(r"^\s*from app\.fontes\.banco import (.+)$", re.M)
_RE_OPERACAO_BANCO = re.compile(r"\b(query|upsert|apagar)\b")
_RE_CHAMADA_BANCO = re.compile(r"banco\.(query|upsert|apagar)\(")


def _violacoes(caminho_relativo: str, texto: str) -> list[str]:
    motivos = []
    if _RE_HTTPX.search(texto) and caminho_relativo not in PERMITIDO_HTTPX:
        motivos.append("importa httpx fora de app/fontes/")
    for import_banco in _RE_IMPORT_BANCO.finditer(texto):
        if _RE_OPERACAO_BANCO.search(import_banco.group(1)):
            motivos.append("importa query/upsert/apagar de app.fontes.banco")
    if _RE_CHAMADA_BANCO.search(texto):
        motivos.append("chama banco.query/upsert/apagar fora de app/fontes/")
    return [f"{caminho_relativo}: {motivo}" for motivo in motivos]


def test_so_app_fontes_fala_com_fontes_externas():
    violacoes = []
    for arquivo in APP.rglob("*.py"):
        caminho = arquivo.relative_to(RAIZ).as_posix()
        if caminho.startswith("app/fontes/"):
            continue
        violacoes.extend(_violacoes(caminho, arquivo.read_text(encoding="utf-8")))
    assert violacoes == []


def test_trava_pega_um_dominio_que_volta_a_chamar_query():
    assert _violacoes("app/dominios/x/banco.py", "from app.fontes.banco import query\n") != []
    assert _violacoes(
        "app/dominios/x/rotas.py",
        "from app.fontes.banco import iniciar_registro_de_falhas, tabelas_com_falha\n",
    ) == []
