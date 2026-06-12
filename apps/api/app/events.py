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
        "score.updated",
        "fault.injected",
        "attack.injected",
        "agent.quarantined",
        # Runtime workspace lifecycle (v1.0) — metadata-only control-plane
        # events; no execution happens behind them.
        "workspace.created",
        "workspace.updated",
        "workspace.status_changed",
        "workspace.archived",
        "workspace.artifact_registered",
        # Workspace agent definitions (v1.1) — metadata-only control-plane
        # events; agents do not execute, write files, or enforce anything.
        "workspace_agent.created",
        "workspace_agent.updated",
        "workspace_agent.permission_changed",
        "workspace_agent.status_changed",
        "workspace_agent.deleted",
        "workspace_agent.template_instantiated",
        # Sandboxed file runtime (v1.2) — workspace-bounded file operations.
        # Payloads carry logical workspace paths and hashes, never host paths
        # or file content. No commands/builds/servers run behind these.
        "sandbox.initialized",
        "sandbox.file.created",
        "sandbox.file.updated",
        "sandbox.file.read",
        "sandbox.file.deleted",
        "sandbox.directory.created",
        "sandbox.file.blocked",
        # Safe command runner (v1.3) — allowlisted, workspace-bounded commands.
        # Deterministic safety decides before any process spawns; payloads
        # carry capped/redacted output summaries, never host paths or env.
        "sandbox.command.proposed",
        "sandbox.command.allowed",
        "sandbox.command.blocked",
        "sandbox.command.started",
        "sandbox.command.completed",
        "sandbox.command.failed",
        "sandbox.command.timed_out",
    }
)

FAILURE_EVENT_TYPES: frozenset[str] = frozenset(
    {"agent.failed", "message.failed", "tool.failed", "model.failed"}
)

# Control-plane events emitted by Lab Mode. Their source ("lab-controller")
# is an operator action, not a workflow participant — graph/metrics/replay
# folds skip them when collecting topology participants.
LAB_EVENT_TYPES: frozenset[str] = frozenset({"fault.injected", "attack.injected"})
