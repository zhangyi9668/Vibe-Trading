import asyncio

import httpx

from src.event_probability import (
    EventProbability,
    ProbabilitySnapshot,
    RefreshState,
    SourceStatus,
)
from src.event_probability.kalshi import (
    discover_priority_series,
    fetch_full,
    fetch_series,
    shape_kalshi_event,
)
from src.event_probability.polymarket import (
    fetch_markets,
    shape_polymarket_market,
)


def test_event_probability_wire_serialization() -> None:
    event = EventProbability(
        question="Will the Fed cut rates in 2026?",
        topic="Federal Reserve",
        prices=[0.62, 0.38],
        prob_yes=0.62,
        pick_label="Yes",
        change_24h=0.01,
        change_7d=-0.02,
        volume_24h=125_000.5,
        liquidity=980_000.0,
        end_date="2026-12-31",
        slug="fed-cut-rates-2026",
        series_ticker="FED",
        token_id_yes="yes-token",
        source="polymarket",
        source_category="Economy",
    )

    assert event.model_dump(mode="json") == {
        "question": "Will the Fed cut rates in 2026?",
        "question_zh": None,
        "topic": "Federal Reserve",
        "outcomes": ["Yes", "No"],
        "prices": [0.62, 0.38],
        "prob_yes": 0.62,
        "pick_label": "Yes",
        "change_24h": 0.01,
        "change_7d": -0.02,
        "volume_24h": 125_000.5,
        "liquidity": 980_000.0,
        "end_date": "2026-12-31",
        "slug": "fed-cut-rates-2026",
        "series_ticker": "FED",
        "token_id_yes": "yes-token",
        "source": "polymarket",
        "source_category": "Economy",
    }


def test_refresh_state_wire_defaults() -> None:
    state = RefreshState()

    assert state.model_dump(mode="json") == {
        "status": "idle",
        "kind": None,
        "stage": None,
        "progress_current": 0,
        "progress_total": 0,
        "started_at": None,
        "finished_at": None,
        "error": None,
        "translation": {
            "new_translations": 0,
            "cache_hits": 0,
            "pending": 0,
        },
    }


def test_empty_source_status_defaults_as_of_to_none() -> None:
    status = SourceStatus(source="polymarket", status="empty")

    assert status.as_of is None


def test_probability_snapshot_wire_defaults() -> None:
    snapshot = ProbabilitySnapshot()

    assert snapshot.as_of is None
    assert snapshot.events == []
    assert snapshot.sources == []
    assert snapshot.translation_cache_size == 0
    assert snapshot.refresh.status == "idle"


def test_probability_snapshot_mutable_defaults_are_isolated() -> None:
    first = ProbabilitySnapshot()
    second = ProbabilitySnapshot()

    first.events.append(
        EventProbability(
            question="Will event X happen?",
            topic="other",
            slug="event-x",
            source="polymarket",
        )
    )
    first.sources.append(SourceStatus(source="polymarket", status="ok"))
    first.refresh.translation.pending = 1

    assert second.events == []
    assert second.sources == []
    assert second.refresh.translation.pending == 0


def test_polymarket_parses_json_encoded_fields() -> None:
    row = shape_polymarket_market(
        {
            "question": "Will event X happen?",
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["0.62", "0.38"]',
            "clobTokenIds": '["yes-token", "no-token"]',
            "volume24hr": 1234,
            "slug": "event-x",
        }
    )

    assert row is not None
    assert row.prob_yes == 0.62
    assert row.token_id_yes == "yes-token"


def test_polymarket_does_not_invent_yes_for_multi_choice_market() -> None:
    row = shape_polymarket_market(
        {
            "question": "Who will win?",
            "outcomes": '["Alice", "Bob"]',
            "outcomePrices": '["0.62", "0.38"]',
            "clobTokenIds": '["alice-token", "bob-token"]',
            "volume24hr": 1234,
            "slug": "winner",
        }
    )

    assert row is not None
    assert row.prob_yes is None
    assert row.token_id_yes is None


def test_kalshi_uses_dollar_fields_and_nearest_fifty_percent_leg() -> None:
    row = shape_kalshi_event(
        {
            "title": "Average gas price",
            "event_ticker": "KXGAS",
            "category": "Commodities",
            "series_ticker": "KXGAS",
            "markets": [
                {
                    "yes_sub_title": "Above $4.10",
                    "yes_ask_dollars": "0.95",
                    "volume_24h_fp": "10",
                },
                {
                    "yes_sub_title": "Above $4.20",
                    "yes_ask_dollars": "0.53",
                    "volume_24h_fp": "20",
                },
                {
                    "yes_sub_title": "Above $4.30",
                    "yes_ask_dollars": "0.08",
                    "volume_24h_fp": "30",
                },
            ],
        }
    )

    assert row is not None
    assert row.prob_yes == 0.53
    assert row.pick_label == "Above $4.20"
    assert row.volume_24h == 60.0


