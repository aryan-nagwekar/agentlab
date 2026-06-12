"""Project templates (v0.9): registry, create-from-template, and the rule that
a template-created workflow is a completely normal v0.8 Studio workflow."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.studio.templates import TEMPLATES

REQUIRED_TEMPLATE_IDS = {
    "code-review-team",
    "research-team",
    "resume-tailoring-team",
    "soc-investigation-team",
    "customer-support-team",
    "data-analysis-team",
}


# ------------------------------------------------------------------- registry


def test_list_templates(client):
    templates = client.get("/api/studio/templates").json()
    assert {t["template_id"] for t in templates} == REQUIRED_TEMPLATE_IDS
    for template in templates:
        assert template["agent_count"] == 5
        assert template["name"]
        assert template["category"]
        assert template["tags"]
        assert template["difficulty"] in ("beginner", "intermediate")
        assert template["use_case"].startswith("Good for:")


def test_get_template_detail(client):
    detail = client.get("/api/studio/templates/code-review-team").json()
    assert [a["name"] for a in detail["agents"]] == [
        "Planner Agent",
        "Coder Agent",
        "Test Writer Agent",
        "Security Reviewer Agent",
        "Final Report Agent",
    ]
    assert len(detail["edges"]) == 4
    assert detail["edges"][0]["source_agent_id"] == "planner-agent"
    assert detail["edges"][0]["target_agent_id"] == "coder-agent"
    assert "FastAPI" in detail["default_input"]
    assert len(detail["expected_outputs"]) == 5
    assert detail["demo_notes"]
    # every default stays on the keyless mock provider
    assert all(a["provider"] == "mock" for a in detail["agents"])
    assert all(a["model_name"].startswith("mock:") for a in detail["agents"])


def test_every_template_defaults_to_mock_models():
    for template in TEMPLATES.values():
        assert all(a.provider == "mock" for a in template.agents)
        assert all(a.model_name.startswith("mock:") for a in template.agents)
        agent_names = {a.name for a in template.agents}
        for edge in template.edges:
            assert edge.source_agent_name in agent_names
            assert edge.target_agent_name in agent_names


def test_unknown_template_404(client):
    assert client.get("/api/studio/templates/ghost-team").status_code == 404
    assert (
        client.post(
            "/api/studio/templates/ghost-team/create-workflow", json={}
        ).status_code
        == 404
    )


# --------------------------------------------------------- create-from-template


def test_create_workflow_from_template(client):
    response = client.post(
        "/api/studio/templates/code-review-team/create-workflow",
        json={"project_id": "demo-project", "name": "My Code Review Team"},
    )
    assert response.status_code == 201
    created = response.json()
    assert created["template_id"] == "code-review-team"
    assert created["open_url"] == f"/studio/workflows/{created['workflow_id']}"

    workflow = client.get(f"/api/studio/workflows/{created['workflow_id']}").json()
    assert workflow["name"] == "My Code Review Team"
    assert {a["agent_id"] for a in workflow["agents"]} == {
        "planner-agent",
        "coder-agent",
        "test-writer-agent",
        "security-reviewer-agent",
        "final-report-agent",
    }
    assert len(workflow["edges"]) == 4
    by_id = {a["agent_id"]: a for a in workflow["agents"]}
    assert by_id["coder-agent"]["model_name"] == "mock:gpt-4.1"
    assert by_id["test-writer-agent"]["system_prompt"]
    # provenance lands in the editable definition too
    assert by_id["planner-agent"]["metadata"]["template_id"] == "code-review-team"


def test_created_workflow_default_name_is_template_name(client):
    created = client.post(
        "/api/studio/templates/customer-support-team/create-workflow", json={}
    ).json()
    workflow = client.get(f"/api/studio/workflows/{created['workflow_id']}").json()
    assert workflow["name"] == "Customer Support Agent Team"


def test_created_workflow_validates_and_is_editable(client):
    created = client.post(
        "/api/studio/templates/data-analysis-team/create-workflow", json={}
    ).json()
    workflow_id = created["workflow_id"]
    verdict = client.post(f"/api/studio/workflows/{workflow_id}/validate").json()
    assert verdict == {"valid": True, "errors": [], "warnings": []}
    # normal v0.8 editing applies — e.g. retarget an agent's model
    updated = client.put(
        f"/api/studio/workflows/{workflow_id}/agents/analysis-planner",
        json={"name": "Analysis Planner", "role": "planner", "provider": "mock",
              "model_name": "mock:local-ollama"},
    )
    assert updated.status_code == 200
    assert updated.json()["model_name"] == "mock:local-ollama"


def test_every_template_creates_valid_workflow(client):
    for template_id in REQUIRED_TEMPLATE_IDS:
        created = client.post(
            f"/api/studio/templates/{template_id}/create-workflow", json={}
        )
        assert created.status_code == 201, template_id
        verdict = client.post(
            f"/api/studio/workflows/{created.json()['workflow_id']}/validate"
        ).json()
        assert verdict["valid"] is True, (template_id, verdict)


# ---------------------------------------------------------------- run + views


def test_template_run_flows_into_existing_views(client):
    template = client.get("/api/studio/templates/soc-investigation-team").json()
    created = client.post(
        "/api/studio/templates/soc-investigation-team/create-workflow", json={}
    ).json()
    result = client.post(
        f"/api/studio/workflows/{created['workflow_id']}/run",
        json={"input": template["default_input"]},
    ).json()
    assert result["status"] == "completed"
    run_id = result["run_id"]

    types = [e["event_type"] for e in client.get(f"/api/runs/{run_id}/events").json()]
    assert types[0] == "run.started" and types[-1] == "run.completed"
    assert types.count("model.completed") == 5

    graph = client.get(f"/api/runs/{run_id}/graph").json()
    assert {n["id"] for n in graph["nodes"]} == {
        "log-parser-agent", "threat-classifier-agent", "timeline-builder-agent",
        "remediation-agent", "incident-report-agent",
    }
    assert len(graph["edges"]) == 4

    replay = client.get(f"/api/runs/{run_id}/replay").json()
    assert replay["status"] == "completed"
    assert replay["event_count"] == len(types)

    costs = client.get(f"/api/runs/{run_id}/costs").json()
    assert costs["total_tokens"] > 0
    assert costs["estimated_cost_usd"] > 0
    assert len(costs["agent_breakdown"]) == 5

    scores = client.get(f"/api/runs/{run_id}/scores").json()
    assert all(a["tier"] == "trusted" for a in scores["agents"])


def test_no_raw_key_in_template_responses(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/tpl-keys.db",
        api_keys="",
        cors_origins="",
        openai_api_key="sk-template-secret-key-3333",
        gemini_api_key="AIzaTemplateSecret4444",
    )
    with TestClient(create_app(settings)) as client:
        texts = [
            client.get("/api/studio/templates").text,
            client.get("/api/studio/templates/research-team").text,
            client.post(
                "/api/studio/templates/research-team/create-workflow", json={}
            ).text,
        ]
        for text in texts:
            assert "sk-template-secret-key-3333" not in text
            assert "AIzaTemplateSecret4444" not in text


def test_create_requires_api_key_when_configured(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/tpl-auth.db", api_keys="k1", cors_origins=""
    )
    with TestClient(create_app(settings)) as client:
        url = "/api/studio/templates/code-review-team/create-workflow"
        assert client.post(url, json={}).status_code == 401
        assert client.post(url, json={}, headers={"X-API-Key": "k1"}).status_code == 201
