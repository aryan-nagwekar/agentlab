"""Ingest pipeline: validate -> persist raw event -> update projections.

Projections are intentionally forgiving: events may reference agents or runs
that have not announced themselves yet (shell rows are created), and replaying
the same event_id is a no-op, so SDK retries are always safe.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, scoring
from .events import FAILURE_EVENT_TYPES
from .schemas import EventIn
from .timeutil import to_utc_naive, utcnow


def _ensure_project(session: Session, project_id: str) -> models.Project:
    project = session.get(models.Project, project_id)
    if project is None:
        project = models.Project(id=project_id, name=project_id)
        session.add(project)
        session.flush()
    return project


def _ensure_run(session: Session, event: EventIn, ts) -> models.Run:
    run = session.get(models.Run, event.run_id)
    if run is None:
        run = models.Run(
            id=event.run_id,
            project_id=event.project_id,
            status="running",
            started_at=ts,
        )
        session.add(run)
        session.flush()
    return run


def _ensure_agent(session: Session, project_id: str, agent_id: str, ts) -> models.Agent:
    agent = session.get(models.Agent, {"project_id": project_id, "id": agent_id})
    if agent is None:
        agent = models.Agent(
            project_id=project_id,
            id=agent_id,
            name=agent_id,
            status="unknown",
            created_at=ts,
            last_seen_at=ts,
        )
        session.add(agent)
        session.flush()
    return agent


def _message_id(event: EventIn) -> str:
    return str(event.metadata.get("message_id") or event.event_id)


def _tool_call_id(event: EventIn) -> str:
    return str(event.metadata.get("tool_call_id") or event.event_id)


def process_events(
    session: Session, events: list[EventIn]
) -> tuple[list[models.Event], int]:
    """Persist a batch. Returns (stored ORM rows, duplicate count). Commits."""
    stored: list[models.Event] = []
    duplicates = 0
    for item in events:
        exists = session.execute(
            select(models.Event.id).where(models.Event.event_id == item.event_id)
        ).first()
        if exists:
            duplicates += 1
            continue

        ts = to_utc_naive(item.timestamp) if item.timestamp else utcnow()
        _ensure_project(session, item.project_id)

        row = models.Event(
            event_id=item.event_id,
            event_type=item.event_type,
            timestamp=ts,
            project_id=item.project_id,
            run_id=item.run_id,
            source_agent_id=item.source_agent_id,
            target_agent_id=item.target_agent_id,
            payload=item.payload,
            meta=item.metadata,
        )
        session.add(row)
        session.flush()  # assign autoincrement id while preserving arrival order
        _apply_projection(session, item, ts)
        stored.append(row)

    session.commit()
    return stored, duplicates


def _apply_projection(session: Session, event: EventIn, ts) -> None:
    etype = event.event_type
    payload = event.payload or {}
    run = _ensure_run(session, event, ts)

    # Any referenced agent gets a row immediately so topology/trust queries
    # never miss participants (e.g. an "external" message source).
    for agent_id in (event.source_agent_id, event.target_agent_id):
        if agent_id:
            agent = _ensure_agent(session, event.project_id, agent_id, ts)
            agent.last_seen_at = ts

    if etype == "run.started":
        run.status = "running"
        run.started_at = run.started_at or ts
        if payload.get("name"):
            run.name = str(payload["name"])

    elif etype in ("run.completed", "run.failed"):
        run.status = "completed" if etype == "run.completed" else "failed"
        run.completed_at = ts
        if payload.get("total_latency_ms") is not None:
            run.total_latency_ms = float(payload["total_latency_ms"])
        _finalize_run(session, run)

    elif etype == "agent.started":
        agent = _ensure_agent(session, event.project_id, event.source_agent_id or "unknown", ts)
        agent.status = "running"
        if payload.get("name"):
            agent.name = str(payload["name"])
        if payload.get("role"):
            agent.role = str(payload["role"])

    elif etype == "agent.completed":
        agent = _ensure_agent(session, event.project_id, event.source_agent_id or "unknown", ts)
        agent.status = "idle"

    elif etype == "agent.failed":
        agent = _ensure_agent(session, event.project_id, event.source_agent_id or "unknown", ts)
        agent.status = "failed"

    elif etype == "agent.heartbeat":
        agent = _ensure_agent(session, event.project_id, event.source_agent_id or "unknown", ts)
        if payload.get("status"):
            agent.status = str(payload["status"])

    elif etype == "agent.joined":
        agent = _ensure_agent(session, event.project_id, event.source_agent_id or "unknown", ts)
        agent.status = str(payload.get("status") or "running")
        if payload.get("name"):
            agent.name = str(payload["name"])
        if payload.get("role"):
            agent.role = str(payload["role"])

    elif etype == "agent.suspicious":
        agent = _ensure_agent(session, event.project_id, event.source_agent_id or "unknown", ts)
        # Don't override a stronger quarantined state.
        if agent.status != "quarantined":
            agent.status = "suspicious"
        if payload.get("name"):
            agent.name = str(payload["name"])
        if payload.get("role"):
            agent.role = str(payload["role"])

    elif etype == "agent.quarantined":
        agent = _ensure_agent(session, event.project_id, event.source_agent_id or "unknown", ts)
        agent.status = "quarantined"

    elif etype == "message.sent":
        mid = _message_id(event)
        message = session.get(models.Message, mid)
        if message is None:
            session.add(
                models.Message(
                    id=mid,
                    project_id=event.project_id,
                    run_id=event.run_id,
                    source_agent_id=event.source_agent_id,
                    target_agent_id=event.target_agent_id,
                    content=payload.get("content"),
                    status="sent",
                    created_at=ts,
                )
            )

    elif etype == "message.received":
        mid = _message_id(event)
        message = session.get(models.Message, mid)
        if message is None:
            message = models.Message(
                id=mid,
                project_id=event.project_id,
                run_id=event.run_id,
                source_agent_id=event.source_agent_id,
                target_agent_id=event.target_agent_id,
                content=payload.get("content"),
                created_at=ts,
            )
            session.add(message)
        message.status = "delivered"
        if payload.get("latency_ms") is not None:
            message.latency_ms = float(payload["latency_ms"])

    elif etype == "message.failed":
        mid = _message_id(event)
        message = session.get(models.Message, mid)
        if message is not None:
            message.status = "failed"

    elif etype == "message.flagged":
        mid = _message_id(event)
        message = session.get(models.Message, mid)
        if message is None:
            message = models.Message(
                id=mid,
                project_id=event.project_id,
                run_id=event.run_id,
                source_agent_id=event.source_agent_id,
                target_agent_id=event.target_agent_id,
                content=payload.get("content"),
                created_at=ts,
            )
            session.add(message)
        message.status = "flagged"

    elif etype == "tool.called":
        tid = _tool_call_id(event)
        if session.get(models.ToolCall, tid) is None:
            session.add(
                models.ToolCall(
                    id=tid,
                    project_id=event.project_id,
                    run_id=event.run_id,
                    agent_id=event.source_agent_id,
                    tool_name=str(payload.get("tool_name") or "unknown"),
                    input=payload.get("input"),
                    status="running",
                    created_at=ts,
                )
            )

    elif etype in ("tool.completed", "tool.failed"):
        tid = _tool_call_id(event)
        call = session.get(models.ToolCall, tid)
        if call is None:
            call = models.ToolCall(
                id=tid,
                project_id=event.project_id,
                run_id=event.run_id,
                agent_id=event.source_agent_id,
                tool_name=str(payload.get("tool_name") or "unknown"),
                input=payload.get("input"),
                created_at=ts,
            )
            session.add(call)
        call.status = "completed" if etype == "tool.completed" else "failed"
        if etype == "tool.completed":
            call.output = payload.get("output")
        else:
            call.output = {"error": payload.get("error")}
        if payload.get("latency_ms") is not None:
            call.latency_ms = float(payload["latency_ms"])

    elif etype == "routing.decision":
        if session.get(models.RoutingDecision, event.event_id) is None:
            session.add(
                models.RoutingDecision(
                    id=event.event_id,
                    project_id=event.project_id,
                    run_id=event.run_id,
                    source_agent_id=event.source_agent_id,
                    selected_agent_id=str(
                        payload.get("selected_agent_id")
                        or event.target_agent_id
                        or "unknown"
                    ),
                    candidate_agents=payload.get("candidate_agents"),
                    reason=payload.get("reason"),
                    confidence=payload.get("confidence"),
                    created_at=ts,
                )
            )

    # Trust/risk are owned by the scoring engine (v0.5). Applying the same
    # rule table here keeps the stored Agent row consistent with the run-scoped
    # fold used by the graph/replay/score endpoints — and fixes the v0.4 bug
    # where a quarantined agent could still read trust 1.0.
    subject = scoring.subject_of(event)
    if subject:
        agent = _ensure_agent(session, event.project_id, subject, ts)
        agent.trust_score, agent.risk_score = scoring.score_values(
            agent.trust_score, agent.risk_score, event
        )

    if etype in FAILURE_EVENT_TYPES:
        run.error_count = (run.error_count or 0) + 1


def _finalize_run(session: Session, run: models.Run) -> None:
    """Recompute authoritative aggregates when a run finishes."""
    model_events = (
        session.execute(
            select(models.Event.payload).where(
                models.Event.run_id == run.id,
                models.Event.event_type == "model.completed",
            )
        )
        .scalars()
        .all()
    )
    tokens = 0
    cost = 0.0
    for payload in model_events:
        payload = payload or {}
        try:
            tokens += int(payload.get("total_tokens") or 0)
        except (TypeError, ValueError):
            pass
        try:
            cost += float(payload.get("cost_estimate") or 0.0)
        except (TypeError, ValueError):
            pass
    run.total_tokens = tokens
    run.total_cost_estimate = round(cost, 6)

    failures = (
        session.execute(
            select(models.Event.id).where(
                models.Event.run_id == run.id,
                models.Event.event_type.in_(sorted(FAILURE_EVENT_TYPES)),
            )
        )
        .scalars()
        .all()
    )
    run.error_count = len(failures)

    if run.total_latency_ms is None and run.started_at and run.completed_at:
        run.total_latency_ms = (run.completed_at - run.started_at).total_seconds() * 1000
