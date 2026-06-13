from src.event_probability import EventProbability, RefreshState, SourceStatus


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
