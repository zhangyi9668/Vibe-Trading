# Event Probability Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a left-sidebar “事件概率” page that serves cached Polymarket and Kalshi probabilities, supports fast and full background refreshes, and rate-limits LLM title translation.

**Architecture:** A focused `src.event_probability` package owns source adapters, taxonomy, durable snapshots, translation cache, and refresh orchestration. A separately mounted FastAPI route module exposes the snapshot and task state; the React page reads that API, polls only while a refresh is active, and renders module-grouped cards plus optional Polymarket trends.

**Tech Stack:** Python 3.11, FastAPI, httpx, Pydantic, pytest, React 19, TypeScript, Vite, Tailwind CSS, ECharts, Vitest, Testing Library.

---

## File Structure

Create these backend files:

- `agent/src/event_probability/models.py`: shared event, source, snapshot, and refresh-state models.
- `agent/src/event_probability/taxonomy.py`: deterministic keyword/category classification and module caps.
- `agent/src/event_probability/polymarket.py`: Gamma market fetch and CLOB history adapter.
- `agent/src/event_probability/kalshi.py`: full event-book scan, discovered-series fast refresh, and multi-leg shaping.
- `agent/src/event_probability/storage.py`: atomic JSON snapshots and translation cache persistence.
- `agent/src/event_probability/translation.py`: cached, batched, quota-limited LLM translation.
- `agent/src/event_probability/service.py`: source fallback, merge, refresh lock, task state, and progress.
- `agent/src/event_probability/__init__.py`: public package exports.
- `agent/src/api/event_probability_routes.py`: authenticated HTTP route registration.

Create these frontend files:

- `frontend/src/pages/EventProbability.tsx`: page state, filters, polling, module sections, and event rows.
- `frontend/src/components/charts/ProbabilityTrend.tsx`: lazy Polymarket history chart.
- `frontend/src/pages/EventProbability.test.tsx`: page interaction and fallback tests.

Modify:

- `agent/api_server.py`: register routes and recognize the SPA deep link.
- `agent/tests/test_spa_deep_link.py`: cover `/event-probability`.
- `frontend/src/lib/api.ts`: API methods and TypeScript response types.
- `frontend/src/router.tsx`: lazy page route.
- `frontend/src/components/layout/Layout.tsx`: sidebar entry.
- `frontend/vite.config.ts`: dev proxy and HTML fallback.
- `frontend/package.json` and `frontend/package-lock.json`: add the frontend test command and test dependencies while preserving existing local Rollup changes.
- `NOTICE`: record Apache-2.0 attribution without exposing it in the UI.

Create backend tests:

- `agent/tests/test_event_probability_taxonomy.py`
- `agent/tests/test_event_probability_sources.py`
- `agent/tests/test_event_probability_storage.py`
- `agent/tests/test_event_probability_translation.py`
- `agent/tests/test_event_probability_service.py`
- `agent/tests/test_event_probability_api.py`

## Task 1: Define the Stable Event and Refresh Contracts

**Files:**
- Create: `agent/src/event_probability/models.py`
- Create: `agent/src/event_probability/__init__.py`
- Test: `agent/tests/test_event_probability_sources.py`

- [ ] **Step 1: Write the failing model serialization test**

```python
from src.event_probability.models import EventProbability, RefreshState


def test_event_probability_serializes_wire_contract() -> None:
    event = EventProbability(
        question="Will the Fed cut rates?",
        topic="monetary_policy",
        prob_yes=0.68,
        source="kalshi",
        slug="KXFED-TEST",
    )
    payload = event.model_dump(mode="json")
    assert payload["question_zh"] is None
    assert payload["prob_yes"] == 0.68
    assert payload["source"] == "kalshi"


def test_refresh_state_defaults_to_idle() -> None:
    state = RefreshState()
    assert state.status == "idle"
    assert state.progress_current == 0
    assert state.error is None
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
.venv/bin/python -m pytest agent/tests/test_event_probability_sources.py -v
```

Expected: collection fails with `ModuleNotFoundError: No module named 'src.event_probability'`.

- [ ] **Step 3: Implement the Pydantic models**

Define:

