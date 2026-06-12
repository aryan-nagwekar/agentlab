"""Application factory. `uvicorn app.main:app` for the default configuration;
tests build isolated instances via create_app(Settings(...))."""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import OperationalError

from .config import Settings
from .db import Base, make_engine, make_session_factory
from .model_gateway import build_registry
from .routers import agents, costs, events, lab, model_gateway, projects, runs, scoring
from .ws import ConnectionManager

logger = logging.getLogger("agentlab.api")

API_VERSION = "0.7.1"


def _init_db(engine, attempts: int = 12, delay: float = 1.5) -> None:
    """create_all with retries: in docker-compose PostgreSQL may still be booting."""
    for attempt in range(1, attempts + 1):
        try:
            Base.metadata.create_all(engine)
            return
        except OperationalError:
            if attempt == attempts:
                raise
            logger.warning("database not ready (attempt %d/%d), retrying…", attempt, attempts)
            time.sleep(delay)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        _init_db(engine)
        yield
        engine.dispose()

    app = FastAPI(
        title="AgentLab API",
        description="Event collector and read API for the AgentLab observability platform.",
        version=API_VERSION,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.ws_manager = ConnectionManager()
    app.state.provider_registry = build_registry(settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(events.router, prefix="/api", tags=["events"])
    app.include_router(projects.router, prefix="/api", tags=["projects"])
    app.include_router(runs.router, prefix="/api", tags=["runs"])
    app.include_router(agents.router, prefix="/api", tags=["agents"])
    app.include_router(lab.router, prefix="/api", tags=["lab"])
    app.include_router(scoring.router, prefix="/api", tags=["scoring"])
    app.include_router(costs.router, prefix="/api", tags=["costs"])
    app.include_router(model_gateway.router, prefix="/api", tags=["model-gateway"])

    @app.get("/api/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "service": "agentlab-api", "version": API_VERSION}

    @app.websocket("/ws/projects/{project_id}")
    async def project_stream(websocket: WebSocket, project_id: str) -> None:
        manager: ConnectionManager = websocket.app.state.ws_manager
        await manager.connect(project_id, websocket)
        try:
            while True:
                # Clients may send pings/keepalives; the channel is server-push.
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            await manager.disconnect(project_id, websocket)

    return app


app = create_app()
