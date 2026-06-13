"""Real Runtime Quarantine (v1.7).

Upgrades quarantine from a status marker into an enforced restriction. A
quarantined WorkspaceAgent cannot perform mutating runtime actions: the v1.5
enforcement gateway's ``block-unassignable-actor`` rule already refuses any
action proposed by a quarantined actor before execution, and v1.7 wires the
*real* lifecycle around it — manual quarantine/unquarantine, quarantine
applied from an approval resolution or an extreme-risk enforcement decision,
existing assigned tasks blocked on quarantine, and a quarantine-specific
``agent.quarantine.blocked_action`` audit event.

Bookkeeping lives in ``agent.meta["quarantine"]`` (not new columns) so it
works on existing local databases without a migration; it is surfaced as a
dedicated ``quarantine`` field on the agent and preserved across metadata
PATCHes. Quarantine never weakens v1.2 path safety or v1.3 command safety —
it sits in front of them.

Out of scope (later versions): validators (v1.8), the visual debugger
(v1.9), autonomous execution, a full agent-to-agent message system.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as core_models
from ..timeutil import isoz, utcnow
from .models import RuntimeTask, RuntimeWorkflow, Workspace, WorkspaceAgent
from .sandbox import SandboxError
from .service import _emit

# Reserved key under agent.meta; the quarantine service is its only writer.
META_KEY = "quarantine"

# Status restored on unquarantine when the pre-quarantine status was itself
# unassignable (or unknown).
DEFAULT_RESTORE_STATUS = "ready"
_NON_RESTORABLE = frozenset({"quarantined", "disabled"})


def quarantine_info(agent: WorkspaceAgent) -> dict[str, Any] | None:
    return (agent.meta or {}).get(META_KEY)


def is_quarantined(agent: WorkspaceAgent) -> bool:
    return agent.status == "quarantined"


def _public_metadata(agent: WorkspaceAgent) -> dict[str, Any]:
    """Agent metadata with the quarantine bookkeeping key removed."""
    return {k: v for k, v in (agent.meta or {}).items() if k != META_KEY}


def _set_info(agent: WorkspaceAgent, info: dict[str, Any] | None) -> None:
    meta = {k: v for k, v in (agent.meta or {}).items() if k != META_KEY}
    if info is not None:
        meta[META_KEY] = info
    agent.meta = meta


def _block_assigned_tasks(
    session: Session, workspace: Workspace, agent: WorkspaceAgent
) -> list[core_models.Event]:
    """Existing pending/running tasks for a newly-quarantined agent become
    blocked with a clear reason (the workflow can reroute them in the UI)."""
    tasks = session.execute(
        select(RuntimeTask).where(
            RuntimeTask.workspace_id == workspace.id,
            RuntimeTask.assigned_agent_id == agent.id,
            RuntimeTask.status.in_(("pending", "running")),
        )
    ).scalars()
    stored: list[core_models.Event] = []
    for task in tasks:
        task.status = "blocked"
        task.meta = {**(task.meta or {}), "blocked_reason": "assigned agent quarantined"}
        stored += _emit(
            session,
            workspace,
            "runtime.task.blocked",
            {
                "workflow_id": task.workflow_id,
                "task_id": task.id,
                "assigned_agent_id": agent.id,
                "reason": "assigned agent quarantined",
            },
        )
    return stored


def quarantine_agent(
    session: Session,
    workspace: Workspace,
    agent: WorkspaceAgent,
    *,
    reason: str,
    requested_by: str,
    source_action_id: str | None = None,
    source_approval_id: str | None = None,
    policy_rules: list[dict[str, str]] | None = None,
) -> list[core_models.Event]:
    """Apply real quarantine. Idempotent: re-quarantining is a no-op."""
    if agent.status == "quarantined":
        return []
    previous_status = agent.status
    info = {
        "reason": reason[:500],
        "requested_by": requested_by[:255],
        "quarantined_at": isoz(utcnow()),
        "source_action_id": source_action_id,
        "source_approval_id": source_approval_id,
        "policy_rules": policy_rules or [],
        "previous_status": previous_status,
        "lifted_at": None,
        "lifted_by": None,
        "lift_reason": None,
    }
    _set_info(agent, info)
    agent.status = "quarantined"

    safe = {
        "agent_id": agent.id,
        "reason": reason[:500],
        "requested_by": requested_by[:255],
        **({"source_action_id": source_action_id} if source_action_id else {}),
        **({"source_approval_id": source_approval_id} if source_approval_id else {}),
        **({"matched_rules": policy_rules} if policy_rules else {}),
    }
    stored = _emit(session, workspace, "agent.quarantine.requested", safe)
    stored += _emit(
        session,
        workspace,
        "workspace_agent.status_changed",
        {"agent_id": agent.id, "from_status": previous_status, "to_status": "quarantined"},
    )
    stored += _emit(session, workspace, "agent.quarantined", safe)
    blocked = _block_assigned_tasks(session, workspace, agent)
    stored += _emit(
        session,
        workspace,
        "agent.quarantine.enforced",
        {**safe, "blocked_task_count": len(blocked)},
    )
    stored += blocked
    return stored


def unquarantine_agent(
    session: Session,
    workspace: Workspace,
    agent: WorkspaceAgent,
    *,
    requested_by: str,
    reason: str | None = None,
) -> list[core_models.Event]:
    """Lift quarantine and restore a usable status. Requires an explicit
    caller — quarantine is never lifted implicitly."""
    if agent.status != "quarantined":
        raise SandboxError("agent is not quarantined", status_code=409)
    info = dict(quarantine_info(agent) or {})
    previous = info.get("previous_status", DEFAULT_RESTORE_STATUS)
    restore = previous if previous not in _NON_RESTORABLE else DEFAULT_RESTORE_STATUS
    info.update(
        {
            "lifted_at": isoz(utcnow()),
            "lifted_by": requested_by[:255],
            "lift_reason": (reason or "")[:500] or None,
        }
    )
    _set_info(agent, info)
    agent.status = restore

    safe = {"agent_id": agent.id, "requested_by": requested_by[:255], "restored_status": restore}
    if reason:
        safe["reason"] = reason[:500]
    stored = _emit(session, workspace, "agent.unquarantine.requested", safe)
    stored += _emit(
        session,
        workspace,
        "workspace_agent.status_changed",
        {"agent_id": agent.id, "from_status": "quarantined", "to_status": restore},
    )
    stored += _emit(session, workspace, "agent.unquarantined", safe)
    stored += _emit(session, workspace, "agent.permissions.restored", safe)
    return stored


def blocked_action_event(
    session: Session,
    workspace: Workspace,
    agent_id: str,
    *,
    action_type: str,
    target: str,
    reason: str,
) -> list[core_models.Event]:
    """Emitted alongside enforcement.blocked when a quarantined agent's
    action is refused — the quarantine-specific audit signal."""
    return _emit(
        session,
        workspace,
        "agent.quarantine.blocked_action",
        {
            "agent_id": agent_id,
            "blocked_action_type": action_type,
            "target": target[:200],
            "reason": reason,
        },
    )


def quarantine_events(
    session: Session, workspace_id: str, run_id: str, limit: int = 100
) -> list[core_models.Event]:
    """Quarantine history is an event query — raw events stay the source of truth."""
    like_prefixes = ("agent.quarantine", "agent.unquarantine", "agent.quarantined", "agent.permissions.restored")
    rows = (
        session.execute(
            select(core_models.Event)
            .where(core_models.Event.run_id == run_id)
            .order_by(core_models.Event.timestamp.desc(), core_models.Event.id.desc())
            .limit(500)
        )
        .scalars()
        .all()
    )
    matched = [
        e
        for e in rows
        if e.event_type.startswith(like_prefixes) or e.event_type == "agent.quarantined"
    ]
    return matched[: max(1, min(limit, 200))]
