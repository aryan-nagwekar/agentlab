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

# Runtime workspaces (v1.0) — metadata-only lifecycle events emitted by the
# server's workspace APIs; no execution happens behind them.
WORKSPACE_CREATED = "workspace.created"
WORKSPACE_UPDATED = "workspace.updated"
WORKSPACE_STATUS_CHANGED = "workspace.status_changed"
WORKSPACE_ARCHIVED = "workspace.archived"
WORKSPACE_ARTIFACT_REGISTERED = "workspace.artifact_registered"

# Workspace agent definitions (v1.1) — metadata-only control-plane events
# emitted by the server's workspace-agent APIs; nothing executes behind them.
WORKSPACE_AGENT_CREATED = "workspace_agent.created"
WORKSPACE_AGENT_UPDATED = "workspace_agent.updated"
WORKSPACE_AGENT_PERMISSION_CHANGED = "workspace_agent.permission_changed"
WORKSPACE_AGENT_STATUS_CHANGED = "workspace_agent.status_changed"
WORKSPACE_AGENT_DELETED = "workspace_agent.deleted"
WORKSPACE_AGENT_TEMPLATE_INSTANTIATED = "workspace_agent.template_instantiated"

# Sandboxed file runtime (v1.2) — workspace-bounded file operations emitted by
# the server's sandbox APIs. Payloads carry logical workspace paths and
# hashes, never host paths or file content; nothing executes behind them.
SANDBOX_INITIALIZED = "sandbox.initialized"
SANDBOX_FILE_CREATED = "sandbox.file.created"
SANDBOX_FILE_UPDATED = "sandbox.file.updated"
SANDBOX_FILE_READ = "sandbox.file.read"
SANDBOX_FILE_DELETED = "sandbox.file.deleted"
SANDBOX_DIRECTORY_CREATED = "sandbox.directory.created"
SANDBOX_FILE_BLOCKED = "sandbox.file.blocked"

# Safe command runner (v1.3) — allowlisted, workspace-bounded commands emitted
# by the server's sandbox command APIs. Deterministic safety decides before
# any process spawns; payloads carry capped/redacted output summaries only.
SANDBOX_COMMAND_PROPOSED = "sandbox.command.proposed"
SANDBOX_COMMAND_ALLOWED = "sandbox.command.allowed"
SANDBOX_COMMAND_BLOCKED = "sandbox.command.blocked"
SANDBOX_COMMAND_STARTED = "sandbox.command.started"
SANDBOX_COMMAND_COMPLETED = "sandbox.command.completed"
SANDBOX_COMMAND_FAILED = "sandbox.command.failed"
SANDBOX_COMMAND_TIMED_OUT = "sandbox.command.timed_out"

# Orchestration engine (v1.4) — workflow/task lifecycle metadata emitted by
# the server's runtime orchestrator. Status transitions only: no autonomous
# file/command/model execution stands behind these events in v1.4.
RUNTIME_WORKFLOW_CREATED = "runtime.workflow.created"
RUNTIME_WORKFLOW_PLAN_REQUESTED = "runtime.workflow.plan_requested"
RUNTIME_WORKFLOW_PLAN_CREATED = "runtime.workflow.plan_created"
RUNTIME_WORKFLOW_STARTED = "runtime.workflow.started"
RUNTIME_WORKFLOW_PAUSED = "runtime.workflow.paused"
RUNTIME_WORKFLOW_RESUMED = "runtime.workflow.resumed"
RUNTIME_WORKFLOW_CANCELLED = "runtime.workflow.cancelled"
RUNTIME_WORKFLOW_BLOCKED = "runtime.workflow.blocked"
RUNTIME_WORKFLOW_COMPLETED = "runtime.workflow.completed"
RUNTIME_WORKFLOW_FAILED = "runtime.workflow.failed"
RUNTIME_TASK_CREATED = "runtime.task.created"
RUNTIME_TASK_ASSIGNED = "runtime.task.assigned"
RUNTIME_TASK_ASSIGNMENT_FAILED = "runtime.task.assignment_failed"
RUNTIME_TASK_STARTED = "runtime.task.started"
RUNTIME_TASK_COMPLETED = "runtime.task.completed"
RUNTIME_TASK_FAILED = "runtime.task.failed"
RUNTIME_TASK_BLOCKED = "runtime.task.blocked"
RUNTIME_TASK_REROUTED = "runtime.task.rerouted"
RUNTIME_TASK_RESULT_RECORDED = "runtime.task.result_recorded"

