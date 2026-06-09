"""Agent profile and recent activity."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import models
from ..deps import get_session
from ..schemas import AgentOut, EventOut

router = APIRouter()


def _find_agent(
    session: Session, agent_id: str, project_id: str | None
) -> models.Agent:
    if project_id:
        agent = session.get(models.Agent, {"project_id": project_id, "id": agent_id})
        if agent is None:
            raise HTTPException(status_code=404, detail="agent not found")
        return agent
    agents = (
        session.execute(select(models.Agent).where(models.Agent.id == agent_id))
        .scalars()
        .all()
    )
    if not agents:
        raise HTTPException(status_code=404, detail="agent not found")
    if len(agents) > 1:
        raise HTTPException(
            status_code=400,
            detail="agent id exists in multiple projects; pass ?project_id=",
        )
    return agents[0]


@router.get("/agents/{agent_id}", response_model=AgentOut)
def get_agent(
    agent_id: str,
    project_id: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> AgentOut:
    return AgentOut.model_validate(_find_agent(session, agent_id, project_id))


@router.get("/agents/{agent_id}/events", response_model=list[EventOut])
def list_agent_events(
    agent_id: str,
    project_id: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    limit: int = Query(default=200, le=2000),
    session: Session = Depends(get_session),
) -> list[EventOut]:
    agent = _find_agent(session, agent_id, project_id)
    query = (
        select(models.Event)
        .where(
            models.Event.project_id == agent.project_id,
            or_(
                models.Event.source_agent_id == agent_id,
                models.Event.target_agent_id == agent_id,
            ),
        )
        .order_by(models.Event.timestamp.desc(), models.Event.id.desc())
        .limit(limit)
    )
    if run_id:
        query = query.where(models.Event.run_id == run_id)
    events = session.execute(query).scalars().all()
    return [EventOut.model_validate(event) for event in events]
