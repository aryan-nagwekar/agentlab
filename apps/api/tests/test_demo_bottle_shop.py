"""Bottle-Selling Website end-to-end demo (v2.0): a deterministic seed that
exercises the existing runtime end to end. Verifies it reuses real services
and events, writes deterministic website files inside the sandbox only, holds
one payment-path write for human approval (which the user can resume), runs
the deterministic validators, leaks no secrets/host paths, and produces a
meaningful v1.9 debug summary — without replacing any core system."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.runtime import demo_bottle_shop


@pytest.fixture
def client_root(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/demo.db",
        api_keys="",
        cors_origins="",
        workspaces_root=str(tmp_path / "workspaces"),
    )
    with TestClient(create_app(settings)) as client:
        yield client, tmp_path / "workspaces"


def _seed(client):
    response = client.post("/api/runtime/demo/bottle-shop")
    assert response.status_code == 201, response.text
    return response.json()


# ----------------------------------------------------------- creation / files


def test_demo_creates_full_workspace(client_root):
    client, _ = client_root
    out = _seed(client)
    assert out["workspace_id"].startswith("ws-")
    assert out["workflow_id"].startswith("wf-")
    assert out["agent_count"] == 6
    assert out["file_count"] == 7
    assert out["command_count"] == 2
    assert len(out["validator_result_ids"]) == 5
    assert out["pending_approval_id"]  # governance halt created an approval

    workspace = client.get(f"/api/runtime/workspaces/{out['workspace_id']}").json()
    assert workspace["metadata"]["demo"] == "bottle_shop"
    assert workspace["agent_count"] == 6


def test_website_files_written_inside_sandbox_only(client_root):
    client, ws_root = client_root
    out = _seed(client)
    wid = out["workspace_id"]
    sandbox_dir = ws_root / wid

    tree = client.get(f"/api/runtime/workspaces/{wid}/files/tree").json()

    def paths(nodes):
        for n in nodes:
            yield n["path"]
            if n.get("children"):
                yield from paths(n["children"])

    listed = set(paths(tree))
    assert {"README.md", "index.html", "styles.css", "app.js", "products.json"} <= listed
    assert "tests/bottle_shop.test.js" in listed
    # every written file is under the workspace sandbox, nowhere else
    for real in sandbox_dir.rglob("*"):
        if real.is_file():
            assert sandbox_dir in real.parents


def test_website_files_are_deterministic(client_root):
    client, ws_root = client_root
    a = _seed(client)
    b = _seed(client)
    for path in ("index.html", "app.js", "products.json"):
        ca = client.get(
            f"/api/runtime/workspaces/{a['workspace_id']}/files/read", params={"path": path}
        ).json()["content"]
        cb = client.get(
            f"/api/runtime/workspaces/{b['workspace_id']}/files/read", params={"path": path}
        ).json()["content"]
        assert ca == cb == demo_bottle_shop.WEBSITE_FILES[path]


def test_readable_index_html_has_expected_features(client_root):
    client, _ = client_root
    out = _seed(client)
    html = client.get(
        f"/api/runtime/workspaces/{out['workspace_id']}/files/read", params={"path": "index.html"}
    ).json()["content"]
    # semantic + accessible + the required features, fictional brand
    assert "<main>" in html and "lang=\"en\"" in html
    assert "aria-label" in html
    assert "product-grid" in html and "cart" in html.lower() and "checkout" in html.lower()
    assert "Tidewater Bottle Co." in html


# --------------------------------------------------- governance / approval


def test_payment_write_is_held_for_approval(client_root):
    client, ws_root = client_root
    out = _seed(client)
    wid = out["workspace_id"]
    # the payment file was NOT written (blocked for approval)
    assert not (ws_root / wid / "src" / "payment" / "checkout.js").exists()
    approval = client.get(
        f"/api/runtime/workspaces/{wid}/approvals/{out['pending_approval_id']}"
    ).json()
    assert approval["status"] == "pending"
    assert approval["action_type"] == "file.write"
    assert "payment" in approval["target"]
    assert approval["matched_policy_rules"][0]["id"] == "approval-sensitive-file"


def test_user_can_approve_the_held_action_to_resume_it(client_root):
    client, ws_root = client_root
    out = _seed(client)
    wid = out["workspace_id"]
    resolved = client.post(
        f"/api/runtime/workspaces/{wid}/approvals/{out['pending_approval_id']}/approve",
        json={"resolved_by": "demo-user"},
    ).json()
    assert resolved["status"] == "approved"
    assert resolved["execution_status"] == "executed"
    # approving resumed the exact stored write
    assert (ws_root / wid / "src" / "payment" / "checkout.js").exists()


def test_user_can_deny_the_held_action(client_root):
    client, ws_root = client_root
    out = _seed(client)
    wid = out["workspace_id"]
    denied = client.post(
        f"/api/runtime/workspaces/{wid}/approvals/{out['pending_approval_id']}/deny",
        json={"reason": "no real payments in the demo"},
    ).json()
    assert denied["status"] == "denied"
    assert not (ws_root / wid / "src" / "payment" / "checkout.js").exists()


# ------------------------------------------------------- runtime systems used


def test_demo_emits_existing_event_families(client_root):
    client, _ = client_root
    out = _seed(client)
    run_id = f"{out['workspace_id']}-activity"
    types = {e["event_type"] for e in client.get(f"/api/runs/{run_id}/events").json()}
    # workspace, agents, workflow/tasks, files, commands, enforcement,
    # approval, validators all flowed through their normal pipelines
    expected = {
        "workspace.created",
        "workspace_agent.created",
        "runtime.workflow.created",
        "runtime.task.completed",
        "sandbox.file.created",
        "sandbox.command.completed",
        "enforcement.allowed",
        "enforcement.approval_required",
        "approval.requested",
        "validator.completed",
        "validation.failed",
    }
    assert expected <= types
    # and replay reconstructs the whole thing
    replay = client.get(f"/api/runs/{run_id}/replay").json()
    assert len(replay["events"]) > 30


def test_safe_commands_ran_through_the_runner(client_root):
    client, _ = client_root
    out = _seed(client)
    history = client.get(
        f"/api/runtime/workspaces/{out['workspace_id']}/commands/history"
    ).json()
    completed = [e for e in history if e["event_type"] == "sandbox.command.completed"]
    assert len(completed) >= 2  # ls + python3 --version


def test_validators_produce_expected_states(client_root):
    client, _ = client_root
    out = _seed(client)
    results = client.get(
        f"/api/runtime/workspaces/{out['workspace_id']}/validators/results"
    ).json()
    by_type = {r["validator_type"]: r for r in results}
    assert by_type["code_syntax"]["passed"] is True  # products.json is valid
    assert by_type["secret_exposure"]["passed"] is True  # no secrets
    assert by_type["command_result"]["passed"] is True  # commands exited 0
    assert by_type["data_flow"]["passed"] is True  # cart ↔ products fields match
    assert by_type["business_risk"]["passed"] is False  # payment feature flagged


# ----------------------------------------------------------- debug summary


def test_debug_summary_is_meaningful(client_root):
    client, _ = client_root
    out = _seed(client)
    summary = client.get(
        f"/api/runtime/workspaces/{out['workspace_id']}/debug/summary"
    ).json()
    assert summary["health"]["state"] == "approval_needed"
    assert "Needs approval" in summary["health"]["active_labels"]
    assert summary["recommended_actions"][0]["action"] == "review_approval"
    assert summary["workflow_progress"]["task_status_counts"].get("completed") == 5
    assert summary["counts"]["agents"] == 6
    issues = client.get(f"/api/runtime/workspaces/{out['workspace_id']}/debug/issues").json()
    assert any(i["kind"] == "approval_needed" for i in issues)
    cmap = client.get(
        f"/api/runtime/workspaces/{out['workspace_id']}/debug/project-map"
    ).json()
    types = {n["type"] for n in cmap["nodes"]}
    assert {"goal", "workflow", "task", "agent"} <= types


# --------------------------------------------------------- security / scope


def test_no_secret_or_host_path_leaks(client_root):
    from app.runtime.commands import _SECRET_PATTERNS

    client, ws_root = client_root
    out = _seed(client)
    wid = out["workspace_id"]
    blob = (
        str(out)
        + str(client.get(f"/api/runtime/workspaces/{wid}/activity").json())
        + str(client.get(f"/api/runtime/workspaces/{wid}/debug/summary").json())
        + str(client.get(f"/api/runtime/workspaces/{wid}/validators/results").json())
    )
    assert str(ws_root) not in blob  # no host absolute path
    # authoritative secret-shape check (boundary-aware — not a naive substring)
    assert _SECRET_PATTERNS.search(blob) is None


def test_demo_requires_api_key_when_configured(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/demo-auth.db",
        api_keys="k1",
        cors_origins="",
        workspaces_root=str(tmp_path / "ws"),
    )
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/runtime/demo/bottle-shop").status_code == 401
        assert client.post(
            "/api/runtime/demo/bottle-shop", headers={"X-API-Key": "k1"}
        ).status_code == 201


def test_website_files_contain_no_secrets_or_network_calls(client_root):
    client, _ = client_root
    out = _seed(client)
    wid = out["workspace_id"]
    for path in demo_bottle_shop.WEBSITE_FILES:
        content = client.get(
            f"/api/runtime/workspaces/{wid}/files/read", params={"path": path}
        ).json()["content"]
        lowered = content.lower()
        # no real payment/secret/CDN/external-network content
        assert "sk-" not in content and "api_key" not in lowered
        assert "https://" not in content  # no external CDN / network calls
        assert "stripe" not in lowered and "paypal" not in lowered
