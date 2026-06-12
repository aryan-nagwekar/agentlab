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
from .agent_templates import AgentTemplate
from .models import (
    Workspace,
    WorkspaceAgent,
    WorkspaceArtifact,
    default_permissions,
)

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


# ----------------------------------------------------------- workspace agents (v1.1)


def _full_permissions(partial: dict[str, bool] | None) -> dict[str, bool]:
    """Overlay a partial permission dict onto the conservative defaults so the
    stored profile always carries every canonical flag."""
    profile = default_permissions()
    profile.update(partial or {})
    return profile


def get_agent(
    session: Session, workspace_id: str, agent_id: str
) -> WorkspaceAgent | None:
    return session.get(WorkspaceAgent, (workspace_id, agent_id))


def list_agents(session: Session, workspace_id: str) -> list[WorkspaceAgent]:
    return list(
        session.execute(
            select(WorkspaceAgent)
            .where(WorkspaceAgent.workspace_id == workspace_id)
            .order_by(WorkspaceAgent.created_at.asc(), WorkspaceAgent.id.asc())
        ).scalars()
    )


def agent_count(session: Session, workspace_id: str) -> int:
    return session.execute(
        select(func.count(WorkspaceAgent.id)).where(
            WorkspaceAgent.workspace_id == workspace_id
        )
    ).scalar_one()


def _add_agent(
    session: Session,
    workspace: Workspace,
    *,
    name: str,
    role: str,
    description: str | None,
    system_prompt: str | None,
    model_provider: str,
    model_name: str,
    allowed_tools: list[str],
    denied_tools: list[str],
    permissions: dict[str, bool],
    max_tokens_per_call: int,
    max_calls_per_run: int,
    max_tool_calls_per_run: int,
    requires_verification: bool,
    trust_score: float,
    risk_score: float,
    status: str,
    metadata: dict[str, Any],
) -> WorkspaceAgent:
    agent = WorkspaceAgent(
        workspace_id=workspace.id,
        id=f"wsagent-{uuid.uuid4().hex[:10]}",
        name=name,
        role=role,
        description=description,
        system_prompt=system_prompt,
        model_provider=model_provider,
        model_name=model_name,
        allowed_tools=list(allowed_tools),
        denied_tools=list(denied_tools),
        permissions=permissions,
        max_tokens_per_call=max_tokens_per_call,
        max_calls_per_run=max_calls_per_run,
        max_tool_calls_per_run=max_tool_calls_per_run,
        requires_verification=requires_verification,
        trust_score=trust_score,
        risk_score=risk_score,
        status=status,
        meta=metadata,
    )
    session.add(agent)
    session.flush()
    return agent


def _agent_created_payload(agent: WorkspaceAgent) -> dict[str, Any]:
    return {
        "agent_id": agent.id,
        "agent_name": agent.name,
        "role": agent.role,
        "status": agent.status,
        "model_provider": agent.model_provider,
        "model_name": agent.model_name,
    }


def create_agent(
    session: Session, workspace: Workspace, **fields: Any
) -> tuple[WorkspaceAgent, list[core_models.Event]]:
    fields["permissions"] = _full_permissions(fields.get("permissions"))
    agent = _add_agent(session, workspace, **fields)
    stored = _emit(
        session, workspace, "workspace_agent.created", _agent_created_payload(agent)
    )
    return agent, stored


def create_agent_from_template(
    session: Session,
    workspace: Workspace,
    template: AgentTemplate,
    *,
    name: str | None,
) -> tuple[WorkspaceAgent, list[core_models.Event]]:
    metadata: dict[str, Any] = {"template_id": template.template_id}
    if template.risk_notes:
        metadata["risk_notes"] = list(template.risk_notes)
    if template.future_approval_required:
        metadata["future_approval_required"] = list(template.future_approval_required)
    agent = _add_agent(
        session,
        workspace,
        name=name or template.name,
        role=template.role,
        description=template.description,
        system_prompt=template.system_prompt,
        model_provider=template.model_provider,
        model_name=template.model_name,
        allowed_tools=list(template.allowed_tools),
        denied_tools=list(template.denied_tools),
        permissions=dict(template.permissions),
        max_tokens_per_call=template.max_tokens_per_call,
        max_calls_per_run=template.max_calls_per_run,
        max_tool_calls_per_run=template.max_tool_calls_per_run,
        requires_verification=template.requires_verification,
        trust_score=template.trust_score,
        risk_score=template.risk_score,
        status=template.status,
        metadata=metadata,
    )
    stored = _emit(
        session,
        workspace,
        "workspace_agent.template_instantiated",
        {**_agent_created_payload(agent), "template_id": template.template_id},
    )
    return agent, stored


# Fields that are a plain metadata edit (emit workspace_agent.updated).
_AGENT_PLAIN_FIELDS = (
    "name",
    "role",
    "description",
    "system_prompt",
    "model_provider",
    "model_name",
    "allowed_tools",
    "denied_tools",
    "max_tokens_per_call",
    "max_calls_per_run",
    "max_tool_calls_per_run",
    "requires_verification",
    "trust_score",
    "risk_score",
    "metadata",
)


def update_agent(
    session: Session,
    workspace: Workspace,
    agent: WorkspaceAgent,
    patch: dict[str, Any],
) -> list[core_models.Event]:
    """Apply a partial update. Permission and status changes get their own
    event types; everything else rolls up into workspace_agent.updated."""
    stored: list[core_models.Event] = []
    changed_fields: list[str] = []

    for field in _AGENT_PLAIN_FIELDS:
        if field not in patch or patch[field] is None:
            continue
        attr = "meta" if field == "metadata" else field
        if getattr(agent, attr) != patch[field]:
            setattr(agent, attr, patch[field])
            changed_fields.append(field)

    if changed_fields:
        stored += _emit(
            session,
            workspace,
            "workspace_agent.updated",
            {"agent_id": agent.id, "changed_fields": changed_fields},
        )

    if patch.get("permissions") is not None:
        new_permissions = _full_permissions(patch["permissions"])
        if new_permissions != (agent.permissions or {}):
            previous = agent.permissions or {}
            changed = sorted(
                key
                for key, value in new_permissions.items()
                if previous.get(key) != value
            )
            agent.permissions = new_permissions
            stored += _emit(
                session,
                workspace,
                "workspace_agent.permission_changed",
                {
                    "agent_id": agent.id,
                    "changed": changed,
                    "permissions": new_permissions,
                },
            )

    if patch.get("status") is not None and patch["status"] != agent.status:
        previous = agent.status
        agent.status = patch["status"]
        stored += _emit(
            session,
            workspace,
            "workspace_agent.status_changed",
            {"agent_id": agent.id, "from_status": previous, "to_status": agent.status},
        )

    return stored


def delete_agent(
    session: Session, workspace: Workspace, agent: WorkspaceAgent
) -> list[core_models.Event]:
    """Remove the definition row. The event log keeps the history, so
    timeline/replay still show the agent's lifecycle."""
    agent_id, agent_name = agent.id, agent.name
    session.delete(agent)
    session.flush()
    return _emit(
        session,
        workspace,
        "workspace_agent.deleted",
        {"agent_id": agent_id, "agent_name": agent_name},
    )
