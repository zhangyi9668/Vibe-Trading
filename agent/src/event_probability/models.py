from typing import Literal

from pydantic import BaseModel, Field


ProbabilitySource = Literal["polymarket", "kalshi"]


class EventProbability(BaseModel):
    question: str
    question_zh: str | None = None
    topic: str
    outcomes: list[str] = Field(default_factory=lambda: ["Yes", "No"])
    prices: list[float | None] = Field(default_factory=list)
    prob_yes: float | None = None
    pick_label: str | None = None
    change_24h: float | None = None
    change_7d: float | None = None
    volume_24h: float = 0.0
    liquidity: float = 0.0
    end_date: str | None = None
    slug: str
    series_ticker: str | None = None
    token_id_yes: str | None = None
    source: ProbabilitySource
    source_category: str | None = None


class SourceStatus(BaseModel):
    source: ProbabilitySource
    status: Literal["ok", "stale", "error", "empty"]
    as_of: str | None = None
    event_count: int = 0
    error: str | None = None


class TranslationStats(BaseModel):
    new_translations: int = 0
    cache_hits: int = 0
    pending: int = 0


class RefreshState(BaseModel):
    status: Literal["idle", "queued", "running", "done", "error"] = "idle"
    kind: Literal["quick", "full"] | None = None
    stage: str | None = None
    progress_current: int = 0
    progress_total: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    translation: TranslationStats = Field(default_factory=TranslationStats)


class ProbabilitySnapshot(BaseModel):
    as_of: str | None = None
    events: list[EventProbability] = Field(default_factory=list)
    sources: list[SourceStatus] = Field(default_factory=list)
    translation_cache_size: int = 0
    refresh: RefreshState = Field(default_factory=RefreshState)
