from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Depends, FastAPI, HTTPException

from src.semiconductor_research.service import SemiconductorQuoteService


logger = logging.getLogger(__name__)
_SERVICE: SemiconductorQuoteService | None = None
AuthDep = Callable[..., Awaitable[Any] | Any]


def _get_service() -> SemiconductorQuoteService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = SemiconductorQuoteService()
    return _SERVICE


def _internal_error(operation: str, exc: Exception) -> HTTPException:
    logger.exception("semiconductor research %s failed", operation, exc_info=exc)
    return HTTPException(status_code=500, detail="internal error; see server logs")


def register_semiconductor_routes(app: FastAPI, require_auth: AuthDep) -> None:
    @app.get("/industries", dependencies=[Depends(require_auth)])
    async def get_industries():
        return {"industries": _get_service().industries()}

    @app.get("/industries/{slug}/quotes", dependencies=[Depends(require_auth)])
    async def get_industry_quotes(slug: str):
        try:
            return await asyncio.to_thread(_get_service().fetch_industry, slug)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/semiconductor/health", dependencies=[Depends(require_auth)])
    async def get_semiconductor_health():
        try:
            return _get_service().health()
        except Exception as exc:
            raise _internal_error("health", exc) from exc

    @app.get("/semiconductor/quotes", dependencies=[Depends(require_auth)])
    async def get_semiconductor_quotes():
        try:
            return await asyncio.to_thread(_get_service().fetch_all)
        except Exception as exc:
            raise _internal_error("quotes", exc) from exc
