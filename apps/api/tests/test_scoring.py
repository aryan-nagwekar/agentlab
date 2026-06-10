"""Deterministic trust/risk scoring: unit rules + endpoints + the headline
'quarantined agent must not read trust 1.0' regression."""
from __future__ import annotations

from types import SimpleNamespace

from app import scoring


def ev(event_type, source=None, target=None, event_id=None, **payload):
    return SimpleNamespace(
        event_id=event_id or f"e-{event_type}-{id(payload)}",
        event_type=event_type,
        source_agent_id=source,
        target_agent_id=target,
        payload=payload,
    )


# --------------------------------------------------------------- unit: rules


def test_default_scores():
    s = scoring.AgentScore("a")
    assert s.trust_score == 1.0 and s.risk_score == 0.0


def test_normal_run_keeps_high_trust_low_risk():
    scores = scoring.score_events(
        [ev("agent.started", source="a"), ev("tool.completed", source="a"), ev("agent.completed", source="a")]
    )
    a = scores["a"]
    assert a.trust_score == 1.0  # already maxed; clamped, no drop
    assert a.risk_score == 0.0
    assert scoring.tier(a.trust_score, a.risk_score) == "trusted"


def test_agent_failed_reduces_trust():
    a = scoring.score_events([ev("agent.failed", source="a")])["a"]
    assert a.trust_score == 0.85
    assert a.risk_score == 0.10


def test_model_failed_increases_risk_slightly():
    a = scoring.score_events([ev("model.failed", source="a")])["a"]
    assert a.risk_score == 0.08
    assert a.trust_score == 0.90


def test_message_flagged_increases_risk_strongly():
    a = scoring.score_events([ev("message.flagged", source="a", reason="bad")])["a"]
    assert a.trust_score == 0.80
    assert a.risk_score == 0.25
    assert a.history[-1].reason == "bad"


def test_attack_injected_attributed_to_target_not_controller():
    scores = scoring.score_events(
        [ev("attack.injected", source="lab-controller", target="mal", attack_type="prompt_injection_message")]
    )
    assert "lab-controller" not in scores
    assert scores["mal"].trust_score == 0.75
    assert scores["mal"].risk_score == 0.30
    assert "prompt injection" in scores["mal"].history[-1].reason


def test_fault_injected_attributed_to_victim():
    scores = scoring.score_events(
        [ev("fault.injected", source="lab-controller", target="victim", fault_type="kill_agent")]
    )
    assert scores["victim"].trust_score == 0.95
    assert scores["victim"].risk_score == 0.10


def test_suspicious_sets_floor_and_ceiling():
    a = scoring.score_events([ev("agent.suspicious", source="a")])["a"]
    assert a.trust_score <= 0.5
    assert a.risk_score >= 0.6


def test_quarantine_low_trust_high_risk():
    a = scoring.score_events([ev("agent.quarantined", source="a", reason="caught")])["a"]
    assert 0.1 <= a.trust_score <= 0.2
    assert a.risk_score >= 0.9


def test_quarantined_malicious_agent_not_trust_one():
    """The v0.4 bug: a quarantined malicious agent showed trust 1.0 / risk 0.95."""
    sequence = [
        ev("agent.joined", source="mal", status="suspicious"),
        ev("attack.injected", source="lab", target="mal", attack_type="fake_capability_advertising"),
        ev("agent.suspicious", source="mal"),
        ev("message.flagged", source="mal", target="planner", reason="caps"),
        ev("attack.injected", source="lab", target="mal", attack_type="mock_data_exfiltration_attempt"),
        ev("message.flagged", source="mal", target="attacker-endpoint", reason="exfil"),
        ev("agent.quarantined", source="mal", reason="exfil"),
    ]
    mal = scoring.score_events(sequence)["mal"]
    assert mal.trust_score < 0.5  # NOT 1.0
    assert 0.1 <= mal.trust_score <= 0.25
    assert mal.risk_score >= 0.9
    assert scoring.tier(mal.trust_score, mal.risk_score) == "high-risk"


def test_scores_are_clamped():
    a = scoring.score_events([ev("agent.failed", source="a")] * 20)["a"]
    assert a.trust_score == 0.0
    assert a.risk_score == 1.0


