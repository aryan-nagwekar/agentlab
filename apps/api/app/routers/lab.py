"""Lab Mode endpoints: fault templates, injection, and fault history.

Injection routes events through the normal collector pipeline (storage,
projections, WebSocket broadcast), so a fault behaves exactly like real
telemetry — visible live, in the timeline, and in replay."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .. import models
from ..collector import process_events
from ..deps import get_session, require_api_key
from ..lab import (
    FAULT_TEMPLATES,
    FAULT_TYPES,
    LAB_CONTROLLER_ID,
    build_fault_events,
    is_channel_fault,
)
from ..schemas import EventOut, FaultInjectIn, FaultInjectOut, FaultTemplateOut

router = APIRouter()


@router.get("/lab/fault-templates", response_model=list[FaultTemplateOut])
def list_fault_templates() -> list[FaultTemplateOut]:
    return FAULT_TEMPLATES


def _run_participants(session: Session, run_id: str) -> set[str]:
    rows = session.execute(
        select(models.Event.source_agent_id, models.Event.target_agent_id).where(
            models.Event.run_id == run_id
        )
    ).all()
    return {
        agent_id
        for source, target in rows
        for agent_id in (source, target)
        if agent_id and agent_id != LAB_CONTROLLER_ID
    }


@router.post(
    "/runs/{run_id}/faults",
    status_code=201,
    response_model=FaultInjectOut,
    dependencies=[Depends(require_api_key)],
)
async def inject_fault(run_id: str, body: FaultInjectIn, request: Request) -> FaultInjectOut:
    session_factory = request.app.state.session_factory

    def _validate_store():
        session = session_factory()
        try:
            run = session.get(models.Run, run_id)
            if run is None:
                raise HTTPException(status_code=404, detail="run not found")
            if body.fault_type not in FAULT_TYPES:
                raise HTTPException(
                    status_code=422,
                    detail=f"unknown fault_type {body.fault_type!r}; known: {sorted(FAULT_TYPES)}",
                )
            if not body.target_agent_id:
                raise HTTPException(status_code=422, detail="target_agent_id is required")
            participants = _run_participants(session, run_id)
            if body.target_agent_id not in participants:
                raise HTTPException(
                    status_code=422,
                    detail=f"agent {body.target_agent_id!r} is not part of run {run_id}",
                )
            if is_channel_fault(body.fault_type):
                if not body.source_agent_id:
                    raise HTTPException(
                        status_code=422,
                        detail=f"{body.fault_type} targets a channel: source_agent_id is required",
                    )
                if body.source_agent_id not in participants:
                    raise HTTPException(
                        status_code=422,
                        detail=f"agent {body.source_agent_id!r} is not part of run {run_id}",
                    )
            events = build_fault_events(run.project_id, run_id, body)
            stored, _ = process_events(session, events)
            return run.project_id, events[0].event_id, stored
        finally:
            session.close()

    project_id, fault_event_id, stored = await run_in_threadpool(_validate_store)

    manager = request.app.state.ws_manager
    out_events = [EventOut.model_validate(row) for row in stored]
    for event in out_events:
        await manager.broadcast(
            project_id, {"type": "event", "data": event.model_dump(mode="json")}
        )
    return FaultInjectOut(
        fault_event_id=fault_event_id, fault_type=body.fault_type, events=out_events
    )


@router.get("/runs/{run_id}/faults", response_model=list[EventOut])
def list_run_faults(run_id: str, session: Session = Depends(get_session)) -> list[EventOut]:
    if session.get(models.Run, run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")
    events = (
        session.execute(
            select(models.Event)
            .where(
                models.Event.run_id == run_id,
                models.Event.event_type.in_(["fault.injected", "attack.injected"]),
            )
            .order_by(models.Event.timestamp.desc(), models.Event.id.desc())
        )
        .scalars()
        .all()
    )
    return [EventOut.model_validate(event) for event in events]
