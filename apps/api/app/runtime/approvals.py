"""Human Approval System (v1.6).

Resolves the enforcement gateway's ``require_human_approval`` decisions.
When v1.5 halts an action, an ApprovalRequest is created (deduplicated per
unresolved action) carrying a plain-English summary, the matched rules, a
risk level, and — for the integrated file/command surfaces — the exact
stored payload needed to resume the action verbatim. The payload is never
mutable through the API and never appears in events.

Resolutions: approve / approve_once re-execute the stored action only
through the existing safe executors (sandbox file service, v1.3 command
runner — whose own safety re-runs and may still refuse); deny blocks it;
approve_readonly executes only a safe read-only path (otherwise records a
skip); reroute and quarantine are recorded as events/metadata ONLY — real
runtime quarantine arrives in v1.7 and validators in v1.8. Every transition
emits approval.* events through the normal pipeline, so the timeline and
replay reconstruct who resolved what, when, and what happened next.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from sqlalchemy.orm import Session

from .. import models as core_models
from . import commands, sandbox
from .commands import _redact
from .models import (
    ActionDecision,
    ActionProposal,
    ApprovalRequest,
    Workspace,
    WorkspaceAgent,
)
from .sandbox import SandboxBlocked, SandboxError
from .service import _emit

# Deciding rule → (risk level, recommended decision). Conservative defaults:
# protected domains are high-risk and recommended for denial unless expected.
_RULE_RISK: dict[str, tuple[str, str]] = {
    "approval-protected-action": ("high", "deny"),
    "approval-sensitive-file": ("high", "approve_once"),
    "approval-sensitive-command": ("medium", "approve_once"),
    "approval-high-risk-publish": ("high", "deny"),
    "approval-flagged-task-result": ("medium", "approve_once"),
}

ALL_OPTIONS = ["approve", "approve_once", "approve_readonly", "deny", "reroute", "quarantine"]


def get_approval(
    session: Session, workspace_id: str, approval_id: str
) -> ApprovalRequest | None:
    approval = session.get(ApprovalRequest, approval_id)
    if approval is None or approval.workspace_id != workspace_id:
        return None
    return approval


def list_approvals(
    session: Session, workspace_id: str, status: str | None = None, limit: int = 50
) -> list[ApprovalRequest]:
    query = select(ApprovalRequest).where(ApprovalRequest.workspace_id == workspace_id)
    if status:
        query = query.where(ApprovalRequest.status == status)
    return list(
        session.execute(
            query.order_by(
                ApprovalRequest.created_at.desc(), ApprovalRequest.id.desc()
            ).limit(max(1, min(limit, 200)))
        ).scalars()
    )


def pending_count(session: Session, workspace_id: str) -> int:
    from sqlalchemy import func

    return session.execute(
        select(func.count(ApprovalRequest.id)).where(
            ApprovalRequest.workspace_id == workspace_id,
            ApprovalRequest.status == "pending",
        )
    ).scalar_one()


def _pending_duplicate(
    session: Session, workspace: Workspace, proposal: ActionProposal
) -> ApprovalRequest | None:
    """An unresolved approval for the same action (same type + target)."""
    candidates = session.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.workspace_id == workspace.id,
            ApprovalRequest.status == "pending",
        )
    ).scalars()
    for candidate in candidates:
        meta = candidate.meta or {}
        if (
            meta.get("action_type") == proposal.action_type
            and meta.get("target") == proposal.target
        ):
            return candidate
    return None


def ensure_approval(
    session: Session,
    workspace: Workspace,
    proposal: ActionProposal,
    decision: ActionDecision,
    execution_payload: dict[str, Any] | None = None,
) -> tuple[ApprovalRequest, list[core_models.Event]]:
    """Create (or reuse) the pending ApprovalRequest for a halted action."""
    existing = _pending_duplicate(session, workspace, proposal)
    if existing is not None:
        # Same unresolved action proposed again: point the approval at the
        # newest proposal/payload, but do not create a duplicate inbox entry.
        existing.action_id = proposal.id
        meta = dict(existing.meta or {})
        if execution_payload is not None:
            meta["execution"] = execution_payload
        existing.meta = meta
        return existing, []

    deciding_rule = (decision.matched_rules or [{}])[0].get("id", "policy")
    risk_level, recommended = _RULE_RISK.get(deciding_rule, ("medium", "approve_once"))
    target = proposal.target or proposal.action_type
    approval = ApprovalRequest(
        id=f"apr-{uuid.uuid4().hex[:10]}",
        workspace_id=workspace.id,
        run_id=workspace.activity_run_id,
        workflow_id=proposal.workflow_id,
        task_id=proposal.task_id,
        action_id=proposal.id,
        agent_id=proposal.agent_id,
        title=f"{proposal.action_type}: {target}"[:255],
        plain_english_summary=(
            f"AgentLab paused this action because {decision.reason}. "
            f"Approving lets the stored action run exactly as proposed; "
            f"denying keeps it blocked."
        ),
        technical_summary=(
            f"action_type={proposal.action_type} target={target} "
            f"actor={proposal.actor_type}"
            + (f" agent={proposal.agent_id}" if proposal.agent_id else "")
            + f" deciding_rule={deciding_rule} decision_id={decision.id}"
        ),
        risk_level=risk_level,
        matched_policy_rules=decision.matched_rules or [],
        recommended_decision=recommended,
        options=list(ALL_OPTIONS),
        meta={
            "action_type": proposal.action_type,
            "target": proposal.target,
            **({"execution": execution_payload} if execution_payload else {}),
        },
    )
    session.add(approval)
    session.flush()
    stored = _emit(
        session,
        workspace,
        "approval.requested",
        {
            "approval_id": approval.id,
            "action_id": proposal.id,
            "decision_id": decision.id,
            "action_type": proposal.action_type,
            "target": proposal.target[:200],
            "risk_level": risk_level,
            "deciding_rule": deciding_rule,
            "recommended_decision": recommended,
        },
    )
    return approval, stored


# ------------------------------------------------------------------ resolve


def _approval_event(
    session: Session,
    workspace: Workspace,
    approval: ApprovalRequest,
    event_type: str,
    payload: dict[str, Any],
) -> list[core_models.Event]:
    return _emit(
        session,
        workspace,
        event_type,
        {
            "approval_id": approval.id,
            "action_id": approval.action_id,
            "action_type": (approval.meta or {}).get("action_type", ""),
            **payload,
        },
    )


def _execute_approved(
    session: Session,
    workspace: Workspace,
    workspaces_root: str,
    approval: ApprovalRequest,
    *,
    readonly: bool,
) -> tuple[str, str | None, list[core_models.Event]]:
    """Resume the exact stored action through existing safe executors only.
    Returns (execution_status, detail, events). The executors' own v1.2/v1.3
    safety re-runs here — an approval never bypasses path/command checks."""
    meta = approval.meta or {}
    action_type = meta.get("action_type", "")
    payload = meta.get("execution") or {}

    try:
        if readonly:
            if action_type == "file.read" and meta.get("target"):
                result, events = sandbox.read_file(
                    session, workspace, workspaces_root, meta["target"]
                )
                return "executed", f"read {result['path']} ({result['size_bytes']} B)", events
            return (
                "skipped",
                "read-only approval recorded; this action type has no safe "
                "read-only execution path",
                [],
            )
        if action_type == "file.write" and "content" in payload:
            result, events = sandbox.write_file(
                session, workspace, workspaces_root, payload["path"], payload["content"]
            )
            return "executed", f"wrote {result['path']} ({result['size_bytes']} B)", events
        if action_type == "file.delete" and payload.get("path"):
            result, events = sandbox.delete_path(
                session, workspace, workspaces_root, payload["path"]
            )
            return "executed", f"deleted {result['path']}", events
        if action_type == "directory.create" and payload.get("path"):
            result, events = sandbox.make_dir(
                session, workspace, workspaces_root, payload["path"]
            )
            return "executed", f"created {result['path']}/", events
        if action_type == "command.run" and payload.get("command"):
            # run_command re-evaluates v1.3 safety; a command that no longer
            # passes is refused here even though the approval was granted.
            result, events = commands.run_command(
                session,
                workspace,
                workspaces_root,
                command=payload["command"],
                args=list(payload.get("args", [])),
                timeout_seconds=int(payload.get("timeout_seconds", 30)),
                working_subdir=str(payload.get("working_subdir", "")),
            )
            return (
                "executed",
                f"command {result['status']} (exit {result['exit_code']})",
                events,
            )
        return (
            "skipped",
            "approved, but this action type has no safe executor path yet — "
            "recorded without execution",
            [],
        )
    except SandboxBlocked as blocked:
        return (
            "execution_failed",
            f"safety re-check refused execution ({blocked.rule}): {blocked.reason}",
            list(blocked.events),
        )
    except SandboxError as failed:
        return "execution_failed", failed.detail, []


_EXECUTION_EVENTS = {
    "executed": "approval.execution_resumed",
    "execution_failed": "approval.execution_failed",
    "skipped": "approval.execution_skipped",
}


def resolve(
    session: Session,
    workspace: Workspace,
    workspaces_root: str,
    approval: ApprovalRequest,
    *,
    decision: str,
    resolved_by: str,
    reason: str | None,
) -> tuple[ApprovalRequest, list[core_models.Event]]:
    if approval.status != "pending":
        raise SandboxError(
            f"approval is already {approval.status} and cannot be resolved again",
            status_code=409,
        )
    from ..timeutil import utcnow

    approval.resolution_decision = decision
    approval.resolved_at = utcnow()
    approval.resolved_by = resolved_by[:255]
    approval.resolution_reason = _redact(reason or "")[:1000] or None
    proposal = session.get(ActionProposal, approval.action_id)
    stored: list[core_models.Event] = []
    common = {
        "decision": decision,
        "resolved_by": approval.resolved_by,
        **({"reason": approval.resolution_reason} if approval.resolution_reason else {}),
        "risk_level": approval.risk_level,
    }

    if decision in ("approve", "approve_once", "approve_readonly"):
        approval.status = "approved"
        stored += _approval_event(session, workspace, approval, "approval.approved", common)
        if decision == "approve_readonly":
            stored += _approval_event(
                session, workspace, approval, "approval.override_used",
                {**common, "override": "readonly"},
            )
        stored += _emit(
            session,
            workspace,
            "action.started",
            {
                "action_id": approval.action_id,
                "action_type": (approval.meta or {}).get("action_type", ""),
                "resumed_from_approval": approval.id,
            },
        )
        status, detail, events = _execute_approved(
            session, workspace, workspaces_root, approval,
            readonly=decision == "approve_readonly",
        )
        approval.execution_status = status
        approval.execution_detail = detail
        stored += events
        stored += _emit(
            session,
            workspace,
            "action.completed" if status == "executed" else "action.failed",
            {
                "action_id": approval.action_id,
                "resumed_from_approval": approval.id,
                "outcome": status,
            },
        )
        stored += _approval_event(
            session, workspace, approval, _EXECUTION_EVENTS[status],
            {**common, "execution_detail": (detail or "")[:300]},
        )
        if proposal is not None:
            proposal.status = {
                "executed": "completed",
                "execution_failed": "failed",
                "skipped": "allowed",
            }[status]
    elif decision == "deny":
        approval.status = "denied"
        if proposal is not None:
            proposal.status = "blocked"
        stored += _approval_event(session, workspace, approval, "approval.denied", common)
    elif decision == "reroute":
        approval.status = "rerouted"
        stored += _approval_event(
            session, workspace, approval, "approval.override_used",
            {**common, "override": "reroute"},
        )
        stored += _approval_event(
            session, workspace, approval, "approval.reroute_requested", common
        )
        # Recorded for a human to act on in the Workflows panel — no
        # autonomous reassignment happens here.
    elif decision == "quarantine":
        approval.status = "quarantine_requested"
        stored += _approval_event(
            session, workspace, approval, "approval.override_used",
            {**common, "override": "quarantine"},
        )
        stored += _approval_event(
            session, workspace, approval, "approval.quarantine_requested",
            {**common, **({"agent_id": approval.agent_id} if approval.agent_id else {})},
        )
        stored += _emit(
            session,
            workspace,
            "enforcement.quarantine_triggered",
            {
                "action_id": approval.action_id,
                "source": "approval_resolution",
                "approval_id": approval.id,
                **({"agent_id": approval.agent_id} if approval.agent_id else {}),
                "reason": "quarantine requested by human during approval review",
            },
        )
        # v1.7: apply REAL quarantine when the approval is linked to an agent.
        if approval.agent_id:
            from . import quarantine

            agent = session.get(
                WorkspaceAgent, {"workspace_id": workspace.id, "id": approval.agent_id}
            )
            if agent is not None:
                stored += quarantine.quarantine_agent(
                    session,
                    workspace,
                    agent,
                    reason=approval.resolution_reason
                    or "quarantine requested by human during approval review",
                    requested_by=resolved_by,
                    source_action_id=approval.action_id,
                    source_approval_id=approval.id,
                    policy_rules=approval.matched_policy_rules,
                )
    else:
        raise SandboxError(f"unknown resolution decision {decision!r}")
    return approval, stored


def cancel(
    session: Session,
    workspace: Workspace,
    approval: ApprovalRequest,
    *,
    resolved_by: str,
    reason: str | None,
) -> tuple[ApprovalRequest, list[core_models.Event]]:
    if approval.status != "pending":
        raise SandboxError(
            f"approval is already {approval.status} and cannot be cancelled",
            status_code=409,
        )
    from ..timeutil import utcnow

    approval.status = "cancelled"
    approval.resolved_at = utcnow()
    approval.resolved_by = resolved_by[:255]
    approval.resolution_reason = _redact(reason or "")[:1000] or None
    stored = _approval_event(
        session, workspace, approval, "approval.cancelled",
        {"resolved_by": approval.resolved_by},
    )
    return approval, stored