```python
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
    source: Literal["polymarket", "kalshi"]
    source_category: str | None = None


class SourceStatus(BaseModel):
    source: Literal["polymarket", "kalshi"]
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
```

Export the four public models from `__init__.py`.

- [ ] **Step 4: Run the model tests and verify GREEN**

Run the same pytest command. Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add agent/src/event_probability agent/tests/test_event_probability_sources.py
git commit -m "feat(probability): define event snapshot contracts"
```

## Task 2: Implement Deterministic Taxonomy and Module Caps

**Files:**
- Create: `agent/src/event_probability/taxonomy.py`
- Test: `agent/tests/test_event_probability_taxonomy.py`

- [ ] **Step 1: Write failing classification tests**

```python
from src.event_probability.taxonomy import classify, limit_by_topic
from src.event_probability.models import EventProbability


def test_high_signal_topics_win_before_generic_terms() -> None:
    assert classify("Will Israel and Iran agree to a ceasefire?") == "geopolitics"
    assert classify("Will the Fed cut rates in September?") == "monetary_policy"
    assert classify("Will US CPI exceed 3 percent?") == "macro_economy"
    assert classify("Will OpenAI release a new model?") == "ai_technology"


def test_kalshi_category_is_a_fallback() -> None:
    assert classify("A neutral title", "Economics") == "macro_economy"


def test_topic_caps_keep_highest_volume_rows() -> None:
    rows = [
        EventProbability(
            question=f"q{i}", topic="geopolitics", prob_yes=0.5,
            source="polymarket", slug=str(i), volume_24h=float(i),
        )
        for i in range(20)
    ]
    limited = limit_by_topic(rows, {"geopolitics": 3})
    assert [row.volume_24h for row in limited] == [19.0, 18.0, 17.0]
```

- [ ] **Step 2: Run and verify RED**

```bash
.venv/bin/python -m pytest agent/tests/test_event_probability_taxonomy.py -v
```

Expected: import failure for `taxonomy`.

- [ ] **Step 3: Implement taxonomy**

Use ordered keyword groups so geopolitics precedes elections, crypto precedes indices, and monetary policy precedes macro economy. Use these wire keys:

```python
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
    "monetary_policy": 20,
    "macro_economy": 20,
    "geopolitics": 24,
    "political_elections": 20,
    "indices_commodities": 20,
    "ai_technology": 16,
    "crypto": 12,
    "sports": 8,
    "entertainment": 8,
    "other": 8,
}
```

`classify(title, native_category=None)` must lowercase once, apply ordered keyword matching, then map Kalshi categories such as `Economics`, `Financials`, `Commodities`, `Elections`, `Politics`, `World`, `Crypto`, `Sports`, `Entertainment`, and `Science and Technology`.

`limit_by_topic` groups rows, sorts each group by `volume_24h` descending, applies caps, and returns groups in `TOPIC_ORDER`.

- [ ] **Step 4: Run and verify GREEN**

Run the taxonomy test file. Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add agent/src/event_probability/taxonomy.py agent/tests/test_event_probability_taxonomy.py
git commit -m "feat(probability): classify and cap event modules"
```

## Task 3: Implement Polymarket and Kalshi Adapters

**Files:**
- Create: `agent/src/event_probability/polymarket.py`
- Create: `agent/src/event_probability/kalshi.py`
- Modify: `agent/tests/test_event_probability_sources.py`

- [ ] **Step 1: Add failing source-shaping tests**

Add tests for:

```python
def test_polymarket_parses_json_encoded_fields() -> None:
    row = shape_polymarket_market({
        "question": "Will event X happen?",
        "outcomes": "[\"Yes\", \"No\"]",
        "outcomePrices": "[\"0.62\", \"0.38\"]",
        "clobTokenIds": "[\"yes-token\", \"no-token\"]",
        "volume24hr": 1234,
        "slug": "event-x",
    })
    assert row is not None
    assert row.prob_yes == 0.62
    assert row.token_id_yes == "yes-token"


def test_kalshi_uses_dollar_fields_and_nearest_fifty_percent_leg() -> None:
    row = shape_kalshi_event({
        "title": "Average gas price",
        "event_ticker": "KXGAS",
        "category": "Commodities",
        "series_ticker": "KXGAS",
        "markets": [
            {"yes_sub_title": "Above $4.10", "yes_ask_dollars": "0.95", "volume_24h_fp": "10"},
            {"yes_sub_title": "Above $4.20", "yes_ask_dollars": "0.53", "volume_24h_fp": "20"},
            {"yes_sub_title": "Above $4.30", "yes_ask_dollars": "0.08", "volume_24h_fp": "30"},
        ],
    })
    assert row is not None
    assert row.prob_yes == 0.53
    assert row.pick_label == "Above $4.20"
    assert row.volume_24h == 60.0
```

