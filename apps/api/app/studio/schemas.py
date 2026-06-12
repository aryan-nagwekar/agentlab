"""Studio wire contract."""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from ..timeutil import isoz


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or f"agent-{uuid.uuid4().hex[:6]}"


class StudioModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AgentDefIn(BaseModel):
    agent_id: str | None = Field(default=None, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    role: str = Field(min_length=1, max_length=255)
    description: str | None = None
    system_prompt: str | None = Field(default=None, max_length=8000)
    provider: str = Field(min_length=1, max_length=64)
    model_name: str = Field(min_length=1, max_length=255)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1000, ge=1, le=8000)
    position_x: float = 0.0
    position_y: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentDefOut(StudioModel):
    agent_id: str
    workflow_id: str
    name: str
    role: str
    description: str | None = None
    system_prompt: str | None = None
    provider: str
    model_name: str
    temperature: float
    max_tokens: int
    position_x: float
    position_y: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class EdgeDefIn(BaseModel):
    edge_id: str | None = Field(default=None, max_length=255)
    source_agent_id: str = Field(min_length=1, max_length=255)
    target_agent_id: str = Field(min_length=1, max_length=255)
    label: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EdgeDefOut(StudioModel):
    edge_id: str
    workflow_id: str
    source_agent_id: str
    target_agent_id: str
    label: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    project_id: str = Field(default="demo-project", min_length=1, max_length=255)
    agents: list[AgentDefIn] = Field(default_factory=list, max_length=50)
    edges: list[EdgeDefIn] = Field(default_factory=list, max_length=200)


class WorkflowOut(StudioModel):
    workflow_id: str
    project_id: str
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime
    agents: list[AgentDefOut] = Field(default_factory=list)
    edges: list[EdgeDefOut] = Field(default_factory=list)

    @field_serializer("created_at", "updated_at", when_used="json")
    def _ser_dt(self, value: datetime) -> str | None:
        return isoz(value)


class WorkflowSummaryOut(StudioModel):
    workflow_id: str
    project_id: str
    name: str
    description: str | None = None
    agent_count: int
    edge_count: int
    updated_at: datetime
    last_run_id: str | None = None
    last_run_status: str | None = None

    @field_serializer("updated_at", when_used="json")
    def _ser_dt(self, value: datetime) -> str | None:
        return isoz(value)


class ValidationOut(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class WorkflowRunIn(BaseModel):
    project_id: str | None = Field(default=None, max_length=255)
    input: str = Field(min_length=1, max_length=8000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowRunOut(BaseModel):
    workflow_id: str
    run_id: str
    status: str  # completed | failed
    open_run_url: str


class WorkflowRunRecordOut(StudioModel):
    run_id: str
    workflow_id: str
    project_id: str
    status: str
    input: str | None = None
    created_at: datetime

    @field_serializer("created_at", when_used="json")
    def _ser_dt(self, value: datetime) -> str | None:
        return isoz(value)
