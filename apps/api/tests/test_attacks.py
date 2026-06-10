"""Security Lab: malicious-agent attack simulation, projections, replay, safety."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

ALL_ATTACKS = {
    "malicious_agent_joined",
    "fake_capability_advertising",
    "prompt_injection_message",
    "mock_data_exfiltration_attempt",
    "high_frequency_spam",
    "trust_poisoning",
    "routing_manipulation",
    "unsafe_tool_request",
}


def _attack(client, attack_type, **kwargs):
    return client.post(
        "/api/runs/run-1/attacks", json={"attack_type": attack_type, **kwargs}
    )


def test_attack_templates(client):
    templates = client.get("/api/lab/attack-templates").json()
    assert {t["attack_type"] for t in templates} == ALL_ATTACKS
    for template in templates:
        assert template["label"] and template["description"]
        assert template["severity"] in ("low", "medium", "high", "critical")
        assert template["target_kind"] in ("agent", "network")
        assert template["emits"][0] == "attack.injected"
        assert template["mock_payload"]  # every template ships a mock example


def test_malicious_agent_joined_appears_suspicious(client, seeded_run):
    response = _attack(client, "malicious_agent_joined")
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["attack_type"] == "malicious_agent_joined"
    types = [e["event_type"] for e in result["events"]]
    assert types == ["attack.injected", "agent.joined", "risk.updated"]

    attack = result["events"][0]
    assert attack["source_agent_id"] == "lab-controller"
    assert attack["target_agent_id"] == "malicious-agent"
    assert attack["payload"]["safe_simulation"] is True
    assert attack["metadata"]["real_secrets_accessed"] is False
    assert attack["metadata"]["real_network_access"] is False

    graph = client.get("/api/runs/run-1/graph").json()
    nodes = {n["id"]: n for n in graph["nodes"]}
    assert nodes["malicious-agent"]["status"] == "suspicious"
    assert nodes["malicious-agent"]["name"] == "Malicious Agent"
    assert nodes["malicious-agent"]["risk_score"] >= 0.5
    # the operator that injected the attack is never a workflow node
    assert "lab-controller" not in nodes


def test_prompt_injection_flags_message_and_raises_risk(client, seeded_run):
    response = _attack(client, "prompt_injection_message", target_agent_id="researcher")
    assert response.status_code == 201
    types = [e["event_type"] for e in response.json()["events"]]
    assert types == [
        "attack.injected",
        "agent.suspicious",
        "message.sent",
        "message.flagged",
        "risk.updated",
    ]
    # suspicious message is visible in the run's event stream
    events = client.get(
        "/api/runs/run-1/events", params={"event_type": "message.flagged"}
    ).json()
    assert len(events) == 1
    assert "MOCK_SECRET_TOKEN" in json.dumps(events[0]["payload"])

    graph = client.get("/api/runs/run-1/graph").json()
    edge = next(e for e in graph["edges"] if e["id"] == "malicious-agent->researcher")
    assert edge["last_status"] == "flagged"
    node = next(n for n in graph["nodes"] if n["id"] == "malicious-agent")
    assert node["status"] == "suspicious"


def test_mock_exfiltration_quarantines_and_uses_mock_data_only(client, seeded_run):
    response = _attack(client, "mock_data_exfiltration_attempt")
    assert response.status_code == 201
    events = response.json()["events"]
    types = [e["event_type"] for e in events]
    assert types[-1] == "agent.quarantined"
    assert "message.flagged" in types

    blob = json.dumps(events)
    assert "MOCK_API_KEY_12345" in blob
    # No real secret-looking material: only MOCK_ placeholders.
    for event in events:
        assert event["metadata"]["real_secrets_accessed"] is False
        assert event["metadata"]["real_network_access"] is False

    graph = client.get("/api/runs/run-1/graph").json()
    nodes = {n["id"]: n for n in graph["nodes"]}
    assert nodes["malicious-agent"]["status"] == "quarantined"
    # exfil destination shows up as a flagged-edge target
    assert "attacker-endpoint" in nodes
    edge = next(e for e in graph["edges"] if e["id"] == "malicious-agent->attacker-endpoint")
    assert edge["last_status"] == "flagged"


def test_spam_inflates_message_count(client, seeded_run):
    response = _attack(
        client, "high_frequency_spam", target_agent_id="planner", params={"count": 10}
    )
    assert response.status_code == 201
    graph = client.get("/api/runs/run-1/graph").json()
    edge = next(e for e in graph["edges"] if e["id"] == "malicious-agent->planner")
    assert edge["message_count"] >= 10
    assert edge["last_status"] == "flagged"


def test_unsafe_tool_request_blocked(client, seeded_run):
    response = _attack(client, "unsafe_tool_request", params={"tool_name": "mock_read_secret_file"})
    assert response.status_code == 201
    types = [e["event_type"] for e in response.json()["events"]]
    assert types == ["attack.injected", "agent.suspicious", "tool.called", "tool.failed", "risk.updated"]
    tool_failed = next(e for e in response.json()["events"] if e["event_type"] == "tool.failed")
    assert "BlockedBySimulation" in tool_failed["payload"]["error"]
    assert tool_failed["payload"]["tool_name"] == "mock_read_secret_file"


def test_routing_manipulation_records_attempt(client, seeded_run):
    response = _attack(client, "routing_manipulation", target_agent_id="planner")
    assert response.status_code == 201
    risk = next(e for e in response.json()["events"] if e["event_type"] == "risk.updated")
    assert risk["payload"]["manipulation_attempt"] is True


def test_attack_in_replay_tape_and_markers(client, seeded_run):
    base = client.get("/api/runs/run-1/replay").json()["event_count"]
    _attack(client, "malicious_agent_joined")

    tape = client.get("/api/runs/run-1/replay").json()
    assert tape["markers"]["attacks"] == [base]
    assert tape["events"][base]["event_type"] == "attack.injected"

    # fold at the attack index shows the malicious node suspicious
    after = client.get(
        "/api/runs/run-1/replay/graph", params={"index": base + 1}
    ).json()
    nodes = {n["id"]: n for n in after["nodes"]}
    assert nodes["malicious-agent"]["status"] == "suspicious"
    assert "lab-controller" not in nodes
    before = client.get(
        "/api/runs/run-1/replay/graph", params={"index": base - 1}
    ).json()
    assert "malicious-agent" not in {n["id"] for n in before["nodes"]}


def test_metrics_count_attacks_and_flags(client, seeded_run):
    _attack(client, "prompt_injection_message", target_agent_id="researcher")
    _attack(client, "mock_data_exfiltration_attempt")
    metrics = client.get("/api/runs/run-1/metrics").json()
    totals = metrics["totals"]
    assert totals["attacks"] == 2
    assert totals["flagged_messages"] >= 2
    assert totals["suspicious_agents"] >= 1
    assert "lab-controller" not in {row["agent_id"] for row in metrics["per_agent"]}


def test_attacks_listed_separately_from_faults(client, seeded_run):
    _attack(client, "malicious_agent_joined")
    client.post(
        "/api/runs/run-1/faults", json={"fault_type": "kill_agent", "target_agent_id": "coder"}
    )
    attacks = client.get("/api/runs/run-1/attacks").json()
    faults = client.get("/api/runs/run-1/faults").json()
    assert [e["event_type"] for e in attacks] == ["attack.injected"]
    assert [e["event_type"] for e in faults] == ["fault.injected"]


def test_attack_validation(client, seeded_run):
    assert _attack(client, "nuke_everything").status_code == 422
    # agent-targeted attack without a victim
    assert _attack(client, "prompt_injection_message").status_code == 422
    # victim not in the run
    assert (
        _attack(client, "prompt_injection_message", target_agent_id="ghost").status_code == 422
    )
    response = client.post(
        "/api/runs/ghost/attacks",
        json={"attack_type": "malicious_agent_joined"},
    )
    assert response.status_code == 404
    assert client.get("/api/runs/ghost/attacks").status_code == 404


def test_attacks_respect_api_keys(tmp_path, event_factory):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/atk-auth.db", api_keys="k1", cors_origins=""
    )
    with TestClient(create_app(settings)) as client:
        headers = {"X-API-Key": "k1"}
        client.post("/api/events", json=event_factory("run.started"), headers=headers)
        body = {"attack_type": "malicious_agent_joined"}
        assert client.post("/api/runs/run-1/attacks", json=body).status_code == 401
        assert (
            client.post("/api/runs/run-1/attacks", json=body, headers=headers).status_code == 201
        )
