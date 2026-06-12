"""Safe Command Runner (v1.3): allowlisted workspace-bounded execution,
deterministic pre-execution blocking (with marker-file proof that blocked
commands never run), timeout/output-cap/redaction behavior, and
sandbox.command.* events flowing through activity/timeline/replay."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.runtime import commands


@pytest.fixture
def sandbox_env(tmp_path):
    """Isolated app with sandboxes under tmp_path, one initialized workspace."""
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/cmd.db",
        api_keys="",
        cors_origins="",
        workspaces_root=str(tmp_path / "workspaces"),
    )
    with TestClient(create_app(settings)) as client:
        created = client.post(
            "/api/runtime/workspaces",
            json={"name": "Command WS", "project_id": "proj-1"},
        )
        wid = created.json()["workspace_id"]
        assert client.post(f"/api/runtime/workspaces/{wid}/sandbox/init").status_code == 200
        yield client, wid, tmp_path / "workspaces" / wid


def _run(client, wid, command, args=None, **kwargs):
    return client.post(
        f"/api/runtime/workspaces/{wid}/commands/run",
        json={"command": command, "args": args or [], **kwargs},
    )


def _command_events(client, wid) -> list[dict]:
    return client.get(f"/api/runtime/workspaces/{wid}/commands/history").json()


# ------------------------------------------------------------- allowed paths


def test_allowed_command_completes_with_output(sandbox_env):
    client, wid, root = sandbox_env
    (root / "hello.txt").write_text("hi")
    response = _run(client, wid, "ls")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "completed"
    assert result["exit_code"] == 0
    assert "hello.txt" in result["stdout"]
    assert result["cwd"] == "."
    assert result["duration_ms"] >= 0


def test_cat_reads_safe_workspace_file(sandbox_env):
    client, wid, root = sandbox_env
    (root / "notes.md").write_text("# sandbox notes")
    result = _run(client, wid, "cat", ["notes.md"]).json()
    assert result["status"] == "completed"
    assert "# sandbox notes" in result["stdout"]


def test_working_subdir_is_honored(sandbox_env):
    client, wid, root = sandbox_env
    (root / "src").mkdir()
    (root / "src" / "inner.txt").write_text("x")
    result = _run(client, wid, "ls", working_subdir="src").json()
    assert result["cwd"] == "src"
    assert "inner.txt" in result["stdout"]
    missing = _run(client, wid, "ls", working_subdir="nope")
    assert missing.status_code == 404


def test_version_commands_allowed(sandbox_env):
    client, wid, _ = sandbox_env
    result = _run(client, wid, "python3", ["--version"]).json()
    assert result["status"] == "completed"
    assert "Python" in result["stdout"] + result["stderr"]


def test_failed_command_reports_exit_code(sandbox_env):
    client, wid, _ = sandbox_env
    # ls of a valid-but-nonexistent relative path → ls exits non-zero
    result = _run(client, wid, "ls", ["does-not-exist"]).json()
    assert result["status"] == "failed"
    assert result["exit_code"] not in (0, None)
    types = [e["event_type"] for e in _command_events(client, wid)]
    assert types[0] == "sandbox.command.failed"


def test_allowed_lifecycle_events_in_order(sandbox_env):
    client, wid, _ = sandbox_env
    _run(client, wid, "pwd")
    types = [e["event_type"] for e in _command_events(client, wid)]  # newest first
    assert types == [
        "sandbox.command.completed",
        "sandbox.command.started",
        "sandbox.command.allowed",
        "sandbox.command.proposed",
    ]
    completed = _command_events(client, wid)[0]
    assert completed["payload"]["exit_code"] == 0
    assert completed["payload"]["cwd"] == "."
    assert completed["metadata"]["source"] == "runtime"


def test_allowed_commands_endpoint(sandbox_env):
    client, wid, _ = sandbox_env
    listed = client.get(f"/api/runtime/workspaces/{wid}/commands/allowed").json()
    names = {c["command"] for c in listed}
    assert {"pwd", "ls", "cat", "node", "npm", "python", "python3"} == names
    assert all(c["description"] and c["examples"] for c in listed)


def test_requires_initialized_sandbox(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/cmd2.db", api_keys="", cors_origins="",
        workspaces_root=str(tmp_path / "ws"),
    )
    with TestClient(create_app(settings)) as client:
        wid = client.post(
            "/api/runtime/workspaces", json={"name": "W", "project_id": "p"}
        ).json()["workspace_id"]
        assert _run(client, wid, "pwd").status_code == 409


# ------------------------------------------------------------ blocked paths


def _assert_blocked(client, wid, root, command, args, expected_rule):
    before = sorted(p.name for p in root.rglob("*"))
    response = _run(client, wid, command, args)
    assert response.status_code == 400, response.text
    assert response.json()["detail"].startswith(f"blocked ({expected_rule})")
    # nothing executed: sandbox contents are unchanged
    assert sorted(p.name for p in root.rglob("*")) == before
    events = _command_events(client, wid)
    assert events[0]["event_type"] == "sandbox.command.blocked"
    assert events[0]["payload"]["rule"] == expected_rule
    assert events[1]["event_type"] == "sandbox.command.proposed"


@pytest.mark.parametrize(
    "command,args,rule",
    [
        ("touch", ["MARKER"], "unknown_command"),
        ("rm", ["-rf", "."], "dangerous_command"),
        ("bash", ["-c", "touch MARKER"], "dangerous_command"),
        ("sh", ["-c", "touch MARKER"], "dangerous_command"),
        ("curl", ["http://evil.example"], "dangerous_command"),
        ("ssh", ["host"], "dangerous_command"),
        ("git", ["push"], "dangerous_command"),
        ("docker", ["run", "img"], "dangerous_command"),
        ("pip", ["install", "requests"], "dangerous_command"),
        ("python3", ["-c", "open('MARKER','w')"], "inline_code"),
        ("node", ["-e", "require('fs').writeFileSync('MARKER','')"], "inline_code"),
        ("npm", ["install", "left-pad"], "package_install"),
        ("ls", ["; touch MARKER"], "shell_metacharacter"),
        ("ls", ["&&", "touch", "MARKER"], "shell_metacharacter"),
        ("ls", ["|", "tee", "MARKER"], "shell_metacharacter"),
        ("ls", [">", "MARKER"], "shell_metacharacter"),
        ("ls", ["$(touch MARKER)"], "shell_metacharacter"),
        ("ls", ["`touch MARKER`"], "shell_metacharacter"),
        ("/bin/ls", [], "program_path"),
        ("./script.sh", [], "program_path"),
        ("pwd", ["extra"], "disallowed_args"),
        ("npm", ["run", "evil-script"], "disallowed_args"),
    ],
)
def test_blocked_commands_never_execute(sandbox_env, command, args, rule):
    client, wid, root = sandbox_env
    _assert_blocked(client, wid, root, command, args, rule)
    # the canonical marker-file proof: no payload ever landed
    assert not (root / "MARKER").exists()


def test_path_escapes_in_args_and_cwd_blocked(sandbox_env):
    client, wid, root = sandbox_env
    _assert_blocked(client, wid, root, "ls", ["../.."], "traversal")
    _assert_blocked(client, wid, root, "cat", ["/etc/passwd"], "absolute_path")
    _assert_blocked(client, wid, root, "cat", [".env"], "secret_file")
    blocked_cwd = _run(client, wid, "pwd", working_subdir="../..")
    assert blocked_cwd.status_code == 400
    assert "traversal" in blocked_cwd.json()["detail"]


def test_npm_test_requires_manifest(sandbox_env):
    client, wid, root = sandbox_env
    _assert_blocked(client, wid, root, "npm", ["test"], "missing_manifest")


def test_blocked_event_is_safe(sandbox_env):
    client, wid, root = sandbox_env
    _run(client, wid, "cat", ["/etc/passwd"])
    blocked = _command_events(client, wid)[0]
    assert str(root) not in str(blocked)  # no host paths in the audit event
    assert blocked["payload"]["reason"]


# ---------------------------------------------- timeout / caps / redaction


def _allow_test_command(monkeypatch, validator=lambda args, root: None):
    """Tests for runner *machinery* (timeout/caps/redaction/env) need commands
    the production allowlist deliberately refuses — patch one in."""
    monkeypatch.setitem(
        commands.ALLOWED_COMMANDS,
        "python3",
        commands.CommandSpec("test-only permissive python3", ["python3"], validator),
    )


def test_timeout_emits_timed_out(sandbox_env, monkeypatch):
    client, wid, _ = sandbox_env
    _allow_test_command(monkeypatch)
    # no ';' — the metacharacter guard scans args before the spec validator
    result = _run(
        client, wid, "python3", ["-c", "__import__('time').sleep(5)"], timeout_seconds=1
    ).json()
    assert result["status"] == "timed_out"
    assert result["exit_code"] is None
    assert "timeout" in result["stderr"]
    types = [e["event_type"] for e in _command_events(client, wid)]
    assert types[0] == "sandbox.command.timed_out"


def test_output_caps_and_truncation_flag(sandbox_env, monkeypatch):
    client, wid, _ = sandbox_env
    _allow_test_command(monkeypatch)
    result = _run(
        client, wid, "python3", ["-c", "print('x' * 50000)"]
    ).json()
    assert result["status"] == "completed"
    assert len(result["stdout"]) <= commands.MAX_OUTPUT_CHARS
    assert result["stdout_truncated"] is True
    completed = _command_events(client, wid)[0]
    assert len(completed["payload"]["stdout_summary"]) <= commands.EVENT_OUTPUT_CHARS
    assert completed["payload"]["output_truncated"] is True


def test_secret_like_output_is_redacted(sandbox_env, monkeypatch):
    client, wid, _ = sandbox_env
    _allow_test_command(monkeypatch)
    # The secret is constructed at runtime: a literal token in the *input*
    # would be blocked by the v1.5 enforcement gateway before execution.
    result = _run(
        client, wid, "python3", ["-c", "print('key: sk-' + 'abcdef1234567890XYZ')"]
    ).json()
    assert "sk-abcdef1234567890XYZ" not in result["stdout"]
    assert "[redacted]" in result["stdout"]
    assert "sk-abcdef1234567890XYZ" not in str(_command_events(client, wid)[0])


def test_host_environment_is_scrubbed(sandbox_env, monkeypatch):
    client, wid, _ = sandbox_env
    _allow_test_command(monkeypatch)
    monkeypatch.setenv("AGENTLAB_TEST_SECRET", "super-secret-value")
    result = _run(
        client,
        wid,
        "python3",
        ["-c", "print(__import__('os').environ.get('AGENTLAB_TEST_SECRET', 'SCRUBBED'))"],
    ).json()
    assert result["status"] == "completed"
    assert "super-secret-value" not in result["stdout"]
    assert "SCRUBBED" in result["stdout"]


# ------------------------------------------------- pipeline / auth / replay


def test_command_events_flow_into_timeline_and_replay(sandbox_env):
    client, wid, _ = sandbox_env
    workspace = client.get(f"/api/runtime/workspaces/{wid}").json()
    run_id = workspace["activity_run_id"]
    _run(client, wid, "pwd")
    _run(client, wid, "rm", ["-rf", "/"])  # blocked

    timeline = [e["event_type"] for e in client.get(f"/api/runs/{run_id}/events").json()]
    assert timeline == [
        "workspace.created",
        "sandbox.initialized",
        # allowed pwd: enforcement decides, then the v1.3 runner executes
        "action.proposed",
        "policy.rule.matched",
        "policy.evaluated",
        "enforcement.allowed",
        "action.started",
        "sandbox.command.proposed",
        "sandbox.command.allowed",
        "sandbox.command.started",
        "sandbox.command.completed",
        "action.completed",
        # blocked rm: enforcement refuses pre-execution; legacy audit parity
        "action.proposed",
        "policy.rule.matched",
        "policy.evaluated",
        "enforcement.blocked",
        "sandbox.command.proposed",
        "sandbox.command.blocked",
    ]
    replay = client.get(f"/api/runs/{run_id}/replay").json()
    assert [e["event_type"] for e in replay["events"]] == timeline
    for path in ("graph", "metrics", "scores"):
        assert client.get(f"/api/runs/{run_id}/{path}").status_code == 200, path


def test_history_endpoint_filters_command_events(sandbox_env):
    client, wid, _ = sandbox_env
    client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "a.txt", "content": "x"},
    )
    _run(client, wid, "pwd")
    history = _command_events(client, wid)
    assert all(e["event_type"].startswith("sandbox.command.") for e in history)
    assert len(history) == 4  # proposed/allowed/started/completed only


def test_run_requires_api_key_when_configured(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/cmd-auth.db",
        api_keys="k1",
        cors_origins="",
        workspaces_root=str(tmp_path / "ws"),
    )
    with TestClient(create_app(settings)) as client:
        wid = client.post(
            "/api/runtime/workspaces", json={"name": "W"}, headers={"X-API-Key": "k1"}
        ).json()["workspace_id"]
        client.post(
            f"/api/runtime/workspaces/{wid}/sandbox/init", headers={"X-API-Key": "k1"}
        )
        body = {"command": "pwd", "args": []}
        assert (
            client.post(
                f"/api/runtime/workspaces/{wid}/commands/run", json=body
            ).status_code
            == 401
        )
        assert (
            client.post(
                f"/api/runtime/workspaces/{wid}/commands/run",
                json=body,
                headers={"X-API-Key": "k1"},
            ).status_code
            == 200
        )
        # reads stay open in local mode
        assert (
            client.get(f"/api/runtime/workspaces/{wid}/commands/history").status_code
            == 200
        )
        assert (
            client.get(f"/api/runtime/workspaces/{wid}/commands/allowed").status_code
            == 200
        )
