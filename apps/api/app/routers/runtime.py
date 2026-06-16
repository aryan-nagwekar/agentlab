"""Runtime workspace endpoints (v1.0 — metadata and events only).

No endpoint here executes commands, writes project files, or enforces
anything; that belongs to later Runtime versions. Lifecycle actions emit
workspace.* events through the normal collector (storage, projections,
WebSocket broadcast), so the activity feed, timeline, and replay come for
free via the workspace's activity run.
"""
from __future__ import annotations

import shlex

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .. import models as core_models
from ..deps import get_session, require_api_key
from ..model_gateway import ModelRequest, ModelResponse
from ..runtime import (
    agent_build,
    agent_run,
    approvals,
    commands,
    debug,
    demo_bottle_shop,
    enforcement,
    orchestration,
    preview,
    quarantine,
    sandbox,
    service,
    team_build,
    validators,
    workspace_templates,
)
from ..runtime.agent_templates import AGENT_TEMPLATES, get_template
from ..runtime.models import (
    ActionDecision,
    ActionProposal,
    ApprovalRequest,
    RuntimeTask,
    RuntimeWorkflow,
    RuntimeWorkflowPlan,
    ValidatorResult,
    Workspace,
    WorkspaceAgent,
)
from ..runtime.schemas import (
    ActionDecisionOut,
    ActionProposalIn,
    ActionProposalOut,
    AgentDefinitionIn,
    AgentDefinitionOut,
    AgentDefinitionPatch,
    AgentFromTemplateIn,
    AgentBuildIn,
    AgentBuildOut,
    AgentRunIn,
    AgentRunOut,
    AgentTemplateOut,
    AllowedCommandOut,
    ApprovalOut,
    ApprovalResolveIn,
    ArtifactIn,
    ArtifactOut,
    PendingCountOut,
    QuarantineIn,
    QuarantineStatusOut,
    UnquarantineIn,
    DecisionRecordOut,
    PolicyRuleOut,
    CommandRunIn,
    CommandRunOut,
    FileDeleteOut,
    FileEntryOut,
    FileReadOut,
    FileWriteIn,
    FileWriteOut,
    MkdirIn,
    MkdirOut,
    DebugIssueOut,
    DebugMapOut,
    DebugSummaryOut,
    DemoSeedOut,
    PreviewStatusOut,
    SandboxStatusOut,
    TaskOut,
    TaskPatch,
    TaskResultIn,
    TaskResultOut,
    ValidatorInfoOut,
    ValidatorResultOut,
    ValidatorRunIn,
    WorkflowIn,
    WorkflowOut,
    WorkflowPlanOut,
    SetTeamModelIn,
    TeamBuildIn,
    TeamBuildOut,
    WorkspaceFromTemplateIn,
    WorkspaceIn,
    WorkspaceOut,
    WorkspacePatch,
    WorkspaceTemplateOut,
)
from ..schemas import EventOut

router = APIRouter()


