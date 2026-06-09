"""Background HTTP transport.

Design constraints, in priority order:
1. Never raise into the host application and never block its hot path.
2. Survive a temporarily unreachable collector by buffering (bounded).
3. Deliver events in order, in batches, with retries and backoff.

Uses only the standard library so the SDK stays dependency-free.
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from typing import Any

logger = logging.getLogger("agentlab")

# Statuses worth retrying; other 4xx mean the batch itself is bad and a retry
# can never succeed, so the batch is dropped (with a warning) instead of
# poisoning the buffer forever.
_RETRYABLE_HTTP = {408, 429, 500, 502, 503, 504}


class HttpTransport:
    def __init__(
        self,
        endpoint: str,
        api_key: str | None = None,
        *,
        flush_interval: float = 0.5,
        batch_size: int = 50,
        max_buffer: int = 10_000,
        timeout: float = 5.0,
        max_retries: int = 3,
        retry_backoff: float = 0.25,
    ) -> None:
        self._url = endpoint.rstrip("/") + "/api/events"
        self._api_key = api_key
        self._flush_interval = flush_interval
        self._batch_size = batch_size
        self._max_buffer = max_buffer
        self._timeout = timeout
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff

        self._queue: "queue.Queue[dict[str, Any]]" = queue.Queue()
        # Events drained from the queue but not yet acknowledged by the
        # collector. Only the worker thread touches this deque.
        self._pending: deque[dict[str, Any]] = deque()
        self._in_flight = False
        self._state_lock = threading.Lock()
        self._stop = threading.Event()
        self._cooldown = 0.0
        self._cooldown_until = 0.0

        self.sent_count = 0
        self.dropped_count = 0

        self._thread = threading.Thread(
            target=self._worker, name="agentlab-transport", daemon=True
        )
        self._thread.start()

    # ------------------------------------------------------------------ API

    def enqueue(self, event: dict[str, Any]) -> None:
        if self._stop.is_set():
            return
        self._queue.put(event)

    def flush(self, timeout: float = 5.0) -> bool:
        """Block until every buffered event is delivered, or the timeout hits."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            # Cancel any backoff so the worker retries immediately.
            self._cooldown_until = 0.0
            with self._state_lock:
                busy = self._in_flight
            if self._queue.empty() and not self._pending and not busy:
                return True
            time.sleep(0.02)
        return False

    def close(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._thread.join(timeout)

    # --------------------------------------------------------------- worker

    def _worker(self) -> None:
        while True:
            stopping = self._stop.is_set()
            try:
                self._pending.append(
                    self._queue.get(timeout=0.01 if stopping else self._flush_interval)
                )
            except queue.Empty:
                pass
            while True:
                try:
                    self._pending.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            self._enforce_buffer_cap()

            attempt_failed = False
            if self._pending and (stopping or time.monotonic() >= self._cooldown_until):
                size = min(self._batch_size, len(self._pending))
                batch = [self._pending.popleft() for _ in range(size)]
                with self._state_lock:
                    self._in_flight = True
                outcome = self._send(batch)
                with self._state_lock:
                    self._in_flight = False
                if outcome == "ok":
                    self.sent_count += len(batch)
                    self._cooldown = 0.0
                    self._cooldown_until = 0.0
                elif outcome == "drop":
                    self.dropped_count += len(batch)
                else:  # retry later, preserving order
                    self._pending.extendleft(reversed(batch))
                    self._cooldown = min(self._cooldown * 2 if self._cooldown else 0.5, 5.0)
                    self._cooldown_until = time.monotonic() + self._cooldown
                    attempt_failed = True

            if stopping and self._queue.empty() and (not self._pending or attempt_failed):
                if self._pending:
                    logger.warning(
                        "agentlab: shutting down with %d undelivered events", len(self._pending)
                    )
                return

    def _enforce_buffer_cap(self) -> None:
        excess = len(self._pending) - self._max_buffer
        if excess > 0:
            for _ in range(excess):
                self._pending.popleft()
            self.dropped_count += excess
            logger.warning("agentlab: event buffer full, dropped %d oldest events", excess)

    def _send(self, batch: list[dict[str, Any]]) -> str:
        """Returns 'ok', 'drop' (unrecoverable rejection), or 'retry'."""
        body = json.dumps({"events": batch}, default=str).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        for attempt in range(self._max_retries):
            request = urllib.request.Request(self._url, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=self._timeout):
                    return "ok"
            except urllib.error.HTTPError as exc:
                if exc.code not in _RETRYABLE_HTTP:
                    detail = b""
                    try:
                        detail = exc.read(300)
                    except Exception:  # noqa: BLE001 - best-effort diagnostics only
                        pass
                    logger.warning(
                        "agentlab: collector rejected batch of %d events (HTTP %s): %s",
                        len(batch),
                        exc.code,
                        detail.decode("utf-8", "replace"),
                    )
                    return "drop"
            except (urllib.error.URLError, OSError):
                pass
            if self._stop.wait(self._retry_backoff * (2**attempt)):
                break
        return "retry"
