from __future__ import annotations

import pytest

from agent_activity_graph.db.repository import ingest_event, seed_policy_rules
from agent_activity_graph.db.session import build_session_factory
from agent_activity_graph.demo.scenarios import invoice_approval_scenario
from agent_activity_graph.policy.evaluator import PolicyEvaluator


@pytest.fixture
def session(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'test.db'}"
    engine, session_factory = build_session_factory(database_url)
    try:
        with session_factory() as session:
            seed_policy_rules(session)
            yield session
    finally:
        engine.dispose()


@pytest.fixture
def seeded_session(session):
    evaluator = PolicyEvaluator()
    for event in invoice_approval_scenario():
        ingest_event(session, event, evaluator=evaluator)
    return session

