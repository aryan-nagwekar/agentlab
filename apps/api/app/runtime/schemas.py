"""Runtime workspace wire contract (v1.0)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from ..timeutil import isoz
from .models import WORKSPACE_STATUSES


class RuntimeModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _validate_status(value: str) -> str:
    if value not in WORKSPACE_STATUSES:
        raise ValueError(
            f"unknown status {value!r}; known: {', '.join(WORKSPACE_STATUSES)}"
        )
    return value


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    goal: str | None = Field(default=None, max_length=4000)
    project_id: str = Field(default="demo-project", min_length=1, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkspacePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    goal: str | None = Field(default=None, max_length=4000)
    status: str | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("status")
    @classmethod
    def _status_known(cls, value: str | None) -> str | None:
        return _validate_status(value) if value is not None else None


class WorkspaceOut(RuntimeModel):
    workspace_id: str
    name: str
    goal: str | None = None
    status: str
    project_id: str
    activity_run_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    artifact_count: int = 0
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at", when_used="json")
    def _ser_dt(self, value: datetime) -> str | None:
        return isoz(value)


class ArtifactIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: str = Field(default="file", min_length=1, max_length=64)
    path: str | None = Field(default=None, max_length=512)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactOut(RuntimeModel):
    artifact_id: str
    workspace_id: str
    name: str
    type: str
    path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at", when_used="json")
    def _ser_dt(self, value: datetime) -> str | None:
        return isoz(value)
