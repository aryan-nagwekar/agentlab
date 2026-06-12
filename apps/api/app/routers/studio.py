"""Agent Builder Studio endpoints (v0.8).

Workflow definitions are plain CRUD; running a workflow validates it, executes
the DAG through the Model Gateway, and pushes the resulting events through the
normal collector pipeline (storage, projections, WebSocket broadcast) — a
Studio run is indistinguishable from an SDK-instrumented run downstream.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..collector import process_events
from ..deps import get_session, require_api_key
from ..schemas import EventOut
from ..studio import service
from ..studio.executor import execute_workflow
from ..studio.models import WorkflowDefinition, WorkflowRun
from ..studio.schemas import (
    AgentDefIn,
    AgentDefOut,
    EdgeDefIn,
    EdgeDefOut,
    ValidationOut,
    WorkflowIn,
    WorkflowOut,
    WorkflowRunIn,
    WorkflowRunOut,
    WorkflowRunRecordOut,
    WorkflowSummaryOut,
)
from ..studio.validation import validate_workflow

router = APIRouter()


def _registry(request: Request):
    return request.app.state.provider_registry


def _agent_out(agent) -> AgentDefOut:
    return AgentDefOut(
        agent_id=agent.id,
        workflow_id=agent.workflow_id,
        name=agent.name,
        role=agent.role,
        description=agent.description,
        system_prompt=agent.system_prompt,
        provider=agent.provider,
        model_name=agent.model_name,
        temperature=agent.temperature,
        max_tokens=agent.max_tokens,
        position_x=agent.position_x,
        position_y=agent.position_y,
        metadata=agent.meta or {},
    )


def _edge_out(edge) -> EdgeDefOut:
    return EdgeDefOut(
        edge_id=edge.id,
        workflow_id=edge.workflow_id,
        source_agent_id=edge.source_agent_id,
        target_agent_id=edge.target_agent_id,
        label=edge.label,
        metadata=edge.meta or {},
    )


def _workflow_out(session: Session, workflow: WorkflowDefinition) -> WorkflowOut:
    return WorkflowOut(
        workflow_id=workflow.id,
        project_id=workflow.project_id,
        name=workflow.name,
        description=workflow.description,
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
        agents=[_agent_out(a) for a in service.workflow_agents(session, workflow.id)],
        edges=[_edge_out(e) for e in service.workflow_edges(session, workflow.id)],
    )


def _require_workflow(session: Session, workflow_id: str) -> WorkflowDefinition:
    workflow = service.get_workflow(session, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    return workflow


# ----------------------------------------------------------------- workflows


@router.get("/studio/workflows", response_model=list[WorkflowSummaryOut])
def list_workflows(session: Session = Depends(get_session)) -> list[WorkflowSummaryOut]:
    workflows = list(
        session.execute(
            select(WorkflowDefinition).order_by(WorkflowDefinition.updated_at.desc())
        ).scalars()
    )
    out: list[WorkflowSummaryOut] = []
    for workflow in workflows:
        last = service.latest_run(session, workflow.id)
        out.append(
            WorkflowSummaryOut(
                workflow_id=workflow.id,
                project_id=workflow.project_id,
                name=workflow.name,
                description=workflow.description,
                agent_count=len(service.workflow_agents(session, workflow.id)),
                edge_count=len(service.workflow_edges(session, workflow.id)),
                updated_at=workflow.updated_at,
                last_run_id=last.run_id if last else None,
                last_run_status=last.status if last else None,
            )
        )
    return out


@router.post(
    "/studio/workflows",
    status_code=201,
    response_model=WorkflowOut,
    dependencies=[Depends(require_api_key)],
)
def create_workflow(body: WorkflowIn, session: Session = Depends(get_session)) -> WorkflowOut:
    workflow = service.create_workflow(session, body)
    session.commit()
    return _workflow_out(session, workflow)


@router.get("/studio/workflows/{workflow_id}", response_model=WorkflowOut)
def get_workflow(workflow_id: str, session: Session = Depends(get_session)) -> WorkflowOut:
    return _workflow_out(session, _require_workflow(session, workflow_id))


@router.put(
    "/studio/workflows/{workflow_id}",
    response_model=WorkflowOut,
    dependencies=[Depends(require_api_key)],
)
def update_workflow(
    workflow_id: str, body: WorkflowIn, session: Session = Depends(get_session)
) -> WorkflowOut:
    workflow = _require_workflow(session, workflow_id)
    service.replace_workflow_graph(session, workflow, body)
    session.commit()
    return _workflow_out(session, workflow)


@router.delete(
    "/studio/workflows/{workflow_id}",
    status_code=204,
    dependencies=[Depends(require_api_key)],
)
def delete_workflow(workflow_id: str, session: Session = Depends(get_session)) -> None:
    service.delete_workflow(session, _require_workflow(session, workflow_id))
    session.commit()


# -------------------------------------------------------------------- agents


@router.post(
    "/studio/workflows/{workflow_id}/agents",
    status_code=201,
    response_model=AgentDefOut,
    dependencies=[Depends(require_api_key)],
)
def create_agent(
    workflow_id: str, body: AgentDefIn, session: Session = Depends(get_session)
) -> AgentDefOut:
    _require_workflow(session, workflow_id)
    taken = {a.id for a in service.workflow_agents(session, workflow_id)}
    if body.agent_id and body.agent_id in taken:
        raise HTTPException(status_code=422, detail=f"duplicate agent id {body.agent_id!r}")
    agent = service.add_agent(session, workflow_id, body, taken)
    session.commit()
    return _agent_out(agent)


@router.put(
    "/studio/workflows/{workflow_id}/agents/{agent_id}",
    response_model=AgentDefOut,
    dependencies=[Depends(require_api_key)],
)
def update_agent(
    workflow_id: str, agent_id: str, body: AgentDefIn, session: Session = Depends(get_session)
) -> AgentDefOut:
    _require_workflow(session, workflow_id)
    agent = session.get(service.AgentDefinition, (workflow_id, agent_id))
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    agent.name = body.name
    agent.role = body.role
    agent.description = body.description
    agent.system_prompt = body.system_prompt
    agent.provider = body.provider
    agent.model_name = body.model_name
    agent.temperature = body.temperature
    agent.max_tokens = body.max_tokens
    agent.position_x = body.position_x
    agent.position_y = body.position_y
    agent.meta = body.metadata
    session.commit()
    return _agent_out(agent)


@router.delete(
    "/studio/workflows/{workflow_id}/agents/{agent_id}",
    status_code=204,
    dependencies=[Depends(require_api_key)],
)
def delete_agent(
    workflow_id: str, agent_id: str, session: Session = Depends(get_session)
) -> None:
    _require_workflow(session, workflow_id)
    agent = session.get(service.AgentDefinition, (workflow_id, agent_id))
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    # An agent takes its edges with it so the graph never dangles.
    for edge in service.workflow_edges(session, workflow_id):
        if agent_id in (edge.source_agent_id, edge.target_agent_id):
            session.delete(edge)
    session.delete(agent)
    session.commit()


# --------------------------------------------------------------------- edges


@router.post(
    "/studio/workflows/{workflow_id}/edges",
    status_code=201,
    response_model=EdgeDefOut,
    dependencies=[Depends(require_api_key)],
)
def create_edge(
    workflow_id: str, body: EdgeDefIn, session: Session = Depends(get_session)
) -> EdgeDefOut:
    _require_workflow(session, workflow_id)
    agent_ids = {a.id for a in service.workflow_agents(session, workflow_id)}
    for endpoint in (body.source_agent_id, body.target_agent_id):
        if endpoint not in agent_ids:
            raise HTTPException(
                status_code=422, detail=f"edge references unknown agent {endpoint!r}"
            )
    if body.source_agent_id == body.target_agent_id:
        raise HTTPException(status_code=422, detail="an edge cannot connect an agent to itself")
    edge = service.add_edge(session, workflow_id, body)
    session.commit()
    return _edge_out(edge)


@router.delete(
    "/studio/workflows/{workflow_id}/edges/{edge_id}",
    status_code=204,
    dependencies=[Depends(require_api_key)],
)
def delete_edge(
    workflow_id: str, edge_id: str, session: Session = Depends(get_session)
) -> None:
    _require_workflow(session, workflow_id)
    edge = session.get(service.WorkflowEdgeDefinition, (workflow_id, edge_id))
    if edge is None:
        raise HTTPException(status_code=404, detail="edge not found")
    session.delete(edge)
    session.commit()


# ------------------------------------------------------------ validate & run


@router.post("/studio/workflows/{workflow_id}/validate", response_model=ValidationOut)
def validate(
    workflow_id: str, request: Request, session: Session = Depends(get_session)
) -> ValidationOut:
    _require_workflow(session, workflow_id)
    errors, warnings = validate_workflow(
        service.workflow_agents(session, workflow_id),
        service.workflow_edges(session, workflow_id),
        _registry(request),
    )
    return ValidationOut(valid=not errors, errors=errors, warnings=warnings)


@router.get(
    "/studio/workflows/{workflow_id}/runs", response_model=list[WorkflowRunRecordOut]
)
def list_workflow_runs(
    workflow_id: str, session: Session = Depends(get_session), limit: int = 20
) -> list[WorkflowRunRecordOut]:
    _require_workflow(session, workflow_id)
    rows = session.execute(
        select(WorkflowRun)
        .where(WorkflowRun.workflow_id == workflow_id)
        .order_by(WorkflowRun.created_at.desc(), WorkflowRun.run_id.desc())
        .limit(max(1, min(limit, 100)))
    ).scalars()
    return [WorkflowRunRecordOut.model_validate(row) for row in rows]


@router.post(
    "/studio/workflows/{workflow_id}/run",
    status_code=201,
    response_model=WorkflowRunOut,
    dependencies=[Depends(require_api_key)],
)
async def run_workflow(
    workflow_id: str, body: WorkflowRunIn, request: Request
) -> WorkflowRunOut:
    session_factory = request.app.state.session_factory
    registry = _registry(request)

    def _load():
        session = session_factory()
        try:
            workflow = _require_workflow(session, workflow_id)
            agents = service.workflow_agents(session, workflow_id)
            edges = service.workflow_edges(session, workflow_id)
            errors, _warnings = validate_workflow(agents, edges, registry)
            if errors:
                raise HTTPException(
                    status_code=422, detail={"message": "workflow is not valid", "errors": errors}
                )
            session.expunge_all()  # detached copies are safe to use after close
            return workflow, agents, edges
        finally:
            session.close()

    workflow, agents, edges = await run_in_threadpool(_load)
    project_id = body.project_id or workflow.project_id

    # Execute the DAG (model calls go through the gateway) …
    run_id, status, events = await execute_workflow(
        workflow,
        agents,
        edges,
        registry,
        project_id=project_id,
        workflow_input=body.input,
        run_metadata=body.metadata,
    )

    # … then persist through the normal collector and broadcast live.
    def _store():
        session = session_factory()
        try:
            stored, _ = process_events(session, events)
            session.add(
                WorkflowRun(
                    run_id=run_id,
                    workflow_id=workflow.id,
                    project_id=project_id,
                    status=status,
                    input=body.input,
                )
            )
            session.commit()
            return [EventOut.model_validate(row) for row in stored]
        finally:
            session.close()

    out_events = await run_in_threadpool(_store)
    manager = request.app.state.ws_manager
    for event in out_events:
        await manager.broadcast(project_id, {"type": "event", "data": event.model_dump(mode="json")})

    return WorkflowRunOut(
        workflow_id=workflow.id,
        run_id=run_id,
        status=status,
        open_run_url=f"/runs/{run_id}",
    )
