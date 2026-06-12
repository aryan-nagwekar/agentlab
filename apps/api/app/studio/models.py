"""Studio relational model — workflow definitions, separate from telemetry.

These tables describe what a user *authored*; the append-only `events` table
remains the source of truth for what actually *happened* when a workflow ran.
`studio_workflow_runs` is just the join between the two worlds.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, String, Text

from ..db import Base
from ..models import JSONType
from ..timeutil import utcnow

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import DateTime


class WorkflowDefinition(Base):
    __tablename__ = "studio_workflows"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AgentDefinition(Base):
    __tablename__ = "studio_agents"

    # Agent ids are human-readable slugs unique per workflow (mirrors the
    # telemetry convention of per-project agent slugs).
    workflow_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("studio_workflows.id", ondelete="CASCADE"), primary_key=True
    )
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str] = mapped_column(String(64))
    model_name: Mapped[str] = mapped_column(String(255))
    temperature: Mapped[float] = mapped_column(Float, default=0.2)
    max_tokens: Mapped[int] = mapped_column(Integer, default=1000)
    position_x: Mapped[float] = mapped_column(Float, default=0.0)
    position_y: Mapped[float] = mapped_column(Float, default=0.0)
    meta: Mapped[dict] = mapped_column("metadata", JSONType, default=dict)


class WorkflowEdgeDefinition(Base):
    __tablename__ = "studio_edges"

    workflow_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("studio_workflows.id", ondelete="CASCADE"), primary_key=True
    )
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    source_agent_id: Mapped[str] = mapped_column(String(255))
    target_agent_id: Mapped[str] = mapped_column(String(255))
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta: Mapped[dict] = mapped_column("metadata", JSONType, default=dict)


class WorkflowRun(Base):
    """Join table: which AgentLab run came from which workflow definition."""

    __tablename__ = "studio_workflow_runs"

    run_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String(255), index=True)
    project_id: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(32), default="completed")
    input: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
