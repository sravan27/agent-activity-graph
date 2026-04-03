from __future__ import annotations

from agent_activity_graph.db.repository import list_incidents
from agent_activity_graph.replay.evidence_pack import (
    build_evidence_pack,
    render_evidence_pack_markdown,
)


def test_evidence_pack_contains_incident_story(seeded_session):
    incident = next(
        incident for incident in list_incidents(seeded_session) if incident.workflow_id == "wf-invoice-3001"
    )
    pack = build_evidence_pack(seeded_session, incident.incident_id)
    markdown = render_evidence_pack_markdown(pack)

    assert pack.workflow_id == "wf-invoice-3001"
    assert pack.business_object_id == "INV-3001"
    assert pack.business_consequence is not None
    assert any(finding.label == "Incident trigger" for finding in pack.findings)
    assert any(entry.event_kind == "policy_evaluation" for entry in pack.chronology)
    assert "## Executive Summary" in markdown
    assert "## Recommended Actions" in markdown
    assert "INV-3001" in markdown