# Action enforcement gateway (v1.5) — proposals, deterministic policy
# decisions, and execution markers emitted by the server's gateway. Approval
# resolution (v1.6), real quarantine (v1.7), and validators (v1.8) do not
# exist yet; their decisions are recorded as explainable events only.
ACTION_PROPOSED = "action.proposed"
POLICY_EVALUATED = "policy.evaluated"
POLICY_RULE_MATCHED = "policy.rule.matched"
ENFORCEMENT_ALLOWED = "enforcement.allowed"
ENFORCEMENT_BLOCKED = "enforcement.blocked"
ENFORCEMENT_APPROVAL_REQUIRED = "enforcement.approval_required"
ENFORCEMENT_REROUTED = "enforcement.rerouted"
ENFORCEMENT_RETRY_REQUIRED = "enforcement.retry_required"
ENFORCEMENT_PERMISSIONS_DOWNGRADED = "enforcement.permissions_downgraded"
ENFORCEMENT_QUARANTINE_TRIGGERED = "enforcement.quarantine_triggered"
ACTION_STARTED = "action.started"
ACTION_COMPLETED = "action.completed"
ACTION_FAILED = "action.failed"

# Human approval system (v1.6) — resolution of approval_required enforcement
# decisions, emitted by the server. Quarantine/reroute resolutions are
# recorded events only (real quarantine v1.7, validators v1.8).
APPROVAL_REQUESTED = "approval.requested"
APPROVAL_APPROVED = "approval.approved"
APPROVAL_DENIED = "approval.denied"
APPROVAL_CANCELLED = "approval.cancelled"
APPROVAL_OVERRIDE_USED = "approval.override_used"
APPROVAL_EXECUTION_RESUMED = "approval.execution_resumed"
APPROVAL_EXECUTION_FAILED = "approval.execution_failed"
APPROVAL_EXECUTION_SKIPPED = "approval.execution_skipped"
APPROVAL_REROUTE_REQUESTED = "approval.reroute_requested"
APPROVAL_QUARANTINE_REQUESTED = "approval.quarantine_requested"

# Real runtime quarantine (v1.7) — quarantine now actually restricts an agent's
# runtime actions. agent.quarantine.blocked_action fires when a quarantined
# agent's action is refused before execution.
AGENT_QUARANTINE_REQUESTED = "agent.quarantine.requested"
AGENT_QUARANTINED = "agent.quarantined"
AGENT_QUARANTINE_ENFORCED = "agent.quarantine.enforced"
AGENT_QUARANTINE_BLOCKED_ACTION = "agent.quarantine.blocked_action"
AGENT_UNQUARANTINE_REQUESTED = "agent.unquarantine.requested"
AGENT_UNQUARANTINED = "agent.unquarantined"
AGENT_PERMISSIONS_RESTORED = "agent.permissions.restored"

# Deterministic validators (v1.8) — evidence-based checks emitted by the
# server's validator service. Payloads carry redacted evidence summaries and
# risk/trust scoring signals; never raw secrets/content/host paths.
VALIDATOR_STARTED = "validator.started"
VALIDATOR_COMPLETED = "validator.completed"
VALIDATOR_FAILED = "validator.failed"
VALIDATION_PASSED = "validation.passed"
VALIDATION_FAILED = "validation.failed"
CLAIM_VERIFIED = "claim.verified"
CLAIM_REJECTED = "claim.rejected"
SCHEMA_MISMATCH_DETECTED = "schema.mismatch.detected"
RUNTIME_ERROR_DETECTED = "runtime.error.detected"
APP_ERROR_TRANSLATED = "app.error.translated"
RISKY_FILE_CHANGE_DETECTED = "risky.file_change.detected"
SECRET_EXPOSURE_DETECTED = "secret.exposure.detected"

