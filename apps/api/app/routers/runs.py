"""Run detail, ordered event timeline (replay-ready), graph, and metrics."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import models
from ..deps import get_session
from ..graph import build_run_graph
from ..metrics import build_run_metrics
from ..schemas import EventOut, RunGraphOut, RunMetricsOut, RunOut

router = APIRouter()


def _get_run(session: Session, run_id: str) -> models.Run:
    run = session.get(models.Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: str, session: Session = Depends(get_session)) -> RunOut:
    run = _get_run(session, run_id)
    item = RunOut.model_validate(run)
    item.event_count = session.execute(
        select(func.count()).select_from(models.Event).where(models.Event.run_id == run_id)
    ).scalar_one()
    item.message_count = session.execute(
        select(func.count()).select_from(models.Message).where(models.Message.run_id == run_id)
    ).scalar_one()
    agent_rows = session.execute(
        select(models.Event.source_agent_id, models.Event.target_agent_id).where(
            models.Event.run_id == run_id
        )
    ).all()
    agents = {a for src, tgt in agent_rows for a in (src, tgt) if a}
    item.agent_count = len(agents)
    return item


@router.get("/runs/{run_id}/events", response_model=list[EventOut])
def list_run_events(
    run_id: str,
    event_type: str | None = Query(default=None, description="Exact event type filter"),
    agent_id: str | None = Query(default=None, description="Matches source or target"),
    limit: int = Query(default=2000, le=5000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[EventOut]:
    _get_run(session, run_id)
    query = (
        select(models.Event)
        .where(models.Event.run_id == run_id)
        .order_by(models.Event.timestamp, models.Event.id)
        .limit(limit)
        .offset(offset)
    )
    if event_type:
        query = query.where(models.Event.event_type == event_type)
    if agent_id:
        query = query.where(
            or_(
                models.Event.source_agent_id == agent_id,
                models.Event.target_agent_id == agent_id,
            )
        )
    events = session.execute(query).scalars().all()
    return [EventOut.model_validate(event) for event in events]


@router.get("/runs/{run_id}/graph", response_model=RunGraphOut)
def get_run_graph(run_id: str, session: Session = Depends(get_session)) -> RunGraphOut:
    run = _get_run(session, run_id)
    return build_run_graph(session, run)


@router.get("/runs/{run_id}/metrics", response_model=RunMetricsOut)
def get_run_metrics(run_id: str, session: Session = Depends(get_session)) -> RunMetricsOut:
    run = _get_run(session, run_id)
    return build_run_metrics(session, run)
