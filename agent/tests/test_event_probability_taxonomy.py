import pytest

from src.event_probability.models import EventProbability
from src.event_probability.taxonomy import classify, limit_by_topic


def test_high_signal_topics_win_before_generic_terms() -> None:
    assert classify("Will Israel and Iran agree to a ceasefire?") == "geopolitics"
    assert classify("Will the Fed cut rates in September?") == "monetary_policy"
    assert classify("Will US CPI exceed 3 percent?") == "macro_economy"
    assert classify("Will OpenAI release a new model?") == "ai_technology"


def test_ordered_topics_resolve_overlapping_terms() -> None:
    assert classify("Will Bitcoin lead the crypto index?") == "crypto"
    assert classify("Will the Fed change its inflation target?") == "monetary_policy"


def test_kalshi_category_is_a_fallback() -> None:
    assert classify("A neutral title", "Economics") == "macro_economy"
    assert classify("A neutral title", "Science and Technology") == "ai_technology"


def test_keyword_matching_respects_word_boundaries() -> None:
    assert classify("Will Golden State Warriors win the championship?") == "sports"
    assert classify("Will Ex Machina win best movie?") == "entertainment"
    assert classify("Will the devoted candidate appear?") == "other"


def test_topic_caps_keep_highest_volume_rows_in_topic_order() -> None:
    geopolitics = [
        EventProbability(
            question=f"geo-{index}",
            topic="geopolitics",
            prob_yes=0.5,
            source="polymarket",
            slug=f"geo-{index}",
            volume_24h=float(index),
        )
        for index in range(20)
    ]
    monetary = EventProbability(
        question="rates",
        topic="monetary_policy",
        prob_yes=0.5,
        source="kalshi",
        slug="rates",
        volume_24h=1.0,
    )

    limited = limit_by_topic(geopolitics + [monetary], {"geopolitics": 3})

    assert limited[0] == monetary
    assert [row.volume_24h for row in limited[1:]] == [19.0, 18.0, 17.0]


def test_unknown_topics_are_kept_in_other() -> None:
    row = EventProbability(
        question="unknown",
        topic="custom_topic",
        source="polymarket",
        slug="unknown",
    )

    assert limit_by_topic([row]) == [row]


def test_topic_caps_reject_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="Unknown topic cap"):
        limit_by_topic([], {"typo": 1})

    with pytest.raises(ValueError, match="non-negative integer"):
        limit_by_topic([], {"sports": -1})

    assert limit_by_topic([], {"sports": 0}) == []