Also use `httpx.MockTransport` to prove:

- Polymarket paginates with offsets and server-side `order=volume24hr`.
- Kalshi full mode follows cursors and reports page progress.
- Kalshi quick mode requests discovered `series_ticker` values concurrently.

- [ ] **Step 2: Run and verify RED**

```bash
.venv/bin/python -m pytest agent/tests/test_event_probability_sources.py -v
```

Expected: missing adapter imports.

- [ ] **Step 3: Implement Polymarket**

Implement:

```python
async def fetch_markets(
    *,
    client: httpx.AsyncClient | None = None,
    max_pages: int = 4,
) -> list[EventProbability]

async def fetch_history(
    token_id: str,
    *,
    interval: str = "1w",
    fidelity: int = 720,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, float | int]]
```

Requirements:

- Gamma URL: `https://gamma-api.polymarket.com/markets`.
- Query: `active=true`, `closed=false`, `limit=100`, offset paging, `order=volume24hr`, `ascending=false`.
- Parse JSON-encoded `outcomes`, `outcomePrices`, and `clobTokenIds`.
- Skip malformed rows without failing the full fetch.
- Accept an injected client for unit tests.
- Use bounded 15-second requests and two attempts per page.

- [ ] **Step 4: Implement Kalshi**

Implement:

```python
async def fetch_full(
    *,
    client: httpx.AsyncClient | None = None,
    max_pages: int = 30,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[EventProbability]

async def fetch_series(
    series_tickers: Sequence[str],
    *,
    client: httpx.AsyncClient | None = None,
    concurrency: int = 6,
) -> list[EventProbability]

def discover_priority_series(events: Sequence[EventProbability], limit: int = 24) -> list[str]
```

Requirements:

- Full URL: `https://api.elections.kalshi.com/trade-api/v2/events`.
- Full query: `limit=200`, `status=open`, `with_nested_markets=true`, cursor paging.
- Quick URL: `https://api.elections.kalshi.com/trade-api/v2/markets` with query parameters `limit=200`, `status=open`, and one concrete `series_ticker`.
- Seed quick refresh with `KXFED`; merge it with series discovered from the last successful full snapshot.
- Select discovered series only from core modules and rank by aggregated 24-hour volume.
- Use a semaphore for quick-refresh series concurrency.
- Use `*_dollars`, `volume_24h_fp`, and `liquidity_dollars`.
- Multi-leg events select the priced leg nearest 50% and expose `pick_label`.

- [ ] **Step 5: Run and verify GREEN**

Run the source test file. Expected: all source tests pass with no network access.

- [ ] **Step 6: Commit**

```bash
git add agent/src/event_probability/polymarket.py agent/src/event_probability/kalshi.py agent/tests/test_event_probability_sources.py
git commit -m "feat(probability): add prediction market adapters"
```

## Task 4: Add Atomic Snapshots and Translation Cache

**Files:**
- Create: `agent/src/event_probability/storage.py`
- Test: `agent/tests/test_event_probability_storage.py`

- [ ] **Step 1: Write failing storage tests**

```python
def test_atomic_json_round_trip(tmp_path: Path) -> None:
    store = ProbabilityStorage(tmp_path)
    store.save_source("polymarket", [sample_event()])
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
```

- [ ] **Step 2: Run and verify RED**

```bash
.venv/bin/python -m pytest agent/tests/test_event_probability_storage.py -v
```

Expected: missing `ProbabilityStorage`.

- [ ] **Step 3: Implement storage**

`ProbabilityStorage()` defaults to:

```python
get_data_dir() / "event_probability"
```

Persist:

