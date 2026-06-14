import asyncio
from pathlib import Path

from src.event_probability.models import EventProbability
from src.event_probability.storage import ProbabilityStorage
from src.event_probability.translation import TitleTranslator


def event(question: str) -> EventProbability:
    return EventProbability(
        question=question,
        topic="other",
        source="polymarket",
        slug=question,
    )


async def async_noop() -> None:
    return None


def test_translation_uses_cache_batches_and_quota(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    async def fake_translate(titles: list[str]) -> dict[str, str]:
        calls.append(titles)
        return {title: f"中文:{title}" for title in titles}

    store = ProbabilityStorage(tmp_path)
    store.save_translation_cache({"cached": "已缓存"})
    translator = TitleTranslator(
        store,
        translate_batch=fake_translate,
        sleep=lambda _: async_noop(),
    )
    events = [event("cached")] + [event(f"new-{index}") for index in range(7)]

    stats = asyncio.run(
        translator.translate(events, limit=5, batch_size=4, batch_delay=0)
    )

    assert [len(batch) for batch in calls] == [4, 1]
    assert stats.new_translations == 5
    assert stats.cache_hits == 1
    assert stats.pending == 2
    assert events[0].question_zh == "已缓存"
    assert store.load_translation_cache()["new-4"] == "中文:new-4"


def test_translation_failure_preserves_english(tmp_path: Path) -> None:
    row = event("English")

    async def fail(_: list[str]) -> dict[str, str]:
        raise RuntimeError("provider down")

    translator = TitleTranslator(
        ProbabilityStorage(tmp_path),
        translate_batch=fail,
        sleep=lambda _: async_noop(),
    )

    stats = asyncio.run(translator.translate([row], limit=30, batch_delay=0))

    assert stats.new_translations == 0
    assert stats.pending == 1
    assert row.question_zh is None


def test_translation_deduplicates_titles_and_ignores_unknown_keys(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    async def fake_translate(titles: list[str]) -> dict[str, str]:
        calls.append(titles)
        return {titles[0]: "重复", "not-requested": "忽略"}

    rows = [event("duplicate"), event("duplicate")]
    translator = TitleTranslator(
        ProbabilityStorage(tmp_path),
        translate_batch=fake_translate,
        sleep=lambda _: async_noop(),
    )

    stats = asyncio.run(translator.translate(rows, limit=3, batch_delay=0))

    assert calls == [["duplicate"]]
    assert [row.question_zh for row in rows] == ["重复", "重复"]
    assert stats.new_translations == 1


def test_failed_batch_still_observes_batch_delay(tmp_path: Path) -> None:
    delays: list[float] = []

    async def fail(_: list[str]) -> dict[str, str]:
        raise RuntimeError("provider down")

    async def record_delay(delay: float) -> None:
        delays.append(delay)

    translator = TitleTranslator(
        ProbabilityStorage(tmp_path),
        translate_batch=fail,
        sleep=record_delay,
    )

    asyncio.run(
        translator.translate(
            [event("one"), event("two")],
            limit=2,
            batch_size=1,
            batch_delay=0.25,
        )
    )

    assert delays == [0.25]


def test_invalid_translator_result_does_not_interrupt_refresh(tmp_path: Path) -> None:
    async def invalid(_: list[str]) -> dict[str, str]:
        return None  # type: ignore[return-value]

    row = event("English")
    translator = TitleTranslator(
        ProbabilityStorage(tmp_path),
        translate_batch=invalid,
        sleep=lambda _: async_noop(),
    )

    stats = asyncio.run(translator.translate([row], limit=1, batch_delay=0))

    assert row.question_zh is None
    assert stats.pending == 1


def test_cache_write_failure_does_not_interrupt_refresh(
    tmp_path: Path,
    monkeypatch,
) -> None:
    async def translate(titles: list[str]) -> dict[str, str]:
        return {titles[0]: "中文"}

    store = ProbabilityStorage(tmp_path)
    monkeypatch.setattr(
        store,
        "save_translation_cache",
        lambda _: (_ for _ in ()).throw(OSError("disk full")),
    )
    row = event("English")
    translator = TitleTranslator(
        store,
        translate_batch=translate,
        sleep=lambda _: async_noop(),
    )

    stats = asyncio.run(translator.translate([row], limit=1, batch_delay=0))

    assert row.question_zh == "中文"
    assert stats.new_translations == 1


def test_empty_cached_translation_remains_pending(tmp_path: Path) -> None:
    store = ProbabilityStorage(tmp_path)
    store.save_translation_cache({"English": ""})
    row = event("English")
    translator = TitleTranslator(
        store,
        translate_batch=lambda _: async_noop(),  # type: ignore[arg-type]
        sleep=lambda _: async_noop(),
    )

    stats = asyncio.run(translator.translate([row], limit=0, batch_delay=0))

    assert row.question_zh is None
    assert stats.cache_hits == 0
    assert stats.pending == 1
