import asyncio
import json
import math
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

import httpx

from .models import (
    EventProbability,
    EventProbabilityResult,
    ProbabilityHistorySeries,
    ProbabilityHistorySeriesRequest,
)
from .taxonomy import classify


EVENTS_URL = "https://gamma-api.polymarket.com/events"
HISTORY_URL = "https://clob.polymarket.com/prices-history"
REQUEST_TIMEOUT = 15.0
HISTORY_UNAVAILABLE_ERROR = "history unavailable"


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return parsed
    raise ValueError("Expected a JSON array")


def _finite_float(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _probability(value: Any) -> float | None:
    parsed = _finite_float(value)
    if parsed is None or not 0 <= parsed <= 1:
        return None
    return parsed


def _non_negative(value: Any) -> float:
    parsed = _finite_float(value)
    return parsed if parsed is not None and parsed >= 0 else 0.0


def _category(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def shape_polymarket_market(data: dict[str, Any]) -> EventProbability | None:
    try:
        question = str(data["question"]).strip()
        slug = str(data["slug"]).strip()
        category = _category(data.get("category"))
        outcomes = [str(value) for value in _json_list(data["outcomes"])]
        prices = [_probability(value) for value in _json_list(data["outcomePrices"])]
        token_ids = [str(value) for value in _json_list(data["clobTokenIds"])]
        if not question or not slug or not outcomes:
            return None

        yes_index = next(
            (
                index
                for index, label in enumerate(outcomes)
                if label.casefold() == "yes"
            ),
            None,
        )
        prob_yes = (
            prices[yes_index]
            if yes_index is not None and yes_index < len(prices)
            else None
        )
        token_id_yes = (
            token_ids[yes_index]
            if yes_index is not None and yes_index < len(token_ids)
            else None
        )

        row = EventProbability(
            question=question,
            topic=classify(question, category),
            outcomes=outcomes,
            prices=prices,
            prob_yes=prob_yes,
            change_24h=_finite_float(data.get("oneDayPriceChange")),
            change_7d=_finite_float(data.get("oneWeekPriceChange")),
            volume_24h=_non_negative(data.get("volume24hr")),
            liquidity=_non_negative(
                data.get("liquidityNum", data.get("liquidity"))
            ),
            end_date=data.get("endDate"),
            slug=slug,
            token_id_yes=token_id_yes,
            source="polymarket",
            source_category=category,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None

    try:
        events = data.get("events")
        if not isinstance(events, list) or not events:
            return row
        parent = events[0]
        if not isinstance(parent, dict):
            return row

        parent_id_value = parent["id"]
        if isinstance(parent_id_value, bool) or not isinstance(
            parent_id_value, (str, int)
        ):
            return row
        parent_id = str(parent_id_value).strip()
        parent_title = parent["title"]
        parent_slug = parent["slug"]
        if not isinstance(parent_title, str) or not isinstance(parent_slug, str):
            return row
        parent_title = parent_title.strip()
        parent_slug = parent_slug.strip()
        if not parent_id or not parent_title or not parent_slug:
            return row

        label_value = data.get("groupItemTitle")
        label = (
            label_value.strip()
            if isinstance(label_value, str) and label_value.strip()
            else question
        )
        return row.model_copy(
            update={
                "question": parent_title,
                "topic": classify(parent_title, category),
                "event_id": parent_id,
                "results": [
                    EventProbabilityResult(
                        label=label,
                        probability=row.prob_yes,
                        change_24h=row.change_24h,
                        volume_24h=row.volume_24h,
                        token_id=row.token_id_yes,
                    )
                ],
                "slug": parent_slug,
            }
        )
    except (KeyError, TypeError, ValueError):
        return row


def group_polymarket_events(
    rows: Sequence[EventProbability],
) -> list[EventProbability]:
    grouped: dict[str, list[EventProbability]] = {}
    ordered: list[str | EventProbability] = []
    for row in rows:
        if row.event_id is None:
            ordered.append(row)
            continue
        if row.event_id not in grouped:
            grouped[row.event_id] = []
            ordered.append(row.event_id)
        grouped[row.event_id].append(row)

    result: list[EventProbability] = []
    for item in ordered:
        if isinstance(item, EventProbability):
            result.append(item)
            continue

        legs = grouped[item]
        ranked_legs = sorted(
            legs,
            key=lambda row: (
                row.results[0].volume_24h if row.results else row.volume_24h
            ),
            reverse=True,
        )
        representative = ranked_legs[0]
        ranked_children = sorted(
            [
                child.model_copy(deep=True)
                for row in legs
                for child in row.results
            ],
            key=lambda child: child.volume_24h,
            reverse=True,
        )
        top_child = ranked_children[0] if ranked_children else None
        result.append(
            representative.model_copy(
                update={
                    "results": ranked_children[:5],
                    "prob_yes": (
                        top_child.probability
                        if top_child is not None
                        else representative.prob_yes
                    ),
                    "change_24h": (
                        top_child.change_24h
                        if top_child is not None
                        else representative.change_24h
                    ),
                    "volume_24h": sum(row.volume_24h for row in legs),
                    "liquidity": sum(row.liquidity for row in legs),
                    "token_id_yes": (
                        top_child.token_id
                        if top_child is not None
                        else representative.token_id_yes
                    ),
                }
            )
        )
    return result


async def _get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any],
) -> httpx.Response:
    last_error: httpx.HTTPError | None = None
    for _ in range(2):
        try:
            response = await client.get(url, params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


async def fetch_markets(
    *,
    client: httpx.AsyncClient | None = None,
    max_pages: int = 4,
) -> list[EventProbability]:
    if max_pages < 0:
        raise ValueError("max_pages must be non-negative")

    owns_client = client is None
    active_client = client or httpx.AsyncClient()
    rows: list[EventProbability] = []
    seen_market_ids: set[str] = set()
    seen_market_slugs: set[str] = set()
    try:
        for page in range(max_pages):
            response = await _get_with_retry(
                active_client,
                EVENTS_URL,
                params={
                    "active": "true",
                    "closed": "false",
                    "limit": 100,
                    "offset": page * 100,
                    "order": "volume24hr",
                    "ascending": "false",
                },
            )
            payload = response.json()
            if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
                break
            for event in payload:
                if not isinstance(event, dict):
                    continue
                event_id = event.get("id")
                title = event.get("title")
                slug = event.get("slug")
                markets = event.get("markets")
                if not isinstance(markets, list):
                    continue

                reliable_parent = (
                    not isinstance(event_id, bool)
                    and isinstance(event_id, (str, int))
                    and bool(str(event_id).strip())
                    and isinstance(title, str)
                    and bool(title.strip())
                    and isinstance(slug, str)
                    and bool(slug.strip())
                )
                for market in markets:
                    if not isinstance(market, dict):
                        continue
                    market_data = dict(market)
                    if reliable_parent:
                        market_data["events"] = [
                            {
                                "id": event_id,
                                "title": title,
                                "slug": slug,
                            }
                        ]
                        event_end_date = event.get("endDate")
                        if isinstance(event_end_date, str) and event_end_date.strip():
                            market_data["endDate"] = event_end_date
                    event_category = _category(event.get("category"))
                    if "category" not in market_data and event_category is not None:
                        market_data["category"] = event_category
                    shaped = shape_polymarket_market(market_data)
                    if shaped is None:
                        continue

                    market_id = market.get("id")
                    normalized_id = (
                        str(market_id).strip()
                        if (
                            not isinstance(market_id, bool)
                            and isinstance(market_id, (str, int))
                            and str(market_id).strip()
                        )
                        else None
                    )
                    market_slug = market.get("slug")
                    normalized_slug = (
                        market_slug.strip()
                        if isinstance(market_slug, str) and market_slug.strip()
                        else None
                    )
                    if normalized_id is None and normalized_slug is None:
                        continue
                    if (
                        normalized_id is not None
                        and normalized_id in seen_market_ids
                    ) or (
                        normalized_slug is not None
                        and normalized_slug in seen_market_slugs
                    ):
                        continue
                    if normalized_id is not None:
                        seen_market_ids.add(normalized_id)
                    if normalized_slug is not None:
                        seen_market_slugs.add(normalized_slug)
                    rows.append(shaped)
            if len(payload) < 100:
                break
    finally:
        if owns_client:
            await active_client.aclose()
    return group_polymarket_events(rows)


async def fetch_history(
    token_id: str,
    *,
    interval: str = "1w",
    fidelity: int = 720,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, float | int]]:
    owns_client = client is None
    active_client = client or httpx.AsyncClient()
    try:
        response = await _get_with_retry(
            active_client,
            HISTORY_URL,
            params={
                "market": token_id,
                "interval": interval,
                "fidelity": fidelity,
            },
        )
        payload = response.json()
    finally:
        if owns_client:
            await active_client.aclose()

    history = payload.get("history", []) if isinstance(payload, dict) else []
    return [
        {"t": int(point["t"]), "p": float(point["p"])}
        for point in history
        if isinstance(point, dict) and "t" in point and "p" in point
    ]


async def fetch_histories(
    series: Sequence[ProbabilityHistorySeriesRequest],
    history_fetch: Callable[
        [str], Awaitable[list[dict[str, float | int]]]
    ] = fetch_history,
) -> list[ProbabilityHistorySeries]:
    if not 1 <= len(series) <= 5:
        raise ValueError("series count must be 1..5")

    async def fetch_one(
        item: ProbabilityHistorySeriesRequest,
    ) -> ProbabilityHistorySeries:
        try:
            points = await history_fetch(item.token_id)
        except Exception:
            return ProbabilityHistorySeries(
                label=item.label,
                token_id=item.token_id,
                error=HISTORY_UNAVAILABLE_ERROR,
            )
        return ProbabilityHistorySeries(
            label=item.label,
            token_id=item.token_id,
            points=points,
        )

    return await asyncio.gather(*(fetch_one(item) for item in series))
