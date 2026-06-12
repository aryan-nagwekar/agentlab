"""Runtime Orchestration Engine (v1.4).

Turns a workspace goal into a deterministic workflow: a plan (simple DAG of
role-shaped steps), tasks assigned to workspace agents by role keywords, and
a status-driven lifecycle. Every transition emits a runtime.workflow.* /
runtime.task.* event through the normal collector pipeline into the
workspace's activity run, so timeline and replay reconstruct orchestration
with zero special-casing.

Hard boundary for v1.4: orchestration is **status metadata only**. Agents
never autonomously write files, run sandbox commands, call models or tools,
install packages, or touch the network. Task results are recorded manually
as bounded text. Enforcement, approvals, validators, and real quarantine
arrive in later Runtime versions — nothing here pre-builds them.

The planner is deterministic (no model calls): a fixed five-step pipeline
whose steps are matched to workspace agents by role keywords. Steps with no
suitable agent become blocked tasks with an explicit reason. The DAG is
acyclic by construction and dependencies are not user-editable in v1.4, so
no cycle detection is needed yet.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as core_models
from .models import (
    AGENT_ASSIGNMENT_PREFERENCE,
    UNASSIGNABLE_AGENT_STATUSES,
    RuntimeTask,
    RuntimeTaskResult,
    RuntimeWorkflow,
    RuntimeWorkflowPlan,
    Workspace,
    WorkspaceAgent,
)
from .sandbox import SandboxError
from .service import _emit

MAX_RESULT_OUTPUT_CHARS = 4_000
EVENT_SUMMARY_CHARS = 300

# The deterministic plan pipeline. Each step is matched to workspace agents
# whose role/name contains one of the keywords; steps depend on earlier steps
# by index. risk/validation/approval flags are recorded for later versions —
# nothing acts on them in v1.4.
PLAN_STEPS: list[dict[str, Any]] = [
    {
        "index": 0,
        "title": "Draft the project plan",
        "description": "Break the workspace goal into concrete work items.",
        "required_role": "planner",
        "keywords": ("plan",),
        "depends_on": [],
        "risk_level": "low",
        "expected_artifacts": ["plan"],
        "requires_validation": False,
        "requires_approval": False,
    },
    {
        "index": 1,
        "title": "Research the domain",
        "description": "Gather the facts and references the build depends on.",
        "required_role": "researcher",
        "keywords": ("research",),
        "depends_on": [0],
        "risk_level": "medium",
        "expected_artifacts": ["research_result"],
        "requires_validation": True,
        "requires_approval": False,
    },
    {
        "index": 2,
        "title": "Build the backend",
        "description": "Design APIs, schemas, and core logic for the goal.",
        "required_role": "backend coder",
        "keywords": ("backend", "coder", "engineer"),
        "depends_on": [0],
        "risk_level": "high",
        "expected_artifacts": ["generated_code"],
        "requires_validation": True,
        "requires_approval": True,
    },
    {
        "index": 3,
        "title": "Build the user interface",
        "description": "Create the pages and components users interact with.",
        "required_role": "ui",
        "keywords": ("ui", "frontend", "design"),
        "depends_on": [2],
        "risk_level": "medium",
        "expected_artifacts": ["generated_code"],
        "requires_validation": True,
        "requires_approval": False,
    },
    {
        "index": 4,
        "title": "Review and verify the work",
        "description": "Check outputs against the goal and flag gaps or risks.",
        "required_role": "verifier",
        "keywords": ("verif", "review", "qa", "safety"),
        "depends_on": [1, 2, 3],
        "risk_level": "low",
        "expected_artifacts": ["validation_report"],
        "requires_validation": False,
        "requires_approval": False,
    },
]


# ------------------------------------------------------------------ queries


def get_workflow(
    session: Session, workspace_id: str, workflow_id: str
) -> RuntimeWorkflow | None:
    workflow = session.get(RuntimeWorkflow, workflow_id)
    if workflow is None or workflow.workspace_id != workspace_id:
        return None
    return workflow


def list_workflows(session: Session, workspace_id: str) -> list[RuntimeWorkflow]:
    return list(
        session.execute(
            select(RuntimeWorkflow)
            .where(RuntimeWorkflow.workspace_id == workspace_id)
            .order_by(RuntimeWorkflow.created_at.desc(), RuntimeWorkflow.id.desc())
        ).scalars()
    )


def get_plan(session: Session, workflow_id: str) -> RuntimeWorkflowPlan | None:
    return session.execute(
        select(RuntimeWorkflowPlan).where(RuntimeWorkflowPlan.workflow_id == workflow_id)
    ).scalar_one_or_none()


def list_tasks(session: Session, workflow_id: str) -> list[RuntimeTask]:
    return list(
        session.execute(
            select(RuntimeTask)
            .where(RuntimeTask.workflow_id == workflow_id)
            .order_by(RuntimeTask.created_at.asc(), RuntimeTask.id.asc())
        ).scalars()
    )


def list_results(session: Session, task_id: str) -> list[RuntimeTaskResult]:
    return list(
        session.execute(
            select(RuntimeTaskResult)
            .where(RuntimeTaskResult.task_id == task_id)
            .order_by(RuntimeTaskResult.created_at.desc(), RuntimeTaskResult.id.desc())
        ).scalars()
    )


def _workflow_event(
    session: Session,
    workspace: Workspace,
    workflow: RuntimeWorkflow,
    event_type: str,
    payload: dict[str, Any],
) -> list[core_models.Event]:
    return _emit(
        session, workspace, event_type, {"workflow_id": workflow.id, **payload}
    )


# --------------------------------------------------------------- assignment


def _assignable_agents(session: Session, workspace_id: str) -> list[WorkspaceAgent]:
    agents = session.execute(
        select(WorkspaceAgent)
        .where(WorkspaceAgent.workspace_id == workspace_id)
        .order_by(WorkspaceAgent.created_at.asc(), WorkspaceAgent.id.asc())
    ).scalars()
    return [a for a in agents if a.status not in UNASSIGNABLE_AGENT_STATUSES]


def _match_agent(
    agents: list[WorkspaceAgent], keywords: tuple[str, ...]
) -> WorkspaceAgent | None:
    """Best assignable agent whose role/name mentions a step keyword:
    ready > running > caution > suspicious, then creation order."""
    matches = [
        agent
        for agent in agents
        if any(k in f"{agent.role} {agent.name}".lower() for k in keywords)
    ]
    if not matches:
        return None
    return min(
        enumerate(matches),
        key=lambda pair: (AGENT_ASSIGNMENT_PREFERENCE.get(pair[1].status, 9), pair[0]),
    )[1]


# ----------------------------------------------------------------- planning


def create_workflow(
    session: Session, workspace: Workspace, goal: str | None, created_by: str
) -> tuple[RuntimeWorkflow, list[core_models.Event]]:
    effective_goal = (goal or workspace.goal or "").strip()
    if not effective_goal:
        raise SandboxError("a goal is required (set one on the workspace or the workflow)")
    workflow = RuntimeWorkflow(
        id=f"wf-{uuid.uuid4().hex[:10]}",
        workspace_id=workspace.id,
        goal=effective_goal,
        created_by=created_by,
    )
    session.add(workflow)
    session.flush()
    stored = _workflow_event(
        session,
        workspace,
        workflow,
        "runtime.workflow.created",
        {"goal": effective_goal[:300], "created_by": created_by, "status": "planned"},
    )
    return workflow, stored


def create_plan(
    session: Session, workspace: Workspace, workflow: RuntimeWorkflow
) -> tuple[RuntimeWorkflowPlan, list[RuntimeTask], list[core_models.Event]]:
    if workflow.status != "planned":
        raise SandboxError(
            f"workflow is {workflow.status}; a plan can only be created while planned",
            status_code=409,
        )
    if get_plan(session, workflow.id) is not None:
        raise SandboxError("workflow already has a plan", status_code=409)

    stored = _workflow_event(
        session, workspace, workflow, "runtime.workflow.plan_requested", {}
    )
    agents = _assignable_agents(session, workspace.id)

    plan = RuntimeWorkflowPlan(
        id=f"plan-{uuid.uuid4().hex[:10]}",
        workflow_id=workflow.id,
        summary=(
            f"Deterministic {len(PLAN_STEPS)}-step pipeline for: {workflow.goal[:200]}"
        ),
        steps=[{k: v for k, v in step.items() if k != "keywords"} for step in PLAN_STEPS],
        dependencies={
            str(step["index"]): step["depends_on"] for step in PLAN_STEPS
        },
        required_agents=[step["required_role"] for step in PLAN_STEPS],
        risk_assessment=(
            "Backend work is high risk (schema/auth-adjacent); research output "
            "requires future validation before downstream use."
        ),
        validation_requirements=[
            step["required_role"] for step in PLAN_STEPS if step["requires_validation"]
        ],
        approval_requirements=[
            step["required_role"] for step in PLAN_STEPS if step["requires_approval"]
        ],
    )
    session.add(plan)

    tasks: list[RuntimeTask] = []
    index_to_id: dict[int, str] = {}
    for step in PLAN_STEPS:
        task_id = f"task-{uuid.uuid4().hex[:10]}"
        index_to_id[step["index"]] = task_id
        agent = _match_agent(agents, step["keywords"])
        task = RuntimeTask(
            id=task_id,
            workflow_id=workflow.id,
            workspace_id=workspace.id,
            assigned_agent_id=agent.id if agent else None,
            title=step["title"],
            description=step["description"],
            status="pending" if agent else "blocked",
            dependencies=[index_to_id[i] for i in step["depends_on"]],
            expected_artifacts=step["expected_artifacts"],
            risk_level=step["risk_level"],
            requires_validation=step["requires_validation"],
            requires_approval=step["requires_approval"],
            meta=(
                {}
                if agent
                else {"blocked_reason": f"no assignable {step['required_role']} agent"}
            ),
        )
        session.add(task)
        tasks.append(task)
        stored += _workflow_event(
            session,
            workspace,
            workflow,
            "runtime.task.created",
            {
                "task_id": task.id,
                "title": task.title,
                "risk_level": task.risk_level,
                "depends_on": task.dependencies,
            },
        )
        if agent:
            stored += _workflow_event(
                session,
                workspace,
                workflow,
                "runtime.task.assigned",
                {
                    "task_id": task.id,
                    "assigned_agent_id": agent.id,
                    "agent_name": agent.name,
                    "agent_status": agent.status,
                },
            )
        else:
            stored += _workflow_event(
                session,
                workspace,
                workflow,
                "runtime.task.assignment_failed",
                {
                    "task_id": task.id,
                    "required_role": step["required_role"],
                    "reason": f"no assignable {step['required_role']} agent "
                    "(disabled/quarantined agents are never assigned)",
                },
            )

    session.flush()
    stored += _workflow_event(
        session,
        workspace,
        workflow,
        "runtime.workflow.plan_created",
        {
            "plan_id": plan.id,
            "task_count": len(tasks),
            "assigned": sum(1 for t in tasks if t.assigned_agent_id),
            "blocked": sum(1 for t in tasks if t.status == "blocked"),
        },
    )
    return plan, tasks, stored


# ---------------------------------------------------------------- lifecycle


def _deps_completed(task: RuntimeTask, by_id: dict[str, RuntimeTask]) -> bool:
    return all(
        by_id[dep].status == "completed" for dep in task.dependencies if dep in by_id
    )


def _advance(
    session: Session, workspace: Workspace, workflow: RuntimeWorkflow
) -> list[core_models.Event]:
    """Deterministic scheduler tick: start every assigned pending task whose
    dependencies are complete, then settle the workflow status. Starting a
    task is a status transition only — nothing executes in v1.4."""
    if workflow.status != "running":
        return []
    stored: list[core_models.Event] = []
    tasks = list_tasks(session, workflow.id)
    by_id = {t.id: t for t in tasks}

    for task in tasks:
        if task.status == "pending" and task.assigned_agent_id and _deps_completed(task, by_id):
            task.status = "running"
            stored += _workflow_event(
                session,
                workspace,
                workflow,
                "runtime.task.started",
                {"task_id": task.id, "assigned_agent_id": task.assigned_agent_id},
            )

    if tasks and all(t.status == "completed" for t in tasks):
        workflow.status = "completed"
        stored += _workflow_event(
            session, workspace, workflow, "runtime.workflow.completed", {}
        )
        return stored

    # Stuck: nothing running, nothing startable. Failed tasks make the
    # workflow failed; otherwise blocked (e.g. unassigned tasks in the way).
    startable = any(
        t.status == "pending" and t.assigned_agent_id and _deps_completed(t, by_id)
        for t in tasks
    )
    active = any(t.status == "running" for t in tasks)
    if tasks and not active and not startable:
        if any(t.status == "failed" for t in tasks):
            workflow.status = "failed"
            stored += _workflow_event(
                session,
                workspace,
                workflow,
                "runtime.workflow.failed",
                {"reason": "one or more tasks failed and no work can proceed"},
            )
        else:
            workflow.status = "blocked"
            stored += _workflow_event(
                session,
                workspace,
                workflow,
                "runtime.workflow.blocked",
                {"reason": "remaining tasks are blocked or unassigned"},
            )
    return stored


_LIFECYCLE = {
    # action: (allowed_from, new_status, event)
    "start": (("planned",), "running", "runtime.workflow.started"),
    "pause": (("running",), "paused", "runtime.workflow.paused"),
    "resume": (("paused", "blocked"), "running", "runtime.workflow.resumed"),
    "cancel": (
        ("planned", "running", "paused", "blocked"),
        "cancelled",
        "runtime.workflow.cancelled",
    ),
}


def transition_workflow(
    session: Session, workspace: Workspace, workflow: RuntimeWorkflow, action: str
) -> tuple[RuntimeWorkflow, list[core_models.Event]]:
    allowed_from, new_status, event_type = _LIFECYCLE[action]
    if workflow.status not in allowed_from:
        raise SandboxError(
            f"cannot {action} a {workflow.status} workflow "
            f"(allowed from: {', '.join(allowed_from)})",
            status_code=409,
        )
    if action == "start" and get_plan(session, workflow.id) is None:
        raise SandboxError("create a plan before starting the workflow", status_code=409)
    previous = workflow.status
    workflow.status = new_status
    stored = _workflow_event(
        session, workspace, workflow, event_type, {"from": previous, "to": new_status}
    )
    stored += _advance(session, workspace, workflow)
    return workflow, stored


# -------------------------------------------------------------------- tasks


def get_task(
    session: Session, workflow_id: str, task_id: str
) -> RuntimeTask | None:
    task = session.get(RuntimeTask, task_id)
    if task is None or task.workflow_id != workflow_id:
        return None
    return task


_TASK_PATCH_EVENTS = {
    "running": "runtime.task.started",
    "completed": "runtime.task.completed",
    "failed": "runtime.task.failed",
    "blocked": "runtime.task.blocked",
}


def patch_task(
    session: Session,
    workspace: Workspace,
    workflow: RuntimeWorkflow,
    task: RuntimeTask,
    *,
    status: str | None,
    assigned_agent_id: str | None,
    reason: str | None,
) -> tuple[RuntimeTask, list[core_models.Event]]:
    stored: list[core_models.Event] = []

    if assigned_agent_id is not None:
        agent = session.get(
            WorkspaceAgent, {"workspace_id": workspace.id, "id": assigned_agent_id}
        )
        if agent is None:
            raise SandboxError("assigned agent not found in this workspace", status_code=404)
        if agent.status in UNASSIGNABLE_AGENT_STATUSES:
            raise SandboxError(
                f"agent is {agent.status} and cannot receive normal tasks",
                status_code=409,
            )
        rerouted = task.assigned_agent_id is not None and task.assigned_agent_id != agent.id
        task.assigned_agent_id = agent.id
        if task.status == "blocked":
            task.status = "pending"
            task.meta = {k: v for k, v in (task.meta or {}).items() if k != "blocked_reason"}
        stored += _workflow_event(
            session,
            workspace,
            workflow,
            "runtime.task.rerouted" if rerouted else "runtime.task.assigned",
            {
                "task_id": task.id,
                "assigned_agent_id": agent.id,
                "agent_name": agent.name,
                **({"reason": reason[:300]} if reason else {}),
            },
        )

    if status is not None and status != task.status:
        if status not in _TASK_PATCH_EVENTS:
            raise SandboxError(
                f"status {status!r} cannot be set directly in v1.4 "
                f"(allowed: {', '.join(sorted(_TASK_PATCH_EVENTS))})"
            )
        task.status = status
        payload: dict[str, Any] = {"task_id": task.id}
        if task.assigned_agent_id:
            payload["assigned_agent_id"] = task.assigned_agent_id
        if reason:
            payload["reason"] = reason[:300]
        if status == "blocked" and reason:
            task.meta = {**(task.meta or {}), "blocked_reason": reason[:300]}
        stored += _workflow_event(
            session, workspace, workflow, _TASK_PATCH_EVENTS[status], payload
        )

    stored += _advance(session, workspace, workflow)
    return task, stored


def record_result(
    session: Session,
    workspace: Workspace,
    workflow: RuntimeWorkflow,
    task: RuntimeTask,
    *,
    output: str,
    artifacts: list[str],
) -> tuple[RuntimeTaskResult, list[core_models.Event]]:
    if task.status not in ("running", "pending"):
        raise SandboxError(
            f"cannot record a result for a {task.status} task", status_code=409
        )
    result = RuntimeTaskResult(
        id=f"tr-{uuid.uuid4().hex[:10]}",
        task_id=task.id,
        agent_id=task.assigned_agent_id,
        output=output[:MAX_RESULT_OUTPUT_CHARS],
        artifacts=artifacts[:20],
    )
    session.add(result)
    task.status = "completed"
    session.flush()
    stored = _workflow_event(
        session,
        workspace,
        workflow,
        "runtime.task.result_recorded",
        {
            "task_id": task.id,
            "result_id": result.id,
            "assigned_agent_id": task.assigned_agent_id,
            "output_summary": output[:EVENT_SUMMARY_CHARS],
            "artifact_count": len(result.artifacts),
        },
    )
    stored += _workflow_event(
        session,
        workspace,
        workflow,
        "runtime.task.completed",
        {"task_id": task.id, "assigned_agent_id": task.assigned_agent_id},
    )
    stored += _advance(session, workspace, workflow)
    return result, stored