- `polymarket_snapshot.json`
- `kalshi_snapshot.json`
- `overview_snapshot.json`
- `translation_cache.json`
- `priority_series.json`

Implement writes with `NamedTemporaryFile` in the target directory, `flush`, `os.fsync`, and `os.replace`. Source snapshot writes return `False` and leave the previous file untouched for an empty event list.

- [ ] **Step 4: Run and verify GREEN**

Expected: all storage tests pass.

- [ ] **Step 5: Commit**

```bash
git add agent/src/event_probability/storage.py agent/tests/test_event_probability_storage.py
git commit -m "feat(probability): persist atomic event snapshots"
```

## Task 5: Add Quota-Limited Cached Translation

**Files:**
- Create: `agent/src/event_probability/translation.py`
- Test: `agent/tests/test_event_probability_translation.py`

- [ ] **Step 1: Write failing translation tests**

Use an injected fake translator:

```python
async def fake_translate(titles: list[str]) -> dict[str, str]:
    calls.append(titles)
    return {title: f"中文:{title}" for title in titles}


def test_translation_uses_cache_batches_and_quota(tmp_path: Path) -> None:
    store = ProbabilityStorage(tmp_path)
    store.save_translation_cache({"cached": "已缓存"})
    translator = TitleTranslator(store, translate_batch=fake_translate, sleep=lambda _: async_noop())
    events = [event("cached")] + [event(f"new-{i}") for i in range(7)]
    stats = asyncio.run(translator.translate(events, limit=5, batch_size=4, batch_delay=0))
    assert [len(batch) for batch in calls] == [4, 1]
    assert stats.new_translations == 5
    assert stats.cache_hits == 1
    assert stats.pending == 2


def test_translation_failure_preserves_english(tmp_path: Path) -> None:
    row = event("English")

    async def fail(_: list[str]) -> dict[str, str]:
        raise RuntimeError("provider down")

    store = ProbabilityStorage(tmp_path)
    translator = TitleTranslator(
        store,
        translate_batch=fail,
        sleep=lambda _: async_noop(),
    )
    stats = asyncio.run(translator.translate([row], limit=30, batch_delay=0))
    assert stats.new_translations == 0
    assert row.question_zh is None
```

- [ ] **Step 2: Run and verify RED**

```bash
.venv/bin/python -m pytest agent/tests/test_event_probability_translation.py -v
```

- [ ] **Step 3: Implement translator**

`TitleTranslator.translate(events, *, limit, batch_size=4, batch_delay=1.0)` must:

- Load the permanent cache.
- Fill cached translations before selecting new titles.
- Translate at most `limit` unique new titles.
- Save each successful batch immediately.
- Never fail the refresh because translation failed.
- Return `TranslationStats`.

The default batch implementation calls `ChatLLM.chat` through `asyncio.to_thread` with no tools and a 45-second timeout. Prompt for a JSON object mapping each exact English title to concise Simplified Chinese, parse only a JSON object, and discard keys not present in the input batch.

- [ ] **Step 4: Run and verify GREEN**

Expected: batching, cache hits, quota, and failure fallback tests pass.

- [ ] **Step 5: Commit**

```bash
git add agent/src/event_probability/translation.py agent/tests/test_event_probability_translation.py
git commit -m "feat(probability): rate limit title translation"
```

## Task 6: Build Refresh Orchestration and Source Fallback

**Files:**
- Create: `agent/src/event_probability/service.py`
- Test: `agent/tests/test_event_probability_service.py`

- [ ] **Step 1: Write failing service tests**

Define these helpers at the top of the test file:

```python
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
```

Then cover:

```python
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


def test_full_refresh_discovers_series_and_uses_limit_100(tmp_path: Path) -> None:
    store = ProbabilityStorage(tmp_path)
    translator = SpyTranslator()
    full_rows = [event("cpi", source="kalshi", series_ticker="KXCPI")]
    service = EventProbabilityService(
        storage=store,
        polymarket_fetch=AsyncMock(return_value=[]),
        kalshi_full_fetch=AsyncMock(return_value=full_rows),
        kalshi_series_fetch=AsyncMock(),
        translator=translator,
    )
    asyncio.run(service._run_refresh("full"))
    assert "KXCPI" in store.load_priority_series()
    assert translator.limits == [100]


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
```

