"""Cost & token attribution.

A pure fold over a run's `model.*` events → per-agent, per-model, and run
totals. Like scoring, the cost at replay cursor *k* is exactly
`aggregate(events[:k+1])`, and the same logic is mirrored in
`apps/web/src/lib/costing.ts` for live replay. Cost is always recomputed from
tokens via the deterministic pricing table (app/pricing.py), so it is the
single source of truth used by the cost endpoints, metrics, and the graph.

Token fields are read leniently: new payloads use input_tokens/output_tokens/
model_name, older ones use prompt_tokens/completion_tokens/model. Missing token
data is treated as zero.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol

from . import pricing


class EventLike(Protocol):
    event_type: str
    source_agent_id: str | None
    payload: dict[str, Any]


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class ModelCall:
    """A normalized model.completed / model.failed event."""

    agent_id: str | None
    provider: str
    model_name: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float | None
    pricing_status: str
    latency_ms: float | None
    status: str
    error_message: str | None


def normalize_model_event(event: EventLike) -> ModelCall:
    payload = event.payload or {}
    model_name = str(payload.get("model_name") or payload.get("model") or "unknown")
    provider = str(payload.get("provider") or pricing.provider_of(model_name))
    input_tokens = _as_int(payload.get("input_tokens", payload.get("prompt_tokens", 0)))
    output_tokens = _as_int(payload.get("output_tokens", payload.get("completion_tokens", 0)))
    total_tokens = _as_int(payload.get("total_tokens")) or (input_tokens + output_tokens)
    status = "failed" if event.event_type == "model.failed" else "completed"

    cost, pricing_status = pricing.estimate_cost(model_name, input_tokens, output_tokens)
    if cost is None:
        # Unknown model: honour an explicitly provided cost, else leave it null.
        provided = _as_float(payload.get("estimated_cost_usd", payload.get("cost_estimate")))
        if provided is not None:
            cost, pricing_status = round(provided, 6), "provided"

    return ModelCall(
        agent_id=event.source_agent_id,
        provider=provider,
        model_name=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=cost,
        pricing_status=pricing_status,
        latency_ms=_as_float(payload.get("latency_ms")),
        status=status,
        error_message=(payload.get("error") or payload.get("error_message")) if status == "failed" else None,
    )


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(0.95 * len(ordered)) - 1))
    return round(ordered[index], 2)


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


@dataclass
class AgentCosting:
    agent_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    model_call_count: int = 0
    failed_model_call_count: int = 0
    retry_count: int = 0
    _latencies: list[float] = field(default_factory=list)
    _models: dict[str, int] = field(default_factory=dict)

    @property
    def average_latency_ms(self) -> float | None:
        return _avg(self._latencies)

    @property
    def p95_latency_ms(self) -> float | None:
        return _p95(self._latencies)

    @property
    def most_used_model(self) -> str | None:
        return max(self._models, key=self._models.get) if self._models else None


@dataclass
class ModelCosting:
    model_name: str
    provider: str
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    call_count: int = 0
    failure_count: int = 0
    _latencies: list[float] = field(default_factory=list)

    @property
    def average_latency_ms(self) -> float | None:
        return _avg(self._latencies)


@dataclass
class RunCosting:
    agents: dict[str, AgentCosting] = field(default_factory=dict)
    models: dict[str, ModelCosting] = field(default_factory=dict)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    _all_latencies: list[float] = field(default_factory=list)

    @property
    def average_latency_ms(self) -> float | None:
        return _avg(self._all_latencies)

    @property
    def p95_latency_ms(self) -> float | None:
        return _p95(self._all_latencies)


def aggregate(events: Iterable[EventLike]) -> RunCosting:
    run = RunCosting()
    # A model.called immediately followed by another model.called/failed for the
    # same agent without a completion suggests a retry; we approximate retries as
    # (model.called count) - (completed + failed) per agent.
    calls_started: dict[str, int] = {}
    calls_finished: dict[str, int] = {}

    for event in events:
        etype = event.event_type
        agent_id = event.source_agent_id
        if etype == "model.called" and agent_id:
            calls_started[agent_id] = calls_started.get(agent_id, 0) + 1
            continue
        if etype not in ("model.completed", "model.failed"):
            continue

        call = normalize_model_event(event)
        key = agent_id or "unknown"
        if agent_id:
            calls_finished[agent_id] = calls_finished.get(agent_id, 0) + 1

        agent = run.agents.setdefault(key, AgentCosting(key))
        agent.input_tokens += call.input_tokens
        agent.output_tokens += call.output_tokens
        agent.total_tokens += call.total_tokens
        agent.model_call_count += 1
        if call.estimated_cost_usd:
            agent.estimated_cost_usd = round(agent.estimated_cost_usd + call.estimated_cost_usd, 6)
        if call.status == "failed":
            agent.failed_model_call_count += 1
        if call.latency_ms is not None:
            agent._latencies.append(call.latency_ms)
        agent._models[call.model_name] = agent._models.get(call.model_name, 0) + 1

        model = run.models.setdefault(
            call.model_name, ModelCosting(call.model_name, call.provider)
        )
        model.total_tokens += call.total_tokens
        model.input_tokens += call.input_tokens
        model.output_tokens += call.output_tokens
        model.call_count += 1
        if call.estimated_cost_usd:
            model.estimated_cost_usd = round(model.estimated_cost_usd + call.estimated_cost_usd, 6)
        if call.status == "failed":
            model.failure_count += 1
        if call.latency_ms is not None:
            model._latencies.append(call.latency_ms)

        run.total_input_tokens += call.input_tokens
        run.total_output_tokens += call.output_tokens
        run.total_tokens += call.total_tokens
        if call.estimated_cost_usd:
            run.estimated_cost_usd = round(run.estimated_cost_usd + call.estimated_cost_usd, 6)
        if call.latency_ms is not None:
            run._all_latencies.append(call.latency_ms)

    for agent_id, agent in run.agents.items():
        retries = calls_started.get(agent_id, 0) - calls_finished.get(agent_id, 0)
        agent.retry_count = max(0, retries)

    return run


def _best(items: dict[str, AgentCosting], metric: str) -> str | None:
    best_id, best_value = None, 0.0
    for agent_id, agent in items.items():
        value = float(getattr(agent, metric) or 0)
        if value > best_value:
            best_value, best_id = value, agent_id
    return best_id
