import asyncio
import json

import httpx
import pytest
from pydantic import ValidationError

from src.event_probability import models, polymarket
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


@pytest.fixture
def gamma_parent_market() -> dict[str, object]:
    return {
        "question": "Will Candidate A win the 2028 presidential election?",
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.42", "0.58"]',
        "clobTokenIds": '["candidate-a-token", "candidate-a-no-token"]',
        "oneDayPriceChange": "0.03",
        "volume24hr": "250000",
        "liquidityNum": "900000",
        "slug": "will-candidate-a-win-2028",
        "groupItemTitle": "Candidate A",
        "events": [
            {
                "id": "presidential-election-winner-2028",
                "title": "Who will win the 2028 presidential election?",
                "slug": "presidential-election-winner-2028",
            }
        ],
    }


def gamma_event(
    parent_market: dict[str, object],
    markets: list[object],
    *,
    event_id: object = "presidential-election-winner-2028",
    title: object = "Who will win the 2028 presidential election?",
    slug: object = "presidential-election-winner-2028",
) -> dict[str, object]:
    return {
        "id": event_id,
        "title": title,
        "slug": slug,
        "category": "Politics",
        "markets": markets,
    }


def nested_market(
    parent_market: dict[str, object],
    *,
    market_id: object = "candidate-a-market",
    slug: str = "will-candidate-a-win-2028",
    label: str = "Candidate A",
    volume: object = 250000,
) -> dict[str, object]:
    market = dict(parent_market)
    market.pop("events", None)
    market.update(
        {
            "id": market_id,
            "slug": slug,
            "groupItemTitle": label,
            "volume24hr": volume,
        }
    )
    return market


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
        "event_id": None,
        "results": [],
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


def test_grouped_polymarket_event_wire_serialization() -> None:
    event = EventProbability(
        question="Who will win the 2028 presidential election?",
        question_zh="谁将赢得 2028 年总统选举？",
        topic="Politics",
        event_id="presidential-election-winner-2028",
        results=[
            models.EventProbabilityResult(
                label="Candidate A",
                label_zh="候选人 A",
                probability=0.42,
                change_24h=0.03,
                volume_24h=250_000.0,
                token_id="candidate-a-token",
            ),
            models.EventProbabilityResult(label="Candidate B"),
        ],
        volume_24h=500_000.0,
        liquidity=2_000_000.0,
        end_date="2028-11-07",
        slug="presidential-election-winner-2028",
        source="polymarket",
        source_category="Politics",
    )

    assert event.model_dump(mode="json") == {
        "question": "Who will win the 2028 presidential election?",
        "question_zh": "谁将赢得 2028 年总统选举？",
        "topic": "Politics",
        "event_id": "presidential-election-winner-2028",
        "results": [
            {
                "label": "Candidate A",
                "label_zh": "候选人 A",
                "probability": 0.42,
                "change_24h": 0.03,
                "volume_24h": 250_000.0,
                "token_id": "candidate-a-token",
            },
            {
                "label": "Candidate B",
                "label_zh": None,
                "probability": None,
                "change_24h": None,
                "volume_24h": 0.0,
                "token_id": None,
            },
        ],
        "outcomes": ["Yes", "No"],
        "prices": [],
        "prob_yes": None,
        "pick_label": None,
        "change_24h": None,
        "change_7d": None,
        "volume_24h": 500_000.0,
        "liquidity": 2_000_000.0,
        "end_date": "2028-11-07",
        "slug": "presidential-election-winner-2028",
        "series_ticker": None,
        "token_id_yes": None,
        "source": "polymarket",
        "source_category": "Politics",
    }


def test_probability_history_wire_models() -> None:
    request = models.ProbabilityHistoryRequest(
        series=[
            models.ProbabilityHistorySeriesRequest(
                label="Candidate A",
                token_id="candidate-a-token",
            )
        ]
    )
    first = models.ProbabilityHistorySeries(
        label="Candidate A",
        token_id="candidate-a-token",
        points=[{"t": 1_781_280_000, "p": 0.42}],
    )
    second = models.ProbabilityHistorySeries(
        label="Candidate B",
        token_id="candidate-b-token",
    )

    assert request.model_dump(mode="json") == {
        "series": [
            {
                "label": "Candidate A",
                "token_id": "candidate-a-token",
            }
        ]
    }
    first_json = first.model_dump(mode="json")

    assert first_json == {
        "label": "Candidate A",
        "token_id": "candidate-a-token",
        "points": [{"t": 1_781_280_000, "p": 0.42}],
        "error": None,
    }
    assert type(first_json["points"][0]["t"]) is int
    assert type(first_json["points"][0]["p"]) is float
    assert second.points == []


