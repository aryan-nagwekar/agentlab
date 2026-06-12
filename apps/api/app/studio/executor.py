"""Deterministic DAG executor — Studio runs are normal AgentLab runs.

Agents run in topological order; every model call goes through the v0.7 Model
Gateway and its existing telemetry bridge, and the surrounding run/agent/
message events use the standard 22-type registry. No user code, shell, tools,
or loops are executed — the only side effect is model calls via the gateway.

Timestamps come from a simulated clock advanced by each call's reported
latency, so the replay timeline reads like a real run even though mock calls
return instantly.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from ..model_gateway.base import ModelRequest
from ..model_gateway.registry import ProviderRegistry
from ..model_gateway.telemetry import build_model_events
from ..schemas import EventIn
from ..timeutil import utcnow
from .models import AgentDefinition, WorkflowDefinition, WorkflowEdgeDefinition
from .validation import topological_order

STEP_MS = 40  # bookkeeping gap between consecutive events
MESSAGE_MS = 25  # simulated channel latency between agents


def build_prompt(
    agent: AgentDefinition, workflow_input: str, upstream_outputs: dict[str, str]
) -> str:
    upstream_text = (
        "\n".join(f"[{agent_id}]\n{output}" for agent_id, output in upstream_outputs.items())
        if upstream_outputs
        else "(none — you are the first step)"
    )
    return (
        f"You are {agent.name}.\n"
        f"Role: {agent.role}\n\n"
        f"System instructions:\n{agent.system_prompt or '(none)'}\n\n"
        f"Original workflow input:\n{workflow_input}\n\n"
        f"Upstream outputs:\n{upstream_text}\n\n"
        "Now complete your step and return a concise result."
    )


async def execute_workflow(
    workflow: WorkflowDefinition,
    agents: list[AgentDefinition],
    edges: list[WorkflowEdgeDefinition],
    registry: ProviderRegistry,
    *,
    project_id: str,
    workflow_input: str,
    run_metadata: dict[str, Any] | None = None,
) -> tuple[str, str, list[EventIn]]:
    """Returns (run_id, final_status, events). Pure with respect to storage —
    the caller persists the events through the normal collector."""
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    order = topological_order(agents, edges)
    if order is None:  # the router validates first; this is a belt-and-braces guard
        raise ValueError("workflow contains a cycle")

    upstream_of = {
        agent.id: [e.source_agent_id for e in edges if e.target_agent_id == agent.id]
        for agent in agents
    }
    downstream_of = {
        agent.id: [e.target_agent_id for e in edges if e.source_agent_id == agent.id]
        for agent in agents
    }

    clock = utcnow()

    def tick(ms: int = STEP_MS) -> datetime:
        nonlocal clock
        clock = clock + timedelta(milliseconds=ms)
        return clock

    def studio_meta(agent: AgentDefinition | None = None) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "source": "studio",
            "workflow_id": workflow.id,
            "workflow_name": workflow.name,
            **(run_metadata or {}),
        }
        if agent is not None:
            meta.update(
                {
                    "agent_definition_id": agent.id,
                    "role": agent.role,
                    "provider": agent.provider,
                    "model_name": agent.model_name,
                    "upstream_agents": upstream_of[agent.id],
                    "downstream_agents": downstream_of[agent.id],
                }
            )
        return meta

    events: list[EventIn] = [
        EventIn(
            event_type="run.started",
            timestamp=clock,
            project_id=project_id,
            run_id=run_id,
            payload={
                "name": workflow.name,
                "workflow_id": workflow.id,
                "input_preview": workflow_input[:200],
            },
            metadata=studio_meta(),
        )
    ]

    outputs: dict[str, str] = {}
    failed: set[str] = set()
    skipped: set[str] = set()
    started_at = clock

    for agent in order:
        blocked_by = [u for u in upstream_of[agent.id] if u in failed or u in skipped]
        if blocked_by:
            skipped.add(agent.id)
            continue

        # Hand upstream outputs over as normal inter-agent messages.
        for upstream_id in upstream_of[agent.id]:
            message_id = f"msg-{uuid.uuid4().hex[:10]}"
            content = {"output_preview": outputs.get(upstream_id, "")[:200]}
            events.append(
                EventIn(
                    event_type="message.sent",
                    timestamp=tick(),
                    project_id=project_id,
                    run_id=run_id,
                    source_agent_id=upstream_id,
                    target_agent_id=agent.id,
                    payload={"content": content},
                    metadata={**studio_meta(agent), "message_id": message_id},
                )
            )
            events.append(
                EventIn(
                    event_type="message.received",
                    timestamp=tick(MESSAGE_MS),
                    project_id=project_id,
                    run_id=run_id,
                    source_agent_id=upstream_id,
                    target_agent_id=agent.id,
                    payload={"latency_ms": MESSAGE_MS},
                    metadata={**studio_meta(agent), "message_id": message_id},
                )
            )

        agent_started = tick()
        events.append(
            EventIn(
                event_type="agent.started",
                timestamp=agent_started,
                project_id=project_id,
                run_id=run_id,
                source_agent_id=agent.id,
                payload={"name": agent.name, "role": agent.role,
                         "provider": agent.provider, "model_name": agent.model_name},
                metadata=studio_meta(agent),
            )
        )

        provider = registry.get(agent.provider)
        upstream_outputs = {u: outputs[u] for u in upstream_of[agent.id] if u in outputs}
        request = ModelRequest(
            provider=agent.provider,
            model_name=agent.model_name,
            prompt=build_prompt(agent, workflow_input, upstream_outputs),
            system_prompt=agent.system_prompt,
            temperature=agent.temperature,
            max_tokens=agent.max_tokens,
            agent_id=agent.id,
            run_id=run_id,
            project_id=project_id,
            # The agent definition's metadata reaches the provider — this is how
            # the mock provider's simulate_failure/latency knobs work per-agent.
            metadata=dict(agent.meta or {}),
        )
        response = await provider.complete(request)

        called_event, result_event = build_model_events(request, response)
        called_event.timestamp = tick()
        result_event.timestamp = tick(max(response.latency_ms, 1))
        for model_event in (called_event, result_event):
            model_event.metadata.update(studio_meta(agent))
        events.extend([called_event, result_event])

        agent_latency_ms = int((clock - agent_started).total_seconds() * 1000)
        if response.status == "failed":
            failed.add(agent.id)
            events.append(
                EventIn(
                    event_type="agent.failed",
                    timestamp=tick(),
                    project_id=project_id,
                    run_id=run_id,
                    source_agent_id=agent.id,
                    payload={
                        "name": agent.name,
                        "role": agent.role,
                        "error": response.error_message or "model call failed",
                        "latency_ms": agent_latency_ms,
                    },
                    metadata=studio_meta(agent),
                )
            )
        else:
            outputs[agent.id] = response.output_text
            events.append(
                EventIn(
                    event_type="agent.completed",
                    timestamp=tick(),
                    project_id=project_id,
                    run_id=run_id,
                    source_agent_id=agent.id,
                    payload={"name": agent.name, "role": agent.role,
                             "latency_ms": agent_latency_ms},
                    metadata=studio_meta(agent),
                )
            )

    total_latency_ms = int((clock - started_at).total_seconds() * 1000)
    if failed:
        status = "failed"
        events.append(
            EventIn(
                event_type="run.failed",
                timestamp=tick(),
                project_id=project_id,
                run_id=run_id,
                payload={
                    "name": workflow.name,
                    "error": f"{len(failed)} agent(s) failed: {', '.join(sorted(failed))}",
                    "failed_agents": sorted(failed),
                    "skipped_agents": sorted(skipped),
                    "total_latency_ms": total_latency_ms,
                },
                metadata=studio_meta(),
            )
        )
    else:
        status = "completed"
        events.append(
            EventIn(
                event_type="run.completed",
                timestamp=tick(),
                project_id=project_id,
                run_id=run_id,
                payload={"name": workflow.name, "total_latency_ms": total_latency_ms},
                metadata=studio_meta(),
            )
        )
    return run_id, status, events
