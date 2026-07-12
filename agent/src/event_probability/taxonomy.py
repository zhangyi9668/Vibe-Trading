from collections.abc import Mapping, Sequence
import re

from .models import EventProbability


TOPIC_ORDER = (
    "monetary_policy",
    "macro_economy",
    "geopolitics",
    "political_elections",
    "indices_commodities",
    "ai_technology",
    "crypto",
    "sports",
    "entertainment",
    "other",
)

MODULE_CAPS = {
    "monetary_policy": 8,
    "macro_economy": 8,
    "geopolitics": 8,
    "political_elections": 8,
    "indices_commodities": 8,
    "ai_technology": 8,
    "crypto": 8,
    "sports": 8,
    "entertainment": 8,
    "other": 8,
}

_KEYWORD_GROUPS = (
    (
        "geopolitics",
        (
            "ceasefire",
            "war",
            "invasion",
            "military",
            "missile",
            "nuclear",
            "sanction",
            "israel",
            "iran",
            "ukraine",
            "russia",
            "china",
            "taiwan",
            "nato",
        ),
    ),
    (
        "political_elections",
        (
            "election",
            "president",
            "prime minister",
            "congress",
            "senate",
            "governor",
            "vote",
            "polling",
        ),
    ),
    (
        "crypto",
        (
            "bitcoin",
            "ethereum",
            "crypto",
            "blockchain",
            "stablecoin",
            "solana",
            "dogecoin",
        ),
    ),
    (
        "indices_commodities",
        (
            "s&p",
            "nasdaq",
            "dow jones",
            "index",
            "gold",
            "silver",
            "oil",
            "commodity",
            "gas price",
        ),
    ),
    (
        "monetary_policy",
        (
            "federal reserve",
            "the fed",
            "fed",
            "interest rate",
            "rate cut",
            "rate hike",
            "fomc",
            "central bank",
            "inflation target",
        ),
    ),
    (
        "macro_economy",
        (
            "cpi",
            "inflation",
            "gdp",
            "unemployment",
            "jobs report",
            "recession",
            "economy",
            "economic",
            "payroll",
        ),
    ),
    (
        "ai_technology",
        (
            "artificial intelligence",
            "openai",
            "chatgpt",
            "anthropic",
            "nvidia",
            "ai model",
            "technology",
        ),
    ),
    (
        "sports",
        (
            "nba",
            "nfl",
            "mlb",
            "nhl",
            "world cup",
            "championship",
            "tournament",
        ),
    ),
    (
        "entertainment",
        (
            "oscar",
            "grammy",
            "box office",
            "album",
            "movie",
            "television",
            "celebrity",
        ),
    ),
)

_CATEGORY_TOPICS = {
    "economics": "macro_economy",
    "financials": "indices_commodities",
    "commodities": "indices_commodities",
    "elections": "political_elections",
    "politics": "political_elections",
    "world": "geopolitics",
    "crypto": "crypto",
    "sports": "sports",
    "entertainment": "entertainment",
    "science and technology": "ai_technology",
}


def classify(title: str, native_category: str | None = None) -> str:
    normalized_title = title.lower()
    for topic, keywords in _KEYWORD_GROUPS:
        if any(_contains_keyword(normalized_title, keyword) for keyword in keywords):
            return topic

    if native_category:
        return _CATEGORY_TOPICS.get(native_category.strip().lower(), "other")
    return "other"


def _contains_keyword(title: str, keyword: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", title) is not None


def limit_by_topic(
    rows: Sequence[EventProbability],
    caps: Mapping[str, int] | None = None,
) -> list[EventProbability]:
    overrides = dict(caps or {})
    unknown_caps = overrides.keys() - MODULE_CAPS.keys()
    if unknown_caps:
        raise ValueError(f"Unknown topic cap: {sorted(unknown_caps)[0]}")
    if any(type(cap) is not int or cap < 0 for cap in overrides.values()):
        raise ValueError("Topic caps must be a non-negative integer")

    effective_caps = MODULE_CAPS | overrides
    grouped = {topic: [] for topic in TOPIC_ORDER}
    for row in rows:
        topic = row.topic if row.topic in grouped else "other"
        grouped[topic].append(row)

    limited: list[EventProbability] = []
    for topic in TOPIC_ORDER:
        ranked = sorted(
            grouped[topic],
            key=lambda row: row.volume_24h,
            reverse=True,
        )
        limited.extend(ranked[: effective_caps[topic]])
    return limited
