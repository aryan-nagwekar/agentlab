"""Default workspace-agent blueprints (v1.1).

Templates are *data*, not a runtime: instantiating one materializes a normal
WorkspaceAgent definition row. Every default uses the keyless mock provider so
a fresh install can add agents with no API keys. Permission flags and the
`risk_notes` here are metadata + future-enforcement inputs — nothing executes,
writes files, or is blocked in v1.1.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import permission_profile


@dataclass(frozen=True)
class AgentTemplate:
    template_id: str
    name: str
    role: str
    description: str
    system_prompt: str
    permissions: dict[str, bool]
    status: str = "ready"
    model_provider: str = "mock"
    model_name: str = "mock:claude-sonnet"
    allowed_tools: list[str] = field(default_factory=list)
    denied_tools: list[str] = field(default_factory=list)
    max_tokens_per_call: int = 2048
    max_calls_per_run: int = 25
    max_tool_calls_per_run: int = 25
    requires_verification: bool = False
    trust_score: float = 1.0
    risk_score: float = 0.0
    # Human-readable cautions surfaced in the UI; also seeds agent metadata.
    risk_notes: list[str] = field(default_factory=list)
    # Permissions a future approval/enforcement layer should gate for this role.
    future_approval_required: list[str] = field(default_factory=list)


AGENT_TEMPLATES: tuple[AgentTemplate, ...] = (
    AgentTemplate(
        template_id="planner",
        name="Planner Agent",
        role="planner",
        description="Breaks a goal into a task plan and workflow structure for other agents.",
        system_prompt=(
            "You are the Planner. Decompose the workspace goal into an ordered plan of "
            "tasks and assign each to the right agent. You do not write files or run commands."
        ),
        permissions=permission_profile(
            "can_read_files", "can_send_to_agents", "can_send_to_user"
        ),
        risk_notes=["Cannot write files or run commands — planning only."],
    ),
    AgentTemplate(
        template_id="ui-agent",
        name="UI Agent",
        role="frontend",
        description="Creates and edits frontend components, pages, and styles.",
        system_prompt=(
            "You are the UI Agent. Build and refine frontend components, pages, and styles. "
            "You must not touch authentication, payment, or deployment configuration."
        ),
        permissions=permission_profile(
            "can_read_files", "can_write_files", "can_send_to_agents", "can_send_to_user"
        ),
        risk_notes=[
            "Auth, payment, and deployment changes are disallowed and will be approval-required "
            "in a future Runtime version."
        ],
        future_approval_required=[
            "can_modify_auth",
            "can_modify_payment",
            "can_modify_deployment",
        ],
    ),
    AgentTemplate(
        template_id="backend-coder",
        name="Backend Coder Agent",
        role="backend",
        description="Creates APIs, schemas, DB models, and cart/checkout logic.",
        system_prompt=(
            "You are the Backend Coder. Implement APIs, data schemas, database models, and "
            "checkout logic. Treat auth, payment, deployment, and destructive database actions "
            "as high-risk and flag them for review."
        ),
        permissions=permission_profile(
            "can_read_files",
            "can_write_files",
            "can_access_database",
            "can_send_to_agents",
            "can_send_to_user",
        ),
        status="caution",
        risk_score=0.4,
        requires_verification=True,
        risk_notes=[
            "Touches database and server logic; auth/payment/deployment/destructive DB actions "
            "are high-risk and will be gated by a future enforcement gateway."
        ],
        future_approval_required=[
            "can_modify_auth",
            "can_modify_payment",
            "can_modify_deployment",
            "can_delete_files",
        ],
    ),
    AgentTemplate(
        template_id="researcher",
        name="Researcher Agent",
        role="research",
        description="Researches products, suppliers, and market information from the web.",
        system_prompt=(
            "You are the Researcher. Gather information on products, suppliers, and markets. "
            "Do not treat unverified claims as fact — they must be validated before use."
        ),
        permissions=permission_profile(
            "can_read_files", "can_call_web", "can_send_to_agents", "can_send_to_user"
        ),
        model_name="mock:gpt-4.1",
        requires_verification=True,
        risk_notes=[
            "Cannot save business-critical data without verification; product/supplier claims "
            "require validation in a later version."
        ],
    ),
    AgentTemplate(
        template_id="marketing",
        name="Marketing Agent",
        role="marketing",
        description="Writes product copy, SEO content, and ad creative.",
        system_prompt=(
            "You are the Marketing Agent. Write product copy, SEO content, and ads. Only use "
            "product facts that have been verified — never unverified research."
        ),
        permissions=permission_profile(
            "can_read_files", "can_send_to_agents", "can_send_to_user"
        ),
        risk_notes=["Must not use unverified product data."],
    ),
    AgentTemplate(
        template_id="verifier",
        name="Verifier Agent",
        role="verifier",
        description="Validates claims and evidence produced by other agents.",
        system_prompt=(
            "You are the Verifier. Inspect evidence and validate claims. You cannot override "
            "deterministic validators on your own — you advise."
        ),
        permissions=permission_profile(
            "can_read_files", "can_send_to_agents", "can_send_to_user"
        ),
        risk_notes=["Inspects evidence; cannot override deterministic validators alone."],
    ),
    AgentTemplate(
        template_id="safety-reviewer",
        name="Safety Reviewer Agent",
        role="safety",
        description="Summarizes risks and suggests approval decisions.",
        system_prompt=(
            "You are the Safety Reviewer. Summarize the risk of proposed actions and recommend "
            "approve/deny. You are advisory only and cannot execute risky actions."
        ),
        permissions=permission_profile(
            "can_read_files", "can_send_to_agents", "can_send_to_user"
        ),
        risk_notes=["Advisory only — cannot directly execute risky actions."],
    ),
)

_BY_ID = {template.template_id: template for template in AGENT_TEMPLATES}


def get_template(template_id: str) -> AgentTemplate | None:
    return _BY_ID.get(template_id)