def test_polymarket_paginates_by_offset_and_orders_on_server() -> None:
    requests: list[dict[str, str]] = []
    market = {
        "question": "Will event X happen?",
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.62", "0.38"]',
        "clobTokenIds": '["yes-token", "no-token"]',
        "volume24hr": 1234,
        "slug": "event-x",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(dict(request.url.params))
        payload = [market] * 100 if request.url.params["offset"] == "0" else []
        return httpx.Response(200, json=payload)

    async def run() -> list[EventProbability]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_markets(client=client, max_pages=3)

    rows = asyncio.run(run())

    assert len(rows) == 100
    assert [request["offset"] for request in requests] == ["0", "100"]
    assert all(request["order"] == "volume24hr" for request in requests)
    assert all(request["ascending"] == "false" for request in requests)


def test_polymarket_retries_a_failed_page_once() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503)
        return httpx.Response(200, json=[])

    async def run() -> list[EventProbability]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_markets(client=client, max_pages=1)

    assert asyncio.run(run()) == []
    assert attempts == 2


def test_kalshi_full_follows_cursors_and_reports_progress() -> None:
    cursors: list[str | None] = []
    progress: list[tuple[int, int]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["limit"] == "200"
        assert request.url.params["status"] == "open"
        assert request.url.params["with_nested_markets"] == "true"
        cursor = request.url.params.get("cursor")
        cursors.append(cursor)
        suffix = "1" if cursor is None else "2"
        return httpx.Response(
            200,
            json={
                "events": [
                    {
                        "title": f"Fed event {suffix}",
                        "event_ticker": f"KXFED-{suffix}",
                        "category": "Economics",
                        "series_ticker": "KXFED",
                        "markets": [
                            {
                                "yes_sub_title": "Yes",
                                "yes_ask_dollars": "0.5",
                                "volume_24h_fp": "10",
                            }
                        ],
                    }
                ],
                "cursor": "next" if cursor is None else "",
            },
        )

    async def run() -> list[EventProbability]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_full(
                client=client,
                max_pages=5,
                on_progress=lambda current, total: progress.append((current, total)),
            )

    rows = asyncio.run(run())

    assert len(rows) == 2
    assert cursors == [None, "next"]
    assert progress == [(1, 5), (2, 5)]


def test_kalshi_quick_fetches_each_series_concurrently() -> None:
    requested_series: list[str] = []
    active = 0
    max_active = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, max_active
        assert request.url.params["limit"] == "200"
        assert request.url.params["status"] == "open"
        series = request.url.params["series_ticker"]
        requested_series.append(series)
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return httpx.Response(
            200,
            json={
                "markets": [
                    {
                        "title": f"{series} market",
                        "event_ticker": f"{series}-EVENT",
                        "series_ticker": series,
                        "category": "Economics",
                        "yes_sub_title": "Yes",
                        "yes_ask_dollars": "0.5",
                        "volume_24h_fp": "10",
                    }
                ]
            },
        )

    async def run() -> list[EventProbability]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_series(
                ["KXFED", "KXCPI"],
                client=client,
                concurrency=2,
            )

    rows = asyncio.run(run())

    assert len(rows) == 2
    assert set(requested_series) == {"KXFED", "KXCPI"}
    assert max_active == 2


def test_kalshi_quick_follows_market_cursors_and_uses_series_fallback() -> None:
    cursors: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("cursor")
        cursors.append(cursor)
        suffix = "1" if cursor is None else "2"
        return httpx.Response(
            200,
            json={
                "markets": [
                    {
                        "title": f"Market {suffix}",
                        "event_ticker": f"KXCPI-{suffix}",
                        "yes_sub_title": "Yes",
                        "yes_ask_dollars": "0.5",
                        "volume_24h_fp": "10",
                    }
                ],
                "cursor": "next" if cursor is None else "",
            },
        )

    async def run() -> list[EventProbability]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_series(["KXCPI"], client=client)

    rows = asyncio.run(run())

    assert cursors == [None, "next"]
    assert [row.question for row in rows] == ["Market 1", "Market 2"]
    assert all(row.series_ticker == "KXCPI" for row in rows)


def test_kalshi_quick_waits_for_other_series_when_one_fails() -> None:
    completed: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        series = request.url.params["series_ticker"]
        if series == "FAIL":
            return httpx.Response(503)
        await asyncio.sleep(0.01)
        completed.append(series)
        return httpx.Response(200, json={"markets": []})

    async def run() -> list[EventProbability]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_series(["FAIL", "KXCPI"], client=client)

    assert asyncio.run(run()) == []
    assert completed == ["KXCPI"]


def test_priority_series_seed_and_rank_core_topics_only() -> None:
    events = [
        EventProbability(
            question="CPI",
            topic="macro_economy",
            source="kalshi",
            slug="cpi-1",
            series_ticker="KXCPI",
            volume_24h=30,
        ),
        EventProbability(
            question="CPI second market",
            topic="macro_economy",
            source="kalshi",
            slug="cpi-2",
            series_ticker="KXCPI",
            volume_24h=20,
        ),
        EventProbability(
            question="Jobs",
            topic="macro_economy",
            source="kalshi",
            slug="jobs",
            series_ticker="KXJOBS",
            volume_24h=40,
        ),
        EventProbability(
            question="Sports",
            topic="sports",
            source="kalshi",
            slug="sports",
            series_ticker="KXSPORTS",
            volume_24h=1000,
        ),
    ]

    assert discover_priority_series(events) == ["KXFED", "KXCPI", "KXJOBS"]
