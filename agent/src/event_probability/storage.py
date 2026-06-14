import json
import os
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Literal

from pydantic import ValidationError

from src.config.paths import get_data_dir

from .models import EventProbability, ProbabilitySnapshot


SourceName = Literal["polymarket", "kalshi"]
_SOURCES = {"polymarket", "kalshi"}
_REPLACE_BACKOFF = (0.025, 0.05, 0.1, 0.2, 0.4)


class ProbabilityStorage:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or get_data_dir() / "event_probability"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_source(
        self,
        source: SourceName,
        events: list[EventProbability],
    ) -> bool:
        self._validate_source(source)
        if not events:
            return False
        if any(event.source != source for event in events):
            raise ValueError("Event source does not match snapshot source")
        self._write_json(
            self._source_path(source),
            [event.model_dump(mode="json") for event in events],
        )
        return True

    def load_source(self, source: SourceName) -> list[EventProbability]:
        self._validate_source(source)
        payload = self._read_json(self._source_path(source), [])
        if not isinstance(payload, list):
            return []
        events: list[EventProbability] = []
        for row in payload:
            try:
                event = EventProbability.model_validate(row)
            except (TypeError, ValidationError):
                continue
            if event.source == source:
                events.append(event)
        return events

    def save_overview(self, snapshot: ProbabilitySnapshot) -> None:
        self._write_json(
            self.base_dir / "overview_snapshot.json",
            snapshot.model_dump(mode="json"),
        )

    def load_overview(self) -> ProbabilitySnapshot:
        payload = self._read_json(self.base_dir / "overview_snapshot.json", {})
        try:
            return ProbabilitySnapshot.model_validate(payload)
        except (TypeError, ValidationError):
            return ProbabilitySnapshot()

    def save_translation_cache(self, cache: dict[str, str]) -> None:
        self._write_json(self.base_dir / "translation_cache.json", cache)

    def load_translation_cache(self) -> dict[str, str]:
        payload = self._read_json(self.base_dir / "translation_cache.json", {})
        if not isinstance(payload, dict):
            return {}
        return {
            key: value
            for key, value in payload.items()
            if isinstance(key, str) and isinstance(value, str)
        }

    def save_priority_series(self, series_tickers: list[str]) -> None:
        self._write_json(
            self.base_dir / "priority_series.json",
            list(dict.fromkeys(series_tickers)),
        )

    def load_priority_series(self) -> list[str]:
        payload = self._read_json(self.base_dir / "priority_series.json", [])
        if not isinstance(payload, list):
            return []
        return list(dict.fromkeys(item for item in payload if isinstance(item, str)))

    def _source_path(self, source: SourceName) -> Path:
        self._validate_source(source)
        return self.base_dir / f"{source}_snapshot.json"

    @staticmethod
    def _validate_source(source: str) -> None:
        if source not in _SOURCES:
            raise ValueError(f"Unsupported source: {source}")

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        try:
            with path.open(encoding="utf-8") as handle:
                return json.load(handle)
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return default

    def _write_json(self, path: Path, payload: Any) -> None:
        temp_path: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.base_dir,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._replace_with_retry(temp_path, path)
            self._fsync_dir()
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()

    @staticmethod
    def _replace_with_retry(source: Path, target: Path) -> None:
        for attempt in range(len(_REPLACE_BACKOFF) + 1):
            try:
                os.replace(source, target)
                return
            except OSError as exc:
                if getattr(exc, "winerror", None) not in {5, 32}:
                    raise
                if attempt == len(_REPLACE_BACKOFF):
                    raise
                time.sleep(_REPLACE_BACKOFF[attempt])

    def _fsync_dir(self) -> None:
        try:
            directory_fd = os.open(self.base_dir, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(directory_fd)
        except OSError:
            pass
        finally:
            os.close(directory_fd)
