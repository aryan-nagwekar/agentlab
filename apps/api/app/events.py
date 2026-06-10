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
        "agent.joined",
        "agent.suspicious",
        "message.sent",
        "message.received",
        "message.failed",
        "message.flagged",
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

# Control-plane events emitted by Lab Mode. Their source ("lab-controller")
# is an operator action, not a workflow participant — graph/metrics/replay
# folds skip them when collecting topology participants.
LAB_EVENT_TYPES: frozenset[str] = frozenset({"fault.injected", "attack.injected"})
