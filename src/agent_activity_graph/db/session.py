from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine, text
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
    target_engine = active_engine or engine
    Base.metadata.create_all(bind=target_engine)
    _migrate_schema(target_engine)


def _migrate_schema(active_engine) -> None:
    if active_engine.dialect.name != "sqlite":
        return

    event_columns = {
        "authority_subject": "VARCHAR(255)",
        "authority_delegation_source": "VARCHAR(255)",
        "policy_rule_ids": "JSON NOT NULL DEFAULT '[]'",
        "review_case_id": "VARCHAR(128)",
        "review_state": "VARCHAR(64)",
        "human_decision_reason": "TEXT",
        "due_by": "DATETIME",
        "source_trace_ref": "VARCHAR(255)",
        "source_system_ref": "VARCHAR(255)",
        "evidence_hash": "VARCHAR(128)",
    }

    with active_engine.begin() as connection:
        result = connection.execute(text("PRAGMA table_info(events)"))
        existing = {row[1] for row in result}
        for column_name, column_sql in event_columns.items():
            if column_name in existing:
                continue
            connection.execute(text(f"ALTER TABLE events ADD COLUMN {column_name} {column_sql}"))


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
