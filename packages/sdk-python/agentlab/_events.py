"""Event type registry and envelope construction.

The envelope produced here is the wire contract shared with the AgentLab
collector (`apps/api`). Keep the two registries in sync.
"""
from __future__ import annotations

import itertools
import uuid
from datetime import datetime, timezone
from typing import Any

SDK_NAME = "agentlab-python"
SDK_VERSION = "0.1.0"

# Run lifecycle
RUN_STARTED = "run.started"
RUN_COMPLETED = "run.completed"
RUN_FAILED = "run.failed"

# Agent lifecycle
AGENT_STARTED = "agent.started"
AGENT_COMPLETED = "agent.completed"
AGENT_FAILED = "agent.failed"
AGENT_HEARTBEAT = "agent.heartbeat"
AGENT_JOINED = "agent.joined"  # an agent (often simulated/malicious) joins the network
AGENT_SUSPICIOUS = "agent.suspicious"  # marked suspicious by Security Lab simulation

# Agent-to-agent messaging
MESSAGE_SENT = "message.sent"
MESSAGE_RECEIVED = "message.received"
MESSAGE_FAILED = "message.failed"
MESSAGE_FLAGGED = "message.flagged"  # message flagged as suspicious (simulated)

# Tool usage
TOOL_CALLED = "tool.called"
TOOL_COMPLETED = "tool.completed"
TOOL_FAILED = "tool.failed"

# Model usage
MODEL_CALLED = "model.called"
MODEL_COMPLETED = "model.completed"
MODEL_FAILED = "model.failed"

# Control plane
ROUTING_DECISION = "routing.decision"
TRUST_UPDATED = "trust.updated"
RISK_UPDATED = "risk.updated"
# Reserved/formalized: v0.5 derives score changes from outcome events rather
# than emitting these into the store (avoids scoring feedback loops).
SCORE_UPDATED = "score.updated"

# Lab / security simulation (emitted by Lab Mode in v0.3+, accepted from day one
# so the schema does not churn)
FAULT_INJECTED = "fault.injected"
ATTACK_INJECTED = "attack.injected"
AGENT_QUARANTINED = "agent.quarantined"

EVENT_TYPES: frozenset[str] = frozenset(
    {
        RUN_STARTED,
        RUN_COMPLETED,
        RUN_FAILED,
        AGENT_STARTED,
        AGENT_COMPLETED,
        AGENT_FAILED,
        AGENT_HEARTBEAT,
        AGENT_JOINED,
        AGENT_SUSPICIOUS,
        MESSAGE_SENT,
        MESSAGE_RECEIVED,
        MESSAGE_FAILED,
        MESSAGE_FLAGGED,
        TOOL_CALLED,
        TOOL_COMPLETED,
        TOOL_FAILED,
        MODEL_CALLED,
        MODEL_COMPLETED,
        MODEL_FAILED,
        ROUTING_DECISION,
        TRUST_UPDATED,
        RISK_UPDATED,
        SCORE_UPDATED,
        FAULT_INJECTED,
        ATTACK_INJECTED,
        AGENT_QUARANTINED,
    }
)

_sequence = itertools.count(1)


def utc_now_iso() -> str:
    """Current UTC time as ISO-8601 with millisecond precision and a Z suffix."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_id(prefix: str = "") -> str:
    suffix = uuid.uuid4().hex[:12]
    return f"{prefix}-{suffix}" if prefix else uuid.uuid4().hex


def build_event(
    event_type: str,
    *,
    project_id: str,
    run_id: str,
    source_agent_id: str | None = None,
    target_agent_id: str | None = None,
    payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    if event_type not in EVENT_TYPES:
        raise ValueError(
            f"Unknown event_type {event_type!r}. Known types: {sorted(EVENT_TYPES)}"
        )
    meta = dict(metadata or {})
    meta.setdefault("_seq", next(_sequence))
    meta.setdefault("sdk", f"{SDK_NAME}/{SDK_VERSION}")
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "timestamp": timestamp or utc_now_iso(),
        "project_id": project_id,
        "run_id": run_id,
        "source_agent_id": source_agent_id,
        "target_agent_id": target_agent_id,
        "payload": payload or {},
        "metadata": meta,
    }
