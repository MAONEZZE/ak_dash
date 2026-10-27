import httpx

from app.fontes import google_sheets


class _Credenciais:
    def __init__(self):
        self.valid = True
        self.token = "tok"
        self.refresh_chamadas = []

    def refresh(self, request):
        self.refresh_chamadas.append(request)


def test_abas_le_todas_as_abas_e_converte_celulas(monkeypatch):
    chamadas = []
    corpo = {
        "sheets": [
            {
                "properties": {"title": "Isaque"},
                "data": [
                    {
                        "rowData": [
                            {"values": [{"effectiveValue": {"stringValue": "Dia"}}, {"effectiveValue": {"stringValue": "Follow-ups"}}]},
                            {"values": [{"effectiveValue": {"stringValue": "Meta diária"}}, {"effectiveValue": {"numberValue": 50}}]},
                            {},
                            {
                                "values": [
                                    {"effectiveValue": {"numberValue": 1}},
                                    {},
                                    {"effectiveValue": {"boolValue": True}},
                                    {"effectiveValue": {"errorValue": {"type": "DIVIDE_BY_ZERO"}}},
                                ]
                            },
                        ]
                    }
                ],
            },
            {"properties": {"title": "Vazia"}, "data": [{}]},
        ]
    }

    def _get(url, **kwargs):
        chamadas.append((url, kwargs))
        return httpx.Response(200, request=httpx.Request("GET", "https://sheets.googleapis.com"), json=corpo)

    monkeypatch.setattr(google_sheets.httpx, "get", _get)
    credenciais = _Credenciais()

    resultado = google_sheets.LeitorSheets(credenciais).abas("ID123")

    assert resultado == [
        ("Isaque", [["Dia", "Follow-ups"], ["Meta diária", 50], [], [1, None, True, None]]),
        ("Vazia", []),
    ]
    assert len(chamadas) == 1
    url, kwargs = chamadas[0]
    assert url == "https://sheets.googleapis.com/v4/spreadsheets/ID123"
    assert kwargs["params"] == {
        "includeGridData": "true",
        "fields": "sheets(properties(title),data(rowData(values(effectiveValue))))",
    }
    assert kwargs["headers"] == {"Authorization": "Bearer tok"}
    assert credenciais.refresh_chamadas == []
