from __future__ import annotations

from agent_activity_graph.replay.timeline import build_replay_timeline


def test_replay_sequence_for_escalated_workflow(seeded_session):
    replay = build_replay_timeline(seeded_session, "wf-invoice-2001", persist=False)

    assert [entry.sequence_number for entry in replay.entries] == [1, 2, 3, 4, 5, 6, 7]
    assert replay.escalation_count == 1
    assert replay.human_intervention_count == 1
    assert replay.final_outcome == "completed"
    assert any(entry.event_kind == "policy_evaluation" for entry in replay.entries)
    assert replay.business_consequence is not None
    assert "payment run" in replay.business_consequence


def test_replay_marks_blocked_actions(seeded_session):
    replay = build_replay_timeline(seeded_session, "wf-invoice-3001", persist=False)

    assert replay.blocked_count == 2
    assert replay.human_intervention_count == 1
    assert replay.final_outcome == "rejected"
    assert any(highlight.label == "Blocked path" for highlight in replay.highlights)