def test_history_is_deterministic_and_explained():
    seq = [ev("attack.injected", source="lab", target="m", attack_type="x"), ev("message.flagged", source="m", target="v", reason="r")]
    first = scoring.score_events(seq)["m"]
    second = scoring.score_events(seq)["m"]
    assert first.trust_score == second.trust_score
    assert first.risk_score == second.risk_score
    assert [c.caused_by_event_type for c in first.history] == ["attack.injected", "message.flagged"]
    change = first.history[0]
    assert change.previous_trust == 1.0
    assert change.new_trust == 0.75
    assert change.trust_delta == -0.25


def test_no_score_change_records_nothing():
    # message.received bumps trust, but trust is already maxed -> no recorded change
    a = scoring.score_events([ev("message.received", source="a")])["a"]
    assert a.history == []


def test_trust_updated_manual_override():
    a = scoring.score_events([ev("trust.updated", source="a", trust_score=0.42, reason="manual")])["a"]
    assert a.trust_score == 0.42
    assert a.history[-1].reason == "manual"


def test_replay_fold_reproduces_score_at_each_cursor():
    seq = [
        ev("agent.started", source="a"),
        ev("agent.failed", source="a"),
        ev("message.flagged", source="a", target="b", reason="x"),
    ]
    after1 = scoring.score_events(seq[:1]).get("a", scoring.AgentScore("a"))
    after2 = scoring.score_events(seq[:2])["a"]
    after3 = scoring.score_events(seq[:3])["a"]
    assert after1.trust_score == 1.0
    assert after2.trust_score == 0.85
    assert round(after3.trust_score, 2) == 0.65  # 0.85 - 0.20


# ----------------------------------------------------------------- endpoints


def test_run_scores_endpoint(client, seeded_run):
    data = client.get("/api/runs/run-1/scores").json()
    assert data["scoring_version"] == "v0.5"
    by_id = {a["agent_id"]: a for a in data["agents"]}
    # seeded_run: coder fails (tool.failed + agent.failed) -> degraded
    assert by_id["coder"]["trust_score"] < 1.0
    assert by_id["coder"]["tier"] in ("caution", "suspicious", "high-risk")
    assert by_id["coder"]["latest_reason"]
    # planner only sends/routes -> stays trusted
    assert by_id["planner"]["trust_score"] == 1.0


def test_score_history_endpoint_ordered(client, seeded_run):
    history = client.get("/api/runs/run-1/score-history").json()["changes"]
    assert history
    indices = [c["event_index"] for c in history]
    assert indices == sorted(indices)
    assert all("caused_by_event_type" in c and "reason" in c for c in history)


def test_risk_summary_endpoint(client, seeded_run):
    summary = client.get("/api/runs/run-1/risk-summary").json()
    assert summary["highest_risk_agent"]["agent_id"] == "coder"
    assert summary["lowest_trust_agent"]["agent_id"] == "coder"
    assert summary["avg_trust"] is not None
    assert summary["fault_events"] == 0


def test_agent_scores_endpoint_has_factors(client, seeded_run):
    data = client.get("/api/agents/coder/scores", params={"project_id": "proj-1"}).json()
    assert data["agent_id"] == "coder"
    assert data["trust_score"] < 1.0
    assert any(f["event_type"] in ("tool.failed", "agent.failed") for f in data["trust_factors"])
    assert data["history"]


def test_quarantined_agent_score_consistent_via_api(client, seeded_run):
    client.post(
        "/api/runs/run-1/attacks",
        json={"attack_type": "mock_data_exfiltration_attempt"},
    )
    node = next(
        n for n in client.get("/api/runs/run-1/graph").json()["nodes"] if n["id"] == "malicious-agent"
    )
    assert node["status"] == "quarantined"
    assert node["trust_score"] < 0.5  # the headline fix: never 1.0 when quarantined
    assert node["risk_score"] >= 0.9


def test_unknown_run_scores_404(client):
    assert client.get("/api/runs/ghost/scores").status_code == 404
    assert client.get("/api/runs/ghost/risk-summary").status_code == 404
    assert client.get("/api/agents/ghost/scores").status_code == 404
