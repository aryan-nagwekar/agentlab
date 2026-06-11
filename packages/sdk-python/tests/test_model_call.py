"""SDK model_call: gateway happy path + clean failure when unreachable."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from agentlab import AgentLabClient
from agentlab.client import set_default_client


class _GatewayHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        headers = {k.lower(): v for k, v in self.headers.items()}
        self.server.calls.append((self.path, headers, body))  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(
            json.dumps(
                {
                    "provider": body["provider"],
                    "model_name": body["model_name"],
                    "output_text": "ok",
                    "status": "completed",
                    "total_tokens": 42,
                    "latency_ms": 5,
                }
            ).encode("utf-8")
        )

    def log_message(self, *args):
        pass


@pytest.fixture
def gateway():
    server = HTTPServer(("127.0.0.1", 0), _GatewayHandler)
    server.calls = []  # type: ignore[attr-defined]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()
    server.server_close()


def test_model_call_hits_gateway(gateway):
    client = AgentLabClient(
        "proj",
        api_key="secret-key",
        endpoint=f"http://127.0.0.1:{gateway.server_port}",
        disabled=True,
        set_as_default=False,
    )
    try:
        result = client.model_call(
            run_id="run-1",
            agent_id="planner",
            provider="mock",
            model_name="mock:gpt-4.1",
            prompt="hello",
        )
        assert result["status"] == "completed"
        assert result["total_tokens"] == 42
        path, headers, body = gateway.calls[-1]
        assert path == "/api/runs/run-1/model-call"
        assert headers.get("x-api-key") == "secret-key"
        assert body["provider"] == "mock"
        assert body["project_id"] == "proj"
    finally:
        client.close()
        set_default_client(None)


def test_model_call_failure_is_clean_when_unreachable():
    # Point at a port with nothing listening; must not raise.
    client = AgentLabClient(
        "proj",
        endpoint="http://127.0.0.1:1",
        disabled=True,
        set_as_default=False,
    )
    client._transport = type("T", (), {"enqueue": lambda self, e: None, "flush": lambda self, timeout=None: True, "close": lambda self, timeout=None: None})()
    try:
        result = client.model_call(
            run_id="run-1", provider="mock", model_name="mock:gpt-4.1", prompt="hi", timeout=0.5
        )
        assert result["status"] == "failed"
        assert "unreachable" in result["error_message"]
    finally:
        client.close()
        set_default_client(None)