@pytest.mark.parametrize("point", [{"p": 0.42}, {"t": 1_781_280_000}])
def test_probability_history_point_requires_timestamp_and_probability(
    point: dict[str, float],
) -> None:
    with pytest.raises(ValidationError):
        models.ProbabilityHistorySeries(
            label="Candidate A",
            token_id="candidate-a-token",
            points=[point],
        )


def test_polymarket_fetch_histories_fetches_each_series_concurrently() -> None:
    active = 0
    max_active = 0
    requested: list[str] = []

    async def history_fetch(token_id: str) -> list[dict[str, float | int]]:
        nonlocal active, max_active
        requested.append(token_id)
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return [{"t": 1, "p": 0.5}]

    request = [
        models.ProbabilityHistorySeriesRequest(label="A", token_id="token-a"),
        models.ProbabilityHistorySeriesRequest(label="B", token_id="token-b"),
    ]

    histories = asyncio.run(
        polymarket.fetch_histories(request, history_fetch=history_fetch)
    )

    assert [item.model_dump(mode="json") for item in histories] == [
        {
            "label": "A",
            "token_id": "token-a",
            "points": [{"t": 1, "p": 0.5}],
            "error": None,
        },
        {
            "label": "B",
            "token_id": "token-b",
            "points": [{"t": 1, "p": 0.5}],
            "error": None,
        },
    ]
    assert set(requested) == {"token-a", "token-b"}
    assert max_active == 2


def test_polymarket_fetch_histories_returns_error_for_failed_series() -> None:
    async def history_fetch(token_id: str) -> list[dict[str, float | int]]:
        if token_id == "token-b":
            raise RuntimeError("upstream unavailable")
        return [{"t": 1, "p": 0.5}]

    request = [
        models.ProbabilityHistorySeriesRequest(label="A", token_id="token-a"),
        models.ProbabilityHistorySeriesRequest(label="B", token_id="token-b"),
    ]

    histories = asyncio.run(
        polymarket.fetch_histories(request, history_fetch=history_fetch)
    )

    assert [item.model_dump(mode="json") for item in histories] == [
        {
            "label": "A",
            "token_id": "token-a",
            "points": [{"t": 1, "p": 0.5}],
            "error": None,
        },
        {
            "label": "B",
            "token_id": "token-b",
            "points": [],
            "error": "history unavailable",
        },
    ]


def test_polymarket_fetch_histories_uses_safe_error_for_failed_series() -> None:
    sensitive_text = (
        "https://clob.polymarket.com/prices-history?market=secret-token "
        + "internal details " * 50
    )

    async def history_fetch(token_id: str) -> list[dict[str, float | int]]:
        raise RuntimeError(sensitive_text)

    request = [
        models.ProbabilityHistorySeriesRequest(label="A", token_id="token-a"),
    ]

    histories = asyncio.run(
        polymarket.fetch_histories(request, history_fetch=history_fetch)
    )

    assert histories[0].error == "history unavailable"
    assert "clob.polymarket.com" not in histories[0].error
    assert "secret-token" not in histories[0].error
    assert "internal details" not in histories[0].error


@pytest.mark.parametrize("count", [0, 6])
def test_polymarket_fetch_histories_rejects_out_of_range_series_count(
    count: int,
) -> None:
    async def history_fetch(token_id: str) -> list[dict[str, float | int]]:
        return [{"t": 1, "p": 0.5}]

    request = [
        models.ProbabilityHistorySeriesRequest(
            label=f"Series {index}",
            token_id=f"token-{index}",
        )
        for index in range(count)
    ]

    with pytest.raises(ValueError, match="series count must be 1..5"):
        asyncio.run(polymarket.fetch_histories(request, history_fetch=history_fetch))


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


