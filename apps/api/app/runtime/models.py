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
