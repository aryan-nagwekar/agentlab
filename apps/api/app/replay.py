"""Replay support: jump markers over the ordered event tape, and pure
reconstruction of the topology at any cursor position.

`fold_events` and the dashboard's client-side reducer
(apps/web/src/components/replay/replayReducer.ts) implement the SAME semantics
over the same wire events — change one, change both.

Replay state is event-derived only (no projection-table fallback): the result
is the world *as of that point in the tape*. Agents referenced before their
`agent.started` appear as status "unknown" with default trust, mirroring the
collector's shell-agent behavior.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Sequence

from . import models
from .schemas import GraphEdgeOut, GraphNodeOut, ReplayMarkersOut, RunGraphOut


def compute_markers(events: Sequence[models.Event]) -> ReplayMarkersOut:
    errors: list[int] = []
    tool_calls: list[int] = []
    routing: list[int] = []
    messages: list[int] = []
    for index, event in enumerate(events):
        etype = event.event_type
        if etype.endswith(".failed"):  # includes run.failed — a jump target
            errors.append(index)
        if etype == "tool.called":
            tool_calls.append(index)
        if etype == "routing.decision":
            routing.append(index)
        if etype == "message.sent":
            messages.append(index)
    return ReplayMarkersOut(
        errors=errors, tool_calls=tool_calls, routing=routing, messages=messages
    )


def fold_events(run: models.Run, events: Sequence[models.Event]) -> RunGraphOut:
    participants: set[str] = set()
    names: dict[str, str] = {}
    roles: dict[str, str | None] = {}
    status: dict[str, str] = {}
    trust: dict[str, float] = {}
    risk: dict[str, float] = {}
    messages_in: dict[str, int] = defaultdict(int)
    messages_out: dict[str, int] = defaultdict(int)
    tool_calls: dict[str, int] = defaultdict(int)
    errors: dict[str, int] = defaultdict(int)
    latencies: dict[str, list[float]] = defaultdict(list)
    tokens: dict[str, int] = defaultdict(int)
    costs: dict[str, float] = defaultdict(float)
    edges: dict[tuple[str, str], dict[str, Any]] = {}

    for event in events:
        etype = event.event_type
        payload = event.payload or {}
        src = event.source_agent_id
        tgt = event.target_agent_id
        for agent_id in (src, tgt):
            if agent_id:
                participants.add(agent_id)

        if src:
            if etype == "agent.started":
                status[src] = "running"
                if payload.get("name"):
                    names[src] = str(payload["name"])
                if payload.get("role"):
                    roles[src] = str(payload["role"])
            elif etype == "agent.completed":
                status[src] = "idle"
            elif etype == "agent.failed":
                status[src] = "failed"
            elif etype == "agent.quarantined":
                status[src] = "quarantined"
            elif etype == "agent.heartbeat" and payload.get("status"):
                status[src] = str(payload["status"])
            elif etype == "trust.updated" and payload.get("trust_score") is not None:
                try:
                    trust[src] = float(payload["trust_score"])
                except (TypeError, ValueError):
                    pass
            elif etype == "risk.updated" and payload.get("risk_score") is not None:
                try:
                    risk[src] = float(payload["risk_score"])
                except (TypeError, ValueError):
                    pass

            if etype in ("agent.failed", "message.failed", "tool.failed", "model.failed"):
                errors[src] += 1
            if etype in ("agent.completed", "agent.failed") and payload.get("latency_ms") is not None:
                try:
                    latencies[src].append(float(payload["latency_ms"]))
                except (TypeError, ValueError):
                    pass
            if etype == "tool.called":
                tool_calls[src] += 1
            if etype == "model.completed":
                try:
                    tokens[src] += int(payload.get("total_tokens") or 0)
                except (TypeError, ValueError):
                    pass
                try:
                    costs[src] += float(payload.get("cost_estimate") or 0.0)
                except (TypeError, ValueError):
                    pass

        if etype in ("message.sent", "message.received", "message.failed"):
            source = src or "external"
            target = tgt or "external"
            participants.add(source)
            participants.add(target)
            key = (source, target)
            if etype == "message.sent":
                messages_out[source] += 1
                messages_in[target] += 1
                entry = edges.setdefault(
                    key, {"count": 0, "latencies": [], "last_status": None, "last_at": None}
                )
                entry["count"] += 1
                entry["last_status"] = "sent"
                entry["last_at"] = event.timestamp
            else:
                entry = edges.get(key)
                if entry is not None:
                    entry["last_status"] = "delivered" if etype == "message.received" else "failed"
                    entry["last_at"] = event.timestamp
                    if etype == "message.received" and payload.get("latency_ms") is not None:
                        try:
                            entry["latencies"].append(float(payload["latency_ms"]))
                        except (TypeError, ValueError):
                            pass

    nodes = [
        GraphNodeOut(
            id=agent_id,
            name=names.get(agent_id, agent_id),
            role=roles.get(agent_id),
            status=status.get(agent_id, "unknown"),
            trust_score=trust.get(agent_id, 1.0),
            risk_score=risk.get(agent_id, 0.0),
            messages_in=messages_in.get(agent_id, 0),
            messages_out=messages_out.get(agent_id, 0),
            tool_calls=tool_calls.get(agent_id, 0),
            errors=errors.get(agent_id, 0),
            avg_latency_ms=(
                round(sum(latencies[agent_id]) / len(latencies[agent_id]), 2)
                if latencies.get(agent_id)
                else None
            ),
            tokens=tokens.get(agent_id, 0),
            cost_estimate=round(costs.get(agent_id, 0.0), 6),
        )
        for agent_id in sorted(participants)
    ]

    edge_models = [
        GraphEdgeOut(
            id=f"{source}->{target}",
            source=source,
            target=target,
            message_count=entry["count"],
            avg_latency_ms=(
                round(sum(entry["latencies"]) / len(entry["latencies"]), 2)
                if entry["latencies"]
                else None
            ),
            last_status=entry["last_status"],
            last_message_at=entry["last_at"],
        )
        for (source, target), entry in edges.items()
    ]
    edge_models.sort(key=lambda e: e.id)

    return RunGraphOut(
        run_id=run.id, project_id=run.project_id, nodes=nodes, edges=edge_models
    )
