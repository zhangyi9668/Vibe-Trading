import json
import os
from pathlib import Path

import pytest

from src.event_probability.models import EventProbability, ProbabilitySnapshot
from src.event_probability.storage import ProbabilityStorage


def sample_event(source: str = "polymarket") -> EventProbability:
    return EventProbability(
        question="Sample event",
        topic="other",
        prob_yes=0.5,
        source=source,
        slug="sample",
    )


def test_atomic_json_round_trip(tmp_path: Path) -> None:
    store = ProbabilityStorage(tmp_path)

    assert store.save_source("polymarket", [sample_event()]) is True
    assert store.load_source("polymarket")[0].slug == "sample"
    assert not list(tmp_path.glob("*.tmp"))


def test_empty_source_does_not_replace_good_snapshot(tmp_path: Path) -> None:
    store = ProbabilityStorage(tmp_path)
    store.save_source("kalshi", [sample_event(source="kalshi")])

    assert store.save_source("kalshi", []) is False
    assert len(store.load_source("kalshi")) == 1


def test_translation_cache_persists(tmp_path: Path) -> None:
    store = ProbabilityStorage(tmp_path)

    store.save_translation_cache({"Will X happen?": "X 会发生吗？"})

    assert store.load_translation_cache()["Will X happen?"] == "X 会发生吗？"


def test_overview_and_priority_series_round_trip(tmp_path: Path) -> None:
    store = ProbabilityStorage(tmp_path)
    snapshot = ProbabilitySnapshot(
        as_of="2026-06-14T00:00:00Z",
        events=[sample_event()],
    )

    store.save_overview(snapshot)
    store.save_priority_series(["KXFED", "KXCPI"])

    assert store.load_overview() == snapshot
    assert store.load_priority_series() == ["KXFED", "KXCPI"]


def test_corrupt_or_missing_files_return_empty_defaults(tmp_path: Path) -> None:
    store = ProbabilityStorage(tmp_path)
    (tmp_path / "translation_cache.json").write_text("{broken", encoding="utf-8")

    assert store.load_source("polymarket") == []
    assert store.load_overview() == ProbabilitySnapshot()
    assert store.load_translation_cache() == {}
    assert store.load_priority_series() == []


def test_written_json_is_utf8_and_human_readable(tmp_path: Path) -> None:
    store = ProbabilityStorage(tmp_path)
    store.save_translation_cache({"title": "中文标题"})

    payload = json.loads(
        (tmp_path / "translation_cache.json").read_text(encoding="utf-8")
    )

    assert payload == {"title": "中文标题"}


def test_source_name_and_event_source_are_validated(tmp_path: Path) -> None:
    store = ProbabilityStorage(tmp_path)

    with pytest.raises(ValueError, match="Unsupported source"):
        store.save_source("../escaped", [sample_event()])  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="does not match"):
        store.save_source("kalshi", [sample_event()])


def test_source_load_skips_individual_invalid_rows(tmp_path: Path) -> None:
    store = ProbabilityStorage(tmp_path)
    (tmp_path / "polymarket_snapshot.json").write_text(
        json.dumps([sample_event().model_dump(mode="json"), {"broken": True}]),
        encoding="utf-8",
    )

    rows = store.load_source("polymarket")

    assert [row.slug for row in rows] == ["sample"]


def test_transient_windows_replace_error_is_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ProbabilityStorage(tmp_path)
    real_replace = os.replace
    attempts = 0

    def flaky_replace(source: Path, target: Path) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            error = OSError("sharing violation")
            error.winerror = 32  # type: ignore[attr-defined]
            raise error
        real_replace(source, target)

    monkeypatch.setattr("src.event_probability.storage.os.replace", flaky_replace)
    monkeypatch.setattr("src.event_probability.storage.time.sleep", lambda _: None)

    store.save_translation_cache({"title": "标题"})

    assert attempts == 2
    assert store.load_translation_cache() == {"title": "标题"}
