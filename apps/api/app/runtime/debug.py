"""Visual Project Debugging aggregation (v1.9).

Read-only, deterministic comprehension layer over the existing Runtime
systems. It derives a beginner-friendly project-health summary, a
recommended-next-action list, an issues list, and a lite project map by
aggregating data that already exists — workspaces, agents, workflows/tasks,
enforcement decisions, approvals, validators, quarantine state, and the
workspace activity-run events. It creates no new runtime behavior, mutates
nothing, and emits no events.

Everything it returns is grounded in already-redacted/bounded sources
(events exclude host paths; validator evidence is pre-redacted), and it
re-asserts that boundary by only surfacing logical paths and short summaries.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from sqlalchemy.orm import Session

from .. import models as core_models
from . import approvals, enforcement, orchestration, sandbox, service, validators
from .models import Workspace

# How far back the "recent" aggregations look.
_RECENT_EVENT_LIMIT = 200

# Beginner-friendly health states, worst (highest severity) first. The primary
# state is the first one whose signal is present.
_HEALTH_ORDER: list[tuple[str, str]] = [
    ("agent_restricted", "Agent restricted"),
    ("approval_needed", "Needs approval"),
    ("validation_failed", "Verification failed"),
    ("blocked", "Blocked"),
    ("build_test_failed", "Build/test failed"),
    ("action_blocked", "Action blocked"),
    ("risky_change", "Risky change"),
    ("safe_to_continue", "Safe to continue"),
    ("no_signals", "No signals yet"),
]
_HEALTH_LABEL = dict(_HEALTH_ORDER)


def _recent_events(session: Session, run_id: str) -> list[core_models.Event]:
    return list(
        session.execute(
            select(core_models.Event)
            .where(core_models.Event.run_id == run_id)
            .order_by(core_models.Event.timestamp.desc(), core_models.Event.id.desc())
            .limit(_RECENT_EVENT_LIMIT)
        ).scalars()
    )


def _collect(session: Session, workspace: Workspace, workspaces_root: str) -> dict[str, Any]:
    """One read pass over every Runtime surface for this workspace."""
    agents = service.list_agents(session, workspace.id)
    workflows = orchestration.list_workflows(session, workspace.id)
    tasks = [t for wf in workflows for t in orchestration.list_tasks(session, wf.id)]
    decisions = enforcement.list_decisions(session, workspace.id, limit=50)
    pending_approvals = approvals.list_approvals(session, workspace.id, status="pending")
    validator_results = validators.list_results(session, workspace.id, limit=50)
    events = _recent_events(session, workspace.activity_run_id)
    sandbox_status = sandbox.status(workspace, workspaces_root)
    return {
        "agents": agents,
        "workflows": workflows,
        "tasks": tasks,
        "decisions": decisions,
        "pending_approvals": pending_approvals,
        "validator_results": validator_results,
        "events": events,
        "sandbox": sandbox_status,
    }


# ----------------------------------------------------------------- signals


def _signals(data: dict[str, Any]) -> dict[str, Any]:
    quarantined = [a for a in data["agents"] if a.status == "quarantined"]
    disabled = [a for a in data["agents"] if a.status == "disabled"]
    failed_validators = [r for r in data["validator_results"] if not r.passed]
    blocked_decisions = [d for d in data["decisions"] if d.decision == "block"]
    approval_decisions = [
        d for d in data["decisions"] if d.decision == "require_human_approval"
    ]
    blocked_tasks = [t for t in data["tasks"] if t.status == "blocked"]
    failed_tasks = [t for t in data["tasks"] if t.status == "failed"]
    failed_workflows = [w for w in data["workflows"] if w.status in ("failed", "blocked")]
    event_types = [e.event_type for e in data["events"]]
    failed_commands = sum(
        1 for t in event_types if t in ("sandbox.command.failed", "sandbox.command.timed_out")
    )
    risky_events = sum(
        1 for t in event_types
        if t in ("secret.exposure.detected", "risky.file_change.detected")
    )
    # "Meaningful" activity excludes bare workspace.* lifecycle events, so a
    # freshly created (but untouched) workspace reads as "no signals yet".
    has_meaningful = bool(
        data["agents"]
        or data["workflows"]
        or data["validator_results"]
        or data["decisions"]
        or data["sandbox"].get("file_count")
        or any(not t.startswith("workspace.") for t in event_types)
    )
    return {
        "quarantined": quarantined,
        "disabled": disabled,
        "failed_validators": failed_validators,
        "blocked_decisions": blocked_decisions,
        "approval_decisions": approval_decisions,
        "blocked_tasks": blocked_tasks,
        "failed_tasks": failed_tasks,
        "failed_workflows": failed_workflows,
        "failed_commands": failed_commands,
        "risky_events": risky_events,
        "pending_approvals": data["pending_approvals"],
        "has_activity": has_meaningful,
    }


def _health(sig: dict[str, Any]) -> dict[str, Any]:
    present: list[str] = []
    if sig["quarantined"]:
        present.append("agent_restricted")
    if sig["pending_approvals"]:
        present.append("approval_needed")
    if sig["failed_validators"]:
        present.append("validation_failed")
    if sig["blocked_tasks"] or sig["failed_tasks"] or sig["failed_workflows"]:
        present.append("blocked")
    if sig["failed_commands"]:
        present.append("build_test_failed")
    if sig["blocked_decisions"]:
        present.append("action_blocked")
    if sig["risky_events"]:
        present.append("risky_change")

    if present:
        primary = next(state for state, _ in _HEALTH_ORDER if state in present)
        severity = "high" if primary in (
            "agent_restricted", "approval_needed", "validation_failed", "blocked"
        ) else "medium"
    elif sig["has_activity"]:
        primary = "safe_to_continue"
        severity = "ok"
        present = ["safe_to_continue"]
    else:
        primary = "no_signals"
        severity = "none"
        present = ["no_signals"]

    return {
        "state": primary,
        "label": _HEALTH_LABEL[primary],
        "severity": severity,
        "active_labels": [_HEALTH_LABEL[s] for s in present],
    }


# ------------------------------------------------------- recommended actions


def _recommended_actions(data: dict[str, Any], sig: dict[str, Any]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    if sig["pending_approvals"]:
        n = len(sig["pending_approvals"])
        actions.append({
            "action": "review_approval",
            "label": f"Review {n} pending approval{'s' if n > 1 else ''}",
            "link": "approvals",
        })
    if sig["failed_validators"]:
        n = len(sig["failed_validators"])
        actions.append({
            "action": "fix_validation",
            "label": f"Fix {n} validation failure{'s' if n > 1 else ''}",
            "link": "validators",
        })
    if sig["quarantined"]:
        actions.append({
            "action": "inspect_agent",
            "label": "Inspect or unquarantine a restricted agent",
            "link": "agents",
        })
    if sig["blocked_tasks"]:
        actions.append({
            "action": "reroute_task",
            "label": "Reroute a blocked task to another agent",
            "link": "workflows",
        })
    if sig["failed_commands"]:
        actions.append({
            "action": "fix_command",
            "label": "Fix the failing command and re-run",
            "link": "commands",
        })
    if not data["sandbox"]["initialized"]:
        actions.append({
            "action": "init_sandbox",
            "label": "Initialize the workspace sandbox",
            "link": "files",
        })
    if not data["workflows"]:
        actions.append({
            "action": "create_workflow",
            "label": "Create a workflow from the workspace goal",
            "link": "workflows",
        })
    if not actions:
        actions.append({
            "action": "none",
            "label": "No action needed — safe to continue",
            "link": "",
        })
    return actions


# ----------------------------------------------------------------- issues


def _issues(data: dict[str, Any], sig: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for r in sig["failed_validators"]:
        issues.append({
            "severity": "high",
            "kind": "validation_failed",
            "title": f"Verification failed: {r.validator_type}",
            "detail": (r.meta or {}).get("explanation", "")[:300]
            or (r.failures[0] if r.failures else ""),
            "suggested_action": r.suggested_action,
            "link": "validators",
            "ref": r.id,
        })
    for a in sig["quarantined"]:
        info = (a.meta or {}).get("quarantine", {})
        issues.append({
            "severity": "high",
            "kind": "agent_restricted",
            "title": f"Agent restricted: {a.name}",
            "detail": info.get("reason", "this agent is quarantined")[:300],
            "suggested_action": "inspect, then unquarantine if safe",
            "link": "agents",
            "ref": a.id,
        })
    for ap in sig["pending_approvals"]:
        issues.append({
            "severity": "high",
            "kind": "approval_needed",
            "title": f"Needs approval: {ap.title}",
            "detail": ap.plain_english_summary[:300],
            "suggested_action": f"recommended: {ap.recommended_decision}",
            "link": "approvals",
            "ref": ap.id,
        })
    for t in sig["blocked_tasks"]:
        issues.append({
            "severity": "medium",
            "kind": "blocked_task",
            "title": f"Blocked task: {t.title}",
            "detail": (t.meta or {}).get("blocked_reason", "task is blocked")[:300],
            "suggested_action": "reroute to an available agent",
            "link": "workflows",
            "ref": t.id,
        })
    for w in sig["failed_workflows"]:
        issues.append({
            "severity": "medium",
            "kind": "workflow_problem",
            "title": f"Workflow {w.status}: {w.goal[:60]}",
            "detail": f"workflow is {w.status}",
            "suggested_action": "open the workflow to resolve blocked tasks",
            "link": "workflows",
            "ref": w.id,
        })
    for d in sig["blocked_decisions"][:5]:
        rule = (d.matched_rules or [{}])[0].get("name", "policy")
        issues.append({
            "severity": "medium",
            "kind": "action_blocked",
            "title": f"Action blocked: {d.reason[:60]}",
            "detail": f"matched rule: {rule}",
            "suggested_action": None,
            "link": "enforcement",
            "ref": d.id,
        })
    # Failed/timed-out commands from events.
    for e in data["events"]:
        if e.event_type in ("sandbox.command.failed", "sandbox.command.timed_out"):
            payload = e.payload or {}
            issues.append({
                "severity": "medium",
                "kind": "command_failed",
                "title": f"Command failed: {str(payload.get('command', ''))[:60]}",
                "detail": e.event_type.replace("sandbox.command.", "")
                + (f" (exit {payload.get('exit_code')})" if payload.get("exit_code") is not None else ""),
                "suggested_action": "fix and re-run the command",
                "link": "commands",
                "ref": e.event_id,
            })
            if sum(1 for i in issues if i["kind"] == "command_failed") >= 5:
                break
    return issues


# ------------------------------------------------- agents / workflow / map


def _agents_overview(data: dict[str, Any]) -> dict[str, Any]:
    by_status: dict[str, list[dict[str, Any]]] = {}
    for a in data["agents"]:
        assigned = next(
            (t.title for t in data["tasks"]
             if t.assigned_agent_id == a.id and t.status in ("running", "pending")),
            None,
        )
        by_status.setdefault(a.status, []).append({
            "agent_id": a.id,
            "name": a.name,
            "role": a.role,
            "trust_score": a.trust_score,
            "risk_score": a.risk_score,
            "current_assignment": assigned,
            "restricted": a.status in ("quarantined", "disabled"),
        })
    return {"total": len(data["agents"]), "by_status": by_status}


def _workflow_progress(data: dict[str, Any]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    for t in data["tasks"]:
        status_counts[t.status] = status_counts.get(t.status, 0) + 1
    return {
        "workflow_count": len(data["workflows"]),
        "active_workflows": [
            {"workflow_id": w.id, "goal": w.goal[:120], "status": w.status}
            for w in data["workflows"]
            if w.status in ("planned", "running", "paused", "blocked")
        ],
        "task_status_counts": status_counts,
        "blocked_tasks": [
            {"task_id": t.id, "title": t.title,
             "reason": (t.meta or {}).get("blocked_reason", "")}
            for t in data["tasks"] if t.status == "blocked"
        ],
    }


def _validation_summary(data: dict[str, Any]) -> dict[str, Any]:
    recent = data["validator_results"][:8]
    return {
        "total": len(data["validator_results"]),
        "failed": sum(1 for r in data["validator_results"] if not r.passed),
        "recent": [
            {
                "result_id": r.id,
                "validator_type": r.validator_type,
                "passed": r.passed,
                "target_ref": r.target_ref,
                "explanation": (r.meta or {}).get("explanation", "")[:200],
                "suggested_action": r.suggested_action,
            }
            for r in recent
        ],
    }


def _enforcement_summary(data: dict[str, Any]) -> dict[str, Any]:
    recent = data["decisions"][:8]
    return {
        "pending_approvals": len(data["pending_approvals"]),
        "recent_decisions": [
            {
                "decision_id": d.id,
                "decision": d.decision,
                "action_type": d.meta.get("action_type") if d.meta else None,
                "reason": d.reason[:200],
                "matched_rule": (d.matched_rules or [{}])[0].get("name", ""),
            }
            for d in recent
            if d.decision in ("block", "require_human_approval", "reroute_to_verifier")
        ],
    }


# Event type → (category, beginner label).
_CHANGE_CATEGORIES: dict[str, tuple[str, str]] = {
    "sandbox.file.created": ("files", "File created"),
    "sandbox.file.updated": ("files", "File updated"),
    "sandbox.file.deleted": ("files", "File deleted"),
    "sandbox.command.completed": ("commands", "Command ran"),
    "sandbox.command.failed": ("commands", "Command failed"),
    "runtime.workflow.created": ("workflows", "Workflow created"),
    "runtime.workflow.completed": ("workflows", "Workflow completed"),
    "runtime.task.completed": ("workflows", "Task completed"),
    "runtime.task.blocked": ("workflows", "Task blocked"),
    "enforcement.blocked": ("enforcement", "Action blocked"),
    "enforcement.approval_required": ("enforcement", "Approval required"),
    "approval.approved": ("approvals", "Approval approved"),
    "approval.denied": ("approvals", "Approval denied"),
    "validation.failed": ("validators", "Verification failed"),
    "validation.passed": ("validators", "Verification passed"),
    "agent.quarantined": ("agents", "Agent quarantined"),
    "agent.unquarantined": ("agents", "Agent unquarantined"),
}


def _recent_changes(data: dict[str, Any]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for e in data["events"]:
        mapped = _CHANGE_CATEGORIES.get(e.event_type)
        if mapped is None:
            continue
        category, label = mapped
        payload = e.payload or {}
        detail = (
            str(payload.get("path") or payload.get("command") or payload.get("title")
                or payload.get("target") or "")
        )[:120]
        changes.append({
            "category": category,
            "label": label,
            "detail": detail,
            "event_type": e.event_type,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            "event_id": e.event_id,
        })
        if len(changes) >= 12:
            break
    return changes


def _project_map(data: dict[str, Any]) -> dict[str, Any]:
    """Goal → workflows → tasks → agents → artifacts/validation, derived from
    real rows. Generic nodes only — no demo-specific hardcoding."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    goal_id = "goal"
    nodes.append({"id": goal_id, "type": "goal", "label": (data["sandbox"].get("goal") or "Workspace goal")})

    agent_ids = {a.id for a in data["agents"]}
    for a in data["agents"]:
        nodes.append({
            "id": a.id, "type": "agent", "label": a.name,
            "status": a.status, "sublabel": a.role,
        })

    for w in data["workflows"]:
        nodes.append({"id": w.id, "type": "workflow", "label": w.goal[:60], "status": w.status})
        edges.append({"from": goal_id, "to": w.id, "label": "drives"})
        for t in data["tasks"]:
            if t.workflow_id != w.id:
                continue
            nodes.append({
                "id": t.id, "type": "task", "label": t.title,
                "status": t.status, "sublabel": t.risk_level,
            })
            edges.append({"from": w.id, "to": t.id, "label": "step"})
            if t.assigned_agent_id and t.assigned_agent_id in agent_ids:
                edges.append({"from": t.id, "to": t.assigned_agent_id, "label": "assigned"})
            for artifact in (t.expected_artifacts or [])[:3]:
                art_id = f"{t.id}:art:{artifact}"
                nodes.append({"id": art_id, "type": "artifact", "label": artifact})
                edges.append({"from": t.id, "to": art_id, "label": "produces"})

    # Data-flow / claim nodes from validator results (real evidence only).
    for r in data["validator_results"][:8]:
        if r.validator_type in ("data_flow", "research_claim"):
            node_id = f"val:{r.id}"
            nodes.append({
                "id": node_id,
                "type": "validation",
                "label": f"{r.validator_type}: {'ok' if r.passed else 'failed'}",
                "status": "passed" if r.passed else "failed",
                "sublabel": (r.meta or {}).get("explanation", "")[:80],
            })

    # De-duplicate nodes by id (agents/artifacts may repeat across tasks).
    seen: set[str] = set()
    unique_nodes = []
    for n in nodes:
        if n["id"] in seen:
            continue
        seen.add(n["id"])
        unique_nodes.append(n)
    return {"nodes": unique_nodes, "edges": edges}


