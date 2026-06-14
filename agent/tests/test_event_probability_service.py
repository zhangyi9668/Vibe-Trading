import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

from src.event_probability.models import (
    EventProbability,
    ProbabilitySnapshot,
    TranslationStats,
)
from src.event_probability.service import EventProbabilityService
from src.event_probability.storage import ProbabilityStorage


def event(
    question: str,
    *,
    source: str = "polymarket",
    series_ticker: str | None = None,
) -> EventProbability:
    return EventProbability(
        question=question,
        topic="macro_economy",
        prob_yes=0.5,
        source=source,
        slug=f"{source}-{question}",
        series_ticker=series_ticker,
        volume_24h=100.0,
    )


class SpyTranslator:
    def __init__(self) -> None:
        self.limits: list[int] = []

    async def translate(
        self,
        rows: list[EventProbability],
        *,
        limit: int,
        batch_size: int = 4,
        batch_delay: float = 1.0,
    ) -> TranslationStats:
        self.limits.append(limit)
        return TranslationStats()


def service_for(
    tmp_path: Path,
    *,
    polymarket_fetch: AsyncMock,
    kalshi_full_fetch: AsyncMock | None = None,
    kalshi_series_fetch: AsyncMock | None = None,
    translator: SpyTranslator | None = None,
) -> EventProbabilityService:
    return EventProbabilityService(
        storage=ProbabilityStorage(tmp_path),
        polymarket_fetch=polymarket_fetch,
        kalshi_full_fetch=kalshi_full_fetch or AsyncMock(return_value=[]),
        kalshi_series_fetch=kalshi_series_fetch or AsyncMock(return_value=[]),
        translator=translator or SpyTranslator(),
    )


def test_overview_returns_snapshot_without_network(tmp_path: Path) -> None:
    store = ProbabilityStorage(tmp_path)
    store.save_overview(ProbabilitySnapshot(events=[event("cached")]))
    service = EventProbabilityService(
        storage=store,
        polymarket_fetch=AsyncMock(side_effect=AssertionError("network called")),
        kalshi_full_fetch=AsyncMock(side_effect=AssertionError("network called")),
        kalshi_series_fetch=AsyncMock(side_effect=AssertionError("network called")),
        translator=SpyTranslator(),
    )

    assert service.get_overview().events[0].question == "cached"


def test_quick_refresh_uses_discovered_series_and_limit_30(tmp_path: Path) -> None:
    store = ProbabilityStorage(tmp_path)
    store.save_priority_series(["KXCPI", "KXJOBS"])
    translator = SpyTranslator()
    series_fetch = AsyncMock(return_value=[event("kalshi", source="kalshi")])
    service = EventProbabilityService(
        storage=store,
        polymarket_fetch=AsyncMock(return_value=[event("poly")]),
        kalshi_full_fetch=AsyncMock(),
        kalshi_series_fetch=series_fetch,
        translator=translator,
    )

    asyncio.run(service._run_refresh("quick"))

    series = series_fetch.await_args.args[0]
    assert set(series) == {"KXFED", "KXCPI", "KXJOBS"}
    assert translator.limits == [30]
    assert service.get_refresh_state().status == "done"


def test_full_refresh_discovers_series_and_uses_limit_100(tmp_path: Path) -> None:
    store = ProbabilityStorage(tmp_path)
    translator = SpyTranslator()
    full_rows = [event("cpi", source="kalshi", series_ticker="KXCPI")]
    full_fetch = AsyncMock(return_value=full_rows)
    service = EventProbabilityService(
        storage=store,
        polymarket_fetch=AsyncMock(return_value=[]),
        kalshi_full_fetch=full_fetch,
        kalshi_series_fetch=AsyncMock(),
        translator=translator,
    )

    asyncio.run(service._run_refresh("full"))

    assert "KXCPI" in store.load_priority_series()
    assert translator.limits == [100]
    assert full_fetch.await_args.kwargs["on_progress"] is not None


def test_source_failure_keeps_previous_snapshot(tmp_path: Path) -> None:
    store = ProbabilityStorage(tmp_path)
    store.save_source("polymarket", [event("old")])
    service = EventProbabilityService(
        storage=store,
        polymarket_fetch=AsyncMock(side_effect=RuntimeError("down")),
        kalshi_full_fetch=AsyncMock(),
        kalshi_series_fetch=AsyncMock(return_value=[]),
        translator=SpyTranslator(),
    )

    asyncio.run(service._run_refresh("quick"))

    assert store.load_source("polymarket")[0].question == "old"
    snapshot = service.get_overview()
    polymarket_status = next(
        status for status in snapshot.sources if status.source == "polymarket"
    )
    assert polymarket_status.status == "error"
    assert snapshot.events[0].question == "old"


def test_empty_source_keeps_previous_snapshot_and_marks_stale(tmp_path: Path) -> None:
    store = ProbabilityStorage(tmp_path)
    store.save_source("kalshi", [event("old", source="kalshi")])
    service = service_for(
        tmp_path,
        polymarket_fetch=AsyncMock(return_value=[]),
        kalshi_series_fetch=AsyncMock(return_value=[]),
    )

    asyncio.run(service._run_refresh("quick"))

    snapshot = service.get_overview()
    kalshi_status = next(
        status for status in snapshot.sources if status.source == "kalshi"
    )
    assert kalshi_status.status == "stale"
    assert any(row.question == "old" for row in snapshot.events)


def test_second_refresh_reuses_running_task(tmp_path: Path) -> None:
    async def scenario() -> None:
        gate = asyncio.Event()

        async def blocked_fetch() -> list[EventProbability]:
            await gate.wait()
            return [event("poly")]

        service = service_for(
            tmp_path,
            polymarket_fetch=AsyncMock(side_effect=blocked_fetch),
        )
        first = await service.start_refresh("quick")
        second = await service.start_refresh("full")

        assert first.status == "queued"
        assert second.kind == "quick"
        gate.set()
        assert service._refresh_task is not None
        await service._refresh_task

    asyncio.run(scenario())
