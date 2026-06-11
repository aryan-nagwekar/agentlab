"""Run metrics: totals, per-agent breakdown, and highlight superlatives.

Latency aggregates ("avg", "p95") are computed over *operation* latencies —
agent task spans, tool calls, and model calls that report latency_ms — which
is the latency developers can actually act on. The run wall-clock duration is
reported separately as duration_ms.
"""
from __future__ import annotations

import math
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import costing, models, scoring
from .events import FAILURE_EVENT_TYPES, LAB_EVENT_TYPES
from .schemas import AgentMetricsOut, HighlightOut, MetricsTotalsOut, RunMetricsOut
from .timeutil import utcnow

_LATENCY_EVENT_TYPES = (
    "agent.completed",
    "agent.failed",
    "tool.completed",
    "tool.failed",
    "model.completed",
)


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(0.95 * len(ordered)) - 1))
    return round(ordered[index], 2)


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def build_run_metrics(session: Session, run: models.Run) -> RunMetricsOut:
    event_rows = (
        session.execute(
            select(models.Event)
            .where(models.Event.run_id == run.id)
            .order_by(models.Event.timestamp, models.Event.id)
        )
        .scalars()
        .all()
    )
    rows = [(e.event_type, e.source_agent_id, e.payload) for e in event_rows]

    total_events = len(rows)
    participants: set[str] = set()
    operation_latencies: list[float] = []
    agent_task_latencies: dict[str, list[float]] = defaultdict(list)
    per_messages: dict[str, int] = defaultdict(int)
    per_tools: dict[str, int] = defaultdict(int)
    per_models: dict[str, int] = defaultdict(int)
    per_tokens: dict[str, int] = defaultdict(int)
    per_costs: dict[str, float] = defaultdict(float)
    per_errors: dict[str, int] = defaultdict(int)
    per_activity: dict[str, int] = defaultdict(int)
    model_calls = 0
    error_count = 0
    attack_count = 0
    flagged_messages = 0
    suspicious_agents: set[str] = set()

    for etype, src, payload in rows:
        payload = payload or {}
        if src and etype not in LAB_EVENT_TYPES:
            participants.add(src)
            per_activity[src] += 1
        if etype == "attack.injected":
            attack_count += 1
        if etype == "message.flagged":
            flagged_messages += 1
        if etype in ("agent.suspicious", "agent.quarantined") and src:
            suspicious_agents.add(src)
        latency = payload.get("latency_ms")
        if etype in _LATENCY_EVENT_TYPES and latency is not None:
            try:
                operation_latencies.append(float(latency))
            except (TypeError, ValueError):
                pass
        if etype in ("agent.completed", "agent.failed") and src and latency is not None:
            try:
                agent_task_latencies[src].append(float(latency))
            except (TypeError, ValueError):
                pass
        if etype == "message.sent" and src:
            per_messages[src] += 1
        if etype == "tool.called" and src:
            per_tools[src] += 1
        if etype == "model.called":
            model_calls += 1
            if src:
                per_models[src] += 1
        # Tokens and cost come from the costing engine below (single source of
        # truth, pricing-derived) — see `cost_agg`.
        if etype in FAILURE_EVENT_TYPES:
            error_count += 1
            if src:
                per_errors[src] += 1

    message_count = session.execute(
        select(func.count()).select_from(models.Message).where(models.Message.run_id == run.id)
    ).scalar_one()
    tool_call_count = session.execute(
        select(func.count()).select_from(models.ToolCall).where(models.ToolCall.run_id == run.id)
    ).scalar_one()

    agents: dict[str, models.Agent] = {}
    if participants:
        agents = {
            agent.id: agent
            for agent in session.execute(
                select(models.Agent).where(
                    models.Agent.project_id == run.project_id,
                    models.Agent.id.in_(sorted(participants)),
                )
            ).scalars()
        }

    if run.started_at and run.completed_at:
        duration_ms: float | None = (run.completed_at - run.started_at).total_seconds() * 1000
    elif run.started_at and run.status == "running":
        duration_ms = (utcnow() - run.started_at).total_seconds() * 1000
    else:
        duration_ms = run.total_latency_ms

    # Tokens + cost from the costing engine (pricing-derived, single source).
    cost_agg = costing.aggregate(event_rows)
    for agent_id, agent_cost in cost_agg.agents.items():
        per_tokens[agent_id] = agent_cost.total_tokens
        per_costs[agent_id] = agent_cost.estimated_cost_usd
    tokens_total = cost_agg.total_tokens
    cost_total = cost_agg.estimated_cost_usd

    # Run-scoped trust/risk from the deterministic scoring engine.
    scores = scoring.score_events(event_rows, seed=participants)

    per_agent: list[AgentMetricsOut] = []
    for agent_id in sorted(participants):
        agent = agents.get(agent_id)
        score = scores.get(agent_id)
        per_agent.append(
            AgentMetricsOut(
                agent_id=agent_id,
                name=agent.name if agent else agent_id,
                role=agent.role if agent else None,
                messages=per_messages.get(agent_id, 0),
                tool_calls=per_tools.get(agent_id, 0),
                model_calls=per_models.get(agent_id, 0),
                tokens=per_tokens.get(agent_id, 0),
                cost_estimate=round(per_costs.get(agent_id, 0.0), 6),
                avg_latency_ms=_avg(agent_task_latencies.get(agent_id, [])),
                errors=per_errors.get(agent_id, 0),
                trust_score=score.trust_score if score else 1.0,
                risk_score=score.risk_score if score else 0.0,
            )
        )

    def _highlight(metric: str, unit: str, better: str = "max") -> HighlightOut | None:
        best: AgentMetricsOut | None = None
        best_value = 0.0
        for row in per_agent:
            value = getattr(row, metric)
            if value is None:
                continue
            value = float(value)
            if value > best_value:
                best_value = value
                best = row
        if best is None or best_value <= 0:
            return None
        return HighlightOut(agent_id=best.agent_id, name=best.name, value=round(best_value, 2), unit=unit)

    activity_rows = {
        row.agent_id: row.messages + row.tool_calls + row.model_calls for row in per_agent
    }
    most_active: HighlightOut | None = None
    if activity_rows:
        top_agent_id = max(activity_rows, key=lambda k: activity_rows[k])
        if activity_rows[top_agent_id] > 0:
            top_row = next(r for r in per_agent if r.agent_id == top_agent_id)
            most_active = HighlightOut(
                agent_id=top_agent_id,
                name=top_row.name,
                value=float(activity_rows[top_agent_id]),
                unit="ops",
            )

    trust_values = [row.trust_score for row in per_agent]
    risk_values = [row.risk_score for row in per_agent]
    totals = MetricsTotalsOut(
        agents=len(participants),
        messages=message_count,
        tool_calls=tool_call_count,
        model_calls=model_calls,
        events=total_events,
        tokens=tokens_total,
        cost_estimate=cost_total,
        avg_latency_ms=_avg(operation_latencies),
        p95_latency_ms=_p95(operation_latencies),
        error_count=error_count,
        error_rate=round(error_count / total_events, 4) if total_events else 0.0,
        duration_ms=round(duration_ms, 2) if duration_ms is not None else None,
        attacks=attack_count,
        flagged_messages=flagged_messages,
        suspicious_agents=len(suspicious_agents & participants),
        avg_trust=round(sum(trust_values) / len(trust_values), 4) if trust_values else None,
        avg_risk=round(sum(risk_values) / len(risk_values), 4) if risk_values else None,
    )

    highest_risk = max(per_agent, key=lambda r: r.risk_score, default=None)
    lowest_trust = min(per_agent, key=lambda r: r.trust_score, default=None)

    return RunMetricsOut(
        run_id=run.id,
        totals=totals,
        per_agent=per_agent,
        highlights={
            "slowest_agent": _highlight("avg_latency_ms", "ms"),
            "most_expensive_agent": _highlight("cost_estimate", "USD"),
            "most_active_agent": most_active,
            "most_unreliable_agent": _highlight("errors", "errors"),
            "highest_risk_agent": (
                HighlightOut(agent_id=highest_risk.agent_id, name=highest_risk.name, value=highest_risk.risk_score, unit="risk")
                if highest_risk and highest_risk.risk_score > 0
                else None
            ),
            "lowest_trust_agent": (
                HighlightOut(agent_id=lowest_trust.agent_id, name=lowest_trust.name, value=lowest_trust.trust_score, unit="trust")
                if lowest_trust and lowest_trust.trust_score < 1.0
                else None
            ),
        },
    )
