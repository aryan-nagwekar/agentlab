"""Runtime workspace endpoints (v1.0 — metadata and events only).

No endpoint here executes commands, writes project files, or enforces
anything; that belongs to later Runtime versions. Lifecycle actions emit
workspace.* events through the normal collector (storage, projections,
WebSocket broadcast), so the activity feed, timeline, and replay come for
free via the workspace's activity run.
"""
from __future__ import annotations

import shlex

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .. import models as core_models
from ..deps import get_session, require_api_key
from ..runtime import commands, enforcement, orchestration, sandbox, service
from ..runtime.agent_templates import AGENT_TEMPLATES, get_template
from ..runtime.models import (
    ActionDecision,
    ActionProposal,
    RuntimeTask,
    RuntimeWorkflow,
    RuntimeWorkflowPlan,
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
    AgentTemplateOut,
    AllowedCommandOut,
    ArtifactIn,
    ArtifactOut,
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
    SandboxStatusOut,
    TaskOut,
    TaskPatch,
    TaskResultIn,
    TaskResultOut,
    WorkflowIn,
    WorkflowOut,
    WorkflowPlanOut,
    WorkspaceIn,
    WorkspaceOut,
    WorkspacePatch,
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
        metadata=agent.meta or {},
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
            legacy_audit=enforcement.file_legacy_audit(session, workspace, "write", body.path),
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
            legacy_audit=enforcement.file_legacy_audit(session, workspace, "mkdir", body.path),
            execute=lambda: sandbox.make_dir(session, workspace, root, body.path),
        )

    return await _sandbox_call(request, workspace_id, _mkdir)


@router.delete(
    "/runtime/workspaces/{workspace_id}/files",
    response_model=FileDeleteOut,
    dependencies=[Depends(require_api_key)],
)
async def delete_file(workspace_id: str, request: Request, path: str) -> FileDeleteOut:
    root = _workspaces_root(request)

    def _delete(session: Session, workspace: Workspace):
        return enforcement.guarded_execute(
            session,
            workspace,
            root,
            action_type="file.delete",
            target=path,
            legacy_audit=enforcement.file_legacy_audit(session, workspace, "delete", path),
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
            legacy_audit=enforcement.command_legacy_audit(
                session, workspace, body.command, body.args
            ),
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
