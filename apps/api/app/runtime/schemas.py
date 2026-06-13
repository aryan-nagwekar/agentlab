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
    # Quarantine bookkeeping (v1.7) — present while quarantined or after a lift.
    quarantine: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at", when_used="json")
    def _ser_dt(self, value: datetime) -> str | None:
        return isoz(value)


# ----------------------------------------------------------- sandbox files (v1.2)


class SandboxStatusOut(BaseModel):
    workspace_id: str
    initialized: bool
    file_count: int = 0
    directory_count: int = 0
    total_bytes: int = 0


class FileEntryOut(BaseModel):
    name: str
    # Logical workspace-relative path — host filesystem paths never leave the server.
    path: str
    type: str  # "file" | "directory"
    size_bytes: int = 0
    modified_at: float | None = None
    children: list["FileEntryOut"] | None = None


class FileReadOut(BaseModel):
    path: str
    content: str
    size_bytes: int
    sha256: str


class FileWriteIn(BaseModel):
    path: str = Field(min_length=1, max_length=512)
    content: str = Field(default="", max_length=1_000_000)
    # v1.7: attribute the action to an agent; a quarantined agent is refused.
    agent_id: str | None = Field(default=None, max_length=255)


class FileWriteOut(BaseModel):
    path: str
    size_bytes: int
    sha256: str
    created: bool


class MkdirIn(BaseModel):
    path: str = Field(min_length=1, max_length=512)
    agent_id: str | None = Field(default=None, max_length=255)


class MkdirOut(BaseModel):
    path: str
    created: bool


class FileDeleteOut(BaseModel):
    path: str
    kind: str  # "file" | "directory"


# --------------------------------------------------------- sandbox commands (v1.3)


class CommandRunIn(BaseModel):
    # Structured argv — never a shell string. shell=False end to end.
    command: str = Field(min_length=1, max_length=64)
    args: list[str] = Field(default_factory=list, max_length=20)
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    working_subdir: str = Field(default="", max_length=512)
    agent_id: str | None = Field(default=None, max_length=255)

    @field_validator("args")
    @classmethod
    def _args_bounded(cls, value: list[str]) -> list[str]:
        if any(len(arg) > 512 for arg in value):
            raise ValueError("arguments are limited to 512 characters each")
        return value


class CommandRunOut(BaseModel):
    command: str
    argv: list[str]
    # Logical workspace path ("." = sandbox root) — never a host path.
    cwd: str
    status: str  # completed | failed | timed_out
    exit_code: int | None = None
    duration_ms: int
    stdout: str
    stderr: str
    stdout_truncated: bool = False
    stderr_truncated: bool = False


class AllowedCommandOut(BaseModel):
    command: str
    description: str
    examples: list[str] = Field(default_factory=list)


# ------------------------------------------------------------ orchestration (v1.4)


