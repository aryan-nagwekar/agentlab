"""Bounded Agent Loop — multi-step live execution (v3.1).

The model is patched to return scripted step manifests so these tests prove the
*governed loop*, not model quality: each step's file writes and commands are
routed through the v1.5 enforcement gateway exactly like manual ones, validators
run over the outputs and feed the next prompt, and the loop stops on a model
`done` signal, an empty step, max steps, an unrecoverable error, or the first
approval-required action (recorded, then stopped cleanly — resume is v3.2).
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.model_gateway import ModelResponse


@pytest.fixture
def env(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/run.db",
        api_keys="",
        cors_origins="",
        workspaces_root=str(tmp_path / "workspaces"),
    )
    app = create_app(settings)
    # Scripted per-step responses; `default` keeps any extra step safe.
    holder = {
        "responses": [],
        "i": 0,
        "prompts": [],
        "default": _step(done=True, summary="done"),
    }

    async def fake_complete(req):  # patched mock provider
        holder["prompts"].append(req.prompt)
        idx = holder["i"]
        holder["i"] += 1
        resp = holder["responses"][idx] if idx < len(holder["responses"]) else holder["default"]
        status = resp.get("status", "completed")
        return ModelResponse(
            provider="mock",
            model_name=req.model_name,
            output_text=resp.get("text", ""),
            latency_ms=5,
            status=status,
            input_tokens=10,
            output_tokens=20,
            error_message="boom" if status == "failed" else None,
        )

    app.state.provider_registry.get("mock").complete = fake_complete

    with TestClient(app) as client:
        wid = client.post(
            "/api/runtime/workspaces",
            json={"name": "Run WS", "goal": "Build a small site.", "project_id": "p1"},
        ).json()["workspace_id"]
        agent_id = client.post(
            f"/api/runtime/workspaces/{wid}/agents",
            json={"name": "Builder", "role": "UI Agent"},
        ).json()["agent_id"]
        yield client, wid, tmp_path / "workspaces" / wid, agent_id, holder


def _step(files=None, commands=None, done=False, summary="step", status="completed"):
    return {
        "text": json.dumps(
            {"summary": summary, "done": done, "files": files or [], "commands": commands or []}
        ),
        "status": status,
    }


def _run(client, wid, agent_id, responses, **body):
    """Script the per-step responses, reset counters, and run the loop."""
    holder = body.pop("_holder")
    holder["responses"] = responses
    holder["i"] = 0
    holder["prompts"] = []
    return client.post(
        f"/api/runtime/workspaces/{wid}/agent-run",
        json={"agent_id": agent_id, **body},
    )


def _activity_types(client, wid):
    return [e["event_type"] for e in client.get(f"/api/runtime/workspaces/{wid}/activity").json()]


# --------------------------------------------------------- multi-step happy path


def test_multi_step_build_then_done(env):
    client, wid, root, agent_id, holder = env
    responses = [
        _step(files=[{"path": "index.html", "content": "<!doctype html><h1>Hi</h1>"}]),
        _step(files=[{"path": "styles.css", "content": "h1{color:teal}"}]),
        _step(done=True, summary="complete"),
    ]
    out = _run(client, wid, agent_id, responses, _holder=holder).json()

    assert out["status"] == "completed"
    assert out["stop_reason"] == "done"
    assert out["step_count"] == 3
    assert out["total_written"] == 2
    # both files really landed in the sandbox
    assert (root / "index.html").exists()
    assert (root / "styles.css").exists()
    # the loop lifecycle events are present and replayable
    types = _activity_types(client, wid)
    for expected in (
        "runtime.agent_run.started", "runtime.agent_run.step",
        "model.called", "sandbox.file.created", "runtime.agent_run.completed",
    ):
        assert expected in types
    assert types.count("runtime.agent_run.step") == 3
    # previewable now
    assert client.get(f"/api/runtime/workspaces/{wid}/preview-status").json()["previewable"] is True


def test_feedback_from_previous_step_reaches_next_prompt(env):
    client, wid, root, agent_id, holder = env
    responses = [
        _step(files=[{"path": "index.html", "content": "<h1>store</h1>"}]),
        _step(done=True, summary="done"),
    ]
    _run(client, wid, agent_id, responses, _holder=holder)
    # The first prompt sees an empty sandbox; the second prompt is fed the file
    # tree produced by step 0.
    assert "empty" in holder["prompts"][0].lower()
    assert "index.html" in holder["prompts"][1]
    assert "Current files in the sandbox" in holder["prompts"][1]


def test_stops_at_max_steps(env):
    client, wid, root, agent_id, holder = env
    # Every step is actionable and never says done.
    responses = [
        _step(files=[{"path": f"p{i}.html", "content": f"<h1>{i}</h1>"}]) for i in range(5)
    ]
    out = _run(client, wid, agent_id, responses, _holder=holder, max_steps=2).json()
    assert out["step_count"] == 2
    assert out["stop_reason"] == "max_steps"
    assert out["total_written"] == 2


def test_empty_step_stops_clean(env):
    client, wid, root, agent_id, holder = env
    responses = [
        _step(files=[{"path": "index.html", "content": "<h1>x</h1>"}]),
        _step(),  # valid JSON, no actions, not done
    ]
    out = _run(client, wid, agent_id, responses, _holder=holder).json()
    assert out["stop_reason"] == "no_actions"
    assert out["step_count"] == 2
    assert out["status"] == "completed"  # step 0 did real work


# --------------------------------------------------------- governed commands


def test_governed_command_runs_and_validator_feeds_back(env):
    client, wid, root, agent_id, holder = env
    responses = [
        _step(
            files=[{"path": "index.html", "content": "<h1>ok</h1>"}],
            commands=[{"command": "python3", "args": ["--version"]}],
        ),
        _step(done=True, summary="done"),
    ]
    out = _run(client, wid, agent_id, responses, _holder=holder).json()

    step0 = out["steps"][0]
    assert step0["commands"][0]["status"] == "completed"
    assert step0["commands"][0]["exit_code"] == 0
    assert out["commands_run"] == 1
    # the command really executed through the v1.3 runner under enforcement
    types = _activity_types(client, wid)
    assert "sandbox.command.completed" in types
    assert "action.proposed" in types
    # a command_result validation ran and is fed into the next prompt
    assert any(v["validator"] == "command_result" for v in step0["validations"])
    assert "Command results from your previous step" in holder["prompts"][1]


def test_unsafe_command_blocked_disk_untouched(env):
    client, wid, root, agent_id, holder = env
    responses = [
        _step(
            files=[{"path": "index.html", "content": "<h1>ok</h1>"}],
            commands=[{"command": "rm", "args": ["-rf", "/"]}],
        ),
        _step(done=True, summary="done"),
    ]
    out = _run(client, wid, agent_id, responses, _holder=holder).json()
    step0 = out["steps"][0]
    assert step0["commands"][0]["status"] == "blocked"
    assert out["total_blocked"] == 1
    assert "sandbox.command.blocked" in _activity_types(client, wid)
    # the safe file still landed; nothing destructive ran
    assert (root / "index.html").exists()


# ------------------------------------------------ governance halts the loop


def test_sensitive_file_halts_loop_cleanly(env):
    client, wid, root, agent_id, holder = env
    responses = [
        _step(
            files=[
                {"path": "index.html", "content": "<h1>store</h1>"},
                {"path": "src/payment/checkout.js", "content": "// stripe glue"},
            ]
        ),
        _step(files=[{"path": "more.html", "content": "<h1>more</h1>"}]),  # must NOT run
    ]
    out = _run(client, wid, agent_id, responses, _holder=holder).json()

    assert out["stop_reason"] == "halted_for_approval"
    assert out["step_count"] == 1  # loop stopped after the halting step
    assert out["status"] == "completed"  # index.html was written
    assert out["total_held"] == 1
    # safe file written, sensitive file held (not written), step 2 never ran
    assert (root / "index.html").exists()
    assert not (root / "src" / "payment").exists()
    assert not (root / "more.html").exists()
    # a real approval is waiting (resume is v3.2)
    pending = client.get(
        f"/api/runtime/workspaces/{wid}/approvals", params={"status": "pending"}
    ).json()
    assert len(pending) == 1
    assert pending[0]["target"] == "src/payment/checkout.js"


# ---------------------------------------------------- failure / safety


def test_malformed_first_step_fails(env):
    client, wid, root, agent_id, holder = env
    responses = [{"text": "Sorry, just prose, no JSON here.", "status": "completed"}]
    out = _run(client, wid, agent_id, responses, _holder=holder).json()
    assert out["status"] == "failed"
    assert out["stop_reason"] == "malformed"
    assert out["step_count"] == 1
    assert out["total_written"] == 0
    assert not any(root.iterdir())
    assert "runtime.agent_run.failed" in _activity_types(client, wid)


def test_failed_model_call_fails_clean(env):
    client, wid, root, agent_id, holder = env
    responses = [{"text": "", "status": "failed"}]
    out = _run(client, wid, agent_id, responses, _holder=holder).json()
    assert out["status"] == "failed"
    assert out["stop_reason"] == "model_failed"
    types = _activity_types(client, wid)
    assert "model.failed" in types
    assert "runtime.agent_run.failed" in types


def test_quarantined_agent_cannot_run(env):
    client, wid, root, agent_id, holder = env
    client.post(
        f"/api/runtime/workspaces/{wid}/agents/{agent_id}/quarantine",
        json={"reason": "test", "requested_by": "me"},
    )
    responses = [_step(files=[{"path": "index.html", "content": "<h1>x</h1>"}])]
    response = _run(client, wid, agent_id, responses, _holder=holder)
    assert response.status_code == 409
    assert not (root / "index.html").exists()


def test_no_secrets_or_host_paths_in_run_events(env):
    client, wid, root, agent_id, holder = env
    responses = [
        _step(files=[{"path": "app.js", "content": "const k = 'sk-deadbeef1234567890';"}])
    ]
    _run(client, wid, agent_id, responses, _holder=holder, max_steps=1)
    activity = str(client.get(f"/api/runtime/workspaces/{wid}/activity").json())
    assert "sk-deadbeef1234567890" not in activity
    assert str(root) not in activity


# ----------------------------------------------------------- unit: parse_step


def test_parse_step_files_commands_done():
    from app.runtime import agent_run

    step = agent_run.parse_step(
        json.dumps(
            {
                "summary": "build",
                "done": False,
                "files": [{"path": "index.html", "content": "<h1>hi</h1>"}],
                "commands": [{"command": "ls", "args": ["-la"]}, "pwd"],
            }
        )
    )
    assert step is not None
    assert step.done is False
    assert step.files[0]["path"] == "index.html"
    # dict and bare-string commands both parse
    assert step.commands[0] == {"command": "ls", "args": ["-la"]}
    assert step.commands[1] == {"command": "pwd", "args": []}


def test_parse_step_done_empty():
    from app.runtime import agent_run

    step = agent_run.parse_step(json.dumps({"summary": "done", "done": True}))
    assert step is not None and step.done is True
    assert step.files == [] and step.commands == []


def test_parse_step_salvages_html():
    from app.runtime import agent_run

    step = agent_run.parse_step("<!doctype html><html><body><h1>Hi</h1></body></html>")
    assert step is not None
    assert step.done is True
    assert step.files[0]["path"] == "index.html"


def test_parse_step_returns_none_for_prose():
    from app.runtime import agent_run

    assert agent_run.parse_step("Sorry, I cannot help with that.") is None


def test_clamp_steps():
    from app.runtime import agent_run

    assert agent_run.clamp_steps(None) == agent_run.DEFAULT_MAX_STEPS
    assert agent_run.clamp_steps(0) == agent_run.DEFAULT_MAX_STEPS
    assert agent_run.clamp_steps(3) == 3
    assert agent_run.clamp_steps(99) == agent_run.HARD_MAX_STEPS


def test_run_requires_api_key_when_configured(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/run-auth.db",
        api_keys="k1",
        cors_origins="",
        workspaces_root=str(tmp_path / "ws"),
    )
    app = create_app(settings)

    async def fake_complete(req):
        return ModelResponse(
            provider="mock", model_name=req.model_name,
            output_text=_step(done=True)["text"], latency_ms=1, status="completed",
        )

    app.state.provider_registry.get("mock").complete = fake_complete
    with TestClient(app) as client:
        h = {"X-API-Key": "k1"}
        wid = client.post(
            "/api/runtime/workspaces", json={"name": "W", "goal": "g"}, headers=h
        ).json()["workspace_id"]
        agent_id = client.post(
            f"/api/runtime/workspaces/{wid}/agents", json={"name": "B", "role": "UI"}, headers=h
        ).json()["agent_id"]
        assert client.post(
            f"/api/runtime/workspaces/{wid}/agent-run", json={"agent_id": agent_id}
        ).status_code == 401
        assert client.post(
            f"/api/runtime/workspaces/{wid}/agent-run", json={"agent_id": agent_id}, headers=h
        ).status_code == 200
