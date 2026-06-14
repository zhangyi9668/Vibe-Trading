import json
from collections.abc import Sequence
from typing import Any

import httpx

from .models import EventProbability
from .taxonomy import classify


MARKETS_URL = "https://gamma-api.polymarket.com/markets"
HISTORY_URL = "https://clob.polymarket.com/prices-history"
REQUEST_TIMEOUT = 15.0


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return parsed
    raise ValueError("Expected a JSON array")


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def shape_polymarket_market(data: dict[str, Any]) -> EventProbability | None:
    try:
        question = str(data["question"]).strip()
        slug = str(data["slug"]).strip()
        outcomes = [str(value) for value in _json_list(data["outcomes"])]
        prices = [_float(value) for value in _json_list(data["outcomePrices"])]
        token_ids = [str(value) for value in _json_list(data["clobTokenIds"])]
        if not question or not slug or not outcomes:
            return None

        yes_index = next(
            (index for index, label in enumerate(outcomes) if label.casefold() == "yes"),
            0,
        )
        prob_yes = prices[yes_index] if yes_index < len(prices) else None
        token_id_yes = token_ids[yes_index] if yes_index < len(token_ids) else None

        return EventProbability(
            question=question,
            topic=classify(question, data.get("category")),
            outcomes=outcomes,
            prices=prices,
            prob_yes=prob_yes,
            change_24h=_float(data.get("oneDayPriceChange")),
            change_7d=_float(data.get("oneWeekPriceChange")),
            volume_24h=_float(data.get("volume24hr")) or 0.0,
            liquidity=_float(data.get("liquidityNum", data.get("liquidity"))) or 0.0,
            end_date=data.get("endDate"),
            slug=slug,
            token_id_yes=token_id_yes,
            source="polymarket",
            source_category=data.get("category"),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


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
    try:
        for page in range(max_pages):
            response = await _get_with_retry(
                active_client,
                MARKETS_URL,
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
            for item in payload:
                if isinstance(item, dict):
                    shaped = shape_polymarket_market(item)
                    if shaped is not None:
                        rows.append(shaped)
            if len(payload) < 100:
                break
    finally:
        if owns_client:
            await active_client.aclose()
    return rows


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
