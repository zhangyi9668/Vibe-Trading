import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.event_probability.models import EventProbability, EventProbabilityResult
from src.event_probability.storage import ProbabilityStorage
from src.event_probability.translation import (
    TitleTranslator,
    _parse_translation_response,
)
from src.providers.openai_codex import DEFAULT_EVENT_TRANSLATION_MODEL


def event(
    question: str,
    labels: list[str] | None = None,
) -> EventProbability:
    return EventProbability(
        question=question,
        topic="other",
        source="polymarket",
        slug=question,
        results=[
            EventProbabilityResult(label=label)
            for label in labels or []
        ],
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


def test_translation_targets_parent_then_child_labels_in_display_order(
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []

    async def fake_translate(titles: list[str]) -> dict[str, str]:
        calls.append(titles)
        return {title: f"中文:{title}" for title in titles}

    row = event("Parent", ["First child", "Second child"])
    translator = TitleTranslator(
        ProbabilityStorage(tmp_path),
        translate_batch=fake_translate,
        sleep=lambda _: async_noop(),
    )

    stats = asyncio.run(translator.translate([row], limit=3, batch_delay=0))

    assert calls == [["Parent", "First child", "Second child"]]
    assert row.question_zh == "中文:Parent"
    assert [result.label_zh for result in row.results] == [
        "中文:First child",
        "中文:Second child",
    ]
    assert stats.new_translations == 3


def test_translation_deduplicates_repeated_child_labels(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    async def fake_translate(titles: list[str]) -> dict[str, str]:
        calls.append(titles)
        return {title: f"中文:{title}" for title in titles}

    row = event("Parent", ["Same child", "Same child"])
    translator = TitleTranslator(
        ProbabilityStorage(tmp_path),
        translate_batch=fake_translate,
        sleep=lambda _: async_noop(),
    )

    asyncio.run(translator.translate([row], limit=2, batch_delay=0))

    assert calls == [["Parent", "Same child"]]
    assert [result.label_zh for result in row.results] == [
        "中文:Same child",
        "中文:Same child",
    ]


def test_translation_cache_applies_to_parent_and_child_labels(tmp_path: Path) -> None:
    store = ProbabilityStorage(tmp_path)
    store.save_translation_cache({
        "Cached parent": "缓存父标题",
        "Cached child": "缓存结果",
    })
    row = event("Cached parent", ["Cached child"])
    translator = TitleTranslator(
        store,
        translate_batch=lambda _: async_noop(),  # type: ignore[arg-type]
        sleep=lambda _: async_noop(),
    )

    stats = asyncio.run(translator.translate([row], limit=0, batch_delay=0))

    assert row.question_zh == "缓存父标题"
    assert row.results[0].label_zh == "缓存结果"
    assert stats.cache_hits == 2
    assert stats.pending == 0


def test_translation_limit_counts_unique_parent_and_child_texts(
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []

    async def fake_translate(titles: list[str]) -> dict[str, str]:
        calls.append(titles)
        return {title: f"中文:{title}" for title in titles}

    row = event("Parent", ["First child", "Second child"])
    translator = TitleTranslator(
        ProbabilityStorage(tmp_path),
        translate_batch=fake_translate,
        sleep=lambda _: async_noop(),
    )

    stats = asyncio.run(translator.translate([row], limit=2, batch_delay=0))

    assert calls == [["Parent", "First child"]]
    assert row.question_zh == "中文:Parent"
    assert row.results[0].label_zh == "中文:First child"
    assert row.results[1].label_zh is None
    assert stats.new_translations == 2
    assert stats.pending == 1


def test_translation_assigns_same_label_to_results_across_events(
    tmp_path: Path,
) -> None:
    async def fake_translate(titles: list[str]) -> dict[str, str]:
        return {title: f"中文:{title}" for title in titles}

    rows = [
        event("First parent", ["Shared label"]),
        event("Second parent", ["Shared label"]),
    ]
    translator = TitleTranslator(
        ProbabilityStorage(tmp_path),
        translate_batch=fake_translate,
        sleep=lambda _: async_noop(),
    )

    stats = asyncio.run(translator.translate(rows, limit=3, batch_delay=0))

    assert rows[0].results[0].label_zh == "中文:Shared label"
    assert rows[1].results[0].label_zh == "中文:Shared label"
    assert stats.new_translations == 3


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


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ('{"One": "一", "Two": "二"}', {"One": "一", "Two": "二"}),
        (
            '```json\n{"One": "一", "Two": "二"}\n```',
            {"One": "一", "Two": "二"},
        ),
    ],
)
def test_parse_translation_response_accepts_json_object_and_json_fence(
    content: str,
    expected: dict[str, str],
) -> None:
    assert _parse_translation_response(content, ["One", "Two"]) == expected


def test_parse_translation_response_filters_unrequested_or_non_string_values() -> None:
    content = '{"One": "一", "Other": "忽略", "Two": 2}'

    assert _parse_translation_response(content, ["One", "Two"]) == {"One": "一"}


def test_parse_translation_response_rejects_prose_wrapped_json() -> None:
    content = 'Translation:\n```json\n{"One": "一"}\n```'

    assert _parse_translation_response(content, ["One"]) == {}


def test_default_translation_batch_uses_dedicated_codex_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models: list[str | None] = []
    providers: list[str | None] = []

    class FakeChatLLM:
        def __init__(
            self,
            model_name: str | None = None,
            provider: str | None = None,
        ) -> None:
            models.append(model_name)
            providers.append(provider)

        def chat(self, *args: object, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(content='{"Title": "标题"}')

    monkeypatch.setattr(
        "src.event_probability.translation.ChatLLM",
        FakeChatLLM,
    )

    translated = asyncio.run(TitleTranslator._default_translate_batch(["Title"]))

    assert translated == {"Title": "标题"}
    assert models == [DEFAULT_EVENT_TRANSLATION_MODEL]
    assert providers == ["openai-codex"]
