"""Bounded Agent Loop — multi-step live execution (v3.1).

v3.0 shipped the loop *body*: one model call → parse a manifest → route every
file write through the v1.5 enforcement gateway. v3.1 wraps that body in a
**bounded iteration** so an agent can build over several steps, reacting to
what actually happened:

- up to ``max_steps`` passes (hard-capped) — each step builds a prompt from the
  goal + the current sandbox file tree + the previous step's validator/command
  feedback, makes one real gateway call, and parses an action manifest;
- actions are file writes (as in v3.0) **and** governed ``command.run`` actions,
  both attributed to the agent and routed through the same
  ``enforcement.guarded_execute`` choke point (so v1.2/v1.3/v1.5/v1.6/v1.7 all
  apply unchanged);
- after each step, deterministic validators (secret_exposure / code_syntax /
  command_result) run over the step's outputs and their pass/fail is fed back
  into the next prompt;
- the loop stops on a model ``done`` signal, when a step produces no actions,
  on max steps, or on an unrecoverable error. If a step hits an
  approval-required action it is **recorded and the loop stops cleanly** —
  pause/resume across an approval is v3.2, not built here.

Nothing here is a new engine: the gateway, enforcement, approvals, sandbox,
command runner, and validators are all reused exactly as the rest of the
runtime uses them. New ``runtime.agent_run.*`` events (plus the per-step
``model.*`` / ``action.*`` / ``enforcement.*`` / ``sandbox.*`` / ``validator.*``
events) let Replay reconstruct the whole multi-step build.
"""
from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from dataclasses import replace
from typing import Any

from sqlalchemy.orm import Session

from .. import models as core_models
from ..collector import process_events
from ..model_gateway import ModelRequest, ModelResponse, build_model_events
from . import agent_build, commands, enforcement, sandbox, validators
from .commands import _redact
from .models import Workspace, WorkspaceAgent
from .sandbox import SandboxBlocked, SandboxError
from .service import _emit

DEFAULT_MAX_STEPS = 6
HARD_MAX_STEPS = 8
COMMAND_TIMEOUT_SECONDS = 60
MAX_COMMANDS_PER_STEP = 4
MAX_ARGS = 16
MAX_TREE_LINES = 50

# The allowlisted programs the loop tells the model it may run. The real gate
# is still the v1.3 allowlist + v1.5 policy — this is only guidance for the
# model so it doesn't waste a step proposing something that will be blocked.
SUGGESTED_COMMANDS = "ls, cat, pwd, node --version, npm --version, python3 --version, npm test, npm run build, python -m pytest"

STEP_SYSTEM_PROMPT = (
    "You are a senior build agent working ITERATIVELY inside a sandboxed, governed "
    "runtime. You build over several short steps, reacting to feedback. "
    "Each step, respond with ONLY a JSON object — no markdown, no commentary — of the form: "
    '{"summary": "<one sentence>", "done": false, '
    '"files": [{"path": "index.html", "content": "<full file contents>"}], '
    '"commands": [{"command": "ls", "args": ["-la"]}]}. '
    '"files" are files to create or overwrite this step: relative paths only (never '
    "start with / or ..), all CSS and JS inline, no external CDNs, no network calls, "
    "no secrets or API keys. "
    '"commands" are OPTIONAL safe commands to run this step; give command and args '
    f"separately. Only these are permitted: {SUGGESTED_COMMANDS}. Anything else is blocked. "
    'Set "done" to true ONLY when the goal is fully met and no further actions are needed. '
    "Use the file tree and the validator/command feedback from previous steps to fix "
    "problems and improve the result. Keep the page polished and self-contained. "
    'Every JSON key must be double-quoted (write {"path": ...}, never {path: ...}).'
)


@dataclass
class RunPrep:
    """Scalar snapshot taken under a session so model requests can be built
    outside any session during the async loop."""

    workspace_id: str
    activity_run_id: str
    project_id: str
    provider: str
    model_name: str
    agent_id: str


@dataclass
class StepContext:
    """What the previous step produced, fed verbatim into the next prompt."""

    file_tree: list[str] = field(default_factory=list)
    validations: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.file_tree or self.validations or self.commands or self.notes)


@dataclass
class Step:
    """A parsed model step manifest."""

    summary: str
    done: bool
    files: list[dict[str, str]]
    commands: list[dict[str, Any]]


