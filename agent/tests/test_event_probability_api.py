from fastapi.testclient import TestClient

import api_server
from src.api import event_probability_routes
from src.event_probability.models import (
    EventProbability,
    ProbabilityHistorySeries,
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
        self.history_calls: list[str] = []
        self.histories_response: list[ProbabilityHistorySeries] = [
            ProbabilityHistorySeries(
                label="Candidate A",
                token_id="token-a",
                points=[{"t": 1, "p": 0.5}],
            )
        ]

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
        self.history_calls.append(token_id)
        return [{"t": 1, "p": 0.5}]

    async def get_histories(self, series):
        if all(item.error is not None for item in self.histories_response):
            raise RuntimeError("all probability history series failed")
        return self.histories_response


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


def test_history_get_route_still_uses_single_token_service(monkeypatch) -> None:
    test_client, service = client(monkeypatch)

    response = test_client.get("/event-probability/history/yes_token-1")

    assert response.status_code == 200
    assert service.history_calls == ["yes_token-1"]


def test_history_post_returns_multi_series_data(monkeypatch) -> None:
    test_client, _ = client(monkeypatch)

    response = test_client.post(
        "/event-probability/history",
        json={
            "series": [
                {
                    "label": "Candidate A",
                    "token_id": "token-a",
                }
            ]
        },
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "label": "Candidate A",
            "token_id": "token-a",
            "points": [{"t": 1, "p": 0.5}],
            "error": None,
        }
    ]


def test_history_post_rejects_invalid_token(monkeypatch) -> None:
    test_client, _ = client(monkeypatch)

    response = test_client.post(
        "/event-probability/history",
        json={
            "series": [
                {
                    "label": "Candidate A",
                    "token_id": "bad.token",
                }
            ]
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid token_id"


def test_history_post_rejects_more_than_five_series(monkeypatch) -> None:
    test_client, _ = client(monkeypatch)

    response = test_client.post(
        "/event-probability/history",
        json={
            "series": [
                {
                    "label": f"Candidate {index}",
                    "token_id": f"token-{index}",
                }
                for index in range(6)
            ]
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "series count must be 1..5"


def test_history_post_all_failed_returns_internal_error(monkeypatch) -> None:
    test_client, service = client(monkeypatch)

    service.histories_response = [
        ProbabilityHistorySeries(
            label="Candidate A",
            token_id="token-a",
            error="upstream unavailable",
        )
    ]

    response = test_client.post(
        "/event-probability/history",
        json={
            "series": [
                {
                    "label": "Candidate A",
                    "token_id": "token-a",
                }
            ]
        },
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "internal error; see server logs"


def test_history_post_partial_failure_returns_200(monkeypatch) -> None:
    test_client, service = client(monkeypatch)

    service.histories_response = [
        ProbabilityHistorySeries(
            label="Candidate A",
            token_id="token-a",
            points=[{"t": 1, "p": 0.5}],
        ),
        ProbabilityHistorySeries(
            label="Candidate B",
            token_id="token-b",
            error="upstream unavailable",
        ),
    ]

    response = test_client.post(
        "/event-probability/history",
        json={
            "series": [
                {
                    "label": "Candidate A",
                    "token_id": "token-a",
                },
                {
                    "label": "Candidate B",
                    "token_id": "token-b",
                },
            ]
        },
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "label": "Candidate A",
            "token_id": "token-a",
            "points": [{"t": 1, "p": 0.5}],
            "error": None,
        },
        {
            "label": "Candidate B",
            "token_id": "token-b",
            "points": [],
            "error": "upstream unavailable",
        },
    ]