Assertions must prove:

- `get_overview()` does not invoke fetchers.
- Quick refresh fetches Polymarket plus `KXFED` and saved priority series.
- Full refresh discovers and saves priority series.
- A failed/empty source keeps its last valid rows and reports `stale` or `error`.
- Only one `_refresh_task` exists.
- Translation receives exactly 30 or 100 as the limit.

- [ ] **Step 2: Run and verify RED**

```bash
.venv/bin/python -m pytest agent/tests/test_event_probability_service.py -v
```

- [ ] **Step 3: Implement `EventProbabilityService`**

Public methods:

```python
def get_overview(self) -> ProbabilitySnapshot
def get_refresh_state(self) -> RefreshState
async def start_refresh(self, kind: Literal["quick", "full"]) -> RefreshState
async def get_history(self, token_id: str) -> list[dict[str, float | int]]
```

Internal flow:

1. Guard startup with `asyncio.Lock`.
2. If a task is already active, return its current state.
3. Create one retained background task.
4. Fetch `polymarket_call` and `kalshi_call` with `asyncio.gather(polymarket_call, kalshi_call, return_exceptions=True)`.
5. Save only non-empty successful source results.
6. Load valid rows for both sources from storage.
7. Deduplicate by `(source, slug)`; use normalized question only when slug is absent.
8. Classify and apply module caps.
9. Translate with limit 30 for quick and 100 for full.
10. Save the overview atomically.
11. Publish terminal `done` or `error` state while retaining usable data.

Progress stages:

- `fetching_polymarket`
- `fetching_kalshi`
- `classifying`
- `translating`
- `saving`

For full Kalshi scans, expose current page and maximum page count.

- [ ] **Step 4: Run and verify GREEN**

Expected: all service tests pass.

- [ ] **Step 5: Commit**

```bash
git add agent/src/event_probability/service.py agent/tests/test_event_probability_service.py
git commit -m "feat(probability): orchestrate cached refresh jobs"
```

## Task 7: Expose Authenticated FastAPI Routes

**Files:**
- Create: `agent/src/api/event_probability_routes.py`
- Modify: `agent/api_server.py`
- Create: `agent/tests/test_event_probability_api.py`
- Modify: `agent/tests/test_spa_deep_link.py`

- [ ] **Step 1: Write failing route and deep-link tests**

Using `TestClient(api_server.app, client=("127.0.0.1", 50000))`, test:

- `GET /event-probability/overview` returns the injected snapshot.
- Both POST refresh routes return `202`.
- A second refresh returns the same active state instead of creating another task.
- `GET /event-probability/refresh/status` returns progress.
- History rejects an empty or oversized token id and returns data for a valid token.
- `_is_spa_html_route("/event-probability")` is `True`.
- `_is_spa_html_route("/event-probability/extra")` is `False`.

- [ ] **Step 2: Run and verify RED**

```bash
.venv/bin/python -m pytest \
  agent/tests/test_event_probability_api.py \
  agent/tests/test_spa_deep_link.py -v
```

- [ ] **Step 3: Implement route registration**

Create `register_event_probability_routes(app, require_auth)` with:

```text
GET  /event-probability/overview
POST /event-probability/refresh/quick
POST /event-probability/refresh/full
GET  /event-probability/refresh/status
GET  /event-probability/history/{token_id}
```

Use one lazily created process-local service. Validate `token_id` with `^[A-Za-z0-9_-]{1,256}$`. Unexpected exceptions are logged and surfaced as `internal error; see server logs`.

Register the module near the existing Alpha Zoo registration:

```python
from src.api.event_probability_routes import register_event_probability_routes
register_event_probability_routes(app, require_auth=require_auth)
```

Add only `"/event-probability"` to `_SPA_HTML_EXACT_PATHS`.

- [ ] **Step 4: Run and verify GREEN**

Run the two test files. Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add agent/src/api/event_probability_routes.py agent/api_server.py \
  agent/tests/test_event_probability_api.py agent/tests/test_spa_deep_link.py
