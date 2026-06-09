"""Module-level instrumentation API.

These helpers bind to the process-wide default client (the most recently
constructed ``AgentLabClient``), resolved at call time — so decorators may be
applied before the client exists, as long as one exists when the traced code
actually runs.
"""
from __future__ import annotations

import functools
from typing import Any, Callable, TypeVar

from .client import AgentLabClient, get_default_client

F = TypeVar("F", bound=Callable[..., Any])


def _require_client() -> AgentLabClient:
    client = get_default_client()
    if client is None:
        raise RuntimeError(
            "No AgentLab client configured. Construct AgentLabClient(...) or call "
            "agentlab.init(...) before running instrumented code."
        )
    return client


def init(project_id: str, **kwargs: Any) -> AgentLabClient:
    """Create a client and register it as the default. Equivalent to
    ``AgentLabClient(project_id, **kwargs)``."""
    return AgentLabClient(project_id, **kwargs)


def trace_agent(
    name: str | None = None,
    *,
    role: str | None = None,
    agent_id: str | None = None,
) -> Callable[[F], F]:
    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            client = _require_client()
            bound = client.trace_agent(
                name=name or fn.__name__, role=role, agent_id=agent_id
            )(fn)
            return bound(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def trace_tool(tool_name: str, **kwargs: Any) -> Any:
    return _require_client().trace_tool(tool_name, **kwargs)


def send_message(target_agent_id: str, content: Any, **kwargs: Any) -> str:
    return _require_client().send_message(target_agent_id, content, **kwargs)


# Alias used in product examples: tracing a message == recording it.
trace_message = send_message


def log_model_call(model: str, **kwargs: Any) -> None:
    return _require_client().log_model_call(model, **kwargs)


# Alias for symmetry with trace_agent / trace_tool.
trace_model = log_model_call


def routing_decision(**kwargs: Any) -> None:
    return _require_client().routing_decision(**kwargs)


def update_trust(agent_id: str, trust_score: float, **kwargs: Any) -> None:
    return _require_client().update_trust(agent_id, trust_score, **kwargs)


def update_risk(agent_id: str, risk_score: float, **kwargs: Any) -> None:
    return _require_client().update_risk(agent_id, risk_score, **kwargs)
