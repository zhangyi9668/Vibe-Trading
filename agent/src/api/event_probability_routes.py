import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, status

from src.event_probability.models import ProbabilityHistoryRequest
from src.event_probability.service import EventProbabilityService


logger = logging.getLogger(__name__)
_TOKEN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,256}$")
_SERVICE: EventProbabilityService | None = None
AuthDep = Callable[..., Awaitable[Any] | Any]


def _get_service() -> EventProbabilityService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = EventProbabilityService()
    return _SERVICE


def _internal_error(operation: str, exc: Exception) -> HTTPException:
    logger.exception("event probability %s failed", operation, exc_info=exc)
    return HTTPException(
        status_code=500,
        detail="internal error; see server logs",
    )


def register_event_probability_routes(
    app: FastAPI,
    require_auth: AuthDep,
) -> None:
    @app.get(
        "/event-probability/overview",
        dependencies=[Depends(require_auth)],
    )
    async def get_event_probability_overview():
        try:
            return _get_service().get_overview()
        except Exception as exc:
            raise _internal_error("overview", exc) from exc

    @app.post(
        "/event-probability/refresh/quick",
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_auth)],
    )
    async def start_quick_event_probability_refresh():
        try:
            return await _get_service().start_refresh("quick")
        except Exception as exc:
            raise _internal_error("quick refresh", exc) from exc

    @app.post(
        "/event-probability/refresh/full",
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_auth)],
    )
    async def start_full_event_probability_refresh():
        try:
            return await _get_service().start_refresh("full")
        except Exception as exc:
            raise _internal_error("full refresh", exc) from exc

    @app.get(
        "/event-probability/refresh/status",
        dependencies=[Depends(require_auth)],
    )
    async def get_event_probability_refresh_status():
        try:
            return _get_service().get_refresh_state()
        except Exception as exc:
            raise _internal_error("refresh status", exc) from exc

    @app.post(
        "/event-probability/history",
        dependencies=[Depends(require_auth)],
    )
    async def get_event_probability_histories(request: ProbabilityHistoryRequest):
        if not 1 <= len(request.series) <= 5:
            raise HTTPException(
                status_code=400,
                detail="series count must be 1..5",
            )
        for item in request.series:
            if not _TOKEN_ID_RE.fullmatch(item.token_id or ""):
                raise HTTPException(status_code=400, detail="invalid token_id")
        try:
            return await _get_service().get_histories(request.series)
        except Exception as exc:
            raise _internal_error("history", exc) from exc

    @app.get(
        "/event-probability/history/{token_id}",
        dependencies=[Depends(require_auth)],
    )
    async def get_event_probability_history(token_id: str):
        if not _TOKEN_ID_RE.fullmatch(token_id or ""):
            raise HTTPException(status_code=400, detail="invalid token_id")
        try:
            return await _get_service().get_history(token_id)
        except Exception as exc:
            raise _internal_error("history", exc) from exc
