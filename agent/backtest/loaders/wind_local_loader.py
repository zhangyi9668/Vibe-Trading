"""Read OHLCV bars from the project-local Wind stock data warehouse."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from backtest.loaders.base import validate_date_range, validate_ohlc
from backtest.loaders.registry import register

logger = logging.getLogger(__name__)


def _discover_data_root() -> Path:
    configured = os.getenv("VIBE_WIND_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "data" / "wind_stock_universe"
        if candidate.is_dir():
            return candidate
    return Path.cwd() / "data" / "wind_stock_universe"


_DATA_ROOT = _discover_data_root()


def _read_kline(path: Path) -> pd.DataFrame | None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "success":
        return None
    data = payload.get("result", {}).get("data", {})
    columns = [column.get("name") for column in data.get("columns", [])]
    rows = data.get("rows", [])
    if not columns or not rows:
        return None

    frame = pd.DataFrame(rows, columns=columns)
    required = {"_DATE", "OPEN", "HIGH", "LOW", "MATCH", "VOLUME"}
    if not required.issubset(frame.columns):
        return None
    frame = frame.rename(
        columns={
            "OPEN": "open",
            "HIGH": "high",
            "LOW": "low",
            "MATCH": "close",
            "VOLUME": "volume",
        }
    )
    frame["trade_date"] = pd.to_datetime(frame["_DATE"], format="%Y%m%d", errors="coerce")
    frame = frame.dropna(subset=["trade_date"]).set_index("trade_date").sort_index()
    ohlcv = ["open", "high", "low", "close", "volume"]
    frame = frame[ohlcv]
    for column in ohlcv:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["open", "high", "low", "close"])
    frame = validate_ohlc(frame)
    return frame.astype("float64")


@register
class DataLoader:
    """Read cached Wind daily K-lines without making network requests."""

    name = "wind_local"
    markets = {"a_share"}
    requires_auth = False

    def is_available(self) -> bool:
        return (_DATA_ROOT / "universe.csv").is_file() and (_DATA_ROOT / "raw").is_dir()

    def fetch(
        self,
        codes: List[str],
        start_date: str,
        end_date: str,
        *,
        interval: str = "1D",
        fields: Optional[List[str]] = None,
    ) -> Dict[str, pd.DataFrame]:
        validate_date_range(start_date, end_date)
        if interval != "1D":
            logger.warning("wind_local supports daily bars only, got %s", interval)
            return {}

        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
        result: Dict[str, pd.DataFrame] = {}
        for code in codes:
            clean = code.split(":", 1)[1] if code.startswith("wind_local:") else code
            path = _DATA_ROOT / "raw" / clean / "kline.json"
            if not path.is_file():
                logger.warning("wind_local: no cached K-line for %s", clean)
                continue
            try:
                frame = _read_kline(path)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                logger.warning("wind_local failed for %s: %s", clean, exc)
                continue
            if frame is None:
                continue
            frame = frame[(frame.index >= start) & (frame.index <= end)]
            if not frame.empty:
                result[clean] = frame
        return result
