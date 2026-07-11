from __future__ import annotations

import importlib.util
import json
from pathlib import Path


LOADER_PATH = Path(__file__).parents[1] / "backtest" / "loaders" / "wind_local_loader.py"


def load_wind_local_loader():
    assert LOADER_PATH.exists(), "wind_local loader has not been implemented"
    spec = importlib.util.spec_from_file_location("backtest.loaders.wind_local_loader", LOADER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_kline(root: Path, code: str, *, status: str = "success") -> None:
    path = root / "raw" / code / "kline.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "status": status,
                "code": code,
                "dataset": "kline",
                "result": {
                    "data": {
                        "columns": [
                            {"name": "TIME"},
                            {"name": "OPEN"},
                            {"name": "MATCH"},
                            {"name": "HIGH"},
                            {"name": "LOW"},
                            {"name": "TURNOVER"},
                            {"name": "VOLUME"},
                            {"name": "_DATE"},
                        ],
                        "rows": [
                            ["2026-07-09T00:00:00+02:00", "10", "10.5", "11", "9", "10000", "1000", "20260709"],
                            ["2026-07-10T00:00:00+02:00", "12", "12.5", "13", "11", "18000", "1500", "20260710"],
                        ],
                    },
                    "error": None,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_wind_local_loader_reads_cached_kline_as_ohlcv(tmp_path: Path, monkeypatch):
    module = load_wind_local_loader()
    (tmp_path / "universe.csv").write_text("code,name\n300308.SZ,中际旭创\n", encoding="utf-8")
    write_kline(tmp_path, "300308.SZ")
    monkeypatch.setattr(module, "_DATA_ROOT", tmp_path)

    loader = module.DataLoader()
    frames = loader.fetch(["wind_local:300308.SZ"], "2026-07-09", "2026-07-10")

    assert loader.is_available()
    assert set(frames) == {"300308.SZ"}
    frame = frames["300308.SZ"]
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert list(frame["close"]) == [10.5, 12.5]
    assert str(frame.index.tz) == "None"


def test_registry_exposes_wind_local_as_explicit_source():
    import backtest.loaders.registry as registry

    registry._registered = False
    registry.LOADER_REGISTRY.pop("wind_local", None)
    registry._ensure_registered()

    assert "wind_local" in registry.VALID_SOURCES
    assert "wind_local" in registry.LOADER_REGISTRY
    assert "wind_local" not in registry.FALLBACK_CHAINS["a_share"]


def test_explicit_wind_local_never_falls_back_to_network():
    import backtest.loaders.registry as registry

    assert "wind_local" in registry._NO_NETWORK_FALLBACK_SOURCES