def _workspace_out(session: Session, workspace: Workspace) -> WorkspaceOut:
    return WorkspaceOut(
        workspace_id=workspace.id,
        name=workspace.name,
        goal=workspace.goal,
        status=workspace.status,
        project_id=workspace.project_id,
        activity_run_id=workspace.activity_run_id,
        metadata=workspace.meta or {},
        artifact_count=service.artifact_count(session, workspace.id),
        agent_count=service.agent_count(session, workspace.id),
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


def _artifact_out(artifact) -> ArtifactOut:
    return ArtifactOut(
        artifact_id=artifact.id,
        workspace_id=artifact.workspace_id,
        name=artifact.name,
        type=artifact.type,
        path=artifact.path,
        metadata=artifact.meta or {},
        created_at=artifact.created_at,
        updated_at=artifact.updated_at,
    )


def _agent_out(agent: WorkspaceAgent) -> AgentDefinitionOut:
    return AgentDefinitionOut(
        agent_id=agent.id,
        workspace_id=agent.workspace_id,
        name=agent.name,
        role=agent.role,
        description=agent.description,
        system_prompt=agent.system_prompt,
        model_provider=agent.model_provider,
        model_name=agent.model_name,
        allowed_tools=agent.allowed_tools or [],
        denied_tools=agent.denied_tools or [],
        permissions=agent.permissions or {},
        max_tokens_per_call=agent.max_tokens_per_call,
        max_calls_per_run=agent.max_calls_per_run,
        max_tool_calls_per_run=agent.max_tool_calls_per_run,
        requires_verification=agent.requires_verification,
        trust_score=agent.trust_score,
        risk_score=agent.risk_score,
        status=agent.status,
        quarantine=(agent.meta or {}).get("quarantine"),
        metadata={k: v for k, v in (agent.meta or {}).items() if k != "quarantine"},
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


def _require_workspace(session: Session, workspace_id: str) -> Workspace:
    workspace = service.get_workspace(session, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    return workspace


def _require_agent(session: Session, workspace_id: str, agent_id: str) -> WorkspaceAgent:
    agent = service.get_agent(session, workspace_id, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="workspace agent not found")
    return agent


async def _broadcast(request: Request, project_id: str, stored) -> None:
    manager = request.app.state.ws_manager
    for row in stored:
        out = EventOut.model_validate(row)
        await manager.broadcast(project_id, {"type": "event", "data": out.model_dump(mode="json")})


# ---------------------------------------------------------------- workspaces


@router.get("/runtime/workspaces", response_model=list[WorkspaceOut])
def list_workspaces(session: Session = Depends(get_session)) -> list[WorkspaceOut]:
    return [_workspace_out(session, w) for w in service.list_workspaces(session)]


@router.post(
    "/runtime/workspaces",
    status_code=201,
    response_model=WorkspaceOut,
    dependencies=[Depends(require_api_key)],
)
async def create_workspace(body: WorkspaceIn, request: Request) -> WorkspaceOut:
    session_factory = request.app.state.session_factory

    def _create():
        session = session_factory()
        try:
            workspace, stored = service.create_workspace(
                session,
                name=body.name,
                goal=body.goal,
                project_id=body.project_id,
                metadata=body.metadata,
            )
            session.commit()
            out = _workspace_out(session, workspace)
            rows = list(stored)
            return out, rows, workspace.project_id
        finally:
            session.close()

    out, stored, project_id = await run_in_threadpool(_create)
    await _broadcast(request, project_id, stored)
    return out


# ---- workspace templates (v3.3): one-click REAL workspace setup ----
# Instantiates a real workspace + a team of agents + a goal (not the canned
# demo). The agents build for real when the user runs a build afterward.


@router.get("/runtime/workspace-templates", response_model=list[WorkspaceTemplateOut])
def list_workspace_templates() -> list[WorkspaceTemplateOut]:
    return [
        WorkspaceTemplateOut(
            template_id=t.template_id,
            name=t.name,
            description=t.description,
            goal=t.goal,
            agent_roles=workspace_templates.agent_roles(t),
            agent_count=len(t.agent_template_ids),
            tags=list(t.tags),
        )
        for t in workspace_templates.WORKSPACE_TEMPLATES
    ]


@router.post(
    "/runtime/workspace-templates/{template_id}/create",
    response_model=WorkspaceOut,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
async def create_workspace_from_template(
    template_id: str, body: WorkspaceFromTemplateIn, request: Request
) -> WorkspaceOut:
    template = workspace_templates.get_workspace_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="workspace template not found")
    root = _workspaces_root(request)
    session_factory = request.app.state.session_factory

    def _create():
        session = session_factory()
        try:
            workspace, _agents, stored = workspace_templates.instantiate(
                session,
                template,
                root,
                project_id=body.project_id,
                name=body.name,
                goal=body.goal,
            )
            session.commit()
            out = _workspace_out(session, workspace)
            return out, list(stored), workspace.project_id
        finally:
            session.close()

    out, stored, project_id = await run_in_threadpool(_create)
    await _broadcast(request, project_id, stored)
    return out


@router.get("/runtime/workspaces/{workspace_id}", response_model=WorkspaceOut)
def get_workspace(workspace_id: str, session: Session = Depends(get_session)) -> WorkspaceOut:
    return _workspace_out(session, _require_workspace(session, workspace_id))


@router.patch(
    "/runtime/workspaces/{workspace_id}",
    response_model=WorkspaceOut,
    dependencies=[Depends(require_api_key)],
)
async def patch_workspace(
    workspace_id: str, body: WorkspacePatch, request: Request
) -> WorkspaceOut:
    session_factory = request.app.state.session_factory

    def _patch():
        session = session_factory()
        try:
            workspace = _require_workspace(session, workspace_id)
            stored = service.update_workspace(
                session,
                workspace,
                name=body.name,
                goal=body.goal,
                status=body.status,
                metadata=body.metadata,
            )
            session.commit()
            return _workspace_out(session, workspace), list(stored), workspace.project_id
        finally:
            session.close()

    out, stored, project_id = await run_in_threadpool(_patch)
    await _broadcast(request, project_id, stored)
    return out


@router.delete(
    "/runtime/workspaces/{workspace_id}",
    response_model=WorkspaceOut,
    dependencies=[Depends(require_api_key)],
)
async def archive_workspace(workspace_id: str, request: Request) -> WorkspaceOut:
    """v1.0 design choice: DELETE archives (history stays append-only)."""
    session_factory = request.app.state.session_factory

    def _archive():
        session = session_factory()
        try:
            workspace = _require_workspace(session, workspace_id)
            stored = service.archive_workspace(session, workspace)
            session.commit()
            return _workspace_out(session, workspace), list(stored), workspace.project_id
        finally:
            session.close()

    out, stored, project_id = await run_in_threadpool(_archive)
    await _broadcast(request, project_id, stored)
    return out


@router.get("/runtime/workspaces/{workspace_id}/activity", response_model=list[EventOut])
def workspace_activity(
    workspace_id: str, session: Session = Depends(get_session), limit: int = 50
) -> list[EventOut]:
    workspace = _require_workspace(session, workspace_id)
    events = (
        session.execute(
            select(core_models.Event)
            .where(core_models.Event.run_id == workspace.activity_run_id)
            .order_by(core_models.Event.timestamp.desc(), core_models.Event.id.desc())
            .limit(max(1, min(limit, 200)))
        )
        .scalars()
        .all()
    )
    return [EventOut.model_validate(event) for event in events]


# ----------------------------------------------------------------- artifacts


@router.get("/runtime/workspaces/{workspace_id}/artifacts", response_model=list[ArtifactOut])
def list_artifacts(workspace_id: str, session: Session = Depends(get_session)) -> list[ArtifactOut]:
    _require_workspace(session, workspace_id)
    return [_artifact_out(a) for a in service.list_artifacts(session, workspace_id)]


@router.post(
    "/runtime/workspaces/{workspace_id}/artifacts",
    status_code=201,
    response_model=ArtifactOut,
    dependencies=[Depends(require_api_key)],
)
async def register_artifact(
    workspace_id: str, body: ArtifactIn, request: Request
) -> ArtifactOut:
    session_factory = request.app.state.session_factory

    def _register():
        session = session_factory()
        try:
            workspace = _require_workspace(session, workspace_id)
            artifact, stored = service.register_artifact(
                session,
                workspace,
                name=body.name,
                type_=body.type,
                path=body.path,
                metadata=body.metadata,
            )
            session.commit()
            return _artifact_out(artifact), list(stored), workspace.project_id
        finally:
            session.close()

    out, stored, project_id = await run_in_threadpool(_register)
    await _broadcast(request, project_id, stored)
    return out


# ------------------------------------------------------------- sandbox files (v1.2)


async def _sandbox_call(request: Request, workspace_id: str, fn):
    """Run a sandbox operation off the event loop, committing its events —
    including the audit event of a *blocked* operation — and broadcasting
    them before the response (or the safe error) goes out."""
    session_factory = request.app.state.session_factory

    def _run():
        session = session_factory()
        try:
            workspace = _require_workspace(session, workspace_id)
            try:
                result = fn(session, workspace)
            except sandbox.SandboxBlocked as exc:
                session.commit()  # the rejection is part of workspace history
                return "blocked", exc, exc.events, workspace.project_id
            except sandbox.SandboxError as exc:
                session.rollback()
                return "error", exc, [], workspace.project_id
            session.commit()
            payload, stored = result if isinstance(result, tuple) else (result, [])
            return "ok", payload, list(stored), workspace.project_id
        finally:
            session.close()

    kind, payload, stored, project_id = await run_in_threadpool(_run)
    await _broadcast(request, project_id, stored)
    if kind == "blocked":
        # EnforcementRefused (v1.5) may override presentation (e.g. 403
        # "approval required (...)"); plain safety blocks keep the v1.2/v1.3
        # format and status.
        raise HTTPException(
            status_code=getattr(payload, "http_status", 400),
            detail=getattr(payload, "detail_override", None)
            or f"blocked ({payload.rule}): {payload.reason}",
        )
    if kind == "error":
        raise HTTPException(status_code=payload.status_code, detail=payload.detail)
    return payload


def _workspaces_root(request: Request) -> str:
    return request.app.state.settings.workspaces_root


@router.post(
    "/runtime/workspaces/{workspace_id}/sandbox/init",
    response_model=SandboxStatusOut,
    dependencies=[Depends(require_api_key)],
)
async def init_sandbox(workspace_id: str, request: Request) -> SandboxStatusOut:
    root = _workspaces_root(request)
    return await _sandbox_call(
        request, workspace_id, lambda s, w: sandbox.init_sandbox(s, w, root)
    )


@router.get(
    "/runtime/workspaces/{workspace_id}/sandbox/status",
    response_model=SandboxStatusOut,
)
def sandbox_status(
    workspace_id: str, request: Request, session: Session = Depends(get_session)
) -> SandboxStatusOut:
    workspace = _require_workspace(session, workspace_id)
    return SandboxStatusOut(**sandbox.status(workspace, _workspaces_root(request)))


@router.get(
    "/runtime/workspaces/{workspace_id}/files", response_model=list[FileEntryOut]
)
async def list_files(
    workspace_id: str, request: Request, path: str = ""
) -> list[FileEntryOut]:
    root = _workspaces_root(request)
    return await _sandbox_call(
        request, workspace_id, lambda s, w: sandbox.list_dir(s, w, root, path)
    )


@router.get(
    "/runtime/workspaces/{workspace_id}/files/tree", response_model=list[FileEntryOut]
)
async def file_tree(workspace_id: str, request: Request) -> list[FileEntryOut]:
    root = _workspaces_root(request)
    return await _sandbox_call(
        request, workspace_id, lambda s, w: sandbox.tree(s, w, root)
    )


@router.get(
    "/runtime/workspaces/{workspace_id}/files/read", response_model=FileReadOut
)
async def read_file(workspace_id: str, request: Request, path: str) -> FileReadOut:
    root = _workspaces_root(request)
    return await _sandbox_call(
        request, workspace_id, lambda s, w: sandbox.read_file(s, w, root, path)
    )


@router.post(
    "/runtime/workspaces/{workspace_id}/files/write",
    response_model=FileWriteOut,
    dependencies=[Depends(require_api_key)],
)
async def write_file(
    workspace_id: str, body: FileWriteIn, request: Request
) -> FileWriteOut:
    root = _workspaces_root(request)

    def _write(session: Session, workspace: Workspace):
        # v1.5: enforcement decides first; the v1.2 path safety inside
        # write_file still runs after an allow (defense in depth).
        return enforcement.guarded_execute(
            session,
            workspace,
            root,
            action_type="file.write",
            target=body.path,
            actor_type="agent" if body.agent_id else "user",
            agent_id=body.agent_id,
            legacy_audit=enforcement.file_legacy_audit(session, workspace, "write", body.path),
            approval_payload={"path": body.path, "content": body.content},
            execute=lambda: sandbox.write_file(session, workspace, root, body.path, body.content),
        )

    return await _sandbox_call(request, workspace_id, _write)


@router.post(
    "/runtime/workspaces/{workspace_id}/files/mkdir",
    response_model=MkdirOut,
    dependencies=[Depends(require_api_key)],
)
async def make_directory(
    workspace_id: str, body: MkdirIn, request: Request
) -> MkdirOut:
    root = _workspaces_root(request)

    def _mkdir(session: Session, workspace: Workspace):
        return enforcement.guarded_execute(
            session,
            workspace,
            root,
            action_type="directory.create",
            target=body.path,
            actor_type="agent" if body.agent_id else "user",
            agent_id=body.agent_id,
            legacy_audit=enforcement.file_legacy_audit(session, workspace, "mkdir", body.path),
            approval_payload={"path": body.path},
            execute=lambda: sandbox.make_dir(session, workspace, root, body.path),
        )

    return await _sandbox_call(request, workspace_id, _mkdir)


@router.delete(
    "/runtime/workspaces/{workspace_id}/files",
    response_model=FileDeleteOut,
    dependencies=[Depends(require_api_key)],
)
async def delete_file(
    workspace_id: str, request: Request, path: str, agent_id: str | None = None
) -> FileDeleteOut:
    root = _workspaces_root(request)

    def _delete(session: Session, workspace: Workspace):
        return enforcement.guarded_execute(
            session,
            workspace,
            root,
            action_type="file.delete",
            target=path,
            actor_type="agent" if agent_id else "user",
            agent_id=agent_id,
            legacy_audit=enforcement.file_legacy_audit(session, workspace, "delete", path),
            approval_payload={"path": path},
            execute=lambda: sandbox.delete_path(session, workspace, root, path),
        )

    return await _sandbox_call(request, workspace_id, _delete)


# ---------------------------------------------------------- sandbox commands (v1.3)


@router.get(
    "/runtime/workspaces/{workspace_id}/commands/allowed",
    response_model=list[AllowedCommandOut],
)
def list_allowed_commands(
    workspace_id: str, session: Session = Depends(get_session)
) -> list[AllowedCommandOut]:
    _require_workspace(session, workspace_id)
    return [AllowedCommandOut(**entry) for entry in commands.allowed_commands()]


@router.post(
    "/runtime/workspaces/{workspace_id}/commands/run",
    response_model=CommandRunOut,
    dependencies=[Depends(require_api_key)],
)
async def run_sandbox_command(
    workspace_id: str, body: CommandRunIn, request: Request
) -> CommandRunOut:
    """Evaluate and (only if allowed) execute one allowlisted command inside
    the workspace sandbox. v1.5: the enforcement gateway decides first; the
    v1.3 command safety inside run_command still runs after an allow
    (defense in depth). Blocked commands never execute."""
    root = _workspaces_root(request)

    def _run(session: Session, workspace: Workspace):
        return enforcement.guarded_execute(
            session,
            workspace,
            root,
            action_type="command.run",
            target=shlex.join([body.command, *body.args]),
            metadata={"command": body.command, "args": body.args},
            actor_type="agent" if body.agent_id else "user",
            agent_id=body.agent_id,
            legacy_audit=enforcement.command_legacy_audit(
                session, workspace, body.command, body.args
            ),
            approval_payload={
                "command": body.command,
                "args": body.args,
                "timeout_seconds": body.timeout_seconds,
                "working_subdir": body.working_subdir,
            },
            execute=lambda: commands.run_command(
                session,
                workspace,
                root,
                command=body.command,
                args=body.args,
                timeout_seconds=body.timeout_seconds,
                working_subdir=body.working_subdir,
            ),
        )

    return await _sandbox_call(request, workspace_id, _run)


@router.get(
    "/runtime/workspaces/{workspace_id}/commands/history",
    response_model=list[EventOut],
)
def command_history(
    workspace_id: str, session: Session = Depends(get_session), limit: int = 50
) -> list[EventOut]:
    """Command history is an event query — raw events stay the source of truth."""
    workspace = _require_workspace(session, workspace_id)
    events = (
        session.execute(
            select(core_models.Event)
            .where(
                core_models.Event.run_id == workspace.activity_run_id,
                core_models.Event.event_type.like("sandbox.command.%"),
            )
            .order_by(core_models.Event.timestamp.desc(), core_models.Event.id.desc())
            .limit(max(1, min(limit, 200)))
        )
        .scalars()
        .all()
    )
    return [EventOut.model_validate(event) for event in events]


# ------------------------------------------------------ bottle shop demo (v2.0)


@router.post(
    "/runtime/demo/bottle-shop",
    response_model=DemoSeedOut,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
async def create_bottle_shop_demo(request: Request) -> DemoSeedOut:
    """Deterministically seed the end-to-end Bottle Shop demo, reusing the
    existing runtime services and emitting their normal events. Returns a
    summary including the new workspace id and the pending governance approval."""
    root = _workspaces_root(request)
    session_factory = request.app.state.session_factory

    def _seed():
        session = session_factory()
        try:
            summary, stored = demo_bottle_shop.seed(session, root)
            session.commit()
            workspace = service.get_workspace(session, summary["workspace_id"])
            return summary, list(stored), workspace.project_id
        finally:
            session.close()

    summary, stored, project_id = await run_in_threadpool(_seed)
    await _broadcast(request, project_id, stored)
    return DemoSeedOut(**summary)


# ------------------------------------------------ live agent execution (v3.0)
# One governed build pass: the agent's model proposes files; every write goes
# through the v1.5 enforcement gateway (so v1.2/v1.6/v1.7 all apply) before it
# touches the sandbox. No control is bypassed; nothing runs autonomously past
# this single pass.


@router.post(
    "/runtime/workspaces/{workspace_id}/agent-build",
    response_model=AgentBuildOut,
    dependencies=[Depends(require_api_key)],
)
async def run_agent_build(
    workspace_id: str, body: AgentBuildIn, request: Request
) -> AgentBuildOut:
    root = _workspaces_root(request)
    registry = request.app.state.provider_registry
    session_factory = request.app.state.session_factory

    # Prep (sync): validate workspace/agent, init the sandbox, build the request.
    session = session_factory()
    try:
        workspace = _require_workspace(session, workspace_id)
        agent = _require_agent(session, workspace_id, body.agent_id)
        if quarantine.is_quarantined(agent):
            raise HTTPException(status_code=409, detail="agent is quarantined and cannot build")
        goal = (body.prompt or workspace.goal or "").strip()
        if not goal:
            raise HTTPException(status_code=400, detail="a prompt or workspace goal is required")
        sandbox.init_sandbox(session, workspace, root)
        session.commit()
        model_request = agent_build.build_model_request(workspace, agent, goal)
        provider_name = agent.model_provider
    finally:
        session.close()

    provider = registry.get(provider_name)
    if provider is None:
        raise HTTPException(status_code=400, detail=f"unknown provider {provider_name!r}")

    # The model call (async). A provider error returns a failed ModelResponse.
    try:
        response = await provider.complete(model_request)
    except Exception as exc:  # noqa: BLE001 — surface as a clean failed build
        response = ModelResponse(
            provider=provider_name,
            model_name=model_request.model_name,
            output_text="",
            latency_ms=0,
            status="failed",
            error_message=str(exc)[:300],
        )

    # Apply (sync, in a thread): parse + enforcement-gated writes + events.
    def _apply():
        s = session_factory()
        try:
            ws = _require_workspace(s, workspace_id)
            ag = _require_agent(s, workspace_id, body.agent_id)
            result, stored = agent_build.apply_build(s, ws, root, ag, response)
            s.commit()
            return result, list(stored), ws.project_id
        finally:
            s.close()

    result, stored, project_id = await run_in_threadpool(_apply)
    await _broadcast(request, project_id, stored)
    return AgentBuildOut(**result)


# ------------------------------------------------ team build (v3.4 — Goal → Team)
# One click: the v1.4 orchestrator plans + assigns the goal, then each assigned
# agent builds its part through the SAME governed pipeline, sharing one sandbox.
# A bridge over existing services — no new engine; every file write is governed.


@router.post(
    "/runtime/workspaces/{workspace_id}/team-build",
    response_model=TeamBuildOut,
    dependencies=[Depends(require_api_key)],
)
async def run_team_build(
    workspace_id: str, body: TeamBuildIn, request: Request
) -> TeamBuildOut:
    root = _workspaces_root(request)
    registry = request.app.state.provider_registry
    session_factory = request.app.state.session_factory

    # Prep (sync): validate + plan the team (orchestrator assigns tasks to agents).
    def _plan():
        session = session_factory()
        try:
            workspace = _require_workspace(session, workspace_id)
            goal = (body.goal or workspace.goal or "").strip()
            if not goal:
                raise HTTPException(status_code=400, detail="a goal is required")
            workflow, tasks, events = team_build.plan_team(session, workspace, root, goal)
            specs = team_build.assignable_task_specs(tasks)
            session.commit()
            return workspace.project_id, goal, workflow.id, specs, list(events)
        finally:
            session.close()

    project_id, goal, workflow_id, task_specs, started = await run_in_threadpool(_plan)
    await _broadcast(request, project_id, started)

    if not task_specs:
        # No agent matched any plan step — finalize as a clean failure.
        def _empty():
            session = session_factory()
            try:
                workspace = _require_workspace(session, workspace_id)
                out, events = team_build.finalize(
                    session, workspace, workflow_id, goal, [], "no_assignable_agents"
                )
                session.commit()
                return out, list(events), workspace.project_id
            finally:
                session.close()

        out, events, project_id = await run_in_threadpool(_empty)
        await _broadcast(request, project_id, events)
        return TeamBuildOut(**out)

    steps_out: list[dict] = []
    stop_reason = "completed"
    for task_id, _agent_id in task_specs:
        def _prep(tid=task_id):
            session = session_factory()
            try:
                workspace = _require_workspace(session, workspace_id)
                req, writer, provider_name = team_build.prep_task_request(
                    session, workspace, root, tid
                )
                return req, writer, provider_name
            finally:
                session.close()

        model_request, writer, provider_name = await run_in_threadpool(_prep)
        if model_request is None or provider_name is None:
            continue
        provider = registry.get(provider_name)
        if provider is None:
            continue
        try:
            response = await provider.complete(model_request)
        except Exception as exc:  # noqa: BLE001 — surface as a clean failed step
            response = ModelResponse(
                provider=provider_name,
                model_name=model_request.model_name,
                output_text="",
                latency_ms=0,
                status="failed",
                error_message=str(exc)[:300],
            )

        def _apply(resp=response, tid=task_id, is_writer=writer):
            session = session_factory()
            try:
                workspace = _require_workspace(session, workspace_id)
                step, events, halted = team_build.apply_task(
                    session, workspace, root, workflow_id, tid, resp, is_writer
                )
                session.commit()
                return step, list(events), halted, workspace.project_id
            finally:
                session.close()

        step, events, halted, project_id = await run_in_threadpool(_apply)
        await _broadcast(request, project_id, events)
        steps_out.append(step)
        if halted:
            stop_reason = "halted_for_approval"
            break

    def _finalize():
        session = session_factory()
        try:
            workspace = _require_workspace(session, workspace_id)
            out, events = team_build.finalize(
                session, workspace, workflow_id, goal, steps_out, stop_reason
            )
            session.commit()
            return out, list(events), workspace.project_id
        finally:
            session.close()

    out, events, project_id = await run_in_threadpool(_finalize)
    await _broadcast(request, project_id, events)
    return TeamBuildOut(**out)


# ------------------------------------- bounded agent loop (v3.1 + v3.2)
# Wraps the v3.0 single-pass body in a bounded iteration: each step is one
# governed model call that proposes file writes AND commands (both through the
# v1.5 gateway), deterministic validators run over the step's outputs, and
# their pass/fail feeds the next prompt. The loop stops on a model `done`
# signal, an empty step, max steps, an unrecoverable error, or an
# approval-required action — which (v3.2) PAUSES the run as awaiting_approval.
# The run state is persisted (AgentRun), so once the human resolves the
# approval the loop can be RESUMED from the next step.


async def _drive_agent_loop(
    request: Request,
    *,
    root: str,
    workspace_id: str,
    agent_id: str,
    prep,
    goal: str,
    max_steps: int,
    start_step: int,
    context,
    steps_out: list[dict],
) -> tuple[list[dict], object, str, int]:
    """Run steps [start_step, max_steps) until the loop stops. The async model
    call interleaves with synchronous, per-step-committed enforcement work, so
    events stream as the loop progresses. Returns
    (steps_out, context, stop_reason, last_step_index)."""
    session_factory = request.app.state.session_factory
    provider = request.app.state.provider_registry.get(prep.provider)
    if provider is None:
        raise HTTPException(status_code=400, detail=f"unknown provider {prep.provider!r}")

    stop_reason = "max_steps"
    last_index = start_step - 1
    for i in range(start_step, max_steps):
        last_index = i
        model_request = agent_run.build_step_request(prep, goal, i, max_steps, context)
        try:
            response = await provider.complete(model_request)
        except Exception as exc:  # noqa: BLE001 — surface as a clean failed step
            response = ModelResponse(
                provider=prep.provider,
                model_name=model_request.model_name,
                output_text="",
                latency_ms=0,
                status="failed",
                error_message=str(exc)[:300],
            )

        def _apply(resp=response, idx=i):
            s = session_factory()
            try:
                ws = _require_workspace(s, workspace_id)
                ag = _require_agent(s, workspace_id, agent_id)
                result = agent_run.apply_step(s, ws, root, ag, resp, idx)
                s.commit()
                return result, ws.project_id
            finally:
                s.close()

        result, project_id = await run_in_threadpool(_apply)
        await _broadcast(request, project_id, result.events)
        steps_out.append(result.public())
        context = result.context
        if result.stop:
            stop_reason = result.stop_reason
            break
    return steps_out, context, stop_reason, last_index


def _finalize_loop(
    session_factory, workspace_id, run_id, steps_out, context, stop_reason, last_index
):
    """Persist the run as paused (awaiting_approval) or finished, and emit the
    matching lifecycle event."""
    s = session_factory()
    try:
        ws = _require_workspace(s, workspace_id)
        run = agent_run.get_run(s, workspace_id, run_id)
        if stop_reason == "halted_for_approval":
            out, events = agent_run.pause_run(s, ws, run, steps_out, context, last_index)
        else:
            out, events = agent_run.complete_run(s, ws, run, steps_out, stop_reason)
        s.commit()
        return out, list(events), ws.project_id
    finally:
        s.close()


@router.post(
    "/runtime/workspaces/{workspace_id}/agent-run",
    response_model=AgentRunOut,
    dependencies=[Depends(require_api_key)],
)
async def run_agent_loop(
    workspace_id: str, body: AgentRunIn, request: Request
) -> AgentRunOut:
    root = _workspaces_root(request)
    session_factory = request.app.state.session_factory

    # Prep (sync): validate, init sandbox, persist the run state, emit started.
    session = session_factory()
    try:
        workspace = _require_workspace(session, workspace_id)
        agent = _require_agent(session, workspace_id, body.agent_id)
        if quarantine.is_quarantined(agent):
            raise HTTPException(status_code=409, detail="agent is quarantined and cannot build")
        goal = (body.prompt or workspace.goal or "").strip()
        if not goal:
            raise HTTPException(status_code=400, detail="a prompt or workspace goal is required")
        sandbox.init_sandbox(session, workspace, root)
        max_steps = agent_run.clamp_steps(body.max_steps)
        prep = agent_run.RunPrep(
            workspace_id=workspace.id,
            activity_run_id=workspace.activity_run_id,
            project_id=workspace.project_id,
            provider=agent.model_provider,
            model_name=agent.model_name,
            agent_id=agent.id,
        )
        context = agent_run.initial_context(session, workspace, root)
        run = agent_run.create_run(session, workspace, agent, goal, max_steps, context)
        run_id = run.id
        started = agent_run.emit_started(session, workspace, agent, goal, max_steps)
        session.commit()
        project_id = workspace.project_id
    finally:
        session.close()
    await _broadcast(request, project_id, started)

    steps_out, context, stop_reason, last_index = await _drive_agent_loop(
        request, root=root, workspace_id=workspace_id, agent_id=body.agent_id,
        prep=prep, goal=goal, max_steps=max_steps, start_step=0, context=context, steps_out=[],
    )

    out, events, project_id = await run_in_threadpool(
        lambda: _finalize_loop(
            session_factory, workspace_id, run_id, steps_out, context, stop_reason, last_index
        )
    )
    await _broadcast(request, project_id, events)
    return AgentRunOut(**out)


@router.get(
    "/runtime/workspaces/{workspace_id}/agent-run/{run_id}",
    response_model=AgentRunOut,
)
def get_agent_run(
    workspace_id: str, run_id: str, session: Session = Depends(get_session)
) -> AgentRunOut:
    _require_workspace(session, workspace_id)
    run = agent_run.get_run(session, workspace_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="agent run not found")
    return AgentRunOut(**agent_run.build_output(run))


@router.post(
    "/runtime/workspaces/{workspace_id}/agent-run/{run_id}/resume",
    response_model=AgentRunOut,
    dependencies=[Depends(require_api_key)],
)
async def resume_agent_loop(
    workspace_id: str, run_id: str, request: Request
) -> AgentRunOut:
    """Resume a paused run. The linked approvals must be resolved first
    (approve writes the held action via the v1.6 flow; deny keeps it blocked).
    The loop continues from the next step with the resolution folded into the
    prompt; it can pause again if a later step hits another approval."""
    root = _workspaces_root(request)
    session_factory = request.app.state.session_factory

    # Prep (sync): validate run state, require approvals resolved, build the
    # resume context (refreshed tree + resolution notes), emit resumed.
    session = session_factory()
    try:
        workspace = _require_workspace(session, workspace_id)
        run = agent_run.get_run(session, workspace_id, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="agent run not found")
        if run.status != "awaiting_approval":
            raise HTTPException(
                status_code=409,
                detail=f"run is not awaiting approval (status={run.status})",
            )
        agent = _require_agent(session, workspace_id, run.agent_id)
        if quarantine.is_quarantined(agent):
            raise HTTPException(status_code=409, detail="agent is quarantined and cannot build")
        context, unresolved = agent_run.resume_context(session, workspace, root, run)
        if unresolved:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"{len(unresolved)} approval(s) still pending — resolve them in the "
                    "Approvals panel before resuming"
                ),
            )
        run.status = "running"
        prep = agent_run.prep_from_run(workspace, run)
        goal = run.goal
        max_steps = run.max_steps
        start_step = run.next_step
        agent_id = run.agent_id
        steps_out = list(run.steps)
        resumed = agent_run.emit_resumed(session, workspace, run)
        session.commit()
        project_id = workspace.project_id
    finally:
        session.close()
    await _broadcast(request, project_id, resumed)

    steps_out, context, stop_reason, last_index = await _drive_agent_loop(
        request, root=root, workspace_id=workspace_id, agent_id=agent_id,
        prep=prep, goal=goal, max_steps=max_steps, start_step=start_step,
        context=context, steps_out=steps_out,
    )

    out, events, project_id = await run_in_threadpool(
        lambda: _finalize_loop(
            session_factory, workspace_id, run_id, steps_out, context, stop_reason, last_index
        )
    )
    await _broadcast(request, project_id, events)
    return AgentRunOut(**out)


# ---------------------------------------------------- website preview (v2.1)
# Read-only static preview of files already inside the workspace sandbox.
# Open in local mode (an <iframe> can't send X-API-Key); never writes/runs.


@router.get(
    "/runtime/workspaces/{workspace_id}/preview-status",
    response_model=PreviewStatusOut,
)
def preview_status(
    workspace_id: str, request: Request, session: Session = Depends(get_session)
) -> PreviewStatusOut:
    workspace = _require_workspace(session, workspace_id)
    return PreviewStatusOut(
        workspace_id=workspace.id,
        previewable=preview.is_previewable(workspace, _workspaces_root(request)),
    )


def _serve_preview(workspace_id: str, file_path: str, request: Request) -> Response:
    session = next(get_session(request))
    try:
        workspace = _require_workspace(session, workspace_id)
    finally:
        session.close()
    try:
        content, media_type = preview.serve(
            workspace, _workspaces_root(request), file_path
        )
    except sandbox.PathViolation as violation:
        raise HTTPException(status_code=400, detail=f"blocked ({violation.rule}): {violation.reason}")
    except sandbox.SandboxError as err:
        raise HTTPException(status_code=err.status_code, detail=err.detail)
    # Same-origin framing is allowed (the app embeds it); the frontend also
    # sandboxes the iframe. Cache nothing — the sandbox can change.
    return Response(
        content=content,
        media_type=media_type,
        headers={"X-Frame-Options": "SAMEORIGIN", "Cache-Control": "no-store"},
    )


@router.get("/runtime/workspaces/{workspace_id}/preview")
def preview_index(workspace_id: str, request: Request) -> Response:
    return _serve_preview(workspace_id, "index.html", request)


@router.get("/runtime/workspaces/{workspace_id}/preview/{file_path:path}")
def preview_file(workspace_id: str, file_path: str, request: Request) -> Response:
    return _serve_preview(workspace_id, file_path, request)


# ---------------------------------------------------- project debugging (v1.9)
# Read-only deterministic aggregations over existing models/events. These
# endpoints never mutate state and emit no events.


@router.get(
    "/runtime/workspaces/{workspace_id}/debug/summary", response_model=DebugSummaryOut
)
def debug_summary(
    workspace_id: str, request: Request, session: Session = Depends(get_session)
) -> DebugSummaryOut:
    workspace = _require_workspace(session, workspace_id)
    return DebugSummaryOut(**debug.summary(session, workspace, _workspaces_root(request)))


@router.get(
    "/runtime/workspaces/{workspace_id}/debug/issues",
    response_model=list[DebugIssueOut],
)
def debug_issues(
    workspace_id: str, request: Request, session: Session = Depends(get_session)
) -> list[DebugIssueOut]:
    workspace = _require_workspace(session, workspace_id)
    return [DebugIssueOut(**i) for i in debug.issues(session, workspace, _workspaces_root(request))]


@router.get(
    "/runtime/workspaces/{workspace_id}/debug/project-map", response_model=DebugMapOut
)
def debug_project_map(
    workspace_id: str, request: Request, session: Session = Depends(get_session)
) -> DebugMapOut:
    workspace = _require_workspace(session, workspace_id)
    return DebugMapOut(**debug.project_map(session, workspace, _workspaces_root(request)))


# --------------------------------------------------------------- validators (v1.8)


def _validator_result_out(result: ValidatorResult) -> ValidatorResultOut:
    return ValidatorResultOut(
        result_id=result.id,
        workspace_id=result.workspace_id,
        workflow_id=result.workflow_id,
        task_id=result.task_id,
        agent_id=result.agent_id,
        validator_type=result.validator_type,
        target_type=result.target_type,
        target_ref=result.target_ref,
        passed=result.passed,
        confidence=result.confidence,
        evidence=result.evidence or {},
        failures=result.failures or [],
        suggested_action=result.suggested_action,
        risk_delta=result.risk_delta,
        trust_delta=result.trust_delta,
        explanation=(result.meta or {}).get("explanation", ""),
        created_at=result.created_at,
    )


@router.get("/runtime/validators", response_model=list[ValidatorInfoOut])
def list_validators() -> list[ValidatorInfoOut]:
    return [ValidatorInfoOut(**entry) for entry in validators.validator_registry()]


@router.post(
    "/runtime/workspaces/{workspace_id}/validators/run",
    response_model=ValidatorResultOut,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
async def run_validator(
    workspace_id: str, body: ValidatorRunIn, request: Request
) -> ValidatorResultOut:
    root = _workspaces_root(request)

    def _run(session: Session, workspace: Workspace):
        result, stored = validators.run_validator(
            session,
            workspace,
            root,
            validator_type=body.validator_type,
            target_ref=body.target_ref,
            payload=body.payload,
            workflow_id=body.workflow_id,
            task_id=body.task_id,
            agent_id=body.agent_id,
        )
        return _validator_result_out(result), stored

    return await _sandbox_call(request, workspace_id, _run)


@router.get(
    "/runtime/workspaces/{workspace_id}/validators/results",
    response_model=list[ValidatorResultOut],
)
def list_validator_results(
    workspace_id: str, session: Session = Depends(get_session), limit: int = 50
) -> list[ValidatorResultOut]:
    _require_workspace(session, workspace_id)
    return [
        _validator_result_out(r)
        for r in validators.list_results(session, workspace_id, limit)
    ]


@router.get(
    "/runtime/workspaces/{workspace_id}/validators/results/{result_id}",
    response_model=ValidatorResultOut,
)
def get_validator_result(
    workspace_id: str, result_id: str, session: Session = Depends(get_session)
) -> ValidatorResultOut:
    _require_workspace(session, workspace_id)
    result = validators.get_result(session, workspace_id, result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="validator result not found")
    return _validator_result_out(result)


# -------------------------------------------------------------- enforcement (v1.5)


def _decision_out(decision: ActionDecision) -> ActionDecisionOut:
    return ActionDecisionOut(
        decision_id=decision.id,
        action_id=decision.action_id,
        decision=decision.decision,
        matched_rules=decision.matched_rules or [],
        trust_score_before=decision.trust_score_before,
        risk_score_before=decision.risk_score_before,
        reason=decision.reason,
        evidence=decision.evidence or {},
        created_at=decision.created_at,
    )


def _proposal_out(session: Session, proposal: ActionProposal) -> ActionProposalOut:
    decision = enforcement.get_decision(session, proposal.id)
    return ActionProposalOut(
        action_id=proposal.id,
        workspace_id=proposal.workspace_id,
        workflow_id=proposal.workflow_id,
        task_id=proposal.task_id,
        agent_id=proposal.agent_id,
        actor_type=proposal.actor_type,
        action_type=proposal.action_type,
        target=proposal.target,
        input_summary=proposal.input_summary,
        sensitivity_level=proposal.sensitivity_level,
        expected_effect=proposal.expected_effect,
        requires_approval_hint=proposal.requires_approval_hint,
        status=proposal.status,
        decision=_decision_out(decision) if decision else None,
        metadata=proposal.meta or {},
        created_at=proposal.created_at,
    )


@router.get("/runtime/policies", response_model=list[PolicyRuleOut])
def list_policies() -> list[PolicyRuleOut]:
    return [PolicyRuleOut(**entry) for entry in enforcement.policy_registry()]


@router.post(
    "/runtime/workspaces/{workspace_id}/actions/propose",
    response_model=ActionProposalOut,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
async def propose_action(
    workspace_id: str, body: ActionProposalIn, request: Request
) -> ActionProposalOut:
    """Generic proposal/evaluation — records the explainable decision but
    NEVER executes anything, whatever the outcome."""
    root = _workspaces_root(request)

    def _propose(session: Session, workspace: Workspace):
        proposal, _decision, stored = enforcement.propose_action(
            session,
            workspace,
            root,
            actor_type=body.actor_type,
            action_type=body.action_type,
            target=body.target,
            input_summary=body.input_summary,
            sensitivity_level=body.sensitivity_level,
            expected_effect=body.expected_effect,
            requires_approval_hint=body.requires_approval_hint,
            metadata=body.metadata,
            agent_id=body.agent_id,
            workflow_id=body.workflow_id,
            task_id=body.task_id,
            evaluate_now=body.evaluate,
        )
        return _proposal_out(session, proposal), stored

    return await _sandbox_call(request, workspace_id, _propose)


@router.get(
    "/runtime/workspaces/{workspace_id}/actions",
    response_model=list[ActionProposalOut],
)
def list_actions(
    workspace_id: str, session: Session = Depends(get_session), limit: int = 50
) -> list[ActionProposalOut]:
    _require_workspace(session, workspace_id)
    return [
        _proposal_out(session, p)
        for p in enforcement.list_proposals(session, workspace_id, limit)
    ]


@router.get(
    "/runtime/workspaces/{workspace_id}/actions/{action_id}",
    response_model=ActionProposalOut,
)
def get_action(
    workspace_id: str, action_id: str, session: Session = Depends(get_session)
) -> ActionProposalOut:
    _require_workspace(session, workspace_id)
    proposal = enforcement.get_proposal(session, workspace_id, action_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="action not found")
    return _proposal_out(session, proposal)


@router.post(
    "/runtime/workspaces/{workspace_id}/actions/{action_id}/evaluate",
    response_model=ActionProposalOut,
    dependencies=[Depends(require_api_key)],
)
async def evaluate_action(
    workspace_id: str, action_id: str, request: Request
) -> ActionProposalOut:
    root = _workspaces_root(request)

    def _evaluate(session: Session, workspace: Workspace):
        proposal = enforcement.get_proposal(session, workspace_id, action_id)
        if proposal is None:
            raise HTTPException(status_code=404, detail="action not found")
        if proposal.status != "proposed":
            raise sandbox.SandboxError(
                f"action is already {proposal.status}", status_code=409
            )
        _decision, stored = enforcement.evaluate_action(session, workspace, root, proposal)
        return _proposal_out(session, proposal), stored

    return await _sandbox_call(request, workspace_id, _evaluate)


@router.get(
    "/runtime/workspaces/{workspace_id}/enforcement/decisions",
    response_model=list[DecisionRecordOut],
)
def list_enforcement_decisions(
    workspace_id: str, session: Session = Depends(get_session), limit: int = 50
) -> list[DecisionRecordOut]:
    _require_workspace(session, workspace_id)
    records = []
    for decision in enforcement.list_decisions(session, workspace_id, limit):
        proposal = session.get(ActionProposal, decision.action_id)
        records.append(
            DecisionRecordOut(
                **_decision_out(decision).model_dump(),
                action_type=proposal.action_type if proposal else "unknown",
                actor_type=proposal.actor_type if proposal else "unknown",
                target=proposal.target if proposal else "",
                action_status=proposal.status if proposal else "unknown",
            )
        )
    return records


# ---------------------------------------------------------------- approvals (v1.6)


def _approval_out(approval: ApprovalRequest) -> ApprovalOut:
    meta = approval.meta or {}
    return ApprovalOut(
        approval_id=approval.id,
        workspace_id=approval.workspace_id,
        workflow_id=approval.workflow_id,
        task_id=approval.task_id,
        action_id=approval.action_id,
        agent_id=approval.agent_id,
        title=approval.title,
        plain_english_summary=approval.plain_english_summary,
        technical_summary=approval.technical_summary,
        risk_level=approval.risk_level,
        matched_policy_rules=approval.matched_policy_rules or [],
        recommended_decision=approval.recommended_decision,
        options=approval.options or [],
        status=approval.status,
        action_type=meta.get("action_type", ""),
        target=meta.get("target", ""),
        resolution_decision=approval.resolution_decision,
        resolved_at=approval.resolved_at,
        resolved_by=approval.resolved_by,
        resolution_reason=approval.resolution_reason,
        execution_status=approval.execution_status,
        execution_detail=approval.execution_detail,
        created_at=approval.created_at,
    )


@router.get(
    "/runtime/workspaces/{workspace_id}/approvals", response_model=list[ApprovalOut]
)
def list_workspace_approvals(
    workspace_id: str,
    session: Session = Depends(get_session),
    status: str | None = None,
    limit: int = 50,
) -> list[ApprovalOut]:
    _require_workspace(session, workspace_id)
    return [
        _approval_out(a)
        for a in approvals.list_approvals(session, workspace_id, status, limit)
    ]


@router.get(
    "/runtime/workspaces/{workspace_id}/approvals/pending-count",
    response_model=PendingCountOut,
)
def approvals_pending_count(
    workspace_id: str, session: Session = Depends(get_session)
) -> PendingCountOut:
    _require_workspace(session, workspace_id)
    return PendingCountOut(pending=approvals.pending_count(session, workspace_id))


@router.get(
    "/runtime/workspaces/{workspace_id}/approvals/{approval_id}",
    response_model=ApprovalOut,
)
def get_workspace_approval(
    workspace_id: str, approval_id: str, session: Session = Depends(get_session)
) -> ApprovalOut:
    _require_workspace(session, workspace_id)
    approval = approvals.get_approval(session, workspace_id, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="approval not found")
    return _approval_out(approval)


def _approval_resolution_route(action: str, decision: str | None):
    async def _handler(
        workspace_id: str, approval_id: str, body: ApprovalResolveIn, request: Request
    ) -> ApprovalOut:
        root = _workspaces_root(request)

        def _resolve(session: Session, workspace: Workspace):
            approval = approvals.get_approval(session, workspace_id, approval_id)
            if approval is None:
                raise HTTPException(status_code=404, detail="approval not found")
            if decision is None:  # cancel
                approval, stored = approvals.cancel(
                    session, workspace, approval,
                    resolved_by=body.resolved_by, reason=body.reason,
                )
            else:
                effective = decision
                if decision == "approve" and body.once:
                    effective = "approve_once"
                approval, stored = approvals.resolve(
                    session, workspace, root, approval,
                    decision=effective, resolved_by=body.resolved_by, reason=body.reason,
                )
            return _approval_out(approval), stored

        return await _sandbox_call(request, workspace_id, _resolve)

    _handler.__name__ = f"{action}_approval"
    return _handler


for _route, _decision in (
    ("approve", "approve"),
    ("deny", "deny"),
    ("approve-readonly", "approve_readonly"),
    ("reroute", "reroute"),
    ("quarantine", "quarantine"),
    ("cancel", None),
):
    router.add_api_route(
        f"/runtime/workspaces/{{workspace_id}}/approvals/{{approval_id}}/{_route}",
        _approval_resolution_route(_route.replace("-", "_"), _decision),
        methods=["POST"],
        response_model=ApprovalOut,
        dependencies=[Depends(require_api_key)],
    )


# ------------------------------------------------------------ orchestration (v1.4)


def _workflow_out(session: Session, workflow: RuntimeWorkflow) -> WorkflowOut:
    tasks = orchestration.list_tasks(session, workflow.id)
    return WorkflowOut(
        workflow_id=workflow.id,
        workspace_id=workflow.workspace_id,
        goal=workflow.goal,
        status=workflow.status,
        created_by=workflow.created_by,
        task_count=len(tasks),
        completed_task_count=sum(1 for t in tasks if t.status == "completed"),
        has_plan=orchestration.get_plan(session, workflow.id) is not None,
        metadata=workflow.meta or {},
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
    )


def _plan_out(plan: RuntimeWorkflowPlan) -> WorkflowPlanOut:
    return WorkflowPlanOut(
        plan_id=plan.id,
        workflow_id=plan.workflow_id,
        summary=plan.summary,
        steps=plan.steps or [],
        dependencies=plan.dependencies or {},
        required_agents=plan.required_agents or [],
        risk_assessment=plan.risk_assessment,
        validation_requirements=plan.validation_requirements or [],
        approval_requirements=plan.approval_requirements or [],
        created_at=plan.created_at,
    )


def _task_out(session: Session, task: RuntimeTask) -> TaskOut:
    agent_name = None
    if task.assigned_agent_id:
        agent = session.get(
            WorkspaceAgent, {"workspace_id": task.workspace_id, "id": task.assigned_agent_id}
        )
        agent_name = agent.name if agent else None
    results = orchestration.list_results(session, task.id)
    latest = results[0] if results else None
    return TaskOut(
        task_id=task.id,
        workflow_id=task.workflow_id,
        workspace_id=task.workspace_id,
        assigned_agent_id=task.assigned_agent_id,
        assigned_agent_name=agent_name,
        title=task.title,
        description=task.description,
        status=task.status,
        dependencies=task.dependencies or [],
        expected_artifacts=task.expected_artifacts or [],
        risk_level=task.risk_level,
        requires_validation=task.requires_validation,
        requires_approval=task.requires_approval,
        blocked_reason=(task.meta or {}).get("blocked_reason"),
        latest_result=(
            TaskResultOut(
                result_id=latest.id,
                task_id=latest.task_id,
                agent_id=latest.agent_id,
                output=latest.output,
                artifacts=latest.artifacts or [],
                validation_status=latest.validation_status,
                created_at=latest.created_at,
            )
            if latest
            else None
        ),
        metadata={k: v for k, v in (task.meta or {}).items() if k != "blocked_reason"},
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _require_workflow(
    session: Session, workspace_id: str, workflow_id: str
) -> RuntimeWorkflow:
    workflow = orchestration.get_workflow(session, workspace_id, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    return workflow


@router.get(
    "/runtime/workspaces/{workspace_id}/workflows", response_model=list[WorkflowOut]
)
def list_workflows(
    workspace_id: str, session: Session = Depends(get_session)
) -> list[WorkflowOut]:
    _require_workspace(session, workspace_id)
    return [
        _workflow_out(session, wf)
        for wf in orchestration.list_workflows(session, workspace_id)
    ]


@router.post(
    "/runtime/workspaces/{workspace_id}/workflows",
    response_model=WorkflowOut,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
async def create_workflow(
    workspace_id: str, body: WorkflowIn, request: Request
) -> WorkflowOut:
    def _create(session: Session, workspace: Workspace):
        workflow, stored = orchestration.create_workflow(
            session, workspace, body.goal, body.created_by
        )
        if body.metadata:
            workflow.meta = body.metadata
        return _workflow_out(session, workflow), stored

    return await _sandbox_call(request, workspace_id, _create)


@router.get(
    "/runtime/workspaces/{workspace_id}/workflows/{workflow_id}",
    response_model=WorkflowOut,
)
def get_workflow(
    workspace_id: str, workflow_id: str, session: Session = Depends(get_session)
) -> WorkflowOut:
    _require_workspace(session, workspace_id)
    return _workflow_out(session, _require_workflow(session, workspace_id, workflow_id))


@router.get(
    "/runtime/workspaces/{workspace_id}/workflows/{workflow_id}/plan",
    response_model=WorkflowPlanOut,
)
def get_workflow_plan(
    workspace_id: str, workflow_id: str, session: Session = Depends(get_session)
) -> WorkflowPlanOut:
    _require_workspace(session, workspace_id)
    _require_workflow(session, workspace_id, workflow_id)
    plan = orchestration.get_plan(session, workflow_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="workflow has no plan yet")
    return _plan_out(plan)


@router.post(
    "/runtime/workspaces/{workspace_id}/workflows/{workflow_id}/plan",
    response_model=WorkflowPlanOut,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
async def create_workflow_plan(
    workspace_id: str, workflow_id: str, request: Request
) -> WorkflowPlanOut:
    def _plan(session: Session, workspace: Workspace):
        workflow = _require_workflow(session, workspace_id, workflow_id)
        plan, _tasks, stored = orchestration.create_plan(session, workspace, workflow)
        return _plan_out(plan), stored

    return await _sandbox_call(request, workspace_id, _plan)


def _lifecycle_route(action: str):
    async def _handler(workspace_id: str, workflow_id: str, request: Request) -> WorkflowOut:
        root = _workspaces_root(request)

        def _transition(session: Session, workspace: Workspace):
            workflow = _require_workflow(session, workspace_id, workflow_id)

            def _do():
                wf, stored = orchestration.transition_workflow(
                    session, workspace, workflow, action
                )
                return _workflow_out(session, wf), stored

            if action == "start":
                # v1.5: starting a workflow is an enforced (metadata) action.
                return enforcement.guarded_execute(
                    session,
                    workspace,
                    root,
                    action_type="workflow.start",
                    target=workflow.id,
                    workflow_id=workflow.id,
                    execute=_do,
                )
            return _do()

        return await _sandbox_call(request, workspace_id, _transition)

    _handler.__name__ = f"{action}_workflow"
    return _handler


for _action in ("start", "pause", "resume", "cancel"):
    router.add_api_route(
        f"/runtime/workspaces/{{workspace_id}}/workflows/{{workflow_id}}/{_action}",
        _lifecycle_route(_action),
        methods=["POST"],
        response_model=WorkflowOut,
        dependencies=[Depends(require_api_key)],
    )


@router.get(
    "/runtime/workspaces/{workspace_id}/workflows/{workflow_id}/tasks",
    response_model=list[TaskOut],
)
def list_workflow_tasks(
    workspace_id: str, workflow_id: str, session: Session = Depends(get_session)
) -> list[TaskOut]:
    _require_workspace(session, workspace_id)
    _require_workflow(session, workspace_id, workflow_id)
    return [_task_out(session, t) for t in orchestration.list_tasks(session, workflow_id)]


@router.patch(
    "/runtime/workspaces/{workspace_id}/workflows/{workflow_id}/tasks/{task_id}",
    response_model=TaskOut,
    dependencies=[Depends(require_api_key)],
)
async def patch_workflow_task(
    workspace_id: str, workflow_id: str, task_id: str, body: TaskPatch, request: Request
) -> TaskOut:
    def _patch(session: Session, workspace: Workspace):
        workflow = _require_workflow(session, workspace_id, workflow_id)
        task = orchestration.get_task(session, workflow_id, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        task, stored = orchestration.patch_task(
            session,
            workspace,
            workflow,
            task,
            status=body.status,
            assigned_agent_id=body.assigned_agent_id,
            reason=body.reason,
        )
        return _task_out(session, task), stored

    return await _sandbox_call(request, workspace_id, _patch)


@router.post(
    "/runtime/workspaces/{workspace_id}/workflows/{workflow_id}/tasks/{task_id}/result",
    response_model=TaskOut,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
async def record_task_result(
    workspace_id: str,
    workflow_id: str,
    task_id: str,
    body: TaskResultIn,
    request: Request,
) -> TaskOut:
    root = _workspaces_root(request)

    def _record(session: Session, workspace: Workspace):
        workflow = _require_workflow(session, workspace_id, workflow_id)
        task = orchestration.get_task(session, workflow_id, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")

        def _do():
            _result, stored = orchestration.record_result(
                session, workspace, workflow, task,
                output=body.output, artifacts=body.artifacts,
            )
            return _task_out(session, task), stored

        # v1.5: recording a result is an enforced (metadata) action. Manual
        # user recording is allowed; agent-actor recording of flagged tasks
        # is gated via the generic proposal API.
        return enforcement.guarded_execute(
            session,
            workspace,
            root,
            action_type="task.result_record",
            target=task.id,
            workflow_id=workflow.id,
            task_id=task.id,
            execute=_do,
        )

    return await _sandbox_call(request, workspace_id, _record)


# ----------------------------------------------------------- workspace agents (v1.1)


@router.get("/runtime/agent-templates", response_model=list[AgentTemplateOut])
def list_agent_templates() -> list[AgentTemplateOut]:
    return [
        AgentTemplateOut(
            template_id=t.template_id,
            name=t.name,
            role=t.role,
            description=t.description,
            system_prompt=t.system_prompt,
            model_provider=t.model_provider,
            model_name=t.model_name,
            permissions=t.permissions,
            allowed_tools=list(t.allowed_tools),
            denied_tools=list(t.denied_tools),
            max_tokens_per_call=t.max_tokens_per_call,
            max_calls_per_run=t.max_calls_per_run,
            max_tool_calls_per_run=t.max_tool_calls_per_run,
            requires_verification=t.requires_verification,
            trust_score=t.trust_score,
            risk_score=t.risk_score,
            status=t.status,
            risk_notes=list(t.risk_notes),
            future_approval_required=list(t.future_approval_required),
        )
        for t in AGENT_TEMPLATES
    ]


@router.get(
    "/runtime/workspaces/{workspace_id}/agents", response_model=list[AgentDefinitionOut]
)
def list_workspace_agents(
    workspace_id: str, session: Session = Depends(get_session)
) -> list[AgentDefinitionOut]:
    _require_workspace(session, workspace_id)
    return [_agent_out(a) for a in service.list_agents(session, workspace_id)]


@router.post(
    "/runtime/workspaces/{workspace_id}/agents/model",
    response_model=list[AgentDefinitionOut],
    dependencies=[Depends(require_api_key)],
)
async def set_team_model(
    workspace_id: str, body: SetTeamModelIn, request: Request
) -> list[AgentDefinitionOut]:
    """Switch every agent in the workspace to one provider/model in one action,
    so you can flip the whole team between Ollama / Gemini / Claude / mock."""
    session_factory = request.app.state.session_factory

    def _set():
        session = session_factory()
        try:
            workspace = _require_workspace(session, workspace_id)
            stored: list = []
            for agent in service.list_agents(session, workspace_id):
                stored += service.update_agent(
                    session, workspace, agent,
                    {"model_provider": body.model_provider, "model_name": body.model_name},
                )
            session.commit()
            out = [_agent_out(a) for a in service.list_agents(session, workspace_id)]
            return out, list(stored), workspace.project_id
        finally:
            session.close()

    out, stored, project_id = await run_in_threadpool(_set)
    await _broadcast(request, project_id, stored)
    return out


@router.post(
    "/runtime/workspaces/{workspace_id}/agents",
    status_code=201,
    response_model=AgentDefinitionOut,
    dependencies=[Depends(require_api_key)],
)
async def create_workspace_agent(
    workspace_id: str, body: AgentDefinitionIn, request: Request
) -> AgentDefinitionOut:
    session_factory = request.app.state.session_factory

    def _create():
        session = session_factory()
        try:
            workspace = _require_workspace(session, workspace_id)
            agent, stored = service.create_agent(
                session,
                workspace,
                name=body.name,
                role=body.role,
                description=body.description,
                system_prompt=body.system_prompt,
                model_provider=body.model_provider,
                model_name=body.model_name,
                allowed_tools=body.allowed_tools,
                denied_tools=body.denied_tools,
                permissions=body.permissions,
                max_tokens_per_call=body.max_tokens_per_call,
                max_calls_per_run=body.max_calls_per_run,
                max_tool_calls_per_run=body.max_tool_calls_per_run,
                requires_verification=body.requires_verification,
                trust_score=body.trust_score,
                risk_score=body.risk_score,
                status=body.status,
                metadata=body.metadata,
            )
            session.commit()
            return _agent_out(agent), list(stored), workspace.project_id
        finally:
            session.close()

    out, stored, project_id = await run_in_threadpool(_create)
    await _broadcast(request, project_id, stored)
    return out


@router.post(
    "/runtime/workspaces/{workspace_id}/agents/from-template/{template_id}",
    status_code=201,
    response_model=AgentDefinitionOut,
    dependencies=[Depends(require_api_key)],
)
async def create_workspace_agent_from_template(
    workspace_id: str, template_id: str, body: AgentFromTemplateIn, request: Request
) -> AgentDefinitionOut:
    template = get_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="agent template not found")
    session_factory = request.app.state.session_factory

    def _create():
        session = session_factory()
        try:
            workspace = _require_workspace(session, workspace_id)
            agent, stored = service.create_agent_from_template(
                session, workspace, template, name=body.name
            )
            session.commit()
            return _agent_out(agent), list(stored), workspace.project_id
        finally:
            session.close()

    out, stored, project_id = await run_in_threadpool(_create)
    await _broadcast(request, project_id, stored)
    return out


@router.get(
    "/runtime/workspaces/{workspace_id}/agents/{agent_id}",
    response_model=AgentDefinitionOut,
)
def get_workspace_agent(
    workspace_id: str, agent_id: str, session: Session = Depends(get_session)
) -> AgentDefinitionOut:
    _require_workspace(session, workspace_id)
    return _agent_out(_require_agent(session, workspace_id, agent_id))


@router.patch(
    "/runtime/workspaces/{workspace_id}/agents/{agent_id}",
    response_model=AgentDefinitionOut,
    dependencies=[Depends(require_api_key)],
)
async def patch_workspace_agent(
    workspace_id: str, agent_id: str, body: AgentDefinitionPatch, request: Request
) -> AgentDefinitionOut:
    session_factory = request.app.state.session_factory

    def _patch():
        session = session_factory()
        try:
            workspace = _require_workspace(session, workspace_id)
            agent = _require_agent(session, workspace_id, agent_id)
            stored = service.update_agent(
                session, workspace, agent, body.model_dump(exclude_unset=True)
            )
            session.commit()
            return _agent_out(agent), list(stored), workspace.project_id
        finally:
            session.close()

    out, stored, project_id = await run_in_threadpool(_patch)
    await _broadcast(request, project_id, stored)
    return out


@router.delete(
    "/runtime/workspaces/{workspace_id}/agents/{agent_id}",
    status_code=204,
    dependencies=[Depends(require_api_key)],
)
async def delete_workspace_agent(
    workspace_id: str, agent_id: str, request: Request
) -> None:
    """Remove the agent definition. History stays in the event log, so the
    workspace timeline/replay still show the agent's lifecycle."""
    session_factory = request.app.state.session_factory

    def _delete():
        session = session_factory()
        try:
            workspace = _require_workspace(session, workspace_id)
            agent = _require_agent(session, workspace_id, agent_id)
            stored = service.delete_agent(session, workspace, agent)
            session.commit()
            return list(stored), workspace.project_id
        finally:
            session.close()

    stored, project_id = await run_in_threadpool(_delete)
    await _broadcast(request, project_id, stored)


# ---------------------------------------------------------------- quarantine (v1.7)


@router.get(
    "/runtime/workspaces/{workspace_id}/agents/{agent_id}/quarantine",
    response_model=QuarantineStatusOut,
)
def get_agent_quarantine(
    workspace_id: str, agent_id: str, session: Session = Depends(get_session)
) -> QuarantineStatusOut:
    _require_workspace(session, workspace_id)
    agent = _require_agent(session, workspace_id, agent_id)
    return QuarantineStatusOut(
        agent_id=agent.id,
        status=agent.status,
        quarantined=quarantine.is_quarantined(agent),
        quarantine=quarantine.quarantine_info(agent),
    )


@router.post(
    "/runtime/workspaces/{workspace_id}/agents/{agent_id}/quarantine",
    response_model=AgentDefinitionOut,
    dependencies=[Depends(require_api_key)],
)
async def quarantine_workspace_agent(
    workspace_id: str, agent_id: str, body: QuarantineIn, request: Request
) -> AgentDefinitionOut:
    def _quarantine(session: Session, workspace: Workspace):
        agent = _require_agent(session, workspace_id, agent_id)
        if agent.status == "quarantined":
            raise sandbox.SandboxError("agent is already quarantined", status_code=409)
        stored = quarantine.quarantine_agent(
            session, workspace, agent, reason=body.reason, requested_by=body.requested_by
        )
        return _agent_out(agent), stored

    return await _sandbox_call(request, workspace_id, _quarantine)


@router.post(
    "/runtime/workspaces/{workspace_id}/agents/{agent_id}/unquarantine",
    response_model=AgentDefinitionOut,
    dependencies=[Depends(require_api_key)],
)
async def unquarantine_workspace_agent(
    workspace_id: str, agent_id: str, body: UnquarantineIn, request: Request
) -> AgentDefinitionOut:
    def _unquarantine(session: Session, workspace: Workspace):
        agent = _require_agent(session, workspace_id, agent_id)
        stored = quarantine.unquarantine_agent(
            session, workspace, agent, requested_by=body.requested_by, reason=body.reason
        )
        return _agent_out(agent), stored

    return await _sandbox_call(request, workspace_id, _unquarantine)


@router.get(
    "/runtime/workspaces/{workspace_id}/quarantine/events",
    response_model=list[EventOut],
)
def list_quarantine_events(
    workspace_id: str, session: Session = Depends(get_session), limit: int = 100
) -> list[EventOut]:
    workspace = _require_workspace(session, workspace_id)
    events = quarantine.quarantine_events(
        session, workspace_id, workspace.activity_run_id, limit
    )
    return [EventOut.model_validate(event) for event in events]
