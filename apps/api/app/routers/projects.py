"""Project listing and detail."""
from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models
from ..deps import get_session
from ..schemas import AgentOut, ProjectDetailOut, ProjectOut, RunOut

router = APIRouter()


def runs_with_counts(
    session: Session, project_id: str, limit: int = 100
) -> list[RunOut]:
    runs = (
        session.execute(
            select(models.Run)
            .where(models.Run.project_id == project_id)
            .order_by(models.Run.started_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    run_ids = [run.id for run in runs]
    if not run_ids:
        return []

    message_counts = dict(
        session.execute(
            select(models.Message.run_id, func.count())
            .where(models.Message.run_id.in_(run_ids))
            .group_by(models.Message.run_id)
        ).all()
    )
    event_counts = dict(
        session.execute(
            select(models.Event.run_id, func.count())
            .where(models.Event.run_id.in_(run_ids))
            .group_by(models.Event.run_id)
        ).all()
    )
    agent_sets: dict[str, set[str]] = defaultdict(set)
    for run_id, src, tgt in session.execute(
        select(
            models.Event.run_id,
            models.Event.source_agent_id,
            models.Event.target_agent_id,
        ).where(models.Event.run_id.in_(run_ids))
    ):
        if src:
            agent_sets[run_id].add(src)
        if tgt:
            agent_sets[run_id].add(tgt)

    out: list[RunOut] = []
    for run in runs:
        item = RunOut.model_validate(run)
        item.message_count = message_counts.get(run.id, 0)
        item.event_count = event_counts.get(run.id, 0)
        item.agent_count = len(agent_sets.get(run.id, ()))
        out.append(item)
    return out


def _project_out(
    session: Session, project: models.Project
) -> ProjectOut:
    run_count = session.execute(
        select(func.count()).select_from(models.Run).where(models.Run.project_id == project.id)
    ).scalar_one()
    agent_count = session.execute(
        select(func.count())
        .select_from(models.Agent)
        .where(models.Agent.project_id == project.id)
    ).scalar_one()
    last_activity = session.execute(
        select(func.max(models.Event.timestamp)).where(models.Event.project_id == project.id)
    ).scalar_one()
    item = ProjectOut.model_validate(project)
    item.run_count = run_count
    item.agent_count = agent_count
    item.last_activity_at = last_activity
    return item


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(session: Session = Depends(get_session)) -> list[ProjectOut]:
    projects = (
        session.execute(select(models.Project).order_by(models.Project.created_at))
        .scalars()
        .all()
    )
    return [_project_out(session, project) for project in projects]


@router.get("/projects/{project_id}", response_model=ProjectDetailOut)
def get_project(
    project_id: str, session: Session = Depends(get_session)
) -> ProjectDetailOut:
    project = session.get(models.Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    agents = (
        session.execute(
            select(models.Agent)
            .where(models.Agent.project_id == project_id)
            .order_by(models.Agent.name)
        )
        .scalars()
        .all()
    )
    return ProjectDetailOut(
        project=_project_out(session, project),
        runs=runs_with_counts(session, project_id, limit=25),
        agents=[AgentOut.model_validate(agent) for agent in agents],
    )


@router.get("/projects/{project_id}/runs", response_model=list[RunOut])
def list_project_runs(
    project_id: str,
    limit: int = 100,
    session: Session = Depends(get_session),
) -> list[RunOut]:
    if session.get(models.Project, project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    return runs_with_counts(session, project_id, limit=min(limit, 500))
