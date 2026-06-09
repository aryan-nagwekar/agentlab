"""Event type registry. Must stay in sync with packages/sdk-python/agentlab/_events.py."""
from __future__ import annotations

EVENT_TYPES: frozenset[str] = frozenset(
    {
        "run.started",
        "run.completed",
        "run.failed",
        "agent.started",
        "agent.completed",
        "agent.failed",
        "agent.heartbeat",
        "message.sent",
        "message.received",
        "message.failed",
        "tool.called",
        "tool.completed",
        "tool.failed",
        "model.called",
        "model.completed",
        "model.failed",
        "routing.decision",
        "trust.updated",
        "risk.updated",
        "fault.injected",
        "attack.injected",
        "agent.quarantined",
    }
)

FAILURE_EVENT_TYPES: frozenset[str] = frozenset(
    {"agent.failed", "message.failed", "tool.failed", "model.failed"}
)
