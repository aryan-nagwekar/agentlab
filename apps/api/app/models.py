"""Relational model.

`events` is the append-only source of truth. The remaining tables
(runs/agents/messages/tool_calls/routing_decisions) are projections maintained
at ingest time for fast queries; agent ids are stored as plain strings (no FK)
so events referencing not-yet-registered agents never fail ingestion.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .timeutil import utcnow

JSONType = JSON().with_variant(JSONB(), "postgresql")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("projects.id"), index=True
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    total_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_cost_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, default=0)


class Agent(Base):
    __tablename__ = "agents"

    # Composite key: agent ids are human-readable slugs unique per project.
    project_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="unknown")
    trust_score: Mapped[float] = mapped_column(Float, default=1.0)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    project_id: Mapped[str] = mapped_column(String(255), index=True)
    run_id: Mapped[str] = mapped_column(String(255), index=True)
    source_agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    target_agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSONType, default=dict)
    meta: Mapped[dict] = mapped_column("metadata", JSONType, default=dict)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(255), index=True)
    run_id: Mapped[str] = mapped_column(String(255), index=True)
    source_agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="sent")
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(255), index=True)
    run_id: Mapped[str] = mapped_column(String(255), index=True)
    agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    tool_name: Mapped[str] = mapped_column(String(255))
    input: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RoutingDecision(Base):
    __tablename__ = "routing_decisions"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(255), index=True)
    run_id: Mapped[str] = mapped_column(String(255), index=True)
    source_agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    selected_agent_id: Mapped[str] = mapped_column(String(255))
    candidate_agents: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
