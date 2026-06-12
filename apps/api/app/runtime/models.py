"""Runtime workspace relational model (v1.0 — metadata only).

Workspace rows describe project areas a user authored; the append-only
`events` table remains the source of truth for what happened to them (every
lifecycle action emits a workspace.* event into the workspace's activity
run). Artifacts are registry entries for future project outputs — v1.0
stores names/types/logical paths, never file contents.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ..models import JSONType
from ..timeutil import utcnow

WORKSPACE_STATUSES: tuple[str, ...] = (
    "draft",
    "active",
    "paused",
    "completed",
    "archived",
    "failed",
)

# Workspace agent lifecycle (v1.1) — definition metadata only. quarantined and
# disabled gate *assignment* in the UI; no real runtime quarantine exists yet.
AGENT_STATUSES: tuple[str, ...] = (
    "ready",
    "running",
    "caution",
    "suspicious",
    "quarantined",
    "disabled",
)

# Canonical permission flags (v1.1). These are metadata and future enforcement
# inputs only — nothing here grants or blocks a real capability yet.
AGENT_PERMISSION_KEYS: tuple[str, ...] = (
    "can_read_files",
    "can_write_files",
    "can_delete_files",
    "can_run_commands",
    "can_call_web",
    "can_access_database",
    "can_modify_auth",
    "can_modify_payment",
    "can_modify_deployment",
    "can_send_to_agents",
    "can_send_to_user",
    "can_save_product_data",
    "can_use_unverified_research",
)

# Permissions that should surface a warning badge in the UI — destructive or
# sensitive capabilities a future enforcement gateway will gate.
RISKY_PERMISSION_KEYS: frozenset[str] = frozenset(
    {
        "can_write_files",
        "can_delete_files",
        "can_run_commands",
        "can_access_database",
        "can_modify_auth",
        "can_modify_payment",
        "can_modify_deployment",
    }
)

# Conservative default: an agent can read and talk, nothing else, until the
# user widens it. Templates override explicitly.
DEFAULT_AGENT_PERMISSIONS: tuple[str, ...] = (
    "can_read_files",
    "can_send_to_agents",
    "can_send_to_user",
)


def permission_profile(*enabled: str) -> dict[str, bool]:
    """Build a full permission dict (every key present) with `enabled` set True."""
    return {key: key in set(enabled) for key in AGENT_PERMISSION_KEYS}


def default_permissions() -> dict[str, bool]:
    return permission_profile(*DEFAULT_AGENT_PERMISSIONS)


class Workspace(Base):
    __tablename__ = "runtime_workspaces"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    # Workspace telemetry lives in this project; the activity run collects the
    # workspace.* lifecycle events so timeline/replay work unchanged.
    project_id: Mapped[str] = mapped_column(String(255), index=True)
    activity_run_id: Mapped[str] = mapped_column(String(255), unique=True)
    meta: Mapped[dict] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class WorkspaceArtifact(Base):
    __tablename__ = "runtime_workspace_artifacts"

    workspace_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("runtime_workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    # e.g. "file", "document", "design", "report" — free-form in v1.0.
    type: Mapped[str] = mapped_column(String(64))
    # Logical reference only — v1.0 never reads or writes real files.
    path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    meta: Mapped[dict] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class WorkspaceAgent(Base):
    """An agent *definition* inside a workspace (v1.1).

    Pure metadata: role, prompt, model/provider, permission flags, and budget
    limits. The agent does not execute, write files, call tools, or enforce
    anything in v1.1 — these rows describe what a future Runtime version will
    be allowed to run. provider/model reuse the Model Gateway's vocabulary.
    """

    __tablename__ = "runtime_workspace_agents"

    workspace_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("runtime_workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Model Gateway provider/model vocabulary; defaults stay keyless (mock).
    model_provider: Mapped[str] = mapped_column(String(64), default="mock")
    model_name: Mapped[str] = mapped_column(String(128), default="mock:claude-sonnet")
    allowed_tools: Mapped[list] = mapped_column(JSONType, default=list)
    denied_tools: Mapped[list] = mapped_column(JSONType, default=list)
    permissions: Mapped[dict] = mapped_column(JSONType, default=default_permissions)
    # Budget ceilings — recorded for a future runtime; nothing meters them yet.
    max_tokens_per_call: Mapped[int] = mapped_column(default=2048)
    max_calls_per_run: Mapped[int] = mapped_column(default=25)
    max_tool_calls_per_run: Mapped[int] = mapped_column(default=25)
    requires_verification: Mapped[bool] = mapped_column(default=False)
    trust_score: Mapped[float] = mapped_column(default=1.0)
    risk_score: Mapped[float] = mapped_column(default=0.0)
    status: Mapped[str] = mapped_column(String(32), default="ready")
    meta: Mapped[dict] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
