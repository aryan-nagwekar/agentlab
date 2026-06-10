"""Pydantic schemas — the wire contract with the SDK and the dashboard."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
)

from .events import EVENT_TYPES
from .timeutil import isoz


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------- ingest


class EventIn(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()), max_length=64)
    event_type: str
    timestamp: datetime | None = None
    project_id: str = Field(min_length=1, max_length=255)
    run_id: str = Field(min_length=1, max_length=255)
    source_agent_id: str | None = Field(default=None, max_length=255)
    target_agent_id: str | None = Field(default=None, max_length=255)
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def _known_type(cls, value: str) -> str:
        if value not in EVENT_TYPES:
            raise ValueError(f"unknown event_type {value!r}")
        return value


class EventBatchIn(BaseModel):
    events: list[EventIn] = Field(min_length=1, max_length=1000)


class IngestResultOut(BaseModel):
    accepted: int
    duplicates: int


# ----------------------------------------------------------------------- read


class EventOut(APIModel):
    id: int
    event_id: str
    event_type: str
    timestamp: datetime
    project_id: str
    run_id: str
    source_agent_id: str | None = None
    target_agent_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(
        default_factory=dict, validation_alias=AliasChoices("meta", "metadata")
    )

    @field_serializer("timestamp", when_used="json")
    def _ser_ts(self, value: datetime) -> str | None:
        return isoz(value)


class RunOut(APIModel):
    id: str
    project_id: str
    name: str | None = None
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_latency_ms: float | None = None
    total_cost_estimate: float | None = None
    total_tokens: int | None = None
    error_count: int = 0
    # Populated by list endpoints via aggregate queries (not stored columns).
    agent_count: int | None = None
    message_count: int | None = None
    event_count: int | None = None

    @field_serializer("started_at", "completed_at", when_used="json")
    def _ser_dt(self, value: datetime | None) -> str | None:
        return isoz(value)


class AgentOut(APIModel):
    project_id: str
    id: str
    name: str
    role: str | None = None
    description: str | None = None
    status: str
    trust_score: float
    risk_score: float
    created_at: datetime | None = None
    last_seen_at: datetime | None = None

    @field_serializer("created_at", "last_seen_at", when_used="json")
    def _ser_dt(self, value: datetime | None) -> str | None:
        return isoz(value)


class ProjectOut(APIModel):
    id: str
    name: str
    description: str | None = None
    created_at: datetime | None = None
    run_count: int = 0
    agent_count: int = 0
    last_activity_at: datetime | None = None

    @field_serializer("created_at", "last_activity_at", when_used="json")
    def _ser_dt(self, value: datetime | None) -> str | None:
        return isoz(value)


class ProjectDetailOut(BaseModel):
    project: ProjectOut
    runs: list[RunOut]
    agents: list[AgentOut]


# ---------------------------------------------------------------------- graph


class GraphNodeOut(BaseModel):
    id: str
    name: str
    role: str | None = None
    status: str = "unknown"
    trust_score: float = 1.0
    risk_score: float = 0.0
    messages_in: int = 0
    messages_out: int = 0
    tool_calls: int = 0
    errors: int = 0
    avg_latency_ms: float | None = None
    tokens: int = 0
    cost_estimate: float = 0.0


class GraphEdgeOut(BaseModel):
    id: str
    source: str
    target: str
    message_count: int = 0
    avg_latency_ms: float | None = None
    last_status: str | None = None
    last_message_at: datetime | None = None

    @field_serializer("last_message_at", when_used="json")
    def _ser_dt(self, value: datetime | None) -> str | None:
        return isoz(value)


class RunGraphOut(BaseModel):
    run_id: str
    project_id: str
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]


# --------------------------------------------------------------------- replay


class ReplayMarkersOut(BaseModel):
    """Indices into the ordered event tape, used for jump-to navigation."""

    errors: list[int] = Field(default_factory=list)
    tool_calls: list[int] = Field(default_factory=list)
    routing: list[int] = Field(default_factory=list)
    messages: list[int] = Field(default_factory=list)


class RunReplayOut(BaseModel):
    run_id: str
    project_id: str
    status: str
    name: str | None = None
    event_count: int
    duration_ms: float | None = None
    markers: ReplayMarkersOut
    events: list[EventOut]


# -------------------------------------------------------------------- metrics


class MetricsTotalsOut(BaseModel):
    agents: int = 0
    messages: int = 0
    tool_calls: int = 0
    model_calls: int = 0
    events: int = 0
    tokens: int = 0
    cost_estimate: float = 0.0
    avg_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    error_count: int = 0
    error_rate: float = 0.0
    duration_ms: float | None = None


class AgentMetricsOut(BaseModel):
    agent_id: str
    name: str
    role: str | None = None
    messages: int = 0
    tool_calls: int = 0
    model_calls: int = 0
    tokens: int = 0
    cost_estimate: float = 0.0
    avg_latency_ms: float | None = None
    errors: int = 0
    trust_score: float = 1.0


class HighlightOut(BaseModel):
    agent_id: str
    name: str
    value: float
    unit: str


class RunMetricsOut(BaseModel):
    run_id: str
    totals: MetricsTotalsOut
    per_agent: list[AgentMetricsOut]
    highlights: dict[str, HighlightOut | None]
