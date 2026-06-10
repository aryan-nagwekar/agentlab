"""Derive the agent topology of a run: agents as nodes, message flows as edges."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models
from .events import FAILURE_EVENT_TYPES, LAB_EVENT_TYPES
from .schemas import GraphEdgeOut, GraphNodeOut, RunGraphOut


def build_run_graph(session: Session, run: models.Run) -> RunGraphOut:
    rows = session.execute(
        select(
            models.Event.event_type,
            models.Event.source_agent_id,
            models.Event.target_agent_id,
            models.Event.payload,
        )
        .where(models.Event.run_id == run.id)
        .order_by(models.Event.timestamp, models.Event.id)
    ).all()

    participants: set[str] = set()
    errors: dict[str, int] = defaultdict(int)
    agent_latencies: dict[str, list[float]] = defaultdict(list)
    tokens: dict[str, int] = defaultdict(int)
    costs: dict[str, float] = defaultdict(float)
    # Run-scoped state: a node on this run's topology reflects what happened
    # *in this run* (last lifecycle/trust event wins; rows are time-ordered),
    # falling back to the agent's current project-wide state.
    status_in_run: dict[str, str] = {}
    trust_in_run: dict[str, float] = {}
    risk_in_run: dict[str, float] = {}

    for etype, src, tgt, payload in rows:
        payload = payload or {}
        if etype not in LAB_EVENT_TYPES:
            # lab-controller is an operator, not a workflow participant
            for agent_id in (src, tgt):
                if agent_id:
                    participants.add(agent_id)
        if src:
            if etype == "agent.started":
                status_in_run[src] = "running"
            elif etype == "agent.completed":
                status_in_run[src] = "idle"
            elif etype == "agent.failed":
                status_in_run[src] = "failed"
            elif etype == "agent.quarantined":
                status_in_run[src] = "quarantined"
            elif etype == "agent.heartbeat" and payload.get("status"):
                status_in_run[src] = str(payload["status"])
            elif etype == "trust.updated" and payload.get("trust_score") is not None:
                try:
                    trust_in_run[src] = float(payload["trust_score"])
                except (TypeError, ValueError):
                    pass
            elif etype == "risk.updated" and payload.get("risk_score") is not None:
                try:
                    risk_in_run[src] = float(payload["risk_score"])
                except (TypeError, ValueError):
                    pass
        if etype in FAILURE_EVENT_TYPES and src:
            errors[src] += 1
        if (
            etype in ("agent.completed", "agent.failed")
            and src
            and payload.get("latency_ms") is not None
        ):
            agent_latencies[src].append(float(payload["latency_ms"]))
        if etype == "model.completed" and src:
            try:
                tokens[src] += int(payload.get("total_tokens") or 0)
            except (TypeError, ValueError):
                pass
            try:
                costs[src] += float(payload.get("cost_estimate") or 0.0)
            except (TypeError, ValueError):
                pass

    messages = (
        session.execute(
            select(models.Message)
            .where(models.Message.run_id == run.id)
            .order_by(models.Message.created_at)
        )
        .scalars()
        .all()
    )

    edge_data: dict[tuple[str, str], dict] = {}
    messages_in: dict[str, int] = defaultdict(int)
    messages_out: dict[str, int] = defaultdict(int)
    for message in messages:
        src = message.source_agent_id or "external"
        tgt = message.target_agent_id or "external"
        participants.add(src)
        participants.add(tgt)
        messages_out[src] += 1
        messages_in[tgt] += 1
        data = edge_data.setdefault(
            (src, tgt), {"count": 0, "latencies": [], "last_status": None, "last_at": None}
        )
        data["count"] += 1
        if message.latency_ms is not None:
            data["latencies"].append(message.latency_ms)
        data["last_status"] = message.status
        data["last_at"] = message.created_at

    tool_counts = dict(
        session.execute(
            select(models.ToolCall.agent_id, func.count())
            .where(models.ToolCall.run_id == run.id, models.ToolCall.agent_id.is_not(None))
            .group_by(models.ToolCall.agent_id)
        ).all()
    )

    agents: dict[str, models.Agent] = {}
    if participants:
        agents = {
            agent.id: agent
            for agent in session.execute(
                select(models.Agent).where(
                    models.Agent.project_id == run.project_id,
                    models.Agent.id.in_(sorted(participants)),
                )
            ).scalars()
        }

    nodes: list[GraphNodeOut] = []
    for agent_id in sorted(participants):
        agent = agents.get(agent_id)
        latencies = agent_latencies.get(agent_id, [])
        nodes.append(
            GraphNodeOut(
                id=agent_id,
                name=agent.name if agent else agent_id,
                role=agent.role if agent else None,
                status=status_in_run.get(agent_id, agent.status if agent else "unknown"),
                trust_score=trust_in_run.get(agent_id, agent.trust_score if agent else 1.0),
                risk_score=risk_in_run.get(agent_id, agent.risk_score if agent else 0.0),
                messages_in=messages_in.get(agent_id, 0),
                messages_out=messages_out.get(agent_id, 0),
                tool_calls=tool_counts.get(agent_id, 0),
                errors=errors.get(agent_id, 0),
                avg_latency_ms=round(sum(latencies) / len(latencies), 2) if latencies else None,
                tokens=tokens.get(agent_id, 0),
                cost_estimate=round(costs.get(agent_id, 0.0), 6),
            )
        )

    edges: list[GraphEdgeOut] = []
    for (src, tgt), data in edge_data.items():
        latencies = data["latencies"]
        edges.append(
            GraphEdgeOut(
                id=f"{src}->{tgt}",
                source=src,
                target=tgt,
                message_count=data["count"],
                avg_latency_ms=round(sum(latencies) / len(latencies), 2) if latencies else None,
                last_status=data["last_status"],
                last_message_at=data["last_at"],
            )
        )
    edges.sort(key=lambda e: e.id)

    return RunGraphOut(run_id=run.id, project_id=run.project_id, nodes=nodes, edges=edges)
