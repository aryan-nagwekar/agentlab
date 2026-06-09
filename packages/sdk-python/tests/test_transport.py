"""Transport tests against a real in-process HTTP server."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from agentlab._transport import HttpTransport


class _CollectorHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        if self.server.fail_next > 0:  # type: ignore[attr-defined]
            self.server.fail_next -= 1  # type: ignore[attr-defined]
            status = 503
        else:
            status = self.server.respond_with  # type: ignore[attr-defined]
        headers = {k.lower(): v for k, v in self.headers.items()}
        self.server.log.append((status, headers, body))  # type: ignore[attr-defined]
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):  # silence test output
        pass


def _start_server(port: int = 0) -> HTTPServer:
    server = HTTPServer(("127.0.0.1", port), _CollectorHandler)
    server.log = []  # type: ignore[attr-defined]
    server.fail_next = 0  # type: ignore[attr-defined]
    server.respond_with = 202  # type: ignore[attr-defined]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _stop_server(server: HTTPServer) -> None:
    server.shutdown()
    server.server_close()


def _delivered(server: HTTPServer) -> list[dict]:
    events = []
    for status, _, body in server.log:  # type: ignore[attr-defined]
        if status == 202:
            events.extend(body["events"])
    return events


def _make_transport(port: int, **kwargs) -> HttpTransport:
    defaults = dict(
        flush_interval=0.02,
        timeout=0.5,
        max_retries=3,
        retry_backoff=0.01,
    )
    defaults.update(kwargs)
    return HttpTransport(f"http://127.0.0.1:{port}", "secret-key", **defaults)


def test_delivers_batches_in_order_with_api_key():
    server = _start_server()
    transport = _make_transport(server.server_port, batch_size=10)
    try:
        for i in range(25):
            transport.enqueue({"i": i})
        assert transport.flush(timeout=5)
        delivered = _delivered(server)
        assert [e["i"] for e in delivered] == list(range(25))
        # batched, not one request per event
        assert len(server.log) <= 5  # type: ignore[attr-defined]
        _, headers, _ = server.log[0]  # type: ignore[attr-defined]
        assert headers["x-api-key"] == "secret-key"
        assert headers["content-type"] == "application/json"
    finally:
        transport.close()
        _stop_server(server)


def test_retries_through_transient_5xx():
    server = _start_server()
    server.fail_next = 2  # type: ignore[attr-defined]
    transport = _make_transport(server.server_port)
    try:
        transport.enqueue({"i": 1})
        assert transport.flush(timeout=5)
        assert [e["i"] for e in _delivered(server)] == [1]
        assert transport.sent_count == 1
    finally:
        transport.close()
        _stop_server(server)


def test_buffers_through_collector_outage():
    # Reserve a port, then take the collector down before any send.
    server = _start_server()
    port = server.server_port
    _stop_server(server)

    transport = _make_transport(port, max_retries=1)
    try:
        for i in range(5):
            transport.enqueue({"i": i})
        # Nothing reachable: flush must time out but never raise.
        assert transport.flush(timeout=0.3) is False

        revived = _start_server(port)
        try:
            assert transport.flush(timeout=5)
            assert [e["i"] for e in _delivered(revived)] == list(range(5))
        finally:
            _stop_server(revived)
    finally:
        transport.close()


def test_drops_batch_on_unrecoverable_4xx():
    server = _start_server()
    server.respond_with = 422  # type: ignore[attr-defined]
    transport = _make_transport(server.server_port)
    try:
        transport.enqueue({"bad": True})
        assert transport.flush(timeout=5)  # buffer empties because batch is dropped
        assert transport.dropped_count == 1
        assert _delivered(server) == []
    finally:
        transport.close()
        _stop_server(server)


def test_buffer_cap_drops_oldest():
    server = _start_server()
    port = server.server_port
    _stop_server(server)
    transport = _make_transport(port, max_retries=1, max_buffer=10)
    try:
        for i in range(50):
            transport.enqueue({"i": i})
        transport.flush(timeout=0.5)
        revived = _start_server(port)
        try:
            assert transport.flush(timeout=5)
            kept = [e["i"] for e in _delivered(revived)]
            assert len(kept) <= 10 + 1  # cap, +1 for an event already in flight
            assert kept == sorted(kept)
            assert kept[-1] == 49  # newest survives, oldest dropped
            assert transport.dropped_count >= 39
        finally:
            _stop_server(revived)
    finally:
        transport.close()
