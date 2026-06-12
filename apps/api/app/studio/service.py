"""Studio persistence helpers and the seeded demo workflow."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import AgentDefinition, WorkflowDefinition, WorkflowEdgeDefinition, WorkflowRun
from .schemas import AgentDefIn, EdgeDefIn, WorkflowIn, slugify


def get_workflow(session: Session, workflow_id: str) -> WorkflowDefinition | None:
    return session.get(WorkflowDefinition, workflow_id)


def workflow_agents(session: Session, workflow_id: str) -> list[AgentDefinition]:
    return list(
        session.execute(
            select(AgentDefinition)
            .where(AgentDefinition.workflow_id == workflow_id)
            .order_by(AgentDefinition.position_y, AgentDefinition.position_x, AgentDefinition.id)
        ).scalars()
    )


def workflow_edges(session: Session, workflow_id: str) -> list[WorkflowEdgeDefinition]:
    return list(
        session.execute(
            select(WorkflowEdgeDefinition)
            .where(WorkflowEdgeDefinition.workflow_id == workflow_id)
            .order_by(WorkflowEdgeDefinition.id)
        ).scalars()
    )


def _unique_agent_id(requested: str | None, name: str, taken: set[str]) -> str:
    base = requested or slugify(name)
    candidate = base
    suffix = 2
    while candidate in taken:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def add_agent(
    session: Session, workflow_id: str, body: AgentDefIn, taken: set[str]
) -> AgentDefinition:
    agent = AgentDefinition(
        workflow_id=workflow_id,
        id=_unique_agent_id(body.agent_id, body.name, taken),
        name=body.name,
        role=body.role,
        description=body.description,
        system_prompt=body.system_prompt,
        provider=body.provider,
        model_name=body.model_name,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        position_x=body.position_x,
        position_y=body.position_y,
        meta=body.metadata,
    )
    session.add(agent)
    return agent


def add_edge(session: Session, workflow_id: str, body: EdgeDefIn) -> WorkflowEdgeDefinition:
    edge = WorkflowEdgeDefinition(
        workflow_id=workflow_id,
        id=body.edge_id or f"edge-{uuid.uuid4().hex[:8]}",
        source_agent_id=body.source_agent_id,
        target_agent_id=body.target_agent_id,
        label=body.label,
        meta=body.metadata,
    )
    session.add(edge)
    return edge


def replace_workflow_graph(session: Session, workflow: WorkflowDefinition, body: WorkflowIn) -> None:
    """Wholesale update used by the canvas Save button."""
    workflow.name = body.name
    workflow.description = body.description
    workflow.project_id = body.project_id
    for existing in workflow_agents(session, workflow.id):
        session.delete(existing)
    for existing in workflow_edges(session, workflow.id):
        session.delete(existing)
    session.flush()
    taken: set[str] = set()
    for agent_in in body.agents:
        agent = add_agent(session, workflow.id, agent_in, taken)
        taken.add(agent.id)
    for edge_in in body.edges:
        add_edge(session, workflow.id, edge_in)


def create_workflow(session: Session, body: WorkflowIn) -> WorkflowDefinition:
    workflow = WorkflowDefinition(
        id=f"workflow-{uuid.uuid4().hex[:10]}",
        project_id=body.project_id,
        name=body.name,
        description=body.description,
    )
    session.add(workflow)
    session.flush()
    taken: set[str] = set()
    for agent_in in body.agents:
        agent = add_agent(session, workflow.id, agent_in, taken)
        taken.add(agent.id)
    for edge_in in body.edges:
        add_edge(session, workflow.id, edge_in)
    return workflow


def delete_workflow(session: Session, workflow: WorkflowDefinition) -> None:
    for agent in workflow_agents(session, workflow.id):
        session.delete(agent)
    for edge in workflow_edges(session, workflow.id):
        session.delete(edge)
    session.delete(workflow)


def latest_run(session: Session, workflow_id: str) -> WorkflowRun | None:
    return session.execute(
        select(WorkflowRun)
        .where(WorkflowRun.workflow_id == workflow_id)
        .order_by(WorkflowRun.created_at.desc(), WorkflowRun.run_id.desc())
        .limit(1)
    ).scalar_one_or_none()


# ------------------------------------------------------------------ demo seed

SEED_WORKFLOW_NAME = "Code Review Agent Team"
SEED_INPUT = (
    "Build a simple FastAPI endpoint that accepts a username and returns a "
    "greeting. Then review it for basic security issues."
)


def seed_default_workflow(session: Session) -> WorkflowDefinition | None:
    """Create the demo workflow once, so Studio works with zero setup and
    zero API keys (every agent uses the keyless mock provider)."""
    count = session.execute(select(func.count(WorkflowDefinition.id))).scalar_one()
    if count:
        return None
    workflow = create_workflow(
        session,
        WorkflowIn(
            name=SEED_WORKFLOW_NAME,
            description=(
                "Plan → code → security-review → report. Seeded demo workflow; "
                "all agents run on the keyless mock provider."
            ),
            project_id="demo-project",
            agents=[
                AgentDefIn(
                    agent_id="planner-agent",
                    name="Planner Agent",
                    role="planner",
                    system_prompt="Break the request into a short, ordered plan for the team.",
                    provider="mock",
                    model_name="mock:claude-sonnet",
                    position_x=0,
                    position_y=0,
                ),
                AgentDefIn(
                    agent_id="coder-agent",
                    name="Coder Agent",
                    role="coder",
                    system_prompt="Implement the plan as clean, minimal code.",
                    provider="mock",
                    model_name="mock:gpt-4.1",
                    position_x=260,
                    position_y=120,
                ),
                AgentDefIn(
                    agent_id="security-reviewer",
                    name="Security Reviewer",
                    role="security",
                    system_prompt="Review the code for basic security issues (injection, validation, secrets).",
                    provider="mock",
                    model_name="mock:claude-sonnet",
                    position_x=520,
                    position_y=240,
                ),
                AgentDefIn(
                    agent_id="report-agent",
                    name="Report Agent",
                    role="reporter",
                    system_prompt="Summarize the work and findings as a concise report.",
                    provider="mock",
                    model_name="mock:gemini-pro",
                    position_x=780,
                    position_y=360,
                ),
            ],
            edges=[
                EdgeDefIn(edge_id="edge-plan-code", source_agent_id="planner-agent",
                          target_agent_id="coder-agent", label="plan"),
                EdgeDefIn(edge_id="edge-code-review", source_agent_id="coder-agent",
                          target_agent_id="security-reviewer", label="code"),
                EdgeDefIn(edge_id="edge-review-report", source_agent_id="security-reviewer",
                          target_agent_id="report-agent", label="findings"),
            ],
        ),
    )
    session.commit()
    return workflow
