from fastapi.testclient import TestClient

import api_server
from src.api import event_probability_routes
from src.event_probability.models import (
    EventProbability,
    ProbabilitySnapshot,
    RefreshState,
)


class FakeService:
    def __init__(self) -> None:
        self.state = RefreshState(
            status="running",
            kind="quick",
            stage="fetching_kalshi",
            progress_current=2,
            progress_total=30,
        )
        self.start_calls: list[str] = []

    def get_overview(self) -> ProbabilitySnapshot:
        return ProbabilitySnapshot(
            events=[
                EventProbability(
                    question="Cached event",
                    topic="other",
                    source="polymarket",
                    slug="cached",
                )
            ]
        )

    async def start_refresh(self, kind: str) -> RefreshState:
        self.start_calls.append(kind)
        return self.state

    def get_refresh_state(self) -> RefreshState:
        return self.state

    async def get_history(self, token_id: str) -> list[dict[str, float | int]]:
        return [{"t": 1, "p": 0.5}]


def client(monkeypatch) -> tuple[TestClient, FakeService]:
    monkeypatch.delenv("API_AUTH_KEY", raising=False)
    monkeypatch.setattr(api_server, "_API_KEY", None)
    service = FakeService()
    monkeypatch.setattr(event_probability_routes, "_SERVICE", service)
    return TestClient(api_server.app, client=("127.0.0.1", 50000)), service


def test_overview_returns_injected_snapshot(monkeypatch) -> None:
    test_client, _ = client(monkeypatch)

    response = test_client.get("/event-probability/overview")

    assert response.status_code == 200
    assert response.json()["events"][0]["question"] == "Cached event"


def test_refresh_routes_return_202_and_reuse_active_state(monkeypatch) -> None:
    test_client, service = client(monkeypatch)

    quick = test_client.post("/event-probability/refresh/quick")
    full = test_client.post("/event-probability/refresh/full")

    assert quick.status_code == 202
    assert full.status_code == 202
    assert quick.json() == full.json()
    assert service.start_calls == ["quick", "full"]


def test_refresh_status_returns_progress(monkeypatch) -> None:
    test_client, _ = client(monkeypatch)

    response = test_client.get("/event-probability/refresh/status")

    assert response.status_code == 200
    assert response.json()["progress_current"] == 2
    assert response.json()["progress_total"] == 30


def test_history_validates_token_and_returns_data(monkeypatch) -> None:
    test_client, _ = client(monkeypatch)

    valid = test_client.get("/event-probability/history/yes_token-1")
    invalid = test_client.get("/event-probability/history/bad.token")
    oversized = test_client.get(f"/event-probability/history/{'a' * 257}")

    assert valid.status_code == 200
    assert valid.json() == [{"t": 1, "p": 0.5}]
    assert invalid.status_code == 400
    assert oversized.status_code == 400
