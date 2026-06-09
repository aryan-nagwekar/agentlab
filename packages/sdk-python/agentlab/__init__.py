"""AgentLab Python SDK — instrumentation for multi-agent AI systems.

Quickstart::

    from agentlab import AgentLabClient, trace_agent

    client = AgentLabClient(project_id="demo", endpoint="http://localhost:8000")

    @trace_agent(name="PlannerAgent", role="planner")
    def plan(goal: str):
        ...

    with client.run(name="nightly-pipeline"):
        plan("ship it")
"""
from ._events import EVENT_TYPES, SDK_VERSION
from .client import AgentLabClient, RunHandle, ToolSpan, get_default_client, set_default_client
from .decorators import (
    init,
    log_model_call,
    routing_decision,
    send_message,
    trace_agent,
    trace_message,
    trace_model,
    trace_tool,
    update_risk,
    update_trust,
)

__version__ = SDK_VERSION

__all__ = [
    "AgentLabClient",
    "RunHandle",
    "ToolSpan",
    "EVENT_TYPES",
    "init",
    "get_default_client",
    "set_default_client",
    "trace_agent",
    "trace_tool",
    "trace_message",
    "trace_model",
    "send_message",
    "log_model_call",
    "routing_decision",
    "update_trust",
    "update_risk",
    "__version__",
]
