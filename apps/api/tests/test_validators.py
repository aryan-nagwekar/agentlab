"""Deterministic Validators (v1.8): six evidence-based validators, bounded
redacted evidence (no raw secrets/host paths), validator.* events through the
normal pipeline, a narrow enforcement hook (validator-failed actions blocked),
and metadata-only task linkage."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

SECRET = "sk-deadBEEF1234567890abcd"


@pytest.fixture
def env(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/val.db",
        api_keys="",
        cors_origins="",
        workspaces_root=str(tmp_path / "workspaces"),
    )
    with TestClient(create_app(settings)) as client:
        wid = client.post(
            "/api/runtime/workspaces",
            json={"name": "Validator WS", "goal": "Test validators.", "project_id": "p1"},
        ).json()["workspace_id"]
        client.post(f"/api/runtime/workspaces/{wid}/sandbox/init")
        yield client, wid, tmp_path / "workspaces" / wid


def _run(client, wid, validator_type, **body):
    return client.post(
        f"/api/runtime/workspaces/{wid}/validators/run",
        json={"validator_type": validator_type, **body},
    )


def _write(client, wid, path, content):
    return client.post(
        f"/api/runtime/workspaces/{wid}/files/write", json={"path": path, "content": content}
    )


def _activity_types(client, wid):
    return [e["event_type"] for e in client.get(f"/api/runtime/workspaces/{wid}/activity").json()]


# ----------------------------------------------------------- registry / run


def test_validator_registry_lists_six(env):
    client, wid, _ = env
    registry = client.get("/api/runtime/validators").json()
    assert {v["type"] for v in registry} == {
        "secret_exposure", "code_syntax", "command_result",
        "research_claim", "data_flow", "business_risk",
    }
    assert all(v["description"] and v["target_type"] for v in registry)


def test_unknown_validator_400(env):
    client, wid, _ = env
    assert _run(client, wid, "warp_core").status_code == 400


# ------------------------------------------------------- secret exposure


def test_secret_exposure_pass_on_safe_content(env):
    client, wid, _ = env
    _write(client, wid, "app.py", "x = 1\nprint('hello')\n")
    result = _run(client, wid, "secret_exposure", target_ref="app.py").json()
    assert result["passed"] is True
    assert result["evidence"]["match_count"] == 0


def test_secret_exposure_fail_redacts_secret_everywhere(env):
    client, wid, _ = env
    _write(client, wid, "leak.py", f"API_KEY = '{SECRET}'\n")
    response = _run(client, wid, "secret_exposure", target_ref="leak.py")
    assert response.status_code == 201
    result = response.json()
    assert result["passed"] is False
    assert result["failures"]
    assert result["suggested_action"]
    # the raw secret never appears in the result, events, or DB-backed reads
    assert SECRET not in str(result)
    assert "[redacted]" in str(result["evidence"])
    assert SECRET not in str(client.get(f"/api/runtime/workspaces/{wid}/activity").json())
    assert SECRET not in str(
        client.get(f"/api/runtime/workspaces/{wid}/validators/results").json()
    )
    assert "secret.exposure.detected" in _activity_types(client, wid)


def test_secret_exposure_inline_content(env):
    client, wid, _ = env
    result = _run(
        client, wid, "secret_exposure", payload={"content": f"token={SECRET}"}
    ).json()
    assert result["passed"] is False
    assert SECRET not in str(result)


# ------------------------------------------------------------ code syntax


def test_python_syntax_pass_and_fail(env):
    client, wid, _ = env
    _write(client, wid, "good.py", "def f():\n    return 1\n")
    _write(client, wid, "bad.py", "def f(:\n    return\n")
    assert _run(client, wid, "code_syntax", target_ref="good.py").json()["passed"] is True
    bad = _run(client, wid, "code_syntax", target_ref="bad.py").json()
    assert bad["passed"] is False
    assert "syntax error" in bad["explanation"].lower()


def test_json_syntax_pass_and_fail(env):
    client, wid, _ = env
    _write(client, wid, "ok.json", '{"a": 1}')
    _write(client, wid, "broken.json", '{"a": 1,,}')
    assert _run(client, wid, "code_syntax", target_ref="ok.json").json()["passed"] is True
    assert _run(client, wid, "code_syntax", target_ref="broken.json").json()["passed"] is False


def test_package_json_requires_name_version(env):
    client, wid, _ = env
    _write(client, wid, "package.json", '{"dependencies": {}}')
    result = _run(client, wid, "code_syntax", target_ref="package.json").json()
    assert result["passed"] is False
    assert any("name" in f for f in result["failures"])


# -------------------------------------------------------- command result


def test_command_result_pass_on_exit_zero(env):
    client, wid, _ = env
    client.post(f"/api/runtime/workspaces/{wid}/commands/run", json={"command": "pwd"})
    result = _run(client, wid, "command_result").json()
    assert result["passed"] is True
    assert result["evidence"]["exit_code"] == 0


def test_command_result_fail_on_nonzero(env):
    client, wid, _ = env
    client.post(
        f"/api/runtime/workspaces/{wid}/commands/run",
        json={"command": "ls", "args": ["does-not-exist"]},
    )
    result = _run(client, wid, "command_result").json()
    assert result["passed"] is False
    assert "runtime.error.detected" in _activity_types(client, wid)


def test_command_result_no_command(env):
    client, wid, _ = env
    result = _run(client, wid, "command_result").json()
    assert result["passed"] is False
    assert "no recorded command" in result["failures"][0]


# --------------------------------------------------------- research claim


def test_research_claim_fails_missing_url(env):
    client, wid, _ = env
    result = _run(
        client, wid, "research_claim",
        payload={"claim": "Acme sells bottles", "evidence_text": "price moq shipping supplier_name acme bottles"},
    ).json()
    assert result["passed"] is False
    assert any("source_url" in f for f in result["failures"])
    assert "claim.rejected" in _activity_types(client, wid)


def test_research_claim_fails_missing_evidence_fields(env):
    client, wid, _ = env
    result = _run(
        client, wid, "research_claim",
        payload={"claim": "Acme bottles", "source_url": "https://acme.example",
                 "evidence_text": "acme bottles only"},
    ).json()
    assert result["passed"] is False
    assert any("missing required field" in f for f in result["failures"])


def test_research_claim_passes_with_complete_evidence(env):
    client, wid, _ = env
    result = _run(
        client, wid, "research_claim",
        payload={
            "claim": "Acme bottles wholesale",
            "source_url": "https://acme.example/bottles",
            "evidence_text": "Acme bottles wholesale price $2 MOQ 500 shipping 7 days supplier_name Acme",
        },
    ).json()
    assert result["passed"] is True
    assert "claim.verified" in _activity_types(client, wid)


# ------------------------------------------------------------- data flow


def test_data_flow_detects_field_mismatch(env):
    client, wid, _ = env
    result = _run(
        client, wid, "data_flow",
        payload={
            "consumer": {"label": "product page", "fields": {"price": "number"}},
            "producer": {"label": "product API", "fields": {"cost": "number"}},
        },
    ).json()
    assert result["passed"] is False
    assert "price" in result["explanation"]
    assert "schema.mismatch.detected" in _activity_types(client, wid)
    assert "app.error.translated" in _activity_types(client, wid)


def test_data_flow_passes_when_fields_match(env):
    client, wid, _ = env
    result = _run(
        client, wid, "data_flow",
        payload={"expected": {"price": "number"}, "actual": {"price": "number"}},
    ).json()
    assert result["passed"] is True


# --------------------------------------------------------- business risk


def test_business_risk_flags_payment_and_requires_approval(env):
    client, wid, _ = env
    result = _run(
        client, wid, "business_risk",
        payload={"target": "src/payment/checkout.ts", "description": "wire stripe"},
    ).json()
    assert result["passed"] is False
    assert result["evidence"]["requires_approval"] is True
    assert result["risk_delta"] > 0
    assert "risky.file_change.detected" in _activity_types(client, wid)


def test_business_risk_flags_unverified_data(env):
    client, wid, _ = env
    result = _run(
        client, wid, "business_risk",
        payload={"target": "product copy", "unverified": True},
    ).json()
    assert result["passed"] is False
    assert any("unverified" in f for f in result["failures"])


def test_business_risk_passes_for_safe_change(env):
    client, wid, _ = env
    result = _run(
        client, wid, "business_risk", payload={"target": "src/components/Hero.tsx"}
    ).json()
    assert result["passed"] is True


# --------------------------------------------- enforcement / task / replay


def test_failed_validation_blocks_future_action(env):
    client, wid, _ = env
    # an action tagged as validator-failed is blocked by the new policy rule
    proposed = client.post(
        f"/api/runtime/workspaces/{wid}/actions/propose",
        json={"action_type": "data.save", "target": "suppliers",
              "metadata": {"validation_failed": True, "validator_result_id": "val-xyz"}},
    ).json()
    assert proposed["status"] == "blocked"
    assert proposed["decision"]["matched_rules"][0]["id"] == "block-failed-validation"


def test_task_validation_status_metadata(env):
    client, wid, _ = env
    client.post(f"/api/runtime/workspaces/{wid}/agents", json={"name": "P", "role": "Planner"})
    wfid = client.post(f"/api/runtime/workspaces/{wid}/workflows", json={}).json()["workflow_id"]
    client.post(f"/api/runtime/workspaces/{wid}/workflows/{wfid}/plan")
    task = client.get(f"/api/runtime/workspaces/{wid}/workflows/{wfid}/tasks").json()[0]
    _write(client, wid, "bad.py", "def (:")
    _run(client, wid, "code_syntax", target_ref="bad.py", workflow_id=wfid, task_id=task["task_id"])
    refreshed = client.get(
        f"/api/runtime/workspaces/{wid}/workflows/{wfid}/tasks"
    ).json()
    target = next(t for t in refreshed if t["task_id"] == task["task_id"])
    assert target["metadata"]["validation_status"] == "failed"


def test_validator_results_listed_and_fetched(env):
    client, wid, _ = env
    _write(client, wid, "a.py", "x = 1")
    run = _run(client, wid, "code_syntax", target_ref="a.py").json()
    listed = client.get(f"/api/runtime/workspaces/{wid}/validators/results").json()
    assert listed[0]["result_id"] == run["result_id"]
    detail = client.get(
        f"/api/runtime/workspaces/{wid}/validators/results/{run['result_id']}"
    ).json()
    assert detail["validator_type"] == "code_syntax"
    assert client.get(
        f"/api/runtime/workspaces/{wid}/validators/results/val-nope"
    ).status_code == 404


def test_validation_events_in_timeline_and_replay(env):
    client, wid, _ = env
    workspace = client.get(f"/api/runtime/workspaces/{wid}").json()
    run_id = workspace["activity_run_id"]
    _write(client, wid, "x.json", '{"a":1}')
    _run(client, wid, "code_syntax", target_ref="x.json")
    timeline = [e["event_type"] for e in client.get(f"/api/runs/{run_id}/events").json()]
    for expected in ("validator.started", "validation.passed", "validator.completed"):
        assert expected in timeline
    replay = client.get(f"/api/runs/{run_id}/replay").json()
    assert [e["event_type"] for e in replay["events"]] == timeline
    for path in ("graph", "metrics", "scores"):
        assert client.get(f"/api/runs/{run_id}/{path}").status_code == 200, path


def test_no_host_paths_in_validation_events(env):
    client, wid, root = env
    _write(client, wid, "app.py", "x = 1")
    _run(client, wid, "secret_exposure", target_ref="app.py")
    assert str(root) not in str(client.get(f"/api/runtime/workspaces/{wid}/activity").json())


def test_run_requires_api_key_when_configured(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/val-auth.db",
        api_keys="k1",
        cors_origins="",
        workspaces_root=str(tmp_path / "ws"),
    )
    with TestClient(create_app(settings)) as client:
        h = {"X-API-Key": "k1"}
        wid = client.post(
            "/api/runtime/workspaces", json={"name": "W"}, headers=h
        ).json()["workspace_id"]
        body = {"validator_type": "business_risk", "payload": {"target": "x"}}
        assert client.post(
            f"/api/runtime/workspaces/{wid}/validators/run", json=body
        ).status_code == 401
        assert client.post(
            f"/api/runtime/workspaces/{wid}/validators/run", json=body, headers=h
        ).status_code == 201
        # reads stay open
        assert client.get("/api/runtime/validators").status_code == 200
        assert client.get(
            f"/api/runtime/workspaces/{wid}/validators/results"
        ).status_code == 200