class WorkflowIn(BaseModel):
    # Defaults to the workspace goal when omitted.
    goal: str | None = Field(default=None, max_length=4000)
    created_by: str = Field(default="user", min_length=1, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowOut(RuntimeModel):
    workflow_id: str
    workspace_id: str
    goal: str
    status: str
    created_by: str
    task_count: int = 0
    completed_task_count: int = 0
    has_plan: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at", when_used="json")
    def _ser_dt(self, value: datetime) -> str | None:
        return isoz(value)


class WorkflowPlanOut(RuntimeModel):
    plan_id: str
    workflow_id: str
    summary: str
    steps: list[dict[str, Any]] = Field(default_factory=list)
    dependencies: dict[str, Any] = Field(default_factory=dict)
    required_agents: list[str] = Field(default_factory=list)
    risk_assessment: str | None = None
    validation_requirements: list[str] = Field(default_factory=list)
    approval_requirements: list[str] = Field(default_factory=list)
    created_at: datetime

    @field_serializer("created_at", when_used="json")
    def _ser_dt(self, value: datetime) -> str | None:
        return isoz(value)


class TaskResultOut(RuntimeModel):
    result_id: str
    task_id: str
    agent_id: str | None = None
    output: str
    artifacts: list[str] = Field(default_factory=list)
    validation_status: str
    created_at: datetime

    @field_serializer("created_at", when_used="json")
    def _ser_dt(self, value: datetime) -> str | None:
        return isoz(value)


class TaskOut(RuntimeModel):
    task_id: str
    workflow_id: str
    workspace_id: str
    assigned_agent_id: str | None = None
    assigned_agent_name: str | None = None
    title: str
    description: str | None = None
    status: str
    dependencies: list[str] = Field(default_factory=list)
    expected_artifacts: list[str] = Field(default_factory=list)
    risk_level: str
    requires_validation: bool
    requires_approval: bool
    blocked_reason: str | None = None
    latest_result: TaskResultOut | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at", when_used="json")
    def _ser_dt(self, value: datetime) -> str | None:
        return isoz(value)


class TaskPatch(BaseModel):
    # v1.4 allows direct transitions to these statuses only; dependencies are
    # planner-owned and not editable.
    status: str | None = None
    assigned_agent_id: str | None = Field(default=None, max_length=255)
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator("status")
    @classmethod
    def _status_known(cls, value: str | None) -> str | None:
        allowed = {"running", "completed", "failed", "blocked"}
        if value is not None and value not in allowed:
            raise ValueError(
                f"status {value!r} cannot be set directly in v1.4; "
                f"allowed: {', '.join(sorted(allowed))}"
            )
        return value


class TaskResultIn(BaseModel):
    output: str = Field(min_length=1, max_length=4000)
    artifacts: list[str] = Field(default_factory=list, max_length=20)


# -------------------------------------------------------------- enforcement (v1.5)


class ActionProposalIn(BaseModel):
    action_type: str = Field(min_length=1, max_length=64)
    actor_type: str = Field(default="user")
    target: str = Field(default="", max_length=512)
    input_summary: str = Field(default="", max_length=2000)
    sensitivity_level: str = Field(default="normal")
    expected_effect: str | None = Field(default=None, max_length=500)
    requires_approval_hint: bool = False
    agent_id: str | None = Field(default=None, max_length=255)
    workflow_id: str | None = Field(default=None, max_length=255)
    task_id: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)
    # The generic API only proposes/evaluates — it never executes anything.
    evaluate: bool = True

    @field_validator("actor_type")
    @classmethod
    def _actor_known(cls, value: str) -> str:
        from .models import ACTOR_TYPES

        if value not in ACTOR_TYPES:
            raise ValueError(
                f"unknown actor_type {value!r}; known: {', '.join(ACTOR_TYPES)}"
            )
        return value

    @field_validator("sensitivity_level")
    @classmethod
    def _sensitivity_known(cls, value: str) -> str:
        if value not in ("low", "normal", "high"):
            raise ValueError("sensitivity_level must be low, normal, or high")
        return value


class ActionDecisionOut(RuntimeModel):
    decision_id: str
    action_id: str
    decision: str
    matched_rules: list[dict[str, str]] = Field(default_factory=list)
    trust_score_before: float | None = None
    risk_score_before: float | None = None
    reason: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    @field_serializer("created_at", when_used="json")
    def _ser_dt(self, value: datetime) -> str | None:
        return isoz(value)


class ActionProposalOut(RuntimeModel):
    action_id: str
    workspace_id: str
    workflow_id: str | None = None
    task_id: str | None = None
    agent_id: str | None = None
    actor_type: str
    action_type: str
    target: str
    input_summary: str
    sensitivity_level: str
    expected_effect: str | None = None
    requires_approval_hint: bool
    status: str
    decision: ActionDecisionOut | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    @field_serializer("created_at", when_used="json")
    def _ser_dt(self, value: datetime) -> str | None:
        return isoz(value)


class DecisionRecordOut(ActionDecisionOut):
    """A decision joined with its proposal's headline fields, for the panel."""

    action_type: str
    actor_type: str
    target: str
    action_status: str


class PolicyRuleOut(BaseModel):
    id: str
    name: str
    description: str
    enabled: bool
    priority: int
    action_types: list[str]
    decision: str
    reason: str


# ------------------------------------------------------------- approvals (v1.6)


class ApprovalOut(RuntimeModel):
    approval_id: str
    workspace_id: str
    workflow_id: str | None = None
    task_id: str | None = None
    action_id: str
    agent_id: str | None = None
    title: str
    plain_english_summary: str
    technical_summary: str
    risk_level: str
    matched_policy_rules: list[dict[str, str]] = Field(default_factory=list)
    recommended_decision: str
    options: list[str] = Field(default_factory=list)
    status: str
    action_type: str = ""
    target: str = ""
    resolution_decision: str | None = None
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    resolution_reason: str | None = None
    execution_status: str
    execution_detail: str | None = None
    created_at: datetime

    @field_serializer("created_at", "resolved_at", when_used="json")
    def _ser_dt(self, value: datetime | None) -> str | None:
        return isoz(value) if value else None


class ApprovalResolveIn(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)
    resolved_by: str = Field(default="user", min_length=1, max_length=255)
    # approve endpoint only: record as a one-time approval.
    once: bool = False


class PendingCountOut(BaseModel):
    pending: int


# ------------------------------------------------------------- quarantine (v1.7)


class QuarantineIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    requested_by: str = Field(default="user", min_length=1, max_length=255)


class UnquarantineIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    requested_by: str = Field(default="user", min_length=1, max_length=255)


class QuarantineStatusOut(BaseModel):
    agent_id: str
    status: str
    quarantined: bool
    quarantine: dict[str, Any] | None = None


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
