from fastapi.testclient import TestClient

import api_server
from src.api import semiconductor_routes


class FakeService:
    def fetch_all(self):
        return {
            "updated_at": "2026-06-19T20:00:00+08:00",
            "success_count": 1,
            "error_count": 0,
            "rows": [
                {
                    "code": "688981.SH",
                    "name": "中芯国际",
                    "segment": "制造/代工",
                    "price": 50.0,
                    "change_pct": 1.0,
                    "amount": 100000000.0,
                    "market_cap": 500000000000.0,
                    "pe_ttm": 30.0,
                    "pb": 3.0,
                    "source": "iFinD",
                    "error": None,
                }
            ],
        }

    def health(self):
        return {"status": "ok", "wind_cli": True, "ifind_configured": True}


def client(monkeypatch) -> TestClient:
    monkeypatch.delenv("API_AUTH_KEY", raising=False)
    monkeypatch.setattr(api_server, "_API_KEY", None)
    monkeypatch.setattr(semiconductor_routes, "_SERVICE", FakeService())
    return TestClient(api_server.app, client=("127.0.0.1", 50000))


def test_quotes_route_returns_semiconductor_payload(monkeypatch) -> None:
    test_client = client(monkeypatch)

    response = test_client.get("/semiconductor/quotes")

    assert response.status_code == 200
    assert response.json()["rows"][0]["name"] == "中芯国际"


def test_health_route_reports_ifind_configuration(monkeypatch) -> None:
    test_client = client(monkeypatch)

    response = test_client.get("/semiconductor/health")

    assert response.status_code == 200
    assert response.json()["ifind_configured"] is True
