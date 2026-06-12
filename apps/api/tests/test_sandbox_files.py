"""Sandboxed File Runtime (v1.2): workspace-bounded file CRUD, deterministic
path safety (absolute/traversal/outside-root/symlink/secret blocked, with
proof that blocked operations never touch disk), and sandbox.* events flowing
through the normal event/timeline/replay systems."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def sandbox_env(tmp_path):
    """Isolated app whose sandboxes live under tmp_path, plus one workspace."""
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/sbx.db",
        api_keys="",
        cors_origins="",
        workspaces_root=str(tmp_path / "workspaces"),
    )
    with TestClient(create_app(settings)) as client:
        created = client.post(
            "/api/runtime/workspaces",
            json={"name": "Sandbox WS", "project_id": "proj-1"},
        )
        assert created.status_code == 201
        yield client, created.json()["workspace_id"], tmp_path / "workspaces"


def _init(client, wid):
    response = client.post(f"/api/runtime/workspaces/{wid}/sandbox/init")
    assert response.status_code == 200, response.text
    return response.json()


def _activity_types(client, wid) -> list[str]:
    return [
        e["event_type"]
        for e in client.get(f"/api/runtime/workspaces/{wid}/activity").json()
    ]


# ------------------------------------------------------------------ lifecycle


def test_init_creates_bounded_directory_and_event(sandbox_env):
    client, wid, root = sandbox_env
    status = _init(client, wid)
    assert status == {
        "workspace_id": wid,
        "initialized": True,
        "file_count": 0,
        "directory_count": 0,
        "total_bytes": 0,
    }
    assert (root / wid).is_dir()
    assert "sandbox.initialized" in _activity_types(client, wid)
    # re-init is idempotent: no second event
    _init(client, wid)
    assert _activity_types(client, wid).count("sandbox.initialized") == 1


def test_status_before_init(sandbox_env):
    client, wid, _ = sandbox_env
    status = client.get(f"/api/runtime/workspaces/{wid}/sandbox/status").json()
    assert status["initialized"] is False


def test_operations_require_initialized_sandbox(sandbox_env):
    client, wid, _ = sandbox_env
    response = client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "a.txt", "content": "x"},
    )
    assert response.status_code == 409
    assert "not initialized" in response.json()["detail"]


# ----------------------------------------------------------------- file CRUD


def test_write_read_update_delete_roundtrip(sandbox_env):
    client, wid, root = sandbox_env
    _init(client, wid)

    created = client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "src/index.html", "content": "<h1>hello</h1>"},
    )
    assert created.status_code == 200, created.text
    assert created.json()["created"] is True
    assert (root / wid / "src" / "index.html").read_text() == "<h1>hello</h1>"

    read = client.get(
        f"/api/runtime/workspaces/{wid}/files/read", params={"path": "src/index.html"}
    ).json()
    assert read["content"] == "<h1>hello</h1>"
    assert read["path"] == "src/index.html"
    assert len(read["sha256"]) == 16

    updated = client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "src/index.html", "content": "<h1>v2</h1>"},
    ).json()
    assert updated["created"] is False

    deleted = client.delete(
        f"/api/runtime/workspaces/{wid}/files", params={"path": "src/index.html"}
    ).json()
    assert deleted == {"path": "src/index.html", "kind": "file"}
    assert not (root / wid / "src" / "index.html").exists()


def test_list_and_tree(sandbox_env):
    client, wid, _ = sandbox_env
    _init(client, wid)
    client.post(
        f"/api/runtime/workspaces/{wid}/files/mkdir", json={"path": "site"}
    )
    client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "site/a.css", "content": "body{}"},
    )
    client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "README.md", "content": "# hi"},
    )

    top = client.get(f"/api/runtime/workspaces/{wid}/files").json()
    assert [(e["name"], e["type"]) for e in top] == [
        ("site", "directory"),
        ("README.md", "file"),
    ]
    nested = client.get(
        f"/api/runtime/workspaces/{wid}/files", params={"path": "site"}
    ).json()
    assert [e["path"] for e in nested] == ["site/a.css"]

    tree = client.get(f"/api/runtime/workspaces/{wid}/files/tree").json()
    site = next(n for n in tree if n["name"] == "site")
    assert [c["name"] for c in site["children"]] == ["a.css"]


def test_mkdir_and_empty_dir_delete(sandbox_env):
    client, wid, root = sandbox_env
    _init(client, wid)
    made = client.post(
        f"/api/runtime/workspaces/{wid}/files/mkdir", json={"path": "docs/img"}
    ).json()
    assert made == {"path": "docs/img", "created": True}
    assert (root / wid / "docs" / "img").is_dir()

    client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "docs/img/x.svg", "content": "<svg/>"},
    )
    not_empty = client.delete(
        f"/api/runtime/workspaces/{wid}/files", params={"path": "docs/img"}
    )
    assert not_empty.status_code == 400
    assert "not empty" in not_empty.json()["detail"]

    client.delete(f"/api/runtime/workspaces/{wid}/files", params={"path": "docs/img/x.svg"})
    emptied = client.delete(
        f"/api/runtime/workspaces/{wid}/files", params={"path": "docs/img"}
    ).json()
    assert emptied["kind"] == "directory"


def test_read_missing_file_404_and_binary_rejected(sandbox_env):
    client, wid, root = sandbox_env
    _init(client, wid)
    assert (
        client.get(
            f"/api/runtime/workspaces/{wid}/files/read", params={"path": "nope.txt"}
        ).status_code
        == 404
    )
    (root / wid / "blob.bin").write_bytes(b"\x00\xff\xfe\x01")
    binary = client.get(
        f"/api/runtime/workspaces/{wid}/files/read", params={"path": "blob.bin"}
    )
    assert binary.status_code == 400
    assert "binary" in binary.json()["detail"]


# -------------------------------------------------------------- path safety


@pytest.mark.parametrize(
    "path,rule",
    [
        ("/etc/passwd", "absolute_path"),
        ("~/secrets.txt", "absolute_path"),
        ("../outside.txt", "traversal"),
        ("a/../../outside.txt", "traversal"),
        (".env", "secret_file"),
        (".env.production", "secret_file"),
        ("keys/server.pem", "secret_file"),
        ("id_rsa", "secret_file"),
    ],
)
def test_unsafe_write_blocked_and_disk_untouched(sandbox_env, path, rule):
    client, wid, root = sandbox_env
    _init(client, wid)
    before = sorted(p.relative_to(root) for p in root.rglob("*"))

    response = client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": path, "content": "MUST NOT LAND"},
    )
    assert response.status_code == 400
    assert response.json()["detail"].startswith(f"blocked ({rule})")

    # nothing was created anywhere under the sandbox root
    after = sorted(p.relative_to(root) for p in root.rglob("*"))
    assert after == before
    # and the attempted escape target does not exist
    assert not (root / "outside.txt").exists()

    blocked = [
        e
        for e in client.get(f"/api/runtime/workspaces/{wid}/activity").json()
        if e["event_type"] == "sandbox.file.blocked"
    ]
    assert blocked, "blocked operation must emit an audit event"
    payload = blocked[0]["payload"]
    assert payload["rule"] == rule
    assert payload["operation"] == "write"
    # the event never carries host paths or the attempted content
    assert str(root) not in str(blocked[0])
    assert "MUST NOT LAND" not in str(blocked[0])


def test_unsafe_read_and_delete_blocked(sandbox_env):
    client, wid, root = sandbox_env
    _init(client, wid)
    secret_outside = root.parent / "host-secret.txt"
    secret_outside.write_text("HOST SECRET")

    read = client.get(
        f"/api/runtime/workspaces/{wid}/files/read",
        params={"path": "../../host-secret.txt"},
    )
    assert read.status_code == 400
    assert "HOST SECRET" not in read.text

    delete = client.delete(
        f"/api/runtime/workspaces/{wid}/files", params={"path": "/etc/hosts"}
    )
    assert delete.status_code == 400
    assert secret_outside.exists()  # untouched


def test_symlink_escape_blocked(sandbox_env):
    client, wid, root = sandbox_env
    _init(client, wid)
    outside = root.parent / "outside-target.txt"
    outside.write_text("OUTSIDE")
    os.symlink(outside, root / wid / "sneaky.txt")

    read = client.get(
        f"/api/runtime/workspaces/{wid}/files/read", params={"path": "sneaky.txt"}
    )
    assert read.status_code == 400
    assert read.json()["detail"].startswith("blocked (outside_root)")
    assert "OUTSIDE" not in read.text

    write = client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "sneaky.txt", "content": "overwritten"},
    )
    assert write.status_code == 400
    assert outside.read_text() == "OUTSIDE"  # target untouched


def test_secret_file_dropped_on_disk_is_still_unreadable(sandbox_env):
    client, wid, root = sandbox_env
    _init(client, wid)
    # even if a secret-named file exists inside the sandbox, the API refuses it
    (root / wid / ".env").write_text("API_KEY=sk-super-secret")
    read = client.get(
        f"/api/runtime/workspaces/{wid}/files/read", params={"path": ".env"}
    )
    assert read.status_code == 400
    assert read.json()["detail"].startswith("blocked (secret_file)")
    assert "sk-super-secret" not in read.text


# --------------------------------------------------------------------- events


def test_successful_operations_emit_events_in_order(sandbox_env):
    client, wid, _ = sandbox_env
    _init(client, wid)
    client.post(f"/api/runtime/workspaces/{wid}/files/mkdir", json={"path": "src"})
    client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "src/app.py", "content": "print('hi')"},
    )
    client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "src/app.py", "content": "print('v2')"},
    )
    client.get(
        f"/api/runtime/workspaces/{wid}/files/read", params={"path": "src/app.py"}
    )
    client.delete(f"/api/runtime/workspaces/{wid}/files", params={"path": "src/app.py"})

    # v1.5: mutations are wrapped by the enforcement gateway, so each one is
    # bracketed by action/policy/enforcement events; reads are not wrapped.
    _ENFORCED = [
        "action.completed",
        "{legacy}",
        "action.started",
        "enforcement.allowed",
        "policy.evaluated",
        "policy.rule.matched",
        "action.proposed",
    ]

    def enforced(legacy: str) -> list[str]:
        return [t.format(legacy=legacy) for t in _ENFORCED]

    types = _activity_types(client, wid)  # newest first
    assert types == [
        *enforced("sandbox.file.deleted"),
        "sandbox.file.read",
        *enforced("sandbox.file.updated"),
        *enforced("sandbox.file.created"),
        *enforced("sandbox.directory.created"),
        "sandbox.initialized",
        "workspace.created",
    ]
    activity = client.get(f"/api/runtime/workspaces/{wid}/activity").json()
    created = next(e for e in activity if e["event_type"] == "sandbox.file.created")
    assert created["payload"]["path"] == "src/app.py"
    assert created["payload"]["size_bytes"] == len("print('hi')")
    assert "content" not in created["payload"]
    assert created["metadata"]["source"] == "runtime"


def test_sandbox_events_flow_into_timeline_and_replay(sandbox_env):
    client, wid, _ = sandbox_env
    workspace = client.get(f"/api/runtime/workspaces/{wid}").json()
    run_id = workspace["activity_run_id"]
    _init(client, wid)
    client.post(
        f"/api/runtime/workspaces/{wid}/files/write",
        json={"path": "notes.md", "content": "# notes"},
    )

    timeline = [e["event_type"] for e in client.get(f"/api/runs/{run_id}/events").json()]
    assert timeline == [
        "workspace.created",
        "sandbox.initialized",
        # v1.5 enforcement gateway wraps the write
        "action.proposed",
        "policy.rule.matched",
        "policy.evaluated",
        "enforcement.allowed",
        "action.started",
        "sandbox.file.created",
        "action.completed",
    ]
    replay = client.get(f"/api/runs/{run_id}/replay").json()
    assert [e["event_type"] for e in replay["events"]] == timeline
    for path in ("graph", "metrics", "scores"):
        assert client.get(f"/api/runs/{run_id}/{path}").status_code == 200, path


def test_writes_require_api_key_when_configured(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/sbx-auth.db",
        api_keys="k1",
        cors_origins="",
        workspaces_root=str(tmp_path / "workspaces"),
    )
    with TestClient(create_app(settings)) as client:
        wid = client.post(
            "/api/runtime/workspaces", json={"name": "W"}, headers={"X-API-Key": "k1"}
        ).json()["workspace_id"]
        assert client.post(f"/api/runtime/workspaces/{wid}/sandbox/init").status_code == 401
        assert (
            client.post(
                f"/api/runtime/workspaces/{wid}/sandbox/init", headers={"X-API-Key": "k1"}
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/runtime/workspaces/{wid}/files/write",
                json={"path": "a.txt", "content": "x"},
            ).status_code
            == 401
        )
        assert (
            client.delete(
                f"/api/runtime/workspaces/{wid}/files", params={"path": "a.txt"}
            ).status_code
            == 401
        )
        # reads stay open in local mode
        assert (
            client.get(f"/api/runtime/workspaces/{wid}/sandbox/status").status_code == 200
        )
        assert client.get(f"/api/runtime/workspaces/{wid}/files").status_code == 200