@dataclass
class StepResult:
    index: int
    summary: str
    status: str  # "ok" | "failed"
    done: bool
    files: list[dict[str, Any]]
    commands: list[dict[str, Any]]
    validations: list[dict[str, Any]]
    stop: bool
    stop_reason: str | None
    context: StepContext
    events: list[core_models.Event]

    @property
    def written(self) -> int:
        return sum(1 for f in self.files if f["status"] == "written")

    @property
    def held(self) -> int:
        return sum(
            1 for a in (self.files + self.commands) if a["status"] == "halted_for_approval"
        )

    @property
    def blocked(self) -> int:
        return sum(1 for a in (self.files + self.commands) if a["status"] == "blocked")

    @property
    def commands_run(self) -> int:
        return sum(
            1 for c in self.commands if c["status"] in ("completed", "failed", "timed_out")
        )

    def public(self) -> dict[str, Any]:
        return {
            "step": self.index,
            "summary": self.summary,
            "status": self.status,
            "done": self.done,
            "files": self.files,
            "commands": self.commands,
            "validations": self.validations,
        }


# ----------------------------------------------------------------- parsing


def clamp_steps(requested: int | None) -> int:
    if not requested or requested < 1:
        return DEFAULT_MAX_STEPS
    return min(requested, HARD_MAX_STEPS)


