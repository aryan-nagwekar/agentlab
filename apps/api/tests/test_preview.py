"""Website Preview (v2.1): a safe, read-only static serve of files already
inside a workspace sandbox. Path safety (traversal/outside-root/secret) and
the static-extension allowlist are enforced before any disk access; no host
path ever leaks; the preview never writes, runs, installs, or deploys."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def env(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/prev.db",
        api_keys="",
        cors_origins="",
        workspaces_root=str(tmp_path / "workspaces"),
    )
    with TestClient(create_app(settings)) as client:
        wid = client.post(
            "/api/runtime/workspaces",
            json={"name": "Preview WS", "goal": "Preview test.", "project_id": "p1"},
        ).json()["workspace_id"]
        client.post(f"/api/runtime/workspaces/{wid}/sandbox/init")
        yield client, wid, tmp_path / "workspaces" / wid


def _write(client, wid, path, content):
    return client.post(
        f"/api/runtime/workspaces/{wid}/files/write", json={"path": path, "content": content}
    )


def test_preview_status_false_then_true(env):
    client, wid, _ = env
    assert client.get(
        f"/api/runtime/workspaces/{wid}/preview-status"
    ).json()["previewable"] is False
    _write(client, wid, "index.html", "<h1>Bottles</h1>")
    status = client.get(f"/api/runtime/workspaces/{wid}/preview-status").json()
    assert status == {"workspace_id": wid, "previewable": True}


def test_serves_index_and_assets_with_content_types(env):
    client, wid, _ = env
    _write(client, wid, "index.html", "<!doctype html><h1>Tidewater Bottles</h1>")
    _write(client, wid, "styles.css", "body{margin:0}")
    _write(client, wid, "app.js", "console.log('cart')")
    _write(client, wid, "products.json", '[{"name":"Bottle"}]')

    index = client.get(f"/api/runtime/workspaces/{wid}/preview")
    assert index.status_code == 200
    assert index.headers["content-type"].startswith("text/html")
    assert "Tidewater Bottles" in index.text
    assert index.headers["x-frame-options"] == "SAMEORIGIN"

    for path, ctype in [
        ("styles.css", "text/css"),
        ("app.js", "text/javascript"),
        ("products.json", "application/json"),
    ]:
        resp = client.get(f"/api/runtime/workspaces/{wid}/preview/{path}")
        assert resp.status_code == 200, path
        assert resp.headers["content-type"].startswith(ctype), path


def test_nested_asset_served(env):
    client, wid, _ = env
    _write(client, wid, "index.html", "<h1>x</h1>")
    _write(client, wid, "assets/logo.svg", "<svg/>")
    resp = client.get(f"/api/runtime/workspaces/{wid}/preview/assets/logo.svg")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/svg")


def test_missing_file_404(env):
    client, wid, _ = env
    _write(client, wid, "index.html", "<h1>x</h1>")
    assert client.get(
        f"/api/runtime/workspaces/{wid}/preview/missing.html"
    ).status_code == 404


def test_disallowed_extension_415(env):
    client, wid, _ = env
    _write(client, wid, "README.md", "# notes")
    resp = client.get(f"/api/runtime/workspaces/{wid}/preview/README.md")
    assert resp.status_code == 415


# ------------------------------------------------------------- safety


def test_secret_file_blocked(env):
    client, wid, root = env
    (root / ".env").write_text("API_KEY=sk-shouldNotPreview1234567890")
    resp = client.get(f"/api/runtime/workspaces/{wid}/preview/.env")
    assert resp.status_code == 400
    assert resp.json()["detail"].startswith("blocked (secret_file)")
    assert "sk-shouldNotPreview" not in resp.text


def test_absolute_path_blocked(env):
    client, wid, _ = env
    resp = client.get(f"/api/runtime/workspaces/{wid}/preview//etc/passwd")
    assert resp.status_code in (400, 404)
    assert "root:" not in resp.text


def test_outside_root_symlink_blocked(env):
    client, wid, root = env
    import os

    outside = root.parent / "outside-secret.html"
    outside.write_text("<h1>OUTSIDE</h1>")
    os.symlink(outside, root / "sneaky.html")
    resp = client.get(f"/api/runtime/workspaces/{wid}/preview/sneaky.html")
    assert resp.status_code == 400
    assert resp.json()["detail"].startswith("blocked (outside_root)")
    assert "OUTSIDE" not in resp.text


def test_no_host_path_leaks_in_preview(env):
    client, wid, root = env
    _write(client, wid, "index.html", "<h1>x</h1>")
    # a 404 / error path must not echo the host filesystem location
    not_found = client.get(f"/api/runtime/workspaces/{wid}/preview/nope.html")
    blocked = client.get(f"/api/runtime/workspaces/{wid}/preview/.env")
    assert str(root) not in not_found.text
    assert str(root) not in blocked.text


def test_uninitialized_sandbox_not_previewable(env, tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/prev2.db",
        api_keys="",
        cors_origins="",
        workspaces_root=str(tmp_path / "ws2"),
    )
    with TestClient(create_app(settings)) as client:
        wid = client.post(
            "/api/runtime/workspaces", json={"name": "No sandbox"}
        ).json()["workspace_id"]
        assert client.get(
            f"/api/runtime/workspaces/{wid}/preview-status"
        ).json()["previewable"] is False
        assert client.get(f"/api/runtime/workspaces/{wid}/preview").status_code == 404


def test_preview_is_read_only_get(env):
    client, wid, _ = env
    _write(client, wid, "index.html", "<h1>x</h1>")
    # the preview route family is GET-only — writes are not exposed here
    assert client.post(f"/api/runtime/workspaces/{wid}/preview").status_code == 405
    assert client.delete(f"/api/runtime/workspaces/{wid}/preview/index.html").status_code == 405


def test_demo_workspace_is_previewable(env):
    client, _, _ = env
    demo = client.post("/api/runtime/demo/bottle-shop").json()
    wid = demo["workspace_id"]
    assert client.get(
        f"/api/runtime/workspaces/{wid}/preview-status"
    ).json()["previewable"] is True
    index = client.get(f"/api/runtime/workspaces/{wid}/preview")
    assert index.status_code == 200
    assert "Tidewater" in index.text or "bottle" in index.text.lower()
