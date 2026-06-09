"""Execution context propagated through instrumented code.

ContextVars make nesting work naturally across threads spawned with
`contextvars.copy_context()` and across async tasks: a tool call made inside
an agent function is attributed to that agent without explicit plumbing.
"""
from __future__ import annotations

from contextvars import ContextVar

# The run currently in flight (set by AgentLabClient.run()).
current_run_id: ContextVar[str | None] = ContextVar("agentlab_current_run_id", default=None)

# The agent whose traced function frame we are inside.
current_agent_id: ContextVar[str | None] = ContextVar("agentlab_current_agent_id", default=None)

# event_id of the enclosing agent.started event; child events reference it as
# metadata.parent_event_id so the inspector can show parent/child relations.
current_span_id: ContextVar[str | None] = ContextVar("agentlab_current_span_id", default=None)
