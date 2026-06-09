"""Engine/session plumbing. The engine is created per-app in main.create_app
so tests can point each app instance at its own database."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str) -> Engine:
    kwargs: dict = {"future": True}
    if database_url.startswith("sqlite"):
        # TestClient and uvicorn workers touch the session from multiple threads.
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(database_url, **kwargs)


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
