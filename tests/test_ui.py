from __future__ import annotations

from fastapi.testclient import TestClient

from agent_activity_graph.api.app import create_app
from agent_activity_graph.db.repository import ingest_event, seed_policy_rules
from agent_activity_graph.db.session import build_session_factory, get_session
from agent_activity_graph.demo.scenarios import invoice_approval_scenario
from agent_activity_graph.policy.evaluator import PolicyEvaluator


def _build_seeded_client(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'ui.db'}"
    engine, session_factory = build_session_factory(database_url)

    with session_factory() as session:
        seed_policy_rules(session)
        evaluator = PolicyEvaluator()
        for event in invoice_approval_scenario():
            ingest_event(session, event, evaluator=evaluator)

    app = create_app()

    def override_get_session():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)
    return client, app, engine


def test_replay_page_keeps_control_story_visible(tmp_path):
    client, app, engine = _build_seeded_client(tmp_path)
    try:
        response = client.get("/workflows/wf-invoice-3001/replay")
        assert response.status_code == 200
        assert "Control points" in response.text
        assert "Policy verdict" in response.text
        assert "Business consequence" in response.text
    finally:
        client.close()
        app.dependency_overrides.clear()
        engine.dispose()


def test_workflow_detail_reads_as_operational_surface(tmp_path):
    client, app, engine = _build_seeded_client(tmp_path)
    try:
        response = client.get("/workflows/wf-invoice-3001")
        assert response.status_code == 200
        assert "Next review" in response.text
        assert "Incident follow-up" in response.text
        assert "Run chronology" in response.text
    finally:
        client.close()
        app.dependency_overrides.clear()
        engine.dispose()


def test_incident_page_stays_serious_and_actionable(tmp_path):
    client, app, engine = _build_seeded_client(tmp_path)
    try:
        response = client.get("/incidents/inc_evt_wf_3001_05")
        assert response.status_code == 200
        assert "Trigger Event" in response.text
        assert "Recommended next actions" in response.text
        assert "manual hold" in response.text
    finally:
        client.close()
        app.dependency_overrides.clear()
        engine.dispose()


def test_evidence_pack_avoids_theatrical_footer(tmp_path):
    client, app, engine = _build_seeded_client(tmp_path)
    try:
        response = client.get("/incidents/inc_evt_wf_3001_05/evidence-pack")
        assert response.status_code == 200
        assert "Record basis" in response.text
        assert "Chronology" in response.text
        assert "Next actions" in response.text
        assert "END OF EVIDENCE PACK" not in response.text
    finally:
        client.close()
        app.dependency_overrides.clear()
        engine.dispose()
