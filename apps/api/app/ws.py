"""WebSocket fan-out: one channel per project."""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("agentlab.ws")


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, project_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[project_id].add(websocket)

    async def disconnect(self, project_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections[project_id].discard(websocket)

    async def broadcast(self, project_id: str, message: dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._connections.get(project_id, ()))
        for websocket in targets:
            try:
                await websocket.send_json(message)
            except Exception:  # noqa: BLE001 - a dead socket must never break ingest
                logger.debug("dropping dead websocket for project %s", project_id)
                await self.disconnect(project_id, websocket)