def test_polymarket_parses_reliable_gamma_parent_event(
    gamma_parent_market: dict[str, object],
) -> None:
    row = shape_polymarket_market(gamma_parent_market)

    assert row is not None
    assert row.question == "Who will win the 2028 presidential election?"
    assert row.slug == "presidential-election-winner-2028"
    assert row.event_id == "presidential-election-winner-2028"
    assert len(row.results) == 1
    assert row.results[0].model_dump() == {
        "label": "Candidate A",
        "label_zh": None,
        "probability": 0.42,
        "change_24h": 0.03,
        "volume_24h": 250000.0,
        "token_id": "candidate-a-token",
    }


def test_polymarket_parent_child_label_falls_back_to_market_question(
    gamma_parent_market: dict[str, object],
) -> None:
    market = dict(gamma_parent_market)
    market.pop("groupItemTitle")

    row = shape_polymarket_market(market)

    assert row is not None
    assert row.results[0].label == gamma_parent_market["question"]


@pytest.mark.parametrize(
    "events",
    [
        None,
        [],
        [{"id": "event-id", "title": "Parent title"}],
        [{"id": "event-id", "slug": "parent-slug"}],
        [{"title": "Parent title", "slug": "parent-slug"}],
        [{"id": True, "title": "Parent title", "slug": "parent-slug"}],
        "not-a-list",
    ],
)
def test_polymarket_incomplete_parent_data_falls_back_to_standalone(
    gamma_parent_market: dict[str, object],
    events: object,
) -> None:
    market = dict(gamma_parent_market)
    if events is None:
        market.pop("events")
    else:
        market["events"] = events

    row = shape_polymarket_market(market)

    assert row is not None
    assert row.question == gamma_parent_market["question"]
    assert row.slug == gamma_parent_market["slug"]
    assert row.event_id is None
    assert row.results == []


def test_group_polymarket_events_ranks_children_and_sums_all_legs(
    gamma_parent_market: dict[str, object],
) -> None:
    rows = []
    for index, volume in enumerate([10, 60, 30, 20, 50, 40], start=1):
        market = dict(gamma_parent_market)
        market.update(
            {
                "question": f"Will Candidate {index} win?",
                "groupItemTitle": f"Candidate {index}",
                "outcomePrices": f'["0.{index}", "0.{10 - index}"]',
                "clobTokenIds": f'["token-{index}", "no-token-{index}"]',
                "oneDayPriceChange": index / 100,
                "volume24hr": volume,
                "liquidityNum": volume * 10,
                "slug": f"candidate-{index}",
            }
        )
        shaped = shape_polymarket_market(market)
        assert shaped is not None
        rows.append(shaped)

    grouped = polymarket.group_polymarket_events(rows)

    assert len(grouped) == 1
    parent = grouped[0]
    assert parent.question == "Who will win the 2028 presidential election?"
    assert parent.slug == "presidential-election-winner-2028"
    assert parent.event_id == "presidential-election-winner-2028"
    assert [child.label for child in parent.results] == [
        "Candidate 2",
        "Candidate 5",
        "Candidate 6",
        "Candidate 3",
        "Candidate 4",
    ]
    assert parent.volume_24h == 210.0
    assert parent.liquidity == 2100.0
    assert parent.prob_yes == 0.2
    assert parent.change_24h == 0.02
    assert parent.token_id_yes == "token-2"


def test_group_polymarket_events_uses_only_real_event_ids(
    gamma_parent_market: dict[str, object],
) -> None:
    first_market = dict(gamma_parent_market)
    second_market = dict(gamma_parent_market)
    second_market["events"] = [
        {
            "id": "different-event-id",
            "title": "Who will win the 2028 presidential election?",
            "slug": "different-event-slug",
        }
    ]
    first = shape_polymarket_market(first_market)
    second = shape_polymarket_market(second_market)
    standalone_market = dict(gamma_parent_market)
    standalone_market.pop("events")
    standalone = shape_polymarket_market(standalone_market)
    assert first is not None
    assert second is not None
    assert standalone is not None

    grouped = polymarket.group_polymarket_events(
        [first, second, standalone, standalone.model_copy()]
    )

    assert len(grouped) == 4
    assert [row.event_id for row in grouped] == [
        "presidential-election-winner-2028",
        "different-event-id",
        None,
        None,
    ]


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