def _commands_from(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = data.get("commands")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for entry in raw[:MAX_COMMANDS_PER_STEP]:
        if isinstance(entry, str):
            parts = entry.split()
            if not parts:
                continue
            out.append({"command": parts[0], "args": parts[1 : 1 + MAX_ARGS]})
            continue
        if not isinstance(entry, dict):
            continue
        cmd = str(entry.get("command", "")).strip()
        if not cmd:
            continue
        raw_args = entry.get("args") or []
        args = [str(a) for a in raw_args][:MAX_ARGS] if isinstance(raw_args, list) else []
        out.append({"command": cmd, "args": args})
    return out


def parse_step(text: str) -> Step | None:
    """Parse a step manifest (files + commands + done) from a model response,
    reusing v3.0's tolerant JSON extraction. Falls back to HTML salvage for a
    single done step. Returns None only when nothing usable is found."""
    data = agent_build.load_json_object(text)
    if isinstance(data, dict):
        files = agent_build.files_from(data)
        commands_ = _commands_from(data)
        done = bool(data.get("done"))
        summary = str(data.get("summary", "")).strip()[:300] or "Build step."
        # A valid object with no actions and not done is a stuck/empty step —
        # the loop treats it as "no_actions" and stops cleanly.
        return Step(summary=summary, done=done, files=files, commands=commands_)

    html = agent_build._salvage_html(text)
    if html:
        return Step(
            summary="Recovered a single-page site from the model's HTML output",
            done=True,
            files=[{"path": "index.html", "content": html[: agent_build.MAX_FILE_CHARS]}],
            commands=[],
        )
    return None


# -------------------------------------------------------------- prompting


def build_step_prompt(
    goal: str, step_index: int, max_steps: int, context: StepContext | None
) -> str:
    lines = [
        f"Goal: {goal.strip()}",
        "",
        f"This is step {step_index + 1} of at most {max_steps}.",
    ]
    if context is None or context.is_empty():
        lines += ["", "The sandbox is empty. Begin building toward the goal."]
    else:
        if context.file_tree:
            lines += ["", "Current files in the sandbox:"]
            lines += [f"  - {p}" for p in context.file_tree]
        if context.validations:
            lines += ["", "Validator results from your previous step:"]
            lines += [f"  - {v}" for v in context.validations]
        if context.commands:
            lines += ["", "Command results from your previous step:"]
            lines += [f"  - {c}" for c in context.commands]
        if context.notes:
            lines += ["", "Important:"]
            lines += [f"  - {n}" for n in context.notes]
    lines += [
        "",
        "Decide the next actions. If the goal is already fully met, respond with "
        '{"summary": "...", "done": true, "files": [], "commands": []}. Otherwise '
        "return the JSON object with the files to write and/or commands to run now.",
    ]
    return "\n".join(lines)


def build_step_request(
    prep: RunPrep,
    goal: str,
    step_index: int,
    max_steps: int,
    context: StepContext | None,
) -> ModelRequest:
    return ModelRequest(
        provider=prep.provider,
        model_name=agent_build._bare_model(prep.model_name),
        prompt=build_step_prompt(goal, step_index, max_steps, context),
        system_prompt=STEP_SYSTEM_PROMPT,
        agent_id=prep.agent_id,
        run_id=prep.activity_run_id,
        project_id=prep.project_id,
        temperature=0.2,
        max_tokens=6000,
        metadata={"source": "agent_run", "workspace_id": prep.workspace_id, "step": step_index},
    )


# --------------------------------------------------------------- execution


def _model_telemetry(
    session: Session, workspace: Workspace, agent: WorkspaceAgent, response: ModelResponse
) -> list[core_models.Event]:
    # The model OUTPUT is generated code — redact before it enters the preview
    # so a secret the model emitted never lands in the activity stream.
    telemetry = build_model_events(
        ModelRequest(
            provider=response.provider,
            model_name=response.model_name,
            prompt=STEP_SYSTEM_PROMPT,
            agent_id=agent.id,
            run_id=workspace.activity_run_id,
            project_id=workspace.project_id,
        ),
        replace(response, output_text=_redact(response.output_text)),
    )
    rows, _ = process_events(session, telemetry)
    return rows


def _write_files(
    session: Session,
    workspace: Workspace,
    workspaces_root: str,
    agent: WorkspaceAgent,
    files: list[dict[str, str]],
    stored: list[core_models.Event],
) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    for f in files:
        path, content = f["path"], f["content"]
        try:
            _payload, events = enforcement.guarded_execute(
                session,
                workspace,
                workspaces_root,
                action_type="file.write",
                target=path,
                actor_type="agent",
                agent_id=agent.id,
                legacy_audit=enforcement.file_legacy_audit(session, workspace, "write", path),
                approval_payload={"path": path, "content": content},
                execute=lambda p=path, c=content: sandbox.write_file(
                    session, workspace, workspaces_root, p, c
                ),
            )
            stored += events
            outcomes.append({"path": path, "status": "written"})
        except SandboxBlocked as refused:
            stored += list(refused.events)
            halted = getattr(refused, "http_status", 400) == 403
            outcomes.append(
                {
                    "path": path,
                    "status": "halted_for_approval" if halted else "blocked",
                    "reason": refused.reason,
                }
            )
    return outcomes


def _run_commands(
    session: Session,
    workspace: Workspace,
    workspaces_root: str,
    agent: WorkspaceAgent,
    cmds: list[dict[str, Any]],
    stored: list[core_models.Event],
) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    for c in cmds:
        cmd, args = c["command"], c["args"]
        display = _redact(shlex.join([cmd, *args]))[:200]
        try:
            payload, events = enforcement.guarded_execute(
                session,
                workspace,
                workspaces_root,
                action_type="command.run",
                target=shlex.join([cmd, *args]),
                metadata={"command": cmd, "args": args},
                actor_type="agent",
                agent_id=agent.id,
                legacy_audit=enforcement.command_legacy_audit(session, workspace, cmd, args),
                approval_payload={
                    "command": cmd,
                    "args": args,
                    "timeout_seconds": COMMAND_TIMEOUT_SECONDS,
                    "working_subdir": "",
                },
                execute=lambda cc=cmd, aa=args: commands.run_command(
                    session,
                    workspace,
                    workspaces_root,
                    command=cc,
                    args=aa,
                    timeout_seconds=COMMAND_TIMEOUT_SECONDS,
                    working_subdir="",
                ),
            )
            stored += events
            status = payload.get("status", "completed") if isinstance(payload, dict) else "completed"
            outcomes.append(
                {
                    "command": display,
                    "status": status,
                    "exit_code": payload.get("exit_code") if isinstance(payload, dict) else None,
                }
            )
        except SandboxBlocked as refused:
            stored += list(refused.events)
            halted = getattr(refused, "http_status", 400) == 403
            outcomes.append(
                {
                    "command": display,
                    "status": "halted_for_approval" if halted else "blocked",
                    "exit_code": None,
                    "reason": refused.reason,
                }
            )
    return outcomes


def _validate(
    session: Session,
    workspace: Workspace,
    workspaces_root: str,
    agent: WorkspaceAgent,
    validator_type: str,
    target: str,
    stored: list[core_models.Event],
) -> dict[str, Any] | None:
    try:
        result, events = validators.run_validator(
            session,
            workspace,
            workspaces_root,
            validator_type=validator_type,
            target_ref=target,
            agent_id=agent.id,
        )
        stored += events
        return {
            "validator": validator_type,
            "target": target or "command_run",
            "passed": result.passed,
        }
    except SandboxError as exc:
        stored += list(getattr(exc, "events", []))
        return None


def _run_step_validators(
    session: Session,
    workspace: Workspace,
    workspaces_root: str,
    agent: WorkspaceAgent,
    file_outcomes: list[dict[str, Any]],
    command_outcomes: list[dict[str, Any]],
    stored: list[core_models.Event],
) -> list[dict[str, Any]]:
    """Deterministic checks over what the step produced — fed back next step."""
    validations: list[dict[str, Any]] = []
    written = [o["path"] for o in file_outcomes if o["status"] == "written"]
    for path in written:
        secret = _validate(session, workspace, workspaces_root, agent, "secret_exposure", path, stored)
        if secret is not None:
            validations.append(secret)
        if path.endswith((".py", ".json")):
            syntax = _validate(session, workspace, workspaces_root, agent, "code_syntax", path, stored)
            if syntax is not None:
                validations.append(syntax)
    if any(c["status"] in ("completed", "failed", "timed_out") for c in command_outcomes):
        cmd_result = _validate(session, workspace, workspaces_root, agent, "command_result", "", stored)
        if cmd_result is not None:
            validations.append(cmd_result)
    return validations


def _flat_tree(session: Session, workspace: Workspace, workspaces_root: str) -> list[str]:
    out: list[str] = []

    def walk(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            if node.get("type") == "directory":
                walk(node.get("children", []))
            else:
                out.append(node["path"])

    try:
        walk(sandbox.tree(session, workspace, workspaces_root))
    except SandboxError:
        pass
    return out[:MAX_TREE_LINES]


def _gather_context(
    session: Session,
    workspace: Workspace,
    workspaces_root: str,
    validations: list[dict[str, Any]],
    command_outcomes: list[dict[str, Any]],
    file_outcomes: list[dict[str, Any]],
) -> StepContext:
    val_lines = [
        f"{v['validator']} on {v['target']}: {'passed' if v['passed'] else 'FAILED'}"
        for v in validations
    ]
    cmd_lines = []
    for c in command_outcomes:
        if c["status"] in ("completed", "failed", "timed_out"):
            exit_part = f" (exit {c['exit_code']})" if c.get("exit_code") is not None else ""
            cmd_lines.append(f"{c['command']} → {c['status']}{exit_part}")
    notes: list[str] = []
    for o in file_outcomes:
        if o["status"] == "halted_for_approval":
            notes.append(f"{o['path']} was held for human approval and NOT written")
        elif o["status"] == "blocked":
            notes.append(f"{o['path']} was blocked by policy and NOT written")
    for c in command_outcomes:
        if c["status"] == "halted_for_approval":
            notes.append(f"command `{c['command']}` was held for human approval and did NOT run")
        elif c["status"] == "blocked":
            notes.append(f"command `{c['command']}` was blocked by policy and did NOT run")
    return StepContext(
        file_tree=_flat_tree(session, workspace, workspaces_root),
        validations=val_lines,
        commands=cmd_lines,
        notes=notes,
    )


def apply_step(
    session: Session,
    workspace: Workspace,
    workspaces_root: str,
    agent: WorkspaceAgent,
    response: ModelResponse,
    step_index: int,
) -> StepResult:
    """Execute one governed step: model telemetry → parse → governed file writes
    and commands → validators → step event. Never raises on a blocked/held
    action — it records the outcome and decides whether the loop should stop."""
    stored: list[core_models.Event] = []
    stored += _model_telemetry(session, workspace, agent, response)

    if response.status != "completed":
        return _finish_step(
            session, workspace, agent, step_index,
            summary="", status="failed", done=False, files=[], commands=[], validations=[],
            stop_reason="model_failed",
            context=StepContext(file_tree=_flat_tree(session, workspace, workspaces_root)),
            stored=stored,
        )

    step = parse_step(response.output_text)
    if step is None:
        return _finish_step(
            session, workspace, agent, step_index,
            summary="", status="failed", done=False, files=[], commands=[], validations=[],
            stop_reason="malformed",
            context=StepContext(file_tree=_flat_tree(session, workspace, workspaces_root)),
            stored=stored,
        )

    file_outcomes = _write_files(session, workspace, workspaces_root, agent, step.files, stored)
    command_outcomes = _run_commands(session, workspace, workspaces_root, agent, step.commands, stored)
    validations = _run_step_validators(
        session, workspace, workspaces_root, agent, file_outcomes, command_outcomes, stored
    )

    halted = any(
        a["status"] == "halted_for_approval" for a in (file_outcomes + command_outcomes)
    )
    no_actions = not step.files and not step.commands
    stop_reason: str | None = None
    if halted:
        stop_reason = "halted_for_approval"
    elif step.done:
        stop_reason = "done"
    elif no_actions:
        stop_reason = "no_actions"

    context = _gather_context(
        session, workspace, workspaces_root, validations, command_outcomes, file_outcomes
    )
    return _finish_step(
        session, workspace, agent, step_index,
        summary=step.summary, status="ok", done=step.done,
        files=file_outcomes, commands=command_outcomes, validations=validations,
        stop_reason=stop_reason, context=context, stored=stored,
    )


def _finish_step(
    session: Session,
    workspace: Workspace,
    agent: WorkspaceAgent,
    step_index: int,
    *,
    summary: str,
    status: str,
    done: bool,
    files: list[dict[str, Any]],
    commands: list[dict[str, Any]],
    validations: list[dict[str, Any]],
    stop_reason: str | None,
    context: StepContext,
    stored: list[core_models.Event],
) -> StepResult:
    result = StepResult(
        index=step_index,
        summary=summary,
        status=status,
        done=done,
        files=files,
        commands=commands,
        validations=validations,
        stop=stop_reason is not None,
        stop_reason=stop_reason,
        context=context,
        events=stored,
    )
    stored += _emit(
        session, workspace, "runtime.agent_run.step",
        {
            "agent_id": agent.id,
            "step": step_index,
            "summary": summary[:300],
            "status": status,
            "done": done,
            "written": result.written,
            "halted_for_approval": result.held,
            "blocked": result.blocked,
            "commands_run": result.commands_run,
            "validations_passed": sum(1 for v in validations if v["passed"]),
            "validations_failed": sum(1 for v in validations if not v["passed"]),
            **({"stop_reason": stop_reason} if stop_reason else {}),
        },
    )
    return result


# ----------------------------------------------------------- run lifecycle


def emit_started(
    session: Session,
    workspace: Workspace,
    agent: WorkspaceAgent,
    goal: str,
    max_steps: int,
) -> list[core_models.Event]:
    return _emit(
        session, workspace, "runtime.agent_run.started",
        {
            "agent_id": agent.id,
            "model": agent.model_name,
            "provider": agent.model_provider,
            "max_steps": max_steps,
            "goal": goal[:300],
        },
    )


def initial_context(
    session: Session, workspace: Workspace, workspaces_root: str
) -> StepContext:
    """Step 0 sees whatever is already in the sandbox (usually nothing)."""
    return StepContext(file_tree=_flat_tree(session, workspace, workspaces_root))


def finalize_run(
    session: Session,
    workspace: Workspace,
    agent: WorkspaceAgent,
    agent_name: str,
    prep: RunPrep,
    goal: str,
    steps: list[dict[str, Any]],
    stop_reason: str,
) -> tuple[dict[str, Any], list[core_models.Event]]:
    total_written = sum(sum(1 for f in s["files"] if f["status"] == "written") for s in steps)
    total_held = sum(
        sum(1 for a in (s["files"] + s["commands"]) if a["status"] == "halted_for_approval")
        for s in steps
    )
    total_blocked = sum(
        sum(1 for a in (s["files"] + s["commands"]) if a["status"] == "blocked")
        for s in steps
    )
    commands_run = sum(
        sum(1 for c in s["commands"] if c["status"] in ("completed", "failed", "timed_out"))
        for s in steps
    )
    overall = "completed" if (total_written > 0 or stop_reason == "done") else "failed"

    payload = {
        "agent_id": agent.id,
        "steps": len(steps),
        "stop_reason": stop_reason,
        "total_written": total_written,
        "total_held": total_held,
        "total_blocked": total_blocked,
        "commands_run": commands_run,
    }
    if overall == "failed":
        stored = _emit(
            session, workspace, "runtime.agent_run.failed",
            {**payload, "reason": stop_reason},
        )
    else:
        stored = _emit(session, workspace, "runtime.agent_run.completed", payload)

    out = {
        "status": overall,
        "agent_id": agent.id,
        "agent_name": agent_name,
        "provider": prep.provider,
        "model": prep.model_name,
        "goal": goal,
        "steps": steps,
        "step_count": len(steps),
        "stop_reason": stop_reason,
        "total_written": total_written,
        "total_held": total_held,
        "total_blocked": total_blocked,
        "commands_run": commands_run,
    }
    return out, stored
