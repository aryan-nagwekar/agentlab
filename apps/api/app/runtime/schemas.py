"""Runtime workspace wire contract (v1.0)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from ..timeutil import isoz
from .models import AGENT_PERMISSION_KEYS, AGENT_STATUSES, WORKSPACE_STATUSES


class RuntimeModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _validate_status(value: str) -> str:
    if value not in WORKSPACE_STATUSES:
        raise ValueError(
            f"unknown status {value!r}; known: {', '.join(WORKSPACE_STATUSES)}"
        )
    return value


def _validate_agent_status(value: str) -> str:
    if value not in AGENT_STATUSES:
        raise ValueError(
            f"unknown agent status {value!r}; known: {', '.join(AGENT_STATUSES)}"
        )
    return value


def _validate_permissions(value: dict[str, bool]) -> dict[str, bool]:
    unknown = set(value) - set(AGENT_PERMISSION_KEYS)
    if unknown:
        raise ValueError(
            f"unknown permission(s) {', '.join(sorted(unknown))}; "
            f"known: {', '.join(AGENT_PERMISSION_KEYS)}"
        )
    if any(not isinstance(flag, bool) for flag in value.values()):
        raise ValueError("permission values must be booleans")
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
    agent_count: int = 0
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


# ---------------------------------------------------------- workspace agents (v1.1)


class AgentDefinitionIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    role: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    system_prompt: str | None = Field(default=None, max_length=8000)
    model_provider: str = Field(default="mock", min_length=1, max_length=64)
    model_name: str = Field(default="mock:claude-sonnet", min_length=1, max_length=128)
    allowed_tools: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)
    permissions: dict[str, bool] = Field(default_factory=dict)
    max_tokens_per_call: int = Field(default=2048, ge=1, le=1_000_000)
    max_calls_per_run: int = Field(default=25, ge=1, le=100_000)
    max_tool_calls_per_run: int = Field(default=25, ge=0, le=100_000)
    requires_verification: bool = False
    trust_score: float = Field(default=1.0, ge=0.0, le=1.0)
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    status: str = Field(default="ready")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("status")
    @classmethod
    def _status_known(cls, value: str) -> str:
        return _validate_agent_status(value)

    @field_validator("permissions")
    @classmethod
    def _permissions_known(cls, value: dict[str, bool]) -> dict[str, bool]:
        return _validate_permissions(value)


class AgentDefinitionPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    role: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    system_prompt: str | None = Field(default=None, max_length=8000)
    model_provider: str | None = Field(default=None, min_length=1, max_length=64)
    model_name: str | None = Field(default=None, min_length=1, max_length=128)
    allowed_tools: list[str] | None = None
    denied_tools: list[str] | None = None
    permissions: dict[str, bool] | None = None
    max_tokens_per_call: int | None = Field(default=None, ge=1, le=1_000_000)
    max_calls_per_run: int | None = Field(default=None, ge=1, le=100_000)
    max_tool_calls_per_run: int | None = Field(default=None, ge=0, le=100_000)
    requires_verification: bool | None = None
    trust_score: float | None = Field(default=None, ge=0.0, le=1.0)
    risk_score: float | None = Field(default=None, ge=0.0, le=1.0)
    status: str | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("status")
    @classmethod
    def _status_known(cls, value: str | None) -> str | None:
        return _validate_agent_status(value) if value is not None else None

    @field_validator("permissions")
    @classmethod
    def _permissions_known(
        cls, value: dict[str, bool] | None
    ) -> dict[str, bool] | None:
        return _validate_permissions(value) if value is not None else None


class AgentFromTemplateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)


class AgentDefinitionOut(RuntimeModel):
    agent_id: str
    workspace_id: str
    name: str
    role: str
    description: str | None = None
    system_prompt: str | None = None
    model_provider: str
    model_name: str
    allowed_tools: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)
    permissions: dict[str, bool] = Field(default_factory=dict)
    max_tokens_per_call: int
    max_calls_per_run: int
    max_tool_calls_per_run: int
    requires_verification: bool
    trust_score: float
    risk_score: float
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at", when_used="json")
    def _ser_dt(self, value: datetime) -> str | None:
        return isoz(value)


class AgentTemplateOut(BaseModel):
    template_id: str
    name: str
    role: str
    description: str
    system_prompt: str
    model_provider: str
    model_name: str
    permissions: dict[str, bool]
    allowed_tools: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)
    max_tokens_per_call: int
    max_calls_per_run: int
    max_tool_calls_per_run: int
    requires_verification: bool
    trust_score: float
    risk_score: float
    status: str
    risk_notes: list[str] = Field(default_factory=list)
    future_approval_required: list[str] = Field(default_factory=list)
