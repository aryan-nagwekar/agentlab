"""Workspace persistence + lifecycle events (v1.0).

Every lifecycle action stores the row change *and* emits a workspace.* event
through the normal collector pipeline into the workspace's activity run —
raw events stay the source of truth, and timeline/replay reconstruct
workspace history with zero special-casing.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as core_models
from ..collector import process_events
from ..schemas import EventIn
from .models import Workspace, WorkspaceArtifact

# Workspace status → the projection status of its activity run. The stream
# stays "running" while the workspace can still change.
_RUN_STATUS = {"completed": "completed", "failed": "failed", "archived": "completed"}


def get_workspace(session: Session, workspace_id: str) -> Workspace | None:
    return session.get(Workspace, workspace_id)


def list_workspaces(session: Session) -> list[Workspace]:
    return list(
        session.execute(select(Workspace).order_by(Workspace.updated_at.desc())).scalars()
    )


def artifact_count(session: Session, workspace_id: str) -> int:
    return session.execute(
        select(func.count(WorkspaceArtifact.id)).where(
            WorkspaceArtifact.workspace_id == workspace_id
        )
    ).scalar_one()


def list_artifacts(session: Session, workspace_id: str) -> list[WorkspaceArtifact]:
    return list(
        session.execute(
            select(WorkspaceArtifact)
            .where(WorkspaceArtifact.workspace_id == workspace_id)
            .order_by(WorkspaceArtifact.created_at.desc(), WorkspaceArtifact.id.desc())
        ).scalars()
    )


def _emit(
    session: Session,
    workspace: Workspace,
    event_type: str,
    payload: dict[str, Any],
) -> list[core_models.Event]:
    """Store a workspace lifecycle event through the normal collector."""
    event = EventIn(
        event_type=event_type,
        project_id=workspace.project_id,
        run_id=workspace.activity_run_id,
        payload={"workspace_id": workspace.id, "name": workspace.name, **payload},
        metadata={"source": "runtime", "workspace_id": workspace.id},
    )
    stored, _ = process_events(session, [event])
    _sync_activity_run(session, workspace)
    return stored


def _sync_activity_run(session: Session, workspace: Workspace) -> None:
    """Keep the auto-created activity-run projection readable in run lists."""
    run = session.get(core_models.Run, workspace.activity_run_id)
    if run is not None:
        run.name = f"Workspace · {workspace.name}"
        run.status = _RUN_STATUS.get(workspace.status, "running")


def create_workspace(
    session: Session, *, name: str, goal: str | None, project_id: str, metadata: dict[str, Any]
) -> tuple[Workspace, list[core_models.Event]]:
    workspace_id = f"ws-{uuid.uuid4().hex[:10]}"
    workspace = Workspace(
        id=workspace_id,
        name=name,
        goal=goal,
        status="draft",
        project_id=project_id,
        activity_run_id=f"{workspace_id}-activity",
        meta=metadata,
    )
    session.add(workspace)
    session.flush()
    stored = _emit(
        session,
        workspace,
        "workspace.created",
        {"goal_preview": (goal or "")[:200], "status": workspace.status},
    )
    return workspace, stored


def update_workspace(
    session: Session,
    workspace: Workspace,
    *,
    name: str | None,
    goal: str | None,
    status: str | None,
    metadata: dict[str, Any] | None,
) -> list[core_models.Event]:
    stored: list[core_models.Event] = []
    changed_fields: list[str] = []
    if name is not None and name != workspace.name:
        workspace.name = name
        changed_fields.append("name")
    if goal is not None and goal != workspace.goal:
        workspace.goal = goal
        changed_fields.append("goal")
    if metadata is not None and metadata != (workspace.meta or {}):
        workspace.meta = metadata
        changed_fields.append("metadata")
    if changed_fields:
        stored += _emit(
            session, workspace, "workspace.updated", {"changed_fields": changed_fields}
        )
    if status is not None and status != workspace.status:
        previous = workspace.status
        workspace.status = status
        event_type = "workspace.archived" if status == "archived" else "workspace.status_changed"
        stored += _emit(
            session, workspace, event_type, {"from_status": previous, "to_status": status}
        )
    return stored


def archive_workspace(session: Session, workspace: Workspace) -> list[core_models.Event]:
    """v1.0 keeps history append-only: archiving is the delete."""
    if workspace.status == "archived":
        return []
    previous = workspace.status
    workspace.status = "archived"
    return _emit(
        session, workspace, "workspace.archived", {"from_status": previous, "to_status": "archived"}
    )


def register_artifact(
    session: Session,
    workspace: Workspace,
    *,
    name: str,
    type_: str,
    path: str | None,
    metadata: dict[str, Any],
) -> tuple[WorkspaceArtifact, list[core_models.Event]]:
    artifact = WorkspaceArtifact(
        workspace_id=workspace.id,
        id=f"artifact-{uuid.uuid4().hex[:10]}",
        name=name,
        type=type_,
        path=path,
        meta=metadata,
    )
    session.add(artifact)
    session.flush()
    stored = _emit(
        session,
        workspace,
        "workspace.artifact_registered",
        {
            "artifact_id": artifact.id,
            "artifact_name": name,
            "artifact_type": type_,
            "path": path,
        },
    )
    return artifact, stored
