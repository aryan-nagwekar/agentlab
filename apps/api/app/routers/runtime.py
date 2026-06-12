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
from ..runtime.models import Workspace
from ..runtime.schemas import ArtifactIn, ArtifactOut, WorkspaceIn, WorkspaceOut, WorkspacePatch
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


def _require_workspace(session: Session, workspace_id: str) -> Workspace:
    workspace = service.get_workspace(session, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    return workspace


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
