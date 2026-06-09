"""WebSocket fan-out: dashboard subscribers receive ingested events live."""
from __future__ import annotations


def test_subscriber_receives_broadcast(client, event_factory):
    with client.websocket_connect("/ws/projects/proj-1") as websocket:
        event = event_factory("run.started", payload={"name": "live-run"})
        response = client.post("/api/events", json=event)
        assert response.status_code == 202

        message = websocket.receive_json()
        assert message["type"] == "event"
        assert message["data"]["event_type"] == "run.started"
        assert message["data"]["event_id"] == event["event_id"]
        assert message["data"]["payload"]["name"] == "live-run"
        assert message["data"]["timestamp"].endswith("Z")


def test_subscriber_scoped_to_project(client, event_factory):
    with client.websocket_connect("/ws/projects/proj-A") as websocket:
        client.post("/api/events", json=event_factory("run.started", project="proj-B"))
        match = client.post(
            "/api/events", json=event_factory("run.started", project="proj-A", run="run-A")
        )
        assert match.status_code == 202
        # The first frame must be the proj-A event; proj-B never arrives here.
        message = websocket.receive_json()
        assert message["data"]["project_id"] == "proj-A"


def test_batch_broadcasts_each_event(client, event_factory):
    with client.websocket_connect("/ws/projects/proj-1") as websocket:
        batch = {
            "events": [
                event_factory("run.started"),
                event_factory("agent.started", source="a", payload={"name": "A"}),
            ]
        }
        client.post("/api/events", json=batch)
        first = websocket.receive_json()
        second = websocket.receive_json()
        assert first["data"]["event_type"] == "run.started"
        assert second["data"]["event_type"] == "agent.started"
