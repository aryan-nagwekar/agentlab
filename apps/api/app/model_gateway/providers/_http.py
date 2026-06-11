"""Tiny stdlib HTTP helper for real providers.

Uses urllib (no new dependency) on a worker thread so the event loop is never
blocked. Errors deliberately exclude request headers so an Authorization value
can never leak into an exception message.
"""
from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request
from typing import Any


class HttpError(Exception):
    def __init__(self, status: int | None, message: str) -> None:
        super().__init__(message)
        self.status = status


def _post_sync(url: str, *, headers: dict[str, str], body: dict[str, Any], timeout: float) -> tuple[dict, int]:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8")), response.status
    except urllib.error.HTTPError as exc:  # never echo headers/body that may contain secrets
        detail = ""
        try:
            detail = exc.read(300).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            pass
        raise HttpError(exc.code, f"HTTP {exc.code}: {detail[:200]}") from None
    except (urllib.error.URLError, OSError) as exc:
        raise HttpError(None, f"connection error: {exc.reason if hasattr(exc, 'reason') else exc}") from None


async def post_json(
    url: str, *, headers: dict[str, str], body: dict[str, Any], timeout: float = 30.0
) -> tuple[dict, int, int]:
    """POST JSON, returning (parsed_response, http_status, latency_ms)."""
    started = time.perf_counter()
    payload, status = await asyncio.to_thread(
        _post_sync, url, headers=headers, body=body, timeout=timeout
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    return payload, status, latency_ms


def _get_sync(url: str, *, timeout: float) -> int:
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status


async def get_status(url: str, *, timeout: float = 3.0) -> int:
    return await asyncio.to_thread(_get_sync, url, timeout=timeout)
