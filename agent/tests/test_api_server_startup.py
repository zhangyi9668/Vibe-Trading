import asyncio
from types import SimpleNamespace

import pytest


@pytest.mark.unit
def test_startup_preflight_can_schedule_background_check(monkeypatch) -> None:
    import api_server
    import src.config.accessor
    import src.preflight

    monkeypatch.setattr(src.preflight, "run_preflight", lambda _console: None)
    monkeypatch.setattr(api_server, "_start_scheduled_research_executor", lambda: None)
    monkeypatch.setattr(
        src.config.accessor,
        "get_env_config",
        lambda: SimpleNamespace(
            agent_tuning=SimpleNamespace(vibe_trading_channels_auto_start=False)
        ),
    )

    async def run_startup() -> None:
        await api_server._run_startup_preflight()
        await asyncio.sleep(0)

    asyncio.run(run_startup())