git commit -m "feat(probability): expose refresh and snapshot API"
```

## Task 8: Add Frontend API Types and Navigation

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/router.tsx`
- Modify: `frontend/src/components/layout/Layout.tsx`
- Modify: `frontend/vite.config.ts`

- [ ] **Step 1: Add API types and methods**

Add TypeScript types matching the Pydantic wire fields:

```typescript
export type ProbabilitySource = "polymarket" | "kalshi";
export type ProbabilityTopic =
  | "monetary_policy" | "macro_economy" | "geopolitics"
  | "political_elections" | "indices_commodities" | "ai_technology"
  | "crypto" | "sports" | "entertainment" | "other";

export interface EventProbability {
  question: string;
  question_zh: string | null;
  topic: ProbabilityTopic;
  outcomes: string[];
  prices: Array<number | null>;
  prob_yes: number | null;
  pick_label: string | null;
  change_24h: number | null;
  change_7d: number | null;
  volume_24h: number;
  liquidity: number;
  end_date: string | null;
  slug: string;
  series_ticker: string | null;
  token_id_yes: string | null;
  source: ProbabilitySource;
  source_category: string | null;
}

export interface ProbabilityTranslationStats {
  new_translations: number;
  cache_hits: number;
  pending: number;
}

export interface ProbabilityRefreshState {
  status: "idle" | "queued" | "running" | "done" | "error";
  kind: "quick" | "full" | null;
  stage: string | null;
  progress_current: number;
  progress_total: number;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  translation: ProbabilityTranslationStats;
}

export interface ProbabilitySourceStatus {
  source: ProbabilitySource;
  status: "ok" | "stale" | "error" | "empty";
  as_of: string | null;
  event_count: number;
  error: string | null;
}

export interface ProbabilityOverview {
  as_of: string | null;
  events: EventProbability[];
  sources: ProbabilitySourceStatus[];
  translation_cache_size: number;
  refresh: ProbabilityRefreshState;
}
```

Add:

```typescript
getEventProbabilityOverview()
startEventProbabilityRefresh(kind: "quick" | "full")
getEventProbabilityRefreshStatus()
getEventProbabilityHistory(tokenId: string)
```

- [ ] **Step 2: Add route and sidebar entry**

Lazy-load `@/pages/EventProbability`, route it at `/event-probability`, and add:

```typescript
{ to: "/event-probability", icon: Gauge, label: "事件概率" }
```

Keep the existing navigation order and place it after `Alpha Zoo`.

- [ ] **Step 3: Add Vite proxy and HTML fallback**

Add an exact `"/event-probability"` proxy entry using `apiProxyWithHtmlFallback`, while API subpaths continue through a separate `^/event-probability/` proxy entry.

- [ ] **Step 4: Run TypeScript build to expose missing page**

```bash
cd frontend && npm run build
```

Expected: FAIL because `@/pages/EventProbability` does not exist yet. Preserve the user's existing `@rollup/wasm-node` dependency changes.

- [ ] **Step 5: Commit navigation contract**

Do not commit while the build is red. Continue directly to Task 9.

## Task 9: Build the Module Overview Page and Trend Chart

**Files:**
- Create: `frontend/src/pages/EventProbability.tsx`
- Create: `frontend/src/components/charts/ProbabilityTrend.tsx`
- Create: `frontend/src/pages/EventProbability.test.tsx`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

- [ ] **Step 1: Add frontend test dependencies and script**

Preserve all existing manifest changes and add:

```json
"scripts": {
  "test": "vitest run"
}
```

Dev dependencies:

```text
vitest
jsdom
@testing-library/react
@testing-library/user-event
```

Configure Vitest inside `vite.config.ts` with `environment: "jsdom"`. Use Vitest's built-in assertions so no test setup file is required.

- [ ] **Step 2: Write failing page tests**

Mock `@/lib/api` and test:

- Page renders cached events grouped under Chinese module headings.
- Chinese title is primary and English original remains visible.
- Search, source, and module filters hide non-matching rows.
- Clicking “快速刷新” calls `startEventProbabilityRefresh("quick")`.
- Active refresh causes status polling and keeps cached rows visible.
- Missing Chinese translation displays the English title without an empty heading.
- Polymarket row with `token_id_yes` can open the trend region; Kalshi row cannot.
- Footer contains “风险温度计，不构成交易信号”.

