"""Ingest endpoint: accepts a single event or a batch, broadcasts accepted
events to dashboard subscribers."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool

from ..collector import process_events
from ..deps import require_api_key
from ..schemas import EventBatchIn, EventIn, EventOut, IngestResultOut

router = APIRouter()


@router.post(
    "/events",
    status_code=202,
    response_model=IngestResultOut,
    dependencies=[Depends(require_api_key)],
)
async def ingest_events(body: EventBatchIn | EventIn, request: Request) -> IngestResultOut:
    events = body.events if isinstance(body, EventBatchIn) else [body]

    session_factory = request.app.state.session_factory

    def _store():
        session = session_factory()
        try:
            return process_events(session, events)
        finally:
            session.close()

    stored, duplicates = await run_in_threadpool(_store)

    manager = request.app.state.ws_manager
    for row in stored:
        await manager.broadcast(
            row.project_id,
            {"type": "event", "data": EventOut.model_validate(row).model_dump(mode="json")},
        )

    return IngestResultOut(accepted=len(stored), duplicates=duplicates)