# ------------------------------------------------------------------ public


def summary(session: Session, workspace: Workspace, workspaces_root: str) -> dict[str, Any]:
    data = _collect(session, workspace, workspaces_root)
    sig = _signals(data)
    return {
        "workspace_id": workspace.id,
        "workspace_status": workspace.status,
        "health": _health(sig),
        "recommended_actions": _recommended_actions(data, sig),
        "counts": {
            "agents": len(data["agents"]),
            "quarantined_agents": len(sig["quarantined"]),
            "workflows": len(data["workflows"]),
            "pending_approvals": len(data["pending_approvals"]),
            "failed_validators": len(sig["failed_validators"]),
            "blocked_tasks": len(sig["blocked_tasks"]),
            "sandbox_files": data["sandbox"].get("file_count", 0),
        },
        "agents_overview": _agents_overview(data),
        "workflow_progress": _workflow_progress(data),
        "validation_summary": _validation_summary(data),
        "enforcement_summary": _enforcement_summary(data),
        "recent_changes": _recent_changes(data),
    }


def issues(session: Session, workspace: Workspace, workspaces_root: str) -> list[dict[str, Any]]:
    data = _collect(session, workspace, workspaces_root)
    return _issues(data, _signals(data))


def project_map(session: Session, workspace: Workspace, workspaces_root: str) -> dict[str, Any]:
    data = _collect(session, workspace, workspaces_root)
    # carry the goal through for the map's root node
    data["sandbox"]["goal"] = workspace.goal
    return _project_map(data)
