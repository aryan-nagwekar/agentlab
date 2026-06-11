"""Cost & token attribution endpoints (v0.6).

Cost is derived on read from a run's model.* events via app/costing.py +
app/pricing.py — deterministic, reproducible, replayable. Mock providers only.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import costing, models
from ..costing import AgentCosting, RunCosting
from ..deps import get_session
from ..schemas import (
    AgentCostOut,
    ModelCostOut,
    ProjectCostSummaryOut,
    RunCostOut,
    RunTokenSummaryOut,
)

router = APIRouter()


def _ordered_run_events(session: Session, run_id: str) -> list[models.Event]:
    return list(
        session.execute(
            select(models.Event)
            .where(models.Event.run_id == run_id)
            .order_by(models.Event.timestamp, models.Event.id)
        )
        .scalars()
        .all()
    )


def _agent_out(agent: AgentCosting, name: str | None) -> AgentCostOut:
    return AgentCostOut(
        agent_id=agent.agent_id,
        agent_name=name,
        input_tokens=agent.input_tokens,
        output_tokens=agent.output_tokens,
        total_tokens=agent.total_tokens,
        estimated_cost_usd=agent.estimated_cost_usd,
        average_latency_ms=agent.average_latency_ms,
        p95_latency_ms=agent.p95_latency_ms,
        model_call_count=agent.model_call_count,
        failed_model_calls=agent.failed_model_call_count,
        retry_count=agent.retry_count,
        most_used_model=agent.most_used_model,
    )


def _model_out(model: costing.ModelCosting) -> ModelCostOut:
    return ModelCostOut(
        model_name=model.model_name,
        provider=model.provider,
        total_tokens=model.total_tokens,
        input_tokens=model.input_tokens,
        output_tokens=model.output_tokens,
        estimated_cost_usd=model.estimated_cost_usd,
        call_count=model.call_count,
        failure_count=model.failure_count,
        average_latency_ms=model.average_latency_ms,
    )


def _agent_names(session: Session, project_id: str) -> dict[str, str]:
    return {
        agent.id: agent.name
        for agent in session.execute(
            select(models.Agent).where(models.Agent.project_id == project_id)
        ).scalars()
    }


def _run_cost_out(run_id: str, run: RunCosting, names: dict[str, str]) -> RunCostOut:
    model_breakdown = sorted(
        (_model_out(m) for m in run.models.values()),
        key=lambda m: m.estimated_cost_usd,
        reverse=True,
    )
    agent_breakdown = sorted(
        (_agent_out(a, names.get(a.agent_id, a.agent_id)) for a in run.agents.values()),
        key=lambda a: a.estimated_cost_usd,
        reverse=True,
    )
    return RunCostOut(
        run_id=run_id,
        total_input_tokens=run.total_input_tokens,
        total_output_tokens=run.total_output_tokens,
        total_tokens=run.total_tokens,
        estimated_cost_usd=run.estimated_cost_usd,
        average_latency_ms=run.average_latency_ms,
        p95_latency_ms=run.p95_latency_ms,
        most_expensive_agent=costing._best(run.agents, "estimated_cost_usd"),
        most_token_heavy_agent=costing._best(run.agents, "total_tokens"),
        slowest_agent=costing._best(run.agents, "average_latency_ms"),
        highest_failure_agent=costing._best(run.agents, "failed_model_call_count"),
        model_breakdown=model_breakdown,
        agent_breakdown=agent_breakdown,
    )


@router.get("/runs/{run_id}/costs", response_model=RunCostOut)
def get_run_costs(run_id: str, session: Session = Depends(get_session)) -> RunCostOut:
    run = session.get(models.Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    costed = costing.aggregate(_ordered_run_events(session, run_id))
    return _run_cost_out(run_id, costed, _agent_names(session, run.project_id))


@router.get("/runs/{run_id}/token-summary", response_model=RunTokenSummaryOut)
def get_run_token_summary(
    run_id: str, session: Session = Depends(get_session)
) -> RunTokenSummaryOut:
    if session.get(models.Run, run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")
    run = costing.aggregate(_ordered_run_events(session, run_id))
    return RunTokenSummaryOut(
        run_id=run_id,
        total_input_tokens=run.total_input_tokens,
        total_output_tokens=run.total_output_tokens,
        total_tokens=run.total_tokens,
        model_breakdown=sorted(
            (_model_out(m) for m in run.models.values()),
            key=lambda m: m.total_tokens,
            reverse=True,
        ),
    )


@router.get("/agents/{agent_id}/costs", response_model=AgentCostOut)
def get_agent_costs(
    agent_id: str,
    project_id: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> AgentCostOut:
    agent = None
    if project_id:
        agent = session.get(models.Agent, {"project_id": project_id, "id": agent_id})
    else:
        found = (
            session.execute(select(models.Agent).where(models.Agent.id == agent_id))
            .scalars()
            .all()
        )
        if len(found) > 1:
            raise HTTPException(
                status_code=400, detail="agent id exists in multiple projects; pass ?project_id="
            )
        agent = found[0] if found else None
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")

    query = (
        select(models.Event)
        .where(
            models.Event.project_id == agent.project_id,
            models.Event.source_agent_id == agent_id,
            models.Event.event_type.in_(["model.called", "model.completed", "model.failed"]),
        )
        .order_by(models.Event.timestamp, models.Event.id)
    )
    if run_id:
        query = query.where(models.Event.run_id == run_id)
    run = costing.aggregate(list(session.execute(query).scalars().all()))
    costed = run.agents.get(agent_id, AgentCosting(agent_id))
    return _agent_out(costed, agent.name)


@router.get("/projects/{project_id}/cost-summary", response_model=ProjectCostSummaryOut)
def get_project_cost_summary(
    project_id: str, session: Session = Depends(get_session)
) -> ProjectCostSummaryOut:
    project = session.get(models.Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    events = list(
        session.execute(
            select(models.Event)
            .where(
                models.Event.project_id == project_id,
                models.Event.event_type.in_(["model.completed", "model.failed"]),
            )
            .order_by(models.Event.timestamp, models.Event.id)
        )
        .scalars()
        .all()
    )
    run = costing.aggregate(events)
    run_count = session.execute(
        select(models.Run.id).where(models.Run.project_id == project_id)
    ).all()
    return ProjectCostSummaryOut(
        project_id=project_id,
        total_tokens=run.total_tokens,
        estimated_cost_usd=run.estimated_cost_usd,
        run_count=len(run_count),
        model_breakdown=sorted(
            (_model_out(m) for m in run.models.values()),
            key=lambda m: m.estimated_cost_usd,
            reverse=True,
        ),
    )
