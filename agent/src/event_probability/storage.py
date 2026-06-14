import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Literal

from pydantic import ValidationError

from src.config.paths import get_data_dir

from .models import EventProbability, ProbabilitySnapshot


SourceName = Literal["polymarket", "kalshi"]


class ProbabilityStorage:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or get_data_dir() / "event_probability"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_source(
        self,
        source: SourceName,
        events: list[EventProbability],
    ) -> bool:
        if not events:
            return False
        self._write_json(
            self._source_path(source),
            [event.model_dump(mode="json") for event in events],
        )
        return True

    def load_source(self, source: SourceName) -> list[EventProbability]:
        payload = self._read_json(self._source_path(source), [])
        if not isinstance(payload, list):
            return []
        try:
            return [EventProbability.model_validate(row) for row in payload]
        except (TypeError, ValidationError):
            return []

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
        return self.base_dir / f"{source}_snapshot.json"

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
            os.replace(temp_path, path)
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()
