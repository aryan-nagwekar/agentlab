"""AgentLabClient: the entry point for instrumenting an agent application."""
from __future__ import annotations

import atexit
import functools
import logging
import os
import re
import threading
import time
import traceback
from contextlib import contextmanager
from typing import Any, Callable, Iterator, TypeVar

from . import _events as ev
from ._context import current_agent_id, current_run_id, current_span_id
from ._transport import HttpTransport

logger = logging.getLogger("agentlab")

F = TypeVar("F", bound=Callable[..., Any])

_default_client: "AgentLabClient | None" = None
_default_lock = threading.Lock()


def get_default_client() -> "AgentLabClient | None":
    return _default_client


def set_default_client(client: "AgentLabClient | None") -> None:
    global _default_client
    with _default_lock:
        _default_client = client


def _slugify(name: str) -> str:
    # "SecurityReviewAgent" -> "security-review-agent"
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", name)
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "agent"


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)


class ToolSpan:
    """Handle yielded by ``trace_tool``; set ``output`` before the block ends."""

    def __init__(self) -> None:
        self.output: Any = None
        self.metadata: dict[str, Any] = {}


class RunHandle:
    """A single observed run. Usable as a context manager or explicitly."""

    def __init__(
        self,
        client: "AgentLabClient",
        run_id: str,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.client = client
        self.run_id = run_id
        self.name = name
        self._metadata = metadata or {}
        self._token: Any = None
        self._started_at: float | None = None
        self._finished = False

    @property
    def id(self) -> str:
        return self.run_id

    def __enter__(self) -> "RunHandle":
        self._token = current_run_id.set(self.run_id)
        self._started_at = time.perf_counter()
        self.client.emit(
            ev.RUN_STARTED,
            run_id=self.run_id,
            payload={"name": self.name},
            metadata=self._metadata,
        )
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        try:
            if exc is not None:
                self.fail(error=f"{exc_type.__name__}: {exc}")
            else:
                self.complete()
        finally:
            if self._token is not None:
                current_run_id.reset(self._token)
                self._token = None
        return False  # never suppress exceptions

    def _duration_ms(self) -> float | None:
        if self._started_at is None:
            return None
        return _elapsed_ms(self._started_at)

    def complete(self, **payload: Any) -> None:
        if self._finished:
            return
        self._finished = True
        body = {"name": self.name, "total_latency_ms": self._duration_ms(), **payload}
        self.client.emit(ev.RUN_COMPLETED, run_id=self.run_id, payload=body)
        self.client.flush(timeout=5.0)

    def fail(self, error: str | None = None, **payload: Any) -> None:
        if self._finished:
            return
        self._finished = True
        body = {
            "name": self.name,
            "total_latency_ms": self._duration_ms(),
            "error": error,
            **payload,
        }
        self.client.emit(ev.RUN_FAILED, run_id=self.run_id, payload=body)
        self.client.flush(timeout=5.0)


class AgentLabClient:
    """Send instrumentation events from an agent app to an AgentLab collector.

    Constructing a client registers it as the process-wide default used by the
    module-level helpers (``from agentlab import trace_agent``), mirroring the
    ergonomics of common telemetry SDKs.

    Set ``AGENTLAB_DISABLED=1`` (or pass ``disabled=True``) to turn the client
    into a no-op: traced functions still run, nothing is sent.
    """

    def __init__(
        self,
        project_id: str,
        api_key: str = "dev-key",
        endpoint: str = "http://localhost:8000",
        *,
        disabled: bool | None = None,
        flush_interval: float = 0.5,
        batch_size: int = 50,
        max_buffer: int = 10_000,
        request_timeout: float = 5.0,
        set_as_default: bool = True,
    ) -> None:
        self.project_id = project_id
        self.endpoint = endpoint.rstrip("/")
        if disabled is None:
            disabled = _truthy_env("AGENTLAB_DISABLED")
        self.disabled = bool(disabled)
        self._transport: HttpTransport | None = None
        if not self.disabled:
            self._transport = HttpTransport(
                self.endpoint,
                api_key,
                flush_interval=flush_interval,
                batch_size=batch_size,
                max_buffer=max_buffer,
                timeout=request_timeout,
            )
        self._implicit_run_id: str | None = None
        self._implicit_lock = threading.Lock()
        self._closed = False
        if set_as_default:
            set_default_client(self)
        atexit.register(self.close)

    # ----------------------------------------------------------- low level

    def emit(
        self,
        event_type: str,
        *,
        run_id: str | None = None,
        source_agent_id: str | None = None,
        target_agent_id: str | None = None,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        timestamp: str | None = None,
    ) -> str:
        """Build and enqueue one event; returns its event_id."""
        rid = run_id or current_run_id.get() or self._ensure_implicit_run()
        meta = dict(metadata or {})
        parent = current_span_id.get()
        if parent is not None:
            meta.setdefault("parent_event_id", parent)
        event = ev.build_event(
            event_type,
            project_id=self.project_id,
            run_id=rid,
            source_agent_id=source_agent_id,
            target_agent_id=target_agent_id,
            payload=payload,
            metadata=meta,
            timestamp=timestamp,
        )
        if self._transport is not None:
            self._transport.enqueue(event)
        return event["event_id"]

    def _ensure_implicit_run(self) -> str:
        """Lazily open a shared run for events emitted outside ``client.run()``."""
        with self._implicit_lock:
            if self._implicit_run_id is None:
                self._implicit_run_id = ev.new_id("run")
                self.emit(
                    ev.RUN_STARTED,
                    run_id=self._implicit_run_id,
                    payload={"name": "ad-hoc run", "implicit": True},
                )
            return self._implicit_run_id

    # ----------------------------------------------------------- run scope

    def run(
        self,
        name: str | None = None,
        *,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RunHandle:
        rid = run_id or ev.new_id("run")
        return RunHandle(self, rid, name=name or rid, metadata=metadata)

    # -------------------------------------------------------------- agents

    def trace_agent(
        self,
        name: str | None = None,
        *,
        role: str | None = None,
        agent_id: str | None = None,
    ) -> Callable[[F], F]:
        """Decorator: emits agent.started / agent.completed / agent.failed
        around the function and makes it the current agent for nested calls."""

        def decorator(fn: F) -> F:
            agent_name = name or fn.__name__
            aid = agent_id or _slugify(agent_name)

            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                parent_agent = current_agent_id.get()
                base_payload: dict[str, Any] = {"name": agent_name, "role": role}
                if parent_agent:
                    base_payload["parent_agent_id"] = parent_agent
                started_event_id = self.emit(
                    ev.AGENT_STARTED, source_agent_id=aid, payload=dict(base_payload)
                )
                agent_token = current_agent_id.set(aid)
                span_token = current_span_id.set(started_event_id)
                started = time.perf_counter()
                try:
                    result = fn(*args, **kwargs)
                except Exception as exc:
                    self.emit(
                        ev.AGENT_FAILED,
                        source_agent_id=aid,
                        payload={
                            **base_payload,
                            "latency_ms": _elapsed_ms(started),
                            "error": f"{type(exc).__name__}: {exc}",
                            "traceback": traceback.format_exc(limit=20)[:4000],
                        },
                    )
                    raise
                else:
                    self.emit(
                        ev.AGENT_COMPLETED,
                        source_agent_id=aid,
                        payload={**base_payload, "latency_ms": _elapsed_ms(started)},
                    )
                    return result
                finally:
                    current_span_id.reset(span_token)
                    current_agent_id.reset(agent_token)

            wrapper.agentlab_agent_id = aid  # type: ignore[attr-defined]
            return wrapper  # type: ignore[return-value]

        return decorator

    # ------------------------------------------------------------ messages

    def send_message(
        self,
        target_agent_id: str,
        content: Any,
        *,
        source_agent_id: str | None = None,
        message_id: str | None = None,
        latency_ms: float | None = None,
        status: str = "delivered",
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Record an agent-to-agent message; returns the message_id.

        status: 'delivered' (sent + received), 'sent' (sent only),
        or 'failed' (sent + failed).
        """
        src = source_agent_id or current_agent_id.get() or "external"
        mid = message_id or ev.new_id("msg")
        meta = dict(metadata or {})
        meta["message_id"] = mid
        self.emit(
            ev.MESSAGE_SENT,
            source_agent_id=src,
            target_agent_id=target_agent_id,
            payload={"content": content},
            metadata=meta,
        )
        if status == "failed":
            self.emit(
                ev.MESSAGE_FAILED,
                source_agent_id=src,
                target_agent_id=target_agent_id,
                payload={"error": error or "delivery failed"},
                metadata=meta,
            )
        elif status == "delivered":
            received: dict[str, Any] = {}
            if latency_ms is not None:
                received["latency_ms"] = latency_ms
            self.emit(
                ev.MESSAGE_RECEIVED,
                source_agent_id=src,
                target_agent_id=target_agent_id,
                payload=received,
                metadata=meta,
            )
        return mid

    # ----------------------------------------------------------------- tools

    @contextmanager
    def trace_tool(
        self,
        tool_name: str,
        *,
        input: Any = None,
        agent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[ToolSpan]:
        aid = agent_id or current_agent_id.get()
        meta = dict(metadata or {})
        meta["tool_call_id"] = ev.new_id("tool")
        self.emit(
            ev.TOOL_CALLED,
            source_agent_id=aid,
            payload={"tool_name": tool_name, "input": input},
            metadata=meta,
        )
        span = ToolSpan()
        started = time.perf_counter()
        try:
            yield span
        except Exception as exc:
            self.emit(
                ev.TOOL_FAILED,
                source_agent_id=aid,
                payload={
                    "tool_name": tool_name,
                    "input": input,
                    "error": f"{type(exc).__name__}: {exc}",
                    "latency_ms": _elapsed_ms(started),
                },
                metadata=meta,
            )
            raise
        else:
            self.emit(
                ev.TOOL_COMPLETED,
                source_agent_id=aid,
                payload={
                    "tool_name": tool_name,
                    "input": input,
                    "output": span.output,
                    "latency_ms": _elapsed_ms(started),
                },
                metadata={**meta, **span.metadata},
            )

    # ---------------------------------------------------------------- models

    def log_model_call(
        self,
        model: str,
        *,
        provider: str | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        latency_ms: float | None = None,
        cost_estimate: float | None = None,
        agent_id: str | None = None,
        status: str = "completed",
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a model call. ``model`` is the model name (e.g.
        ``"mock:claude-sonnet"``). ``input_tokens``/``output_tokens`` are the
        preferred token fields; ``prompt_tokens``/``completion_tokens`` remain
        as aliases. Cost is normally derived from the collector's pricing
        table, so ``cost_estimate`` is optional."""
        aid = agent_id or current_agent_id.get()
        meta = dict(metadata or {})
        meta["model_call_id"] = ev.new_id("model")
        in_tokens = input_tokens if input_tokens is not None else prompt_tokens
        out_tokens = output_tokens if output_tokens is not None else completion_tokens
        if provider is None and ":" in model:
            provider = model.split(":", 1)[0]
        self.emit(
            ev.MODEL_CALLED,
            source_agent_id=aid,
            payload={"model": model, "model_name": model, "provider": provider},
            metadata=meta,
        )
        # Both new (model_name/input_tokens/…) and legacy (model/prompt_tokens/…)
        # field names are emitted so old and new readers both work.
        base = {
            "model": model,
            "model_name": model,
            "provider": provider,
            "input_tokens": in_tokens,
            "output_tokens": out_tokens,
            "prompt_tokens": in_tokens,
            "completion_tokens": out_tokens,
            "total_tokens": (in_tokens or 0) + (out_tokens or 0),
            "latency_ms": latency_ms,
        }
        if cost_estimate is not None:
            base["cost_estimate"] = cost_estimate
            base["estimated_cost_usd"] = cost_estimate
        if status == "failed":
            self.emit(
                ev.MODEL_FAILED,
                source_agent_id=aid,
                payload={**base, "status": "failed", "error": error or "model call failed",
                         "error_message": error or "model call failed"},
                metadata=meta,
            )
        else:
            self.emit(
                ev.MODEL_COMPLETED,
                source_agent_id=aid,
                payload={**base, "status": "completed"},
                metadata=meta,
            )

    # --------------------------------------------------------- control plane

    def routing_decision(
        self,
        *,
        candidates: list[dict[str, Any]],
        selected_agent_id: str,
        reason: str,
        confidence: float | None = None,
        task: str | None = None,
        source_agent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        src = source_agent_id or current_agent_id.get()
        self.emit(
            ev.ROUTING_DECISION,
            source_agent_id=src,
            target_agent_id=selected_agent_id,
            payload={
                "task": task,
                "candidate_agents": candidates,
                "selected_agent_id": selected_agent_id,
                "reason": reason,
                "confidence": confidence,
            },
            metadata=metadata,
        )

    def update_trust(
        self, agent_id: str, trust_score: float, *, reason: str | None = None
    ) -> None:
        score = max(0.0, min(1.0, float(trust_score)))
        self.emit(
            ev.TRUST_UPDATED,
            source_agent_id=agent_id,
            payload={"trust_score": score, "reason": reason},
        )

    def update_risk(
        self, agent_id: str, risk_score: float, *, reason: str | None = None
    ) -> None:
        score = max(0.0, min(1.0, float(risk_score)))
        self.emit(
            ev.RISK_UPDATED,
            source_agent_id=agent_id,
            payload={"risk_score": score, "reason": reason},
        )

    def heartbeat(
        self,
        agent_id: str,
        *,
        status: str = "healthy",
        stats: dict[str, Any] | None = None,
    ) -> None:
        self.emit(
            ev.AGENT_HEARTBEAT,
            source_agent_id=agent_id,
            payload={"status": status, "stats": stats or {}},
        )

    # -------------------------------------------------------------- lifecycle

    def flush(self, timeout: float = 5.0) -> bool:
        if self._transport is None:
            return True
        return self._transport.flush(timeout=timeout)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._implicit_run_id is not None and self._transport is not None:
            self.emit(
                ev.RUN_COMPLETED,
                run_id=self._implicit_run_id,
                payload={"name": "ad-hoc run", "implicit": True},
            )
        if self._transport is not None:
            self._transport.flush(timeout=2.0)
            self._transport.close()
        if get_default_client() is self:
            set_default_client(None)