@pytest.mark.parametrize(
    ("prices", "volume", "liquidity"),
    [
        ('["NaN", "Infinity"]', "NaN", "Infinity"),
        ('["1.1", "-0.1"]', "Infinity", -1),
        ('["-Infinity", "0.5"]', -1, "NaN"),
    ],
)
def test_polymarket_sanitizes_non_finite_and_out_of_range_numbers(
    gamma_parent_market: dict[str, object],
    prices: str,
    volume: object,
    liquidity: object,
) -> None:
    market = dict(gamma_parent_market)
    market.update(
        {
            "outcomePrices": prices,
            "volume24hr": volume,
            "liquidityNum": liquidity,
            "oneDayPriceChange": "Infinity",
            "oneWeekPriceChange": "NaN",
        }
    )

    row = shape_polymarket_market(market)

    assert row is not None
    assert all(price is None or 0 <= price <= 1 for price in row.prices)
    assert row.prob_yes is None
    assert row.change_24h is None
    assert row.change_7d is None
    assert row.volume_24h == 0.0
    assert row.liquidity == 0.0
    json.dumps(row.model_dump(mode="json"), allow_nan=False)


def test_polymarket_invalid_numbers_do_not_destabilize_child_ranking(
    gamma_parent_market: dict[str, object],
) -> None:
    invalid_market = dict(gamma_parent_market)
    invalid_market.update(
        {
            "groupItemTitle": "Invalid",
            "outcomePrices": '["NaN", "1"]',
            "volume24hr": "NaN",
        }
    )
    valid_market = dict(gamma_parent_market)
    valid_market.update(
        {
            "groupItemTitle": "Valid",
            "outcomePrices": '["0.4", "0.6"]',
            "volume24hr": 10,
        }
    )
    invalid = shape_polymarket_market(invalid_market)
    valid = shape_polymarket_market(valid_market)
    assert invalid is not None
    assert valid is not None

    grouped = polymarket.group_polymarket_events([invalid, valid])

    assert [child.label for child in grouped[0].results] == ["Valid", "Invalid"]
    assert grouped[0].volume_24h == 10.0


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


def test_polymarket_paginates_by_offset_and_orders_on_server(
    gamma_parent_market: dict[str, object],
) -> None:
    requests: list[dict[str, str]] = []
    urls: list[str] = []
    market = nested_market(gamma_parent_market, market_id="market-1")
    event = gamma_event(gamma_parent_market, [market])

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(dict(request.url.params))
        urls.append(str(request.url))
        payload = [event] * 100 if request.url.params["offset"] == "0" else []
        return httpx.Response(200, json=payload)

    async def run() -> list[EventProbability]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_markets(client=client, max_pages=3)

    rows = asyncio.run(run())

    assert len(rows) == 1
    assert all("/events?" in url for url in urls)
    assert [request["offset"] for request in requests] == ["0", "100"]
    assert all(request["order"] == "volume24hr" for request in requests)
    assert all(request["ascending"] == "false" for request in requests)


