from __future__ import annotations

import pytest

from scripts import rodar_sql


def test_sem_database_url_aborta_com_mensagem(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(rodar_sql, "load_dotenv", lambda *a, **k: None)

    with pytest.raises(SystemExit) as exc:
        rodar_sql.main(["-c", "select 1"])

    assert str(exc.value) == "DATABASE_URL não configurada no ak_dash/.env"
