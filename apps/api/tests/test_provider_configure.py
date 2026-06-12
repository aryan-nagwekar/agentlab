"""Secure provider configuration (v0.9.1): secrets live only in the local
gitignored file, never in the DB, responses, events, or errors."""
from __future__ import annotations

import json
import os
import stat

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

FAKE_GEMINI = "AIzaSyFAKE-configure-flow-key-7890"


def _settings(tmp_path, **overrides) -> Settings:
    kwargs = {
        "database_url": f"sqlite:///{tmp_path}/cfg.db",
        "api_keys": "",
        "cors_origins": "",
        "secrets_file": str(tmp_path / "secrets.json"),
        **overrides,
    }
    return Settings(**kwargs)


def test_configure_stores_secret_in_local_file_only(tmp_path):
    settings = _settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/model-gateway/providers/gemini/configure", json={"api_key": FAKE_GEMINI}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "available"
        assert body["configured"] is True
        assert body["key_redacted"] == "AIz...7890"
        assert FAKE_GEMINI not in response.text  # never echoed

        # The secret lives in the gitignored file with owner-only permissions…
        secrets_path = tmp_path / "secrets.json"
        assert json.loads(secrets_path.read_text())["gemini"]["api_key"] == FAKE_GEMINI
        mode = stat.S_IMODE(os.stat(secrets_path).st_mode)
        assert mode == 0o600

        # …and never in the database.
        import sqlite3

        connection = sqlite3.connect(tmp_path / "cfg.db")
        for (table,) in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall():
            rows = connection.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608
            assert FAKE_GEMINI not in str(rows), table
        connection.close()


def test_configure_refreshes_provider_list_with_redaction(tmp_path):
    settings = _settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        before = {p["name"]: p for p in client.get("/api/model-gateway/providers").json()["providers"]}
        assert before["gemini"]["status"] == "not_configured"
        client.post("/api/model-gateway/providers/gemini/configure", json={"api_key": FAKE_GEMINI})
        raw = client.get("/api/model-gateway/providers").text
        assert FAKE_GEMINI not in raw
        after = {p["name"]: p for p in client.get("/api/model-gateway/providers").json()["providers"]}
        assert after["gemini"]["status"] == "available"
        assert after["gemini"]["key_redacted"] == "AIz...7890"


def test_clear_removes_secret_and_reverts_status(tmp_path):
    settings = _settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        client.post("/api/model-gateway/providers/gemini/configure", json={"api_key": FAKE_GEMINI})
        cleared = client.post("/api/model-gateway/providers/gemini/clear")
        assert cleared.status_code == 200
        assert cleared.json()["status"] == "not_configured"
        assert "gemini" not in json.loads((tmp_path / "secrets.json").read_text())


def test_file_secret_overrides_env_and_clear_falls_back(tmp_path):
    settings = _settings(tmp_path, gemini_api_key="AIzaENVfallback-key-1111")
    with TestClient(create_app(settings)) as client:
        client.post("/api/model-gateway/providers/gemini/configure", json={"api_key": FAKE_GEMINI})
        configured = client.get("/api/model-gateway/providers/gemini/health").json()
        assert configured["key_redacted"] == "AIz...7890"  # file wins
        client.post("/api/model-gateway/providers/gemini/clear")
        fallback = client.get("/api/model-gateway/providers/gemini/health").json()
        assert fallback["key_redacted"] == "AIz...1111"  # env still applies


def test_ollama_accepts_base_url_only(tmp_path):
    settings = _settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        rejected = client.post(
            "/api/model-gateway/providers/ollama/configure", json={"api_key": "nope"}
        )
        assert rejected.status_code == 422
        ok = client.post(
            "/api/model-gateway/providers/ollama/configure",
            json={"base_url": "http://127.0.0.1:9"},
        )
        assert ok.status_code == 200
        assert "http://127.0.0.1:9" in ok.json()["detail"]  # health reflects the new URL


def test_mock_and_unknown_provider_rejected(tmp_path):
    settings = _settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        assert (
            client.post("/api/model-gateway/providers/mock/configure", json={"api_key": "x"})
            .status_code
            == 422
        )
        assert (
            client.post("/api/model-gateway/providers/ghost/configure", json={"api_key": "x"})
            .status_code
            == 404
        )
        assert client.post("/api/model-gateway/providers/ghost/clear").status_code == 404
        empty = client.post("/api/model-gateway/providers/gemini/configure", json={})
        assert empty.status_code == 422


def test_configured_key_never_leaks_into_events_or_errors(tmp_path, event_factory=None):
    # Point Gemini at a refused port so the call fails — the error path and the
    # stored telemetry must not contain the file-configured key.
    settings = _settings(tmp_path, gemini_base_url="http://127.0.0.1:9/v1beta")
    with TestClient(create_app(settings)) as client:
        client.post("/api/model-gateway/providers/gemini/configure", json={"api_key": FAKE_GEMINI})
        response = client.post(
            "/api/model-gateway/test-call",
            json={
                "provider": "gemini",
                "model_name": "gemini-2.0-flash",
                "prompt": "hello",
                "agent_id": "planner",
                "project_id": "demo-project",
                "run_id": "cfg-run",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "failed"
        assert FAKE_GEMINI not in response.text
        events = client.get("/api/runs/cfg-run/events")
        assert FAKE_GEMINI not in events.text
        replay = client.get("/api/runs/cfg-run/replay")
        assert FAKE_GEMINI not in replay.text


def test_configure_requires_api_key_when_auth_enabled(tmp_path):
    settings = _settings(tmp_path, api_keys="k1")
    with TestClient(create_app(settings)) as client:
        url = "/api/model-gateway/providers/gemini/configure"
        assert client.post(url, json={"api_key": FAKE_GEMINI}).status_code == 401
        ok = client.post(url, json={"api_key": FAKE_GEMINI}, headers={"X-API-Key": "k1"})
        assert ok.status_code == 200
