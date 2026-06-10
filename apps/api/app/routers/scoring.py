"""Trust/risk scoring endpoints (v0.5).

Scores are derived on read from the ordered event stream via app/scoring.py —
reproducible, explainable, and replayable. Nothing is stored beyond the
already-existing events.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import models, scoring
from ..deps import get_session
from ..schemas import (
    AgentScoreOut,
    RiskSummaryAgentOut,
    RunRiskSummaryOut,
    RunScoreHistoryOut,
    RunScoresOut,
    ScoreChangeOut,
    ScoreFactorOut,
)

router = APIRouter()


def _ordered_run_events(session: Session, run_id: str) -> list[models.Event]:
    return list(
        session.execute(
            select(models.Event)
            .where(models.Event.run_id == run_id)
            .order_by(models.Event.timestamp, models.Event.id)
        )
        .scalars()
        .all()
    )


def _change_out(change: scoring.ScoreChange) -> ScoreChangeOut:
    return ScoreChangeOut(
        agent_id=change.agent_id,
        event_index=change.event_index,
        caused_by_event_id=change.caused_by_event_id,
        caused_by_event_type=change.caused_by_event_type,
        previous_trust=change.previous_trust,
        new_trust=change.new_trust,
        previous_risk=change.previous_risk,
        new_risk=change.new_risk,
        trust_delta=change.trust_delta,
        risk_delta=change.risk_delta,
        reason=change.reason,
    )


def _factor_rows(rows: list[dict]) -> list[ScoreFactorOut]:
    return [ScoreFactorOut(**row) for row in rows]


def _agent_score_out(
    score: scoring.AgentScore,
    *,
    name: str | None,
    status: str,
) -> AgentScoreOut:
    factors = scoring.factors(score)
    return AgentScoreOut(
        agent_id=score.agent_id,
        name=name,
        status=status,
        trust_score=score.trust_score,
        risk_score=score.risk_score,
        tier=scoring.tier(score.trust_score, score.risk_score),
        latest_reason=score.latest_reason,
        trust_factors=_factor_rows(factors["trust_factors"]),
        risk_factors=_factor_rows(factors["risk_factors"]),
        history=[_change_out(change) for change in score.history],
    )


@router.get("/runs/{run_id}/scores", response_model=RunScoresOut)
def get_run_scores(run_id: str, session: Session = Depends(get_session)) -> RunScoresOut:
    run = session.get(models.Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    events = _ordered_run_events(session, run_id)
    scores = scoring.score_events(events)
    agent_rows = {
        agent.id: agent
        for agent in session.execute(
            select(models.Agent).where(models.Agent.project_id == run.project_id)
        ).scalars()
    }
    agents = [
        _agent_score_out(
            score,
            name=agent_rows[agent_id].name if agent_id in agent_rows else agent_id,
            status=agent_rows[agent_id].status if agent_id in agent_rows else "unknown",
        )
        for agent_id, score in sorted(scores.items())
    ]
    return RunScoresOut(
        run_id=run_id, scoring_version=scoring.SCORING_VERSION, agents=agents
    )


@router.get("/runs/{run_id}/score-history", response_model=RunScoreHistoryOut)
def get_run_score_history(
    run_id: str,
    agent_id: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> RunScoreHistoryOut:
    if session.get(models.Run, run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")
    events = _ordered_run_events(session, run_id)
    scores = scoring.score_events(events)
    changes: list[scoring.ScoreChange] = []
    for agent, score in scores.items():
        if agent_id and agent != agent_id:
            continue
        changes.extend(score.history)
    changes.sort(key=lambda c: c.event_index)
    return RunScoreHistoryOut(
        run_id=run_id,
        scoring_version=scoring.SCORING_VERSION,
        changes=[_change_out(change) for change in changes],
    )


@router.get("/runs/{run_id}/risk-summary", response_model=RunRiskSummaryOut)
def get_run_risk_summary(
    run_id: str, session: Session = Depends(get_session)
) -> RunRiskSummaryOut:
    run = session.get(models.Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    events = _ordered_run_events(session, run_id)
    scores = scoring.score_events(events)
    agent_rows = {
        agent.id: agent
        for agent in session.execute(
            select(models.Agent).where(models.Agent.project_id == run.project_id)
        ).scalars()
    }

    def summary_agent(agent_id: str, score: scoring.AgentScore) -> RiskSummaryAgentOut:
        return RiskSummaryAgentOut(
            agent_id=agent_id,
            name=agent_rows[agent_id].name if agent_id in agent_rows else agent_id,
            trust_score=score.trust_score,
            risk_score=score.risk_score,
            tier=scoring.tier(score.trust_score, score.risk_score),
        )

    highest_risk = lowest_trust = None
    avg_trust = avg_risk = None
    if scores:
        highest = max(scores.items(), key=lambda kv: kv[1].risk_score)
        lowest = min(scores.items(), key=lambda kv: kv[1].trust_score)
        highest_risk = summary_agent(*highest)
        lowest_trust = summary_agent(*lowest)
        avg_trust = round(sum(s.trust_score for s in scores.values()) / len(scores), 4)
        avg_risk = round(sum(s.risk_score for s in scores.values()) / len(scores), 4)

    suspicious = sum(
        1 for s in scores.values() if scoring.tier(s.trust_score, s.risk_score) == "suspicious"
    )
    quarantined = sum(
        1
        for agent_id in scores
        if agent_id in agent_rows and agent_rows[agent_id].status == "quarantined"
    )
    flagged = sum(1 for e in events if e.event_type == "message.flagged")
    attacks = sum(1 for e in events if e.event_type == "attack.injected")
    faults = sum(1 for e in events if e.event_type == "fault.injected")

    return RunRiskSummaryOut(
        run_id=run_id,
        highest_risk_agent=highest_risk,
        lowest_trust_agent=lowest_trust,
        avg_trust=avg_trust,
        avg_risk=avg_risk,
        suspicious_agents=suspicious,
        quarantined_agents=quarantined,
        flagged_messages=flagged,
        attack_events=attacks,
        fault_events=faults,
    )


@router.get("/agents/{agent_id}/scores", response_model=AgentScoreOut)
def get_agent_scores(
    agent_id: str,
    project_id: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> AgentScoreOut:
    """Score + explained history for one agent, optionally scoped to a run."""
    agent = None
    if project_id:
        agent = session.get(models.Agent, {"project_id": project_id, "id": agent_id})
    else:
        found = (
            session.execute(select(models.Agent).where(models.Agent.id == agent_id))
            .scalars()
            .all()
        )
        if len(found) > 1:
            raise HTTPException(
                status_code=400, detail="agent id exists in multiple projects; pass ?project_id="
            )
        agent = found[0] if found else None
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")

    query = (
        select(models.Event)
        .where(
            models.Event.project_id == agent.project_id,
            or_(
                models.Event.source_agent_id == agent_id,
                models.Event.target_agent_id == agent_id,
            ),
        )
        .order_by(models.Event.timestamp, models.Event.id)
    )
    if run_id:
        query = query.where(models.Event.run_id == run_id)
    events = list(session.execute(query).scalars().all())
    scores = scoring.score_events(events)
    score = scores.get(agent_id, scoring.AgentScore(agent_id))
    return _agent_score_out(score, name=agent.name, status=agent.status)
