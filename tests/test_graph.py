from __future__ import annotations

from agent_activity_graph.db.repository import get_workflow_events
from agent_activity_graph.graph.queries import build_graph_snapshot


def test_graph_construction_for_escalated_workflow(seeded_session):
    events = get_workflow_events(seeded_session, "wf-invoice-2001")
    graph = build_graph_snapshot("wf-invoice-2001", events)

    assert graph.node_count == 7
    assert graph.edge_count >= 6
    assert graph.actor_transitions >= 2
    assert "policy-engine" in graph.systems_touched
    assert "erp-approvals" in graph.systems_touched
