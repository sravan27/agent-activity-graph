from __future__ import annotations

from agent_activity_graph.demo.local_trace import generate_local_review_trace
from agent_activity_graph.db.repository import ingest_event, list_incidents
from agent_activity_graph.policy.evaluator import PolicyEvaluator
from agent_activity_graph.replay.evidence_pack import build_evidence_pack
from agent_activity_graph.replay.timeline import build_replay_timeline
from agent_activity_graph.sdk.trace_adapter import map_trace_to_workflow_events


def test_local_trace_generation_builds_review_case_without_model_calls():
    trace = generate_local_review_trace(
        classification_result={
            "classification": "high_value_invoice",
            "control_lane": "finance_review",
            "risk_note": "Same-day cut-off pressure requires explicit review.",
            "action_summary": "AP Agent classified the invoice as a high-value finance review case.",
            "headline": "Agent classified the invoice into a finance-controlled review lane",
        },
        proposal_result={
            "recommendation": "AP Agent prepared the approval packet with PO match, amount, and cut-off context.",
            "why_it_mattered": "The approval packet gathered the facts finance needs before a human decision.",
            "review_summary": "PO matched and spend was authorized.",
            "reviewer_note": "Escalate because delegated authority stops at USD 5,000.",
        },
    )

    assert trace.source.value == "generic_openinference"
    assert trace.workflow.workflow_defaults["runtime_origin"] == "local_ollama_agent"
    assert len(trace.spans) == 5

    events = map_trace_to_workflow_events(trace)

    assert events[2].action_type == "propose_invoice_approval"
    assert events[3].action_type == "policy_evaluation"
    assert events[3].review_case_id == f"review-{trace.workflow.workflow_id}"
    assert events[4].human_decision_reason


def test_local_trace_ingests_into_verified_replay(session):
    trace = generate_local_review_trace(
        trace_id="trace_local_test_7001",
        classification_result={
            "classification": "high_value_invoice",
            "control_lane": "finance_review",
            "risk_note": "Same-day cut-off pressure requires explicit review.",
            "action_summary": "AP Agent classified the invoice as a high-value finance review case.",
            "headline": "Agent classified the invoice into a finance-controlled review lane",
        },
        proposal_result={
            "recommendation": "AP Agent prepared the approval packet with PO match, amount, and cut-off context.",
            "why_it_mattered": "The approval packet gathered the facts finance needs before a human decision.",
            "review_summary": "PO matched and spend was authorized.",
            "reviewer_note": "Escalate because delegated authority stops at USD 5,000.",
        },
    )

    for event in map_trace_to_workflow_events(trace):
        ingest_event(session, event, evaluator=PolicyEvaluator(), preserve_event_policy=True)

    replay = build_replay_timeline(session, trace.workflow.workflow_id, persist=False)
    incidents = list_incidents(session, workflow_id=trace.workflow.workflow_id)
    pack = build_evidence_pack(session, incidents[0].incident_id)

    assert replay.evidence_status == "verified"
    assert replay.review_case_id == f"review-{trace.workflow.workflow_id}"
    assert replay.source_trace_refs == ["trace_local_test_7001"]
    assert incidents
    assert pack.evidence_status == "verified"
