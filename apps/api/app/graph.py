"""Derive the agent topology of a run: agents as nodes, message flows as edges."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import costing, models, scoring
from .events import FAILURE_EVENT_TYPES, LAB_EVENT_TYPES
from .schemas import GraphEdgeOut, GraphNodeOut, RunGraphOut


def build_run_graph(session: Session, run: models.Run) -> RunGraphOut:
    rows = (
        session.execute(
            select(models.Event)
            .where(models.Event.run_id == run.id)
            .order_by(models.Event.timestamp, models.Event.id)
        )
        .scalars()
        .all()
    )

    participants: set[str] = set()
    errors: dict[str, int] = defaultdict(int)
    agent_latencies: dict[str, list[float]] = defaultdict(list)
    tokens: dict[str, int] = defaultdict(int)
    costs: dict[str, float] = defaultdict(float)
    # Run-scoped status: a node reflects what happened *in this run* (last
    # lifecycle event wins; rows are time-ordered).
    status_in_run: dict[str, str] = {}

    for event in rows:
        etype = event.event_type
        src = event.source_agent_id
        payload = event.payload or {}
        if etype not in LAB_EVENT_TYPES:
            # lab-controller is an operator, not a workflow participant
            for agent_id in (src, event.target_agent_id):
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
            elif etype == "agent.joined":
                status_in_run[src] = str(payload.get("status") or "running")
            elif etype == "agent.suspicious":
                if status_in_run.get(src) != "quarantined":
                    status_in_run[src] = "suspicious"
            elif etype == "agent.heartbeat" and payload.get("status"):
                status_in_run[src] = str(payload["status"])
        if etype in FAILURE_EVENT_TYPES and src:
            errors[src] += 1
        if (
            etype in ("agent.completed", "agent.failed")
            and src
            and payload.get("latency_ms") is not None
        ):
            agent_latencies[src].append(float(payload["latency_ms"]))

    # Tokens/cost per node come from the costing engine (pricing-derived).
    cost_agg = costing.aggregate(rows)
    for agent_id, agent_cost in cost_agg.agents.items():
        tokens[agent_id] = agent_cost.total_tokens
        costs[agent_id] = agent_cost.estimated_cost_usd

    # Trust/risk come from the deterministic scoring engine (single source of
    # truth shared with replay, the score endpoints, and the dashboard).
    scores = scoring.score_events(rows, seed=participants)

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
                trust_score=scores[agent_id].trust_score if agent_id in scores else 1.0,
                risk_score=scores[agent_id].risk_score if agent_id in scores else 0.0,
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
