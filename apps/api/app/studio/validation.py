"""Workflow validation — structural checks plus Model Gateway awareness.

Errors block saving/running; warnings (e.g. an unconfigured real provider)
inform the user but the run is still allowed: an unconfigured provider fails
cleanly at execution time with a normal ``model.failed`` event.
"""
from __future__ import annotations

from ..model_gateway.registry import ProviderRegistry
from .models import AgentDefinition, WorkflowEdgeDefinition

CYCLE_ERROR = "Cycles are not supported in v0.8. Please use a DAG workflow."


def topological_order(
    agents: list[AgentDefinition], edges: list[WorkflowEdgeDefinition]
) -> list[AgentDefinition] | None:
    """Kahn's algorithm. Returns None when the graph has a cycle.

    Stable: ties resolve in the agents' given order so execution (and the
    resulting telemetry) is deterministic.
    """
    indegree = {agent.id: 0 for agent in agents}
    for edge in edges:
        if edge.target_agent_id in indegree:
            indegree[edge.target_agent_id] += 1
    ordered: list[AgentDefinition] = []
    remaining = list(agents)
    while remaining:
        ready = [a for a in remaining if indegree[a.id] == 0]
        if not ready:
            return None  # every remaining agent waits on another → cycle
        head = ready[0]
        ordered.append(head)
        remaining.remove(head)
        for edge in edges:
            if edge.source_agent_id == head.id and edge.target_agent_id in indegree:
                indegree[edge.target_agent_id] -= 1
    return ordered


def validate_workflow(
    agents: list[AgentDefinition],
    edges: list[WorkflowEdgeDefinition],
    registry: ProviderRegistry,
) -> tuple[list[str], list[str]]:
    """Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []

    if not agents:
        errors.append("Workflow must contain at least one agent.")

    seen: set[str] = set()
    for agent in agents:
        if agent.id in seen:
            errors.append(f"Duplicate agent id {agent.id!r}.")
        seen.add(agent.id)
        if not (agent.name or "").strip():
            errors.append(f"Agent {agent.id!r} is missing a name.")
        if not (agent.role or "").strip():
            errors.append(f"Agent {agent.id!r} is missing a role.")
        if not (agent.provider or "").strip():
            errors.append(f"Agent {agent.id!r} is missing a provider.")
        if not (agent.model_name or "").strip():
            errors.append(f"Agent {agent.id!r} is missing a model.")

        provider = registry.get(agent.provider) if agent.provider else None
        if agent.provider and provider is None:
            errors.append(
                f"Agent {agent.id!r} uses unknown provider {agent.provider!r}; "
                f"known providers: {', '.join(registry.names())}."
            )
        elif provider is not None and agent.model_name:
            # The mock provider has a fixed catalogue; real providers accept
            # free-form model names (same policy as the gateway test-call).
            if provider.name == "mock" and agent.model_name not in provider.models():
                errors.append(
                    f"Agent {agent.id!r} uses unknown mock model {agent.model_name!r}; "
                    f"known: {', '.join(provider.models())}."
                )
            elif agent.model_name not in provider.models():
                warnings.append(
                    f"Agent {agent.id!r} uses model {agent.model_name!r} which is not in the "
                    f"{provider.name} suggestion list — it will be passed through as-is."
                )
            if not provider.configured:
                warnings.append(
                    f"Provider {provider.name!r} (agent {agent.id!r}) is not configured — "
                    "the run will fail cleanly with model.failed unless a key is set."
                )

    ids = {agent.id for agent in agents}
    for edge in edges:
        if edge.source_agent_id not in ids:
            errors.append(f"Edge {edge.id!r} references unknown source agent {edge.source_agent_id!r}.")
        if edge.target_agent_id not in ids:
            errors.append(f"Edge {edge.id!r} references unknown target agent {edge.target_agent_id!r}.")
        if edge.source_agent_id == edge.target_agent_id:
            errors.append(f"Edge {edge.id!r} connects agent {edge.source_agent_id!r} to itself.")

    valid_edges = [
        e for e in edges if e.source_agent_id in ids and e.target_agent_id in ids
    ]
    if agents and topological_order(agents, valid_edges) is None:
        errors.append(CYCLE_ERROR)

    return errors, warnings
