"""Deterministic, event-derived trust & risk scoring.

No LLM, no randomness: an agent's trust/risk is a pure fold over the ordered
events that mention it. Because it is a pure function of the event log, the
score is reproducible and replayable — the score at replay cursor *k* is just
``score_events(events[:k+1])``.

The same rule table runs in four places that MUST agree:
  - this module                          (endpoints, metrics)
  - app/graph.py                         (live topology node scores)
  - app/replay.py fold_events            (replay reconstruction)
  - app/collector.py                     (stored Agent.trust/risk projection)
  - apps/web/.../replay/scoring.ts       (dashboard reducer mirror)
Change a rule here, change it there.

v0.5 deliberately does NOT emit ``score.updated`` events into the store —
deriving on read makes feedback loops impossible (a score change can never
trigger another score change). Score changes are returned as history records.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol

SCORING_VERSION = "v0.5"
DEFAULT_TRUST = 1.0
DEFAULT_RISK = 0.0
_EPSILON = 1e-9


class EventLike(Protocol):
    event_id: str
    event_type: str
    source_agent_id: str | None
    target_agent_id: str | None
    payload: dict[str, Any]


@dataclass(frozen=True)
class Effect:
    """A score adjustment. Deltas are additive; floors/ceilings clamp after."""

    trust_delta: float = 0.0
    risk_delta: float = 0.0
    trust_ceil: float | None = None
    trust_floor: float | None = None
    risk_floor: float | None = None
    risk_ceil: float | None = None


# A suspicious agent: trust forced to at most 0.5, risk to at least 0.6.
SUSPICIOUS = Effect(trust_ceil=0.5, risk_floor=0.6)
# A quarantined agent: pinned into the "known-bad-but-tracked" band, never 0/1.
QUARANTINE = Effect(trust_ceil=0.2, trust_floor=0.1, risk_floor=0.9)

# event_type -> Effect. Deltas/clamps chosen so cumulative behaviour matches the
# v0.5 spec (e.g. a quarantined malicious agent lands ~0.1 trust / ~0.95 risk,
# never trust 1.0). Events not listed here (and trust/risk.updated, agent.joined,
# handled specially below) have no score effect.
EFFECTS: dict[str, Effect] = {
    # positive — reliable behaviour preserves/raises trust, eases risk
    "agent.completed": Effect(trust_delta=0.05, risk_delta=-0.02),
    "tool.completed": Effect(trust_delta=0.01),
    "model.completed": Effect(trust_delta=0.01),
    "message.received": Effect(trust_delta=0.01),
    # negative — failures degrade reliability
    "agent.failed": Effect(trust_delta=-0.15, risk_delta=0.10),
    "tool.failed": Effect(trust_delta=-0.10, risk_delta=0.08),
    "model.failed": Effect(trust_delta=-0.10, risk_delta=0.08),
    "message.failed": Effect(trust_delta=-0.07, risk_delta=0.05),
    "fault.injected": Effect(trust_delta=-0.05, risk_delta=0.10),
    # negative — adversarial signals degrade trust sharply and raise risk
    "message.flagged": Effect(trust_delta=-0.20, risk_delta=0.25),
    "agent.suspicious": SUSPICIOUS,
    "attack.injected": Effect(trust_delta=-0.25, risk_delta=0.30),
    "agent.quarantined": QUARANTINE,
}

_REASONS: dict[str, str] = {
    "agent.completed": "Completed a task successfully.",
    "tool.completed": "A tool call completed.",
    "model.completed": "A model call completed.",
    "message.received": "Delivered a message successfully.",
    "agent.failed": "An agent task failed.",
    "tool.failed": "A tool call failed.",
    "model.failed": "A model call failed or timed out.",
    "message.failed": "A message failed to deliver.",
    "fault.injected": "A fault was injected into this agent.",
    "message.flagged": "A message from this agent was flagged as suspicious.",
    "agent.suspicious": "Agent was flagged suspicious.",
    "attack.injected": "A simulated attack was attributed to this agent.",
    "agent.quarantined": "Agent was quarantined.",
}


def subject_of(event: EventLike) -> str | None:
    """Which agent a scoring event reflects on.

    Lab control-plane events (attack/fault injected) carry source=lab-controller
    and target=<the agent the event is about>, so they score the target. Every
    other event scores its source.
    """
    if event.event_type in ("attack.injected", "fault.injected"):
        return event.target_agent_id
    return event.source_agent_id


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _reason(event: EventLike) -> str:
    payload = event.payload or {}
    etype = event.event_type
    if etype == "attack.injected" and payload.get("attack_type"):
        return f"Simulated {str(payload['attack_type']).replace('_', ' ')} attack."
    if etype == "fault.injected" and payload.get("fault_type"):
        return f"Fault injected: {str(payload['fault_type']).replace('_', ' ')}."
    if etype == "agent.joined":
        return "An unverified agent joined the network."
    if etype in ("message.flagged", "agent.suspicious", "agent.quarantined") and payload.get("reason"):
        return str(payload["reason"])
    return _REASONS.get(etype, etype)


@dataclass
class ScoreChange:
    agent_id: str
    event_index: int
    caused_by_event_id: str | None
    caused_by_event_type: str
    previous_trust: float
    new_trust: float
    previous_risk: float
    new_risk: float
    reason: str

    @property
    def trust_delta(self) -> float:
        return round(self.new_trust - self.previous_trust, 4)

    @property
    def risk_delta(self) -> float:
        return round(self.new_risk - self.previous_risk, 4)


@dataclass
class AgentScore:
    agent_id: str
    trust_score: float = DEFAULT_TRUST
    risk_score: float = DEFAULT_RISK
    history: list[ScoreChange] = field(default_factory=list)

    @property
    def latest_reason(self) -> str | None:
        return self.history[-1].reason if self.history else None


def _effect_for(event: EventLike) -> Effect | None:
    """Resolve the Effect for an event, handling the conditional/override cases."""
    etype = event.event_type
    if etype == "agent.joined":
        status = (event.payload or {}).get("status")
        if status == "quarantined":
            return QUARANTINE
        if status == "suspicious":
            return SUSPICIOUS
        return None
    return EFFECTS.get(etype)


def _apply_effect(trust: float, risk: float, effect: Effect) -> tuple[float, float]:
    new_trust = _clamp(trust + effect.trust_delta)
    new_risk = _clamp(risk + effect.risk_delta)
    if effect.trust_ceil is not None:
        new_trust = min(new_trust, effect.trust_ceil)
    if effect.trust_floor is not None:
        new_trust = max(new_trust, effect.trust_floor)
    if effect.risk_floor is not None:
        new_risk = max(new_risk, effect.risk_floor)
    if effect.risk_ceil is not None:
        new_risk = min(new_risk, effect.risk_ceil)
    return round(new_trust, 4), round(new_risk, 4)


def score_values(trust: float, risk: float, event: EventLike) -> tuple[float, float]:
    """Apply one event to a (trust, risk) pair. Used by the collector to keep the
    stored Agent row consistent. Returns the new (trust, risk)."""
    etype = event.event_type
    payload = event.payload or {}
    if etype == "trust.updated":
        value = payload.get("trust_score")
        return (round(_clamp(float(value)), 4) if value is not None else trust), risk
    if etype == "risk.updated":
        value = payload.get("risk_score")
        return trust, (round(_clamp(float(value)), 4) if value is not None else risk)
    effect = _effect_for(event)
    if effect is None:
        return trust, risk
    return _apply_effect(trust, risk, effect)


def apply_event(
    scores: dict[str, AgentScore], event: EventLike, index: int
) -> ScoreChange | None:
    """Fold one event into the running scores, recording an explained change."""
    subject = subject_of(event)
    if not subject:
        return None
    state = scores.setdefault(subject, AgentScore(subject))
    prev_trust, prev_risk = state.trust_score, state.risk_score
    payload = event.payload or {}
    etype = event.event_type

    if etype in ("trust.updated", "risk.updated"):
        new_trust, new_risk = score_values(prev_trust, prev_risk, event)
        reason = payload.get("reason") or (
            "Trust manually set." if etype == "trust.updated" else "Risk manually set."
        )
    else:
        effect = _effect_for(event)
        if effect is None:
            return None
        new_trust, new_risk = _apply_effect(prev_trust, prev_risk, effect)
        reason = _reason(event)

    if abs(new_trust - prev_trust) < _EPSILON and abs(new_risk - prev_risk) < _EPSILON:
        return None

    state.trust_score, state.risk_score = new_trust, new_risk
    change = ScoreChange(
        agent_id=subject,
        event_index=index,
        caused_by_event_id=getattr(event, "event_id", None),
        caused_by_event_type=etype,
        previous_trust=prev_trust,
        new_trust=new_trust,
        previous_risk=prev_risk,
        new_risk=new_risk,
        reason=reason,
    )
    state.history.append(change)
    return change


def score_events(
    events: Iterable[EventLike], seed: Iterable[str] = ()
) -> dict[str, AgentScore]:
    """Fold an ordered event stream into per-agent scores + change history.

    `seed` pre-registers agents at default scores so participants that never
    trigger a scoring event still appear (at trust 1.0 / risk 0.0)."""
    scores: dict[str, AgentScore] = {agent_id: AgentScore(agent_id) for agent_id in seed}
    for index, event in enumerate(events):
        apply_event(scores, event, index)
    return scores


def tier(trust: float, risk: float) -> str:
    """Coarse band used for node colouring and badges."""
    if trust <= 0.2 or risk >= 0.9:
        return "high-risk"
    if trust < 0.5 or risk >= 0.6:
        return "suspicious"
    if trust < 0.8 or risk >= 0.3:
        return "caution"
    return "trusted"


def factors(score: AgentScore) -> dict[str, list[dict[str, Any]]]:
    """Aggregate a score's history into the biggest trust/risk movers."""
    agg: dict[str, dict[str, float]] = {}
    for change in score.history:
        bucket = agg.setdefault(
            change.caused_by_event_type, {"count": 0, "trust": 0.0, "risk": 0.0}
        )
        bucket["count"] += 1
        bucket["trust"] += change.trust_delta
        bucket["risk"] += change.risk_delta

    def rows() -> list[dict[str, Any]]:
        return [
            {
                "event_type": etype,
                "count": int(data["count"]),
                "trust_delta": round(data["trust"], 4),
                "risk_delta": round(data["risk"], 4),
            }
            for etype, data in agg.items()
        ]

    trust_factors = sorted(
        [r for r in rows() if abs(r["trust_delta"]) > _EPSILON], key=lambda r: r["trust_delta"]
    )
    risk_factors = sorted(
        [r for r in rows() if abs(r["risk_delta"]) > _EPSILON],
        key=lambda r: r["risk_delta"],
        reverse=True,
    )
    return {"trust_factors": trust_factors, "risk_factors": risk_factors}
