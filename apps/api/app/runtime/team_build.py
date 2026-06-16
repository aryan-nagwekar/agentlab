"""Team Build (v3.4) — Goal → Team.

One click: the v1.4 orchestrator plans the goal and assigns each task to the
right agent, then each assigned agent does **its part** through the SAME governed
pipeline, all sharing one sandbox. This is a *bridge*, not a new engine — it
reuses:

- `orchestration` (plan + role-based assignment + the runtime.workflow/task.*
  events that make the team visible/replayable),
- the v3.1 governed helpers (`agent_run._write_files` / `_run_step_validators` /
  `_model_telemetry`) and `agent_build.parse_manifest`,
- and therefore the v1.5 enforcement gateway — every file an agent writes goes
  through `guarded_execute` exactly like a manual write (safe → sandbox,
  sensitive → halt for approval, unsafe → blocked).

Writer agents (UI / backend) contribute files; the others (planner, researcher,
verifier, safety, marketing) contribute text recorded as their task result. The
loop walks the plan in order and stops cleanly if a step is held for approval
(resume-as-a-team is future work).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .. import models as core_models
from ..model_gateway import ModelRequest, ModelResponse
from . import agent_build, agent_run, orchestration, sandbox
from .models import RuntimeTask, RuntimeWorkflow, Workspace, WorkspaceAgent
from .sandbox import SandboxBlocked, SandboxError
from .service import _emit

# Roles that produce files. Everyone else produces a text contribution (a plan,
# research notes, a review) recorded as their task result.
_WRITER_KEYWORDS = ("ui", "frontend", "design", "backend", "coder", "engineer")


def is_writer(agent: WorkspaceAgent) -> bool:
    text = f"{agent.role} {agent.name}".lower()
    return any(k in text for k in _WRITER_KEYWORDS)


# ------------------------------------------------------------- role prompts


def _writer_focus(agent: WorkspaceAgent) -> str:
    text = f"{agent.role} {agent.name}".lower()
    if any(k in text for k in ("backend", "coder", "engineer")):
        return (
            "the data and behavior the project needs — e.g. the product/content "
            "data and the interactive JavaScript, kept inline in the page."
        )
    return (
        "the user-facing pages and styling — the HTML structure and inline CSS, "
        "building on any data a teammate already added."
    )


def _contribution_kind(agent: WorkspaceAgent) -> str:
    text = f"{agent.role} {agent.name}".lower()
    if "plan" in text:
        return "plan: a short ordered list of what the team should build for this goal"
    if "research" in text:
        return "research notes: the key facts or decisions the build depends on"
    if "market" in text:
        return "marketing copy: a tagline and short copy for the product or page"
    if any(k in text for k in ("verif", "review", "qa", "safety")):
        return "review: whether the build meets the goal, plus any gaps or risks you see"
    return "contribution: a short note advancing the goal"


_WRITER_SYSTEM = (
    "You are the {role} agent on a team building ONE project together in a shared "
    "sandbox. Contribute YOUR part toward the goal and build on what teammates "
    "already wrote — do not throw away their files. Respond with ONLY a JSON "
    'object: {{"summary": "<one sentence>", "files": [{{"path": "index.html", '
    '"content": "<full file>"}}]}}. Write complete, self-contained files with all '
    "CSS and JS inline; relative paths only; no external files, CDNs, secrets, or "
    "API keys. Focus on your role: {focus}"
)

_CONTRIB_SYSTEM = (
    "You are the {role} agent on a team building ONE project. Given the goal and "
    "the files built so far, produce YOUR {kind} as concise plain text (a few "
    "sentences or short bullets). Do not write code or JSON."
)


def build_task_request(
    workspace: Workspace,
    agent: WorkspaceAgent,
    goal: str,
    task: RuntimeTask,
    file_tree: list[str],
    writer: bool,
) -> ModelRequest:
    if writer:
        system = _WRITER_SYSTEM.format(role=agent.role, focus=_writer_focus(agent))
    else:
        system = _CONTRIB_SYSTEM.format(role=agent.role, kind=_contribution_kind(agent))
    tree_txt = (
        "\n".join(f"  - {p}" for p in file_tree) if file_tree else "  (empty — you may be first)"
    )
    prompt = (
        f"Goal: {goal.strip()}\n\n"
        f"Your task: {task.title} — {task.description}\n\n"
        f"Files in the shared sandbox so far:\n{tree_txt}\n\n"
        + (
            "Return the JSON object now with the file(s) your role should add or improve."
            if writer
            else "Write your contribution as plain text now."
        )
    )
    return ModelRequest(
        provider=agent.model_provider,
        model_name=agent_build._bare_model(agent.model_name),
        prompt=prompt,
        system_prompt=system,
        agent_id=agent.id,
        run_id=workspace.activity_run_id,
        project_id=workspace.project_id,
        temperature=0.2,
        max_tokens=6000,
        metadata={"source": "team_build", "workspace_id": workspace.id, "task_id": task.id},
    )


# ----------------------------------------------------------------- planning


def plan_team(
    session: Session, workspace: Workspace, workspaces_root: str, goal: str
) -> tuple[RuntimeWorkflow, list[RuntimeTask], list[core_models.Event]]:
    """Create the workflow + plan (assigns tasks to agents) and announce the team
    build. Reuses the v1.4 orchestrator verbatim."""
    sandbox.init_sandbox(session, workspace, workspaces_root)
    workflow, events = orchestration.create_workflow(session, workspace, goal, created_by="team-build")
    _plan, tasks, plan_events = orchestration.create_plan(session, workspace, workflow)
    events += plan_events
    assignable = [t for t in tasks if t.assigned_agent_id]
    events += _emit(
        session, workspace, "runtime.team_build.started",
        {
            "goal": goal[:300],
            "workflow_id": workflow.id,
            "agent_count": len({t.assigned_agent_id for t in assignable}),
            "task_count": len(assignable),
        },
    )
    return workflow, tasks, events


def assignable_task_specs(tasks: list[RuntimeTask]) -> list[tuple[str, str]]:
    """(task_id, agent_id) for tasks that got an agent, in plan order."""
    return [(t.id, t.assigned_agent_id) for t in tasks if t.assigned_agent_id]


# ----------------------------------------------------------------- execution


def prep_task_request(
    session: Session, workspace: Workspace, workspaces_root: str, task_id: str
) -> tuple[ModelRequest | None, bool, str | None]:
    """Build the role-aware model request for one task, with the current shared
    file tree as context. Returns (request, is_writer, provider)."""
    task = session.get(RuntimeTask, task_id)
    if task is None or not task.assigned_agent_id:
        return None, False, None
    agent = session.get(
        WorkspaceAgent, {"workspace_id": workspace.id, "id": task.assigned_agent_id}
    )
    if agent is None:
        return None, False, None
    writer = is_writer(agent)
    file_tree = agent_run._flat_tree(session, workspace, workspaces_root)
    workflow = session.get(RuntimeWorkflow, task.workflow_id)
    goal = (workflow.goal if workflow else "") or ""
    request = build_task_request(workspace, agent, goal, task, file_tree, writer)
    return request, writer, agent.model_provider


def _record(
    session: Session,
    workspace: Workspace,
    workflow: RuntimeWorkflow,
    task: RuntimeTask,
    *,
    output: str,
    artifacts: list[str],
    stored: list[core_models.Event],
) -> None:
    """Advance the orchestrator task (best-effort) so the Workflows panel shows
    the team progressing. A failure here never breaks the build."""
    try:
        _result, events = orchestration.record_result(
            session, workspace, workflow, task, output=output[:4000], artifacts=artifacts
        )
        stored.extend(events)
    except (SandboxError, SandboxBlocked):
        pass


def apply_task(
    session: Session,
    workspace: Workspace,
    workspaces_root: str,
    workflow_id: str,
    task_id: str,
    response: ModelResponse,
    writer: bool,
) -> tuple[dict[str, Any], list[core_models.Event], bool]:
    """Apply one agent's turn: telemetry + (writer) governed file writes + validators
    or (contributor) recorded text, advance the task, and emit team_build.step.
    Never raises on a blocked/held file. Returns (step, events, halted)."""
    task = session.get(RuntimeTask, task_id)
    workflow = session.get(RuntimeWorkflow, workflow_id)
    agent = session.get(
        WorkspaceAgent, {"workspace_id": workspace.id, "id": task.assigned_agent_id}
    )
    stored = agent_run._model_telemetry(session, workspace, agent, response)
    step: dict[str, Any] = {
        "agent_id": agent.id,
        "agent_name": agent.name,
        "role": agent.role,
        "task_id": task.id,
        "task_title": task.title,
        "kind": "build" if writer else "contribute",
        "files": [],
        "validations": [],
    }
    halted = False

    if response.status != "completed":
        step["status"] = "failed"
        step["note"] = (response.error_message or "model call failed")[:300]
    elif writer:
        parsed = agent_build.parse_manifest(response.output_text)
        if parsed is None:
            step["status"] = "failed"
            step["note"] = "the model did not return a valid file manifest"
        else:
            summary, files = parsed
            outcomes = agent_run._write_files(
                session, workspace, workspaces_root, agent, files, stored
            )
            validations = agent_run._run_step_validators(
                session, workspace, workspaces_root, agent, outcomes, [], stored
            )
            step["status"] = "ok"
            step["summary"] = summary[:200]
            step["files"] = outcomes
            step["validations"] = validations
            halted = any(o["status"] == "halted_for_approval" for o in outcomes)
            written = [o["path"] for o in outcomes if o["status"] == "written"]
            _record(session, workspace, workflow, task, output=summary, artifacts=written, stored=stored)
    else:
        text = (response.output_text or "").strip()
        step["status"] = "ok"
        step["note"] = text[:400]
        _record(session, workspace, workflow, task, output=text or "(no output)", artifacts=[], stored=stored)

    stored += _emit(
        session, workspace, "runtime.team_build.step",
        {
            "agent_id": agent.id,
            "role": agent.role,
            "task_id": task.id,
            "task_title": task.title,
            "kind": step["kind"],
            "status": step["status"],
            "files_written": sum(1 for o in step["files"] if o["status"] == "written"),
            "files_held": sum(1 for o in step["files"] if o["status"] == "halted_for_approval"),
            "files_blocked": sum(1 for o in step["files"] if o["status"] == "blocked"),
        },
    )
    return step, stored, halted


def finalize(
    session: Session,
    workspace: Workspace,
    workflow_id: str,
    goal: str,
    steps: list[dict[str, Any]],
    stop_reason: str,
) -> tuple[dict[str, Any], list[core_models.Event]]:
    total_written = sum(
        sum(1 for o in s.get("files", []) if o["status"] == "written") for s in steps
    )
    total_held = sum(
        sum(1 for o in s.get("files", []) if o["status"] == "halted_for_approval") for s in steps
    )
    total_blocked = sum(
        sum(1 for o in s.get("files", []) if o["status"] == "blocked") for s in steps
    )
    ran = [s for s in steps if s["status"] != "failed"]
    status = "completed" if ran else "failed"
    event_type = "runtime.team_build.completed" if status == "completed" else "runtime.team_build.failed"
    stored = _emit(
        session, workspace, event_type,
        {
            "workflow_id": workflow_id,
            "steps": len(steps),
            "stop_reason": stop_reason,
            "files_written": total_written,
        },
    )
    out = {
        "status": status,
        "goal": goal,
        "workflow_id": workflow_id,
        "stop_reason": stop_reason,
        "steps": steps,
        "step_count": len(steps),
        "total_written": total_written,
        "total_held": total_held,
        "total_blocked": total_blocked,
    }
    return out, stored
