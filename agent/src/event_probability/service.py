import asyncio
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timezone
from typing import Literal

from .kalshi import (
    discover_priority_series,
    fetch_full,
    fetch_series,
)
from .models import (
    EventProbability,
    ProbabilitySnapshot,
    RefreshState,
    SourceStatus,
)
from .polymarket import fetch_history, fetch_markets
from .storage import ProbabilityStorage
from .taxonomy import classify, limit_by_topic
from .translation import TitleTranslator


RefreshKind = Literal["quick", "full"]
RowsFetcher = Callable[..., Awaitable[list[EventProbability]]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventProbabilityService:
    def __init__(
        self,
        *,
        storage: ProbabilityStorage | None = None,
        polymarket_fetch: RowsFetcher = fetch_markets,
        kalshi_full_fetch: RowsFetcher = fetch_full,
        kalshi_series_fetch: RowsFetcher = fetch_series,
        history_fetch: Callable[..., Awaitable[list[dict[str, float | int]]]] = (
            fetch_history
        ),
        translator: TitleTranslator | None = None,
    ) -> None:
        self.storage = storage or ProbabilityStorage()
        self.polymarket_fetch = polymarket_fetch
        self.kalshi_full_fetch = kalshi_full_fetch
        self.kalshi_series_fetch = kalshi_series_fetch
        self.history_fetch = history_fetch
        self.translator = translator or TitleTranslator(self.storage)
        self._start_lock = asyncio.Lock()
        self._refresh_task: asyncio.Task[None] | None = None
        self._state = self.storage.load_overview().refresh

    def get_overview(self) -> ProbabilitySnapshot:
        snapshot = self.storage.load_overview()
        snapshot.refresh = self._state.model_copy(deep=True)
        return snapshot

    def get_refresh_state(self) -> RefreshState:
        return self._state.model_copy(deep=True)

    async def start_refresh(self, kind: RefreshKind) -> RefreshState:
        async with self._start_lock:
            if self._refresh_task is not None and not self._refresh_task.done():
                return self.get_refresh_state()
            self._state = RefreshState(
                status="queued",
                kind=kind,
                stage="fetching_polymarket",
            )
            self._refresh_task = asyncio.create_task(self._run_refresh(kind))
            return self.get_refresh_state()

    async def get_history(self, token_id: str) -> list[dict[str, float | int]]:
        return await self.history_fetch(token_id)

    async def _run_refresh(self, kind: RefreshKind) -> None:
        started_at = _now()
        self._state = RefreshState(
            status="running",
            kind=kind,
            stage="fetching_polymarket",
            started_at=started_at,
        )
        try:
            if kind == "quick":
                saved_series = self.storage.load_priority_series()
                series = list(dict.fromkeys(["KXFED", *saved_series]))
                kalshi_call = self.kalshi_series_fetch(series)
            else:
                kalshi_call = self.kalshi_full_fetch(
                    on_progress=self._update_full_progress
                )

            polymarket_result, kalshi_result = await asyncio.gather(
                self.polymarket_fetch(),
                kalshi_call,
                return_exceptions=True,
            )

            now = _now()
            source_statuses = [
                self._store_source_result(
                    "polymarket",
                    polymarket_result,
                    now,
                ),
                self._store_source_result("kalshi", kalshi_result, now),
            ]

            kalshi_rows = self.storage.load_source("kalshi")
            if kind == "full" and not isinstance(kalshi_result, BaseException):
                if kalshi_result:
                    self.storage.save_priority_series(
                        discover_priority_series(kalshi_rows)
                    )

            self._set_stage("classifying")
            rows = self._prepare_rows(
                [
                    *self.storage.load_source("polymarket"),
                    *kalshi_rows,
                ]
            )

            self._set_stage("translating")
            translation = await self.translator.translate(
                rows,
                limit=30 if kind == "quick" else 100,
            )

            self._set_stage("saving")
            finished_at = _now()
            terminal_status = "done" if rows else "error"
            error = None if rows else "No usable event probability data"
            self._state = RefreshState(
                status=terminal_status,
                kind=kind,
                stage="saving",
                started_at=started_at,
                finished_at=finished_at,
                error=error,
                translation=translation,
            )
            self.storage.save_overview(
                ProbabilitySnapshot(
                    as_of=finished_at,
                    events=rows,
                    sources=source_statuses,
                    translation_cache_size=len(
                        self.storage.load_translation_cache()
                    ),
                    refresh=self._state,
                )
            )
        except Exception as exc:
            self._state = RefreshState(
                status="error",
                kind=kind,
                stage=self._state.stage,
                started_at=started_at,
                finished_at=_now(),
                error=str(exc),
            )
            snapshot = self.storage.load_overview()
            snapshot.refresh = self._state
            self.storage.save_overview(snapshot)

    def _update_full_progress(self, current: int, total: int) -> None:
        self._state.stage = "fetching_kalshi"
        self._state.progress_current = current
        self._state.progress_total = total

    def _set_stage(self, stage: str) -> None:
        self._state.stage = stage
        self._state.progress_current = 0
        self._state.progress_total = 0

    def _store_source_result(
        self,
        source: Literal["polymarket", "kalshi"],
        result: list[EventProbability] | BaseException,
        as_of: str,
    ) -> SourceStatus:
        previous = self.storage.load_source(source)
        if isinstance(result, BaseException):
            return SourceStatus(
                source=source,
                status="error",
                event_count=len(previous),
                error=str(result),
            )
        if result:
            self.storage.save_source(source, result)
            return SourceStatus(
                source=source,
                status="ok",
                as_of=as_of,
                event_count=len(result),
            )
        return SourceStatus(
            source=source,
            status="stale" if previous else "empty",
            event_count=len(previous),
        )

    @staticmethod
    def _prepare_rows(
        rows: Sequence[EventProbability],
    ) -> list[EventProbability]:
        deduplicated: dict[tuple[str, str], EventProbability] = {}
        for row in rows:
            identity = row.slug or " ".join(row.question.lower().split())
            updated = row.model_copy(
                update={
                    "topic": classify(row.question, row.source_category),
                }
            )
            key = (updated.source, identity)
            current = deduplicated.get(key)
            if current is None or updated.volume_24h > current.volume_24h:
                deduplicated[key] = updated
        return limit_by_topic(list(deduplicated.values()))
