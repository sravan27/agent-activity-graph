from __future__ import annotations

from agent_activity_graph.db.repository import get_workflow_events, list_incidents, list_workflows
from agent_activity_graph.sdk.events import ActorType, PolicyStatus


def test_demo_scenario_integrity(seeded_session):
    workflows = list_workflows(seeded_session)
    incidents = list_incidents(seeded_session)

    assert len(workflows) == 3
    assert all(workflow.workflow_name == "Invoice Approval with Agent Participation" for workflow in workflows)
    assert len(incidents) == 3
    assert {incident.incident_id for incident in incidents} == {
        "inc_evt_wf_2001_05",
        "inc_evt_wf_3001_04",
        "inc_evt_wf_3001_05",
    }

    workflow_statuses = {workflow.workflow_id: workflow.status for workflow in workflows}
    assert workflow_statuses["wf-invoice-1001"] == "completed"
    assert workflow_statuses["wf-invoice-2001"] == "completed"
    assert workflow_statuses["wf-invoice-3001"] == "rejected"

    blocked_events = [
        event
        for event in get_workflow_events(seeded_session, "wf-invoice-3001")
        if event.policy_status == PolicyStatus.BLOCKED
    ]
    assert len(blocked_events) == 2

    human_events = [
        event
        for workflow in workflows
        for event in get_workflow_events(seeded_session, workflow.workflow_id)
        if event.actor_type == ActorType.HUMAN
    ]
    assert len(human_events) == 2

    policy_gate_events = [
        event
        for workflow in workflows
        for event in get_workflow_events(seeded_session, workflow.workflow_id)
        if event.action_type == "policy_evaluation"
    ]
    assert len(policy_gate_events) == 3
