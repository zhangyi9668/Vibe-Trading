import asyncio
from collections import defaultdict
from collections.abc import Callable, Sequence
from typing import Any

import httpx

from .models import EventProbability
from .taxonomy import classify


EVENTS_URL = "https://api.elections.kalshi.com/trade-api/v2/events"
MARKETS_URL = "https://api.elections.kalshi.com/trade-api/v2/markets"
REQUEST_TIMEOUT = 15.0
CORE_TOPICS = {
    "monetary_policy",
    "macro_economy",
    "geopolitics",
    "political_elections",
    "indices_commodities",
    "ai_technology",
}


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _market_probability(market: dict[str, Any]) -> float | None:
    for field in ("yes_ask_dollars", "last_price_dollars", "yes_bid_dollars"):
        probability = _float(market.get(field))
        if probability is not None:
            return probability
    return None


def shape_kalshi_event(data: dict[str, Any]) -> EventProbability | None:
    try:
        title = str(data["title"]).strip()
        event_ticker = str(data["event_ticker"]).strip()
        markets = data.get("markets", [])
        if not title or not event_ticker or not isinstance(markets, list):
            return None

        priced_markets = [
            (market, probability)
            for market in markets
            if isinstance(market, dict)
            and (probability := _market_probability(market)) is not None
        ]
        if not priced_markets:
            return None

        selected, probability = min(
            priced_markets,
            key=lambda item: abs(item[1] - 0.5),
        )
        pick_label = (
            selected.get("yes_sub_title")
            or selected.get("subtitle")
            or selected.get("title")
            or "Yes"
        )
        volume_24h = sum(
            _float(market.get("volume_24h_fp")) or 0.0
            for market in markets
            if isinstance(market, dict)
        )
        liquidity = sum(
            _float(market.get("liquidity_dollars")) or 0.0
            for market in markets
            if isinstance(market, dict)
        )
        category = data.get("category")
        series_ticker = data.get("series_ticker") or selected.get("series_ticker")

        return EventProbability(
            question=title,
            topic=classify(title, category),
            outcomes=[str(pick_label), "No"],
            prices=[probability, 1.0 - probability],
            prob_yes=probability,
            pick_label=str(pick_label),
            volume_24h=volume_24h,
            liquidity=liquidity,
            end_date=selected.get("close_time") or data.get("close_time"),
            slug=event_ticker,
            series_ticker=str(series_ticker) if series_ticker else None,
            source="kalshi",
            source_category=str(category) if category else None,
        )
    except (KeyError, TypeError, ValueError):
        return None


async def fetch_full(
    *,
    client: httpx.AsyncClient | None = None,
    max_pages: int = 30,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[EventProbability]:
    if max_pages < 0:
        raise ValueError("max_pages must be non-negative")

    owns_client = client is None
    active_client = client or httpx.AsyncClient()
    cursor: str | None = None
    rows: list[EventProbability] = []
    try:
        for page in range(max_pages):
            params: dict[str, Any] = {
                "limit": 200,
                "status": "open",
                "with_nested_markets": "true",
            }
            if cursor:
                params["cursor"] = cursor
            response = await active_client.get(
                EVENTS_URL,
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            events = payload.get("events", []) if isinstance(payload, dict) else []
            for event in events:
                if isinstance(event, dict):
                    shaped = shape_kalshi_event(event)
                    if shaped is not None:
                        rows.append(shaped)
            if on_progress:
                on_progress(page + 1, max_pages)
            cursor = payload.get("cursor") if isinstance(payload, dict) else None
            if not cursor:
                break
    finally:
        if owns_client:
            await active_client.aclose()
    return rows


def _group_markets(
    markets: Sequence[dict[str, Any]],
    *,
    series_ticker: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for market in markets:
        ticker = market.get("event_ticker")
        if ticker:
            grouped[str(ticker)].append(market)

    events: list[dict[str, Any]] = []
    for event_ticker, event_markets in grouped.items():
        first = event_markets[0]
        events.append(
            {
                "title": first.get("event_title") or first.get("title") or event_ticker,
                "event_ticker": event_ticker,
                "category": first.get("category"),
                "series_ticker": first.get("series_ticker") or series_ticker,
                "markets": event_markets,
            }
        )
    return events


async def fetch_series(
    series_tickers: Sequence[str],
    *,
    client: httpx.AsyncClient | None = None,
    concurrency: int = 6,
) -> list[EventProbability]:
    if concurrency < 1:
        raise ValueError("concurrency must be positive")

    owns_client = client is None
    active_client = client or httpx.AsyncClient()
    semaphore = asyncio.Semaphore(concurrency)

    async def fetch_one(series_ticker: str) -> list[EventProbability]:
        cursor: str | None = None
        markets: list[dict[str, Any]] = []
        while True:
            params: dict[str, Any] = {
                    "limit": 200,
                    "status": "open",
                    "series_ticker": series_ticker,
            }
            if cursor:
                params["cursor"] = cursor
            async with semaphore:
                response = await active_client.get(
                    MARKETS_URL,
                    params=params,
                    timeout=REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                payload = response.json()
            page_markets = (
                payload.get("markets", []) if isinstance(payload, dict) else []
            )
            markets.extend(
                market for market in page_markets if isinstance(market, dict)
            )
            cursor = payload.get("cursor") if isinstance(payload, dict) else None
            if not cursor:
                break

        events = _group_markets(markets, series_ticker=series_ticker)
        return [
            shaped
            for event in events
            if (shaped := shape_kalshi_event(event)) is not None
        ]

    try:
        results = await asyncio.gather(
            *(fetch_one(ticker) for ticker in dict.fromkeys(series_tickers)),
            return_exceptions=True,
        )
    finally:
        if owns_client:
            await active_client.aclose()
    batches = [result for result in results if isinstance(result, list)]
    return [row for batch in batches for row in batch]


def discover_priority_series(
    events: Sequence[EventProbability],
    limit: int = 24,
) -> list[str]:
    if limit < 0:
        raise ValueError("limit must be non-negative")

    volumes: dict[str, float] = defaultdict(float)
    for event in events:
        if event.topic in CORE_TOPICS and event.series_ticker:
            volumes[event.series_ticker] += event.volume_24h

    ranked = sorted(volumes, key=lambda ticker: (-volumes[ticker], ticker))
    return list(dict.fromkeys(["KXFED", *ranked]))[:limit]