- [ ] **Step 3: Run and verify RED**

```bash
cd frontend && npm test -- EventProbability.test.tsx
```

Expected: missing page/component implementation.

- [ ] **Step 4: Implement the page**

Use:

- `useEffect` for initial overview load.
- A 1.5-second polling interval only while refresh status is `queued` or `running`.
- A cleanup function to clear the polling timer.
- Local filters for topic, source, keyword, and minimum absolute 24-hour change.
- `TOPIC_LABELS` and `TOPIC_ORDER` constants matching backend wire keys.
- Existing Tailwind tokens only; do not add global colors.
- Buttons disabled while a refresh is active.
- A non-blocking error banner that leaves current events rendered.

Event row contents:

- Chinese title, then English title in muted text.
- Probability formatted as percent.
- 24-hour change with semantic color.
- Compact volume, source badge, expiry.
- Optional `pick_label`.
- Expandable trend button only for Polymarket rows with `token_id_yes`.

- [ ] **Step 5: Implement the trend chart**

`ProbabilityTrend` fetches history on first expansion, maps probability to percentage, and uses the shared lazy ECharts loader and chart theme patterns. It must render loading, empty, and error states inside the expanded row.

- [ ] **Step 6: Run focused tests and build**

```bash
cd frontend
npm test -- EventProbability.test.tsx
npm run build
```

Expected: tests pass and Vite build succeeds.

- [ ] **Step 7: Commit frontend**

```bash
git add frontend/src/pages/EventProbability.tsx \
  frontend/src/pages/EventProbability.test.tsx \
  frontend/src/components/charts/ProbabilityTrend.tsx \
  frontend/src/lib/api.ts frontend/src/router.tsx \
  frontend/src/components/layout/Layout.tsx frontend/vite.config.ts \
  frontend/package.json frontend/package-lock.json
git commit -m "feat(probability): add event probability dashboard"
```

## Task 10: Add Attribution and Complete Regression Verification

**Files:**
- Modify: `NOTICE`

- [ ] **Step 1: Add non-UI attribution**

Append:

```text
The event probability data pipeline includes code adapted from globalpercent
by Simon Lin (https://github.com/simonlin1212/globalpercent), licensed under
the Apache License 2.0.
```

Do not add this text to the Web UI.

- [ ] **Step 2: Run focused backend tests**

```bash
.venv/bin/python -m pytest \
  agent/tests/test_event_probability_taxonomy.py \
  agent/tests/test_event_probability_sources.py \
  agent/tests/test_event_probability_storage.py \
  agent/tests/test_event_probability_translation.py \
  agent/tests/test_event_probability_service.py \
  agent/tests/test_event_probability_api.py \
  agent/tests/test_spa_deep_link.py -v
```

Expected: all pass without network.

- [ ] **Step 3: Run lint and broader API regressions**

```bash
.venv/bin/python -m ruff check \
  agent/src/event_probability \
  agent/src/api/event_probability_routes.py \
  agent/tests/test_event_probability_*.py

.venv/bin/python -m pytest \
  agent/tests/test_security_auth_api.py \
  agent/tests/test_settings_api.py \
  agent/tests/test_spa_deep_link.py -v
```

Expected: lint clean and regression tests pass.

- [ ] **Step 4: Run frontend verification**

```bash
cd frontend
npm test
npm run build
```

Expected: all frontend tests pass and production bundle builds.

- [ ] **Step 5: Run browser smoke test**

Start the existing single-server production UI, then verify:

1. Sidebar shows “事件概率”.
2. `/event-probability` loads directly and survives reload.
3. Empty first-run state is clear.
4. Quick refresh immediately returns and shows progress.
5. Existing snapshot remains visible during full refresh.
6. Filters work.
7. A Polymarket history row expands without shifting unrelated modules.
8. Dark and light themes remain readable.

Do not expose tokens, headers, or `.env` values during verification.

- [ ] **Step 6: Commit attribution and final fixes**

```bash
git add NOTICE
git commit -m "docs: attribute event probability reference code"
```

If verification required code fixes, commit those fixes separately with the relevant test files before this documentation commit.
