"""Runtime workspace endpoints (v1.0 — metadata and events only).

No endpoint here executes commands, writes project files, or enforces
anything; that belongs to later Runtime versions. Lifecycle actions emit
workspace.* events through the normal collector (storage, projections,
WebSocket broadcast), so the activity feed, timeline, and replay come for
free via the workspace's activity run.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .. import models as core_models
from ..deps import get_session, require_api_key
from ..runtime import service
from ..runtime.agent_templates import AGENT_TEMPLATES, get_template
from ..runtime.models import Workspace, WorkspaceAgent
from ..runtime.schemas import (
    AgentDefinitionIn,
    AgentDefinitionOut,
    AgentDefinitionPatch,
    AgentFromTemplateIn,
    AgentTemplateOut,
    ArtifactIn,
    ArtifactOut,
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