# Live agent execution (v3.0) — a single governed build pass emitted by the
# server: one model call, then enforcement-gated file writes.
AGENT_BUILD_STARTED = "agent.build.started"
AGENT_BUILD_COMPLETED = "agent.build.completed"
AGENT_BUILD_FAILED = "agent.build.failed"

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
        WORKSPACE_CREATED,
        WORKSPACE_UPDATED,
        WORKSPACE_STATUS_CHANGED,
        WORKSPACE_ARCHIVED,
        WORKSPACE_ARTIFACT_REGISTERED,
        WORKSPACE_AGENT_CREATED,
        WORKSPACE_AGENT_UPDATED,
        WORKSPACE_AGENT_PERMISSION_CHANGED,
        WORKSPACE_AGENT_STATUS_CHANGED,
        WORKSPACE_AGENT_DELETED,
        WORKSPACE_AGENT_TEMPLATE_INSTANTIATED,
        SANDBOX_INITIALIZED,
        SANDBOX_FILE_CREATED,
        SANDBOX_FILE_UPDATED,
        SANDBOX_FILE_READ,
        SANDBOX_FILE_DELETED,
        SANDBOX_DIRECTORY_CREATED,
        SANDBOX_FILE_BLOCKED,
        SANDBOX_COMMAND_PROPOSED,
        SANDBOX_COMMAND_ALLOWED,
        SANDBOX_COMMAND_BLOCKED,
        SANDBOX_COMMAND_STARTED,
        SANDBOX_COMMAND_COMPLETED,
        SANDBOX_COMMAND_FAILED,
        SANDBOX_COMMAND_TIMED_OUT,
        RUNTIME_WORKFLOW_CREATED,
        RUNTIME_WORKFLOW_PLAN_REQUESTED,
        RUNTIME_WORKFLOW_PLAN_CREATED,
        RUNTIME_WORKFLOW_STARTED,
        RUNTIME_WORKFLOW_PAUSED,
        RUNTIME_WORKFLOW_RESUMED,
        RUNTIME_WORKFLOW_CANCELLED,
        RUNTIME_WORKFLOW_BLOCKED,
        RUNTIME_WORKFLOW_COMPLETED,
        RUNTIME_WORKFLOW_FAILED,
        RUNTIME_TASK_CREATED,
        RUNTIME_TASK_ASSIGNED,
        RUNTIME_TASK_ASSIGNMENT_FAILED,
        RUNTIME_TASK_STARTED,
        RUNTIME_TASK_COMPLETED,
        RUNTIME_TASK_FAILED,
        RUNTIME_TASK_BLOCKED,
        RUNTIME_TASK_REROUTED,
        RUNTIME_TASK_RESULT_RECORDED,
        ACTION_PROPOSED,
        POLICY_EVALUATED,
        POLICY_RULE_MATCHED,
        ENFORCEMENT_ALLOWED,
        ENFORCEMENT_BLOCKED,
        ENFORCEMENT_APPROVAL_REQUIRED,
        ENFORCEMENT_REROUTED,
        ENFORCEMENT_RETRY_REQUIRED,
        ENFORCEMENT_PERMISSIONS_DOWNGRADED,
        ENFORCEMENT_QUARANTINE_TRIGGERED,
        ACTION_STARTED,
        ACTION_COMPLETED,
        ACTION_FAILED,
        APPROVAL_REQUESTED,
        APPROVAL_APPROVED,
        APPROVAL_DENIED,
        APPROVAL_CANCELLED,
        APPROVAL_OVERRIDE_USED,
        APPROVAL_EXECUTION_RESUMED,
        APPROVAL_EXECUTION_FAILED,
        APPROVAL_EXECUTION_SKIPPED,
        APPROVAL_REROUTE_REQUESTED,
        APPROVAL_QUARANTINE_REQUESTED,
        AGENT_QUARANTINE_REQUESTED,
        AGENT_QUARANTINED,
        AGENT_QUARANTINE_ENFORCED,
        AGENT_QUARANTINE_BLOCKED_ACTION,
        AGENT_UNQUARANTINE_REQUESTED,
        AGENT_UNQUARANTINED,
        AGENT_PERMISSIONS_RESTORED,
        VALIDATOR_STARTED,
        VALIDATOR_COMPLETED,
        VALIDATOR_FAILED,
        VALIDATION_PASSED,
        VALIDATION_FAILED,
        CLAIM_VERIFIED,
        CLAIM_REJECTED,
        SCHEMA_MISMATCH_DETECTED,
        RUNTIME_ERROR_DETECTED,
        APP_ERROR_TRANSLATED,
        RISKY_FILE_CHANGE_DETECTED,
        SECRET_EXPOSURE_DETECTED,
        AGENT_BUILD_STARTED,
        AGENT_BUILD_COMPLETED,
        AGENT_BUILD_FAILED,
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
