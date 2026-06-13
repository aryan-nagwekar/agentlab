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
        # Orchestration engine (v1.4) — workflow/task lifecycle metadata.
        # Status transitions only: no autonomous file/command/model execution
        # stands behind these events in v1.4.
        "runtime.workflow.created",
        "runtime.workflow.plan_requested",
        "runtime.workflow.plan_created",
        "runtime.workflow.started",
        "runtime.workflow.paused",
        "runtime.workflow.resumed",
        "runtime.workflow.cancelled",
        "runtime.workflow.blocked",
        "runtime.workflow.completed",
        "runtime.workflow.failed",
        "runtime.task.created",
        "runtime.task.assigned",
        "runtime.task.assignment_failed",
        "runtime.task.started",
        "runtime.task.completed",
        "runtime.task.failed",
        "runtime.task.blocked",
        "runtime.task.rerouted",
        "runtime.task.result_recorded",
        # Action enforcement gateway (v1.5) — proposals, deterministic policy
        # decisions, and execution markers. Approval RESOLUTION (v1.6), real
        # quarantine (v1.7), and validators (v1.8) do not exist yet; their
        # decisions are recorded here as explainable events only.
        "action.proposed",
        "policy.evaluated",
        "policy.rule.matched",
        "enforcement.allowed",
        "enforcement.blocked",
        "enforcement.approval_required",
        "enforcement.rerouted",
        "enforcement.retry_required",
        "enforcement.permissions_downgraded",
        "enforcement.quarantine_triggered",
        "action.started",
        "action.completed",
        "action.failed",
        # Human approval system (v1.6) — resolution of approval_required
        # enforcement decisions. Quarantine/reroute resolutions are recorded
        # events only (real quarantine v1.7, validators v1.8). Payloads carry
        # summaries and ids, never stored execution payloads.
        "approval.requested",
        "approval.approved",
        "approval.denied",
        "approval.cancelled",
        "approval.override_used",
        "approval.execution_resumed",
        "approval.execution_failed",
        "approval.execution_skipped",
        "approval.reroute_requested",
        "approval.quarantine_requested",
        # Real runtime quarantine (v1.7) — quarantine now actually restricts an
        # agent's runtime actions (not just a status marker). blocked_action
        # fires when a quarantined agent's action is refused pre-execution.
        "agent.quarantine.requested",
        "agent.quarantined",
        "agent.quarantine.enforced",
        "agent.quarantine.blocked_action",
        "agent.unquarantine.requested",
        "agent.unquarantined",
        "agent.permissions.restored",
    }
)

FAILURE_EVENT_TYPES: frozenset[str] = frozenset(
    {"agent.failed", "message.failed", "tool.failed", "model.failed"}
)

# Control-plane events emitted by Lab Mode. Their source ("lab-controller")
# is an operator action, not a workflow participant — graph/metrics/replay
# folds skip them when collecting topology participants.
LAB_EVENT_TYPES: frozenset[str] = frozenset({"fault.injected", "attack.injected"})
