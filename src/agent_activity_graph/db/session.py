from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from agent_activity_graph.db.models import Base


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", "sqlite:///./agent_activity_graph.db")


def create_sqlalchemy_engine(database_url: str | None = None):
    url = database_url or get_database_url()
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, future=True)


engine = create_sqlalchemy_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def init_db(active_engine=None) -> None:
    Base.metadata.create_all(bind=active_engine or engine)


def build_session_factory(database_url: str):
    active_engine = create_sqlalchemy_engine(database_url)
    init_db(active_engine)
    return active_engine, sessionmaker(
        bind=active_engine,
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