def test_polymarket_merges_parent_across_pages_and_deduplicates_markets(
    gamma_parent_market: dict[str, object],
) -> None:
    first_market = nested_market(
        gamma_parent_market,
        market_id="candidate-a-market",
        label="Candidate A",
        volume=100,
    )
    slug_only_market = nested_market(
        gamma_parent_market,
        market_id=None,
        slug="candidate-without-id",
        label="Candidate Without ID",
        volume=50,
    )
    first_page = [
        gamma_event(gamma_parent_market, [first_market, slug_only_market])
    ]
    for index in range(99):
        first_page.append(
            gamma_event(
                gamma_parent_market,
                [],
                event_id=f"empty-{index}",
                title=f"Empty event {index}",
                slug=f"empty-event-{index}",
            )
        )
    duplicate_id = dict(first_market)
    duplicate_id["slug"] = "candidate-a-renamed"
    duplicate_id["volume24hr"] = 999
    duplicate_without_id = dict(first_market)
    duplicate_without_id["id"] = None
    duplicate_without_id["volume24hr"] = 999
    duplicate_slug = dict(slug_only_market)
    duplicate_slug["volume24hr"] = 999
    second_market = nested_market(
        gamma_parent_market,
        market_id="candidate-b-market",
        slug="will-candidate-b-win-2028",
        label="Candidate B",
        volume=300,
    )
    second_market.update(
        {
            "question": "Will Candidate B win?",
            "outcomePrices": '["0.55", "0.45"]',
            "clobTokenIds": '["candidate-b-token", "candidate-b-no-token"]',
        }
    )
    second_page = [
        gamma_event(
            gamma_parent_market,
            [duplicate_id, duplicate_without_id, duplicate_slug, second_market],
        )
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        payload = first_page if request.url.params["offset"] == "0" else second_page
        return httpx.Response(200, json=payload)

    async def run() -> list[EventProbability]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_markets(client=client, max_pages=3)

    rows = asyncio.run(run())

    assert len(rows) == 1
    parent = rows[0]
    assert [child.label for child in parent.results] == [
        "Candidate B",
        "Candidate A",
        "Candidate Without ID",
    ]
    assert parent.volume_24h == 450.0


def test_polymarket_falls_back_to_standalone_for_unreliable_parent(
    gamma_parent_market: dict[str, object],
) -> None:
    standalone_market = nested_market(
        gamma_parent_market,
        market_id="standalone-market",
        slug="standalone-market",
    )
    grouped_market = nested_market(gamma_parent_market, market_id="grouped-market")
    malformed_market = {"id": "bad-market", "slug": "bad-market"}
    payload = [
        {
            "id": "missing-parent-fields",
            "markets": [malformed_market, standalone_market],
        },
        gamma_event(gamma_parent_market, [grouped_market]),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async def run() -> list[EventProbability]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_markets(client=client, max_pages=1)

    rows = asyncio.run(run())

    assert len(rows) == 2
    standalone = next(row for row in rows if row.slug == "standalone-market")
    assert standalone.event_id is None
    assert standalone.results == []
    grouped = next(row for row in rows if row.event_id is not None)
    assert grouped.event_id == "presidential-election-winner-2028"
    assert [child.label for child in grouped.results] == ["Candidate A"]


def test_polymarket_parent_end_date_overrides_child_end_date(
    gamma_parent_market: dict[str, object],
) -> None:
    market = nested_market(gamma_parent_market, market_id="dated-market")
    market["endDate"] = "2028-01-01"
    event = gamma_event(gamma_parent_market, [market])
    event["endDate"] = "2028-11-07"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[event])

    async def run() -> list[EventProbability]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_markets(client=client, max_pages=1)

    rows = asyncio.run(run())

    assert len(rows) == 1
    assert rows[0].end_date == "2028-11-07"


def test_polymarket_ignores_non_string_event_category(
    gamma_parent_market: dict[str, object],
) -> None:
    market = nested_market(gamma_parent_market, market_id="category-market")
    market.pop("category", None)
    event = gamma_event(gamma_parent_market, [market])
    event["category"] = {"name": "Politics"}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[event])

    async def run() -> list[EventProbability]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_markets(client=client, max_pages=1)

    rows = asyncio.run(run())

    assert len(rows) == 1
    assert rows[0].source_category is None


def test_polymarket_shape_ignores_non_string_native_category(
    gamma_parent_market: dict[str, object],
) -> None:
    market = dict(gamma_parent_market)
    market["category"] = {"name": "Politics"}

    row = shape_polymarket_market(market)

    assert row is not None
    assert row.source_category is None


def test_group_polymarket_events_deep_copies_results(
    gamma_parent_market: dict[str, object],
) -> None:
    row = shape_polymarket_market(gamma_parent_market)
    assert row is not None

    grouped = polymarket.group_polymarket_events([row])
    grouped[0].results[0].label_zh = "分组"

    assert row.results[0].label_zh is None
    row.results[0].label_zh = "原始"
    assert grouped[0].results[0].label_zh == "分组"


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
