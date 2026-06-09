"""FastAPI dependencies: DB session and (optional) write-path API key auth."""
from __future__ import annotations

from typing import Iterator

from fastapi import Header, HTTPException, Request
from sqlalchemy.orm import Session


def get_session(request: Request) -> Iterator[Session]:
    factory = request.app.state.session_factory
    session = factory()
    try:
        yield session
    finally:
        session.close()


def require_api_key(
    request: Request, x_api_key: str | None = Header(default=None)
) -> None:
    """Open local mode when no keys are configured; otherwise enforce X-API-Key."""
    keys = request.app.state.settings.api_key_list
    if keys and x_api_key not in keys:
        raise HTTPException(status_code=401, detail="invalid or missing API key")
