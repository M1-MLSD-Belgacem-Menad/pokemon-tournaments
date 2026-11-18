import pymysql
import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_health_sans_base(monkeypatch):
    monkeypatch.setattr(
        "app.main.connect", lambda: pytest.fail("/health ne touche pas la base")
    )
    resp = TestClient(app).get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ready_ok(client):
    resp = client.get("/ready")
    assert (resp.status_code, resp.json()) == (200, {"status": "ready"})


def test_ready_503_si_base_injoignable(client, monkeypatch):
    def down():
        raise pymysql.OperationalError(2003, "Can't connect")

    monkeypatch.setattr("app.main.connect", down)
    assert client.get("/ready").status_code == 503
    assert client.get("/health").status_code == 200  # la liveness reste verte
