from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from fastapi.testclient import TestClient

from agent_activity_graph.api.app import create_app
from agent_activity_graph.db.repository import (
    get_workflow_events,
    ingest_event,
    list_incidents,
    seed_policy_rules,
    verify_evidence_chain,
)
from agent_activity_graph.db.session import build_session_factory, get_session
from agent_activity_graph.policy.evaluator import PolicyEvaluator
from agent_activity_graph.replay.evidence_pack import build_evidence_pack
from agent_activity_graph.replay.timeline import build_replay_timeline
from agent_activity_graph.sdk.events import (
    ActorType,
    PolicyStatus,
    TraceIngestionRequest,
    TraceSource,
    TraceSpan,
    TraceWorkflowContext,
)
from agent_activity_graph.sdk.trace_adapter import map_trace_to_workflow_events


def _workflow_context() -> TraceWorkflowContext:
    return TraceWorkflowContext(
        workflow_id="wf-trace-4001",
        workflow_name="Invoice Approval with Agent Participation",
        business_object_type="invoice",
        business_object_id="INV-TRACE-4001",
        workflow_defaults={
            "invoice_amount": 12500,
            "currency": "USD",
            "vendor_id": "V-TRACE",
            "vendor_name": "Trace Vendor",
            "po_number": "PO-TRACE-1",
            "payment_batch_cutoff": "2026-04-01T14:00:00Z",
            "invoice_due_date": "2026-04-01",
            "cost_center": "FINANCE-77",
            "payment_terms": "Net 10",
            "risk_category": "delayed_payment_risk",
            "business_consequence": "If review slips past the cut-off, payment moves to the next business day.",
        },
    )


def test_sample_trace_fixture_validates():
    fixture_path = (
        Path(__file__).resolve().parent.parent
        / "examples"
        / "traces"
        / "openai_agents_invoice_review.json"
    )

    payload = json.loads(fixture_path.read_text())
    request = TraceIngestionRequest.model_validate(payload)

    assert request.workflow.workflow_id == "wf-trace-proof-5001"
    assert request.source == TraceSource.OPENAI_AGENTS
    assert len(request.spans) == 5
    assert request.spans[0].attributes["trace.id"] == "trace_5001invoiceapprovalproof00000001"
    assert request.spans[1].attributes["mcp.tool.name"] == "lookup_purchase_order"


def test_sample_trace_fixture_maps_public_source_mcp_review_path():
    fixture_path = (
        Path(__file__).resolve().parent.parent
        / "examples"
        / "traces"
        / "openai_agents_invoice_review.json"
    )

    request = TraceIngestionRequest.model_validate_json(fixture_path.read_text())

    events = map_trace_to_workflow_events(request)

    assert len(events) == 5
    assert all(event.source_trace_ref == "trace_5001invoiceapprovalproof00000001" for event in events)
    assert events[1].tool_name == "lookup_purchase_order"
    assert events[1].target_system == "mcp:finance-erp-gateway"
    assert events[3].policy_rule_ids == ["large_invoice_requires_escalation"]
    assert events[4].review_case_id == "review-trace-proof-5001"


def test_sample_trace_fixture_ingests_as_verified_review_case(session):
    fixture_path = (
        Path(__file__).resolve().parent.parent
        / "examples"
        / "traces"
        / "openai_agents_invoice_review.json"
    )

    request = TraceIngestionRequest.model_validate_json(fixture_path.read_text())

    for event in map_trace_to_workflow_events(request):
        ingest_event(session, event, evaluator=PolicyEvaluator(), preserve_event_policy=True)

    replay = build_replay_timeline(session, "wf-trace-proof-5001", persist=False)
    incidents = list_incidents(session, workflow_id="wf-trace-proof-5001")
    pack = build_evidence_pack(session, incidents[0].incident_id)

    assert replay.evidence_status == "verified"
    assert replay.review_case_id == "review-trace-proof-5001"
    assert replay.source_trace_refs == ["trace_5001invoiceapprovalproof00000001"]
    assert len(replay.entries) == 5
    assert incidents[0].incident_id.startswith("inc_evt_wf-trace-proof-5001_")
    assert pack.evidence_status == "verified"


def test_openai_trace_mapping_preserves_policy_review_context():
    request = TraceIngestionRequest(
        source=TraceSource.OPENAI_AGENTS,
        workflow=_workflow_context(),
        spans=[
            TraceSpan(
                span_id="span-01",
                name="Classify invoice",
                start_time=datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc),
                attributes={
                    "openinference.span.kind": "agent",
                    "agent.name": "AP Agent",
                    "aag.workflow.process_step": "classification",
                    "aag.action_summary": "AP Agent classified the invoice for finance review.",
                    "aag.permission_scope": "invoice:classify",
                    "aag.source_trace_ref": "trace-openai-4001",
                },
            ),
            TraceSpan(
                span_id="span-02",
                name="Policy evaluation",
                start_time=datetime(2026, 4, 1, 9, 2, tzinfo=timezone.utc),
                attributes={
                    "aag.action_type": "policy_evaluation",
                    "aag.workflow.process_step": "policy_gate",
                    "aag.action_summary": "Policy engine escalated the invoice because the amount exceeds delegated authority.",
                    "aag.policy_status": "escalated",
                    "aag.policy_rule_ids": ["large_invoice_requires_escalation"],
                    "aag.policy_explanation": "Invoice amount 12,500.00 exceeds delegated authority.",
                    "aag.recommended_next_action": "Escalate to a finance approver before payment can proceed.",
                    "aag.review_case_id": "review-trace-4001",
                    "aag.review_state": "pending_human_review",
                    "aag.due_by": "2026-04-01T14:00:00Z",
                    "aag.source_trace_ref": "trace-openai-4001",
                },
            ),
        ],
    )

    events = map_trace_to_workflow_events(request)

    assert len(events) == 2
    assert events[0].actor_type == ActorType.AGENT
    assert events[0].source_trace_ref == "trace-openai-4001"
    assert events[1].actor_type == ActorType.SYSTEM
    assert events[1].action_type == "policy_evaluation"
    assert events[1].policy_status == PolicyStatus.ESCALATED
    assert events[1].policy_rule_ids == ["large_invoice_requires_escalation"]
    assert events[1].review_case_id == "review-trace-4001"


def test_mcp_trace_mapping_keeps_tool_and_system_context():
    request = TraceIngestionRequest(
        source=TraceSource.MCP,
        workflow=_workflow_context(),
        spans=[
            TraceSpan(
                span_id="span-mcp-01",
                name="lookup_po",
                start_time=datetime(2026, 4, 1, 9, 4, tzinfo=timezone.utc),
                attributes={
                    "mcp.tool.name": "lookup_po",
                    "mcp.server.name": "erp-gateway",
                    "agent.name": "AP Agent",
                    "aag.workflow.process_step": "po_check",
                    "aag.action_summary": "Agent called the MCP ERP gateway to verify the PO.",
                    "aag.permission_scope": "erp:read:purchase_orders",
                    "aag.source_trace_ref": "trace-mcp-4001",
                },
            )
        ],
    )

    [event] = map_trace_to_workflow_events(request)

    assert event.actor_type == ActorType.AGENT
    assert event.action_type == "call_mcp_tool"
    assert event.tool_name == "lookup_po"
    assert event.target_system == "mcp:erp-gateway"
    assert event.source_system_ref == "erp-gateway"


def test_preserved_trace_ingestion_creates_reviewable_incident(session):
    request = TraceIngestionRequest(
        source=TraceSource.OPENAI_AGENTS,
        workflow=_workflow_context(),
        spans=[
            TraceSpan(
                span_id="span-01",
                name="Prepare approval packet",
                start_time=datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc),
                attributes={
                    "openinference.span.kind": "agent",
                    "agent.name": "AP Agent",
                    "aag.workflow.process_step": "approval_recommendation",
                    "aag.action_summary": "AP Agent prepared a high-value approval packet.",
                    "aag.permission_scope": "invoice:approve:proposal",
                    "aag.authority_subject": "AP Agent may prepare packets but not approve above USD 5,000.",
                    "aag.authority_delegation_source": "Finance AP delegation policy v2026.03",
                    "aag.source_trace_ref": "trace-openai-incident",
                },
            ),
            TraceSpan(
                span_id="span-02",
                name="Policy evaluation",
                start_time=datetime(2026, 4, 1, 9, 2, tzinfo=timezone.utc),
                attributes={
                    "aag.action_type": "policy_evaluation",
                    "aag.workflow.process_step": "policy_gate",
                    "aag.action_summary": "Policy engine escalated the invoice to finance review.",
                    "aag.policy_status": "escalated",
                    "aag.policy_rule_ids": ["large_invoice_requires_escalation"],
                    "aag.policy_explanation": "Invoice amount 12,500.00 exceeds delegated authority.",
                    "aag.recommended_next_action": "Escalate to finance review.",
                    "aag.review_case_id": "review-trace-incident",
                    "aag.review_state": "pending_human_review",
                    "aag.due_by": "2026-04-01T14:00:00Z",
                    "aag.headline": "Policy gate escalated the trace-derived workflow",
                    "aag.source_trace_ref": "trace-openai-incident",
                },
            ),
        ],
    )

    for event in map_trace_to_workflow_events(request):
        ingest_event(session, event, evaluator=PolicyEvaluator(), preserve_event_policy=True)

    replay = build_replay_timeline(session, "wf-trace-4001", persist=False)
    incidents = list_incidents(session, workflow_id="wf-trace-4001")
    pack = build_evidence_pack(session, incidents[0].incident_id)

    assert replay.review_case_id == "review-trace-incident"
    assert replay.source_trace_refs == ["trace-openai-incident"]
    assert incidents[0].incident_id.startswith("inc_evt_wf-trace-4001_")
    assert pack.review_case_id == "review-trace-incident"
    assert pack.evidence_status == "verified"


def test_openinference_trace_endpoint_ingests_review_case(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'trace-api.db'}"
    engine, session_factory = build_session_factory(database_url)

    with session_factory() as session:
        seed_policy_rules(session)

    app = create_app()

    def override_get_session():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)

    try:
        response = client.post(
            "/api/traces/openinference",
            json={
                "source": "openai_agents",
                "workflow": _workflow_context().model_dump(mode="json"),
                "spans": [
                    {
                        "span_id": "span-01",
                        "name": "Prepare approval packet",
                        "start_time": "2026-04-01T09:00:00Z",
                        "attributes": {
                            "openinference.span.kind": "agent",
                            "agent.name": "AP Agent",
                            "aag.workflow.process_step": "approval_recommendation",
                            "aag.action_summary": "AP Agent prepared a high-value approval packet.",
                            "aag.permission_scope": "invoice:approve:proposal",
                            "aag.source_trace_ref": "trace-api-4001",
                        },
                    },
                    {
                        "span_id": "span-02",
                        "name": "Policy evaluation",
                        "start_time": "2026-04-01T09:02:00Z",
                        "attributes": {
                            "aag.action_type": "policy_evaluation",
                            "aag.workflow.process_step": "policy_gate",
                            "aag.action_summary": "Policy engine escalated the invoice to finance review.",
                            "aag.policy_status": "escalated",
                            "aag.policy_rule_ids": ["large_invoice_requires_escalation"],
                            "aag.policy_explanation": "Invoice amount 12,500.00 exceeds delegated authority.",
                            "aag.review_case_id": "review-trace-api",
                            "aag.review_state": "pending_human_review",
                            "aag.source_trace_ref": "trace-api-4001",
                        },
                    },
                ],
            },
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["workflow_id"] == "wf-trace-4001"
        assert payload["ingested_events"] == 2
        assert payload["incident_ids"]
    finally:
        client.close()
        app.dependency_overrides.clear()
        engine.dispose()


def test_incomplete_trace_is_marked_for_enrichment(session):
    request = TraceIngestionRequest(
        source=TraceSource.OPENAI_AGENTS,
        workflow=_workflow_context(),
        spans=[
            TraceSpan(
                span_id="span-01",
                name="Prepare approval packet",
                start_time=datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc),
                attributes={
                    "openinference.span.kind": "agent",
                    "agent.name": "AP Agent",
                    "aag.workflow.process_step": "approval_recommendation",
                    "aag.action_summary": "AP Agent prepared a high-value approval packet.",
                    "aag.permission_scope": "invoice:approve:proposal",
                    "aag.source_trace_ref": "trace-incomplete-4001",
                },
            ),
            TraceSpan(
                span_id="span-02",
                name="Policy evaluation",
                start_time=datetime(2026, 4, 1, 9, 2, tzinfo=timezone.utc),
                attributes={
                    "aag.action_type": "policy_evaluation",
                    "aag.workflow.process_step": "policy_gate",
                    "aag.action_summary": "Policy engine escalated the invoice to finance review.",
                    "aag.policy_status": "escalated",
                    "aag.source_trace_ref": "trace-incomplete-4001",
                },
            ),
        ],
    )

    for event in map_trace_to_workflow_events(request):
        ingest_event(session, event, evaluator=PolicyEvaluator(), preserve_event_policy=True)

    replay = build_replay_timeline(session, "wf-trace-4001", persist=False)

    assert replay.evidence_status == "needs_enrichment"
    assert any("missing policy_rule_ids" in issue for issue in replay.evidence_issues)
    assert any("missing review_case_id" in issue for issue in replay.evidence_issues)
    assert any("missing authority_subject" in issue for issue in replay.evidence_issues)


def test_evidence_chain_reports_payload_tampering(seeded_session):
    workflow_events = get_workflow_events(seeded_session, "wf-invoice-3001")

    assert verify_evidence_chain(workflow_events) == []

    tampered_events = [event.model_copy() for event in workflow_events]
    tampered_event = tampered_events[2]
    tampered_events[2] = tampered_event.model_copy(
        update={
            "metadata": {
                **tampered_event.metadata,
                "headline": "Tampered headline that no longer matches the recorded hash.",
            }
        }
    )

    issues = verify_evidence_chain(tampered_events)

    assert any("does not match the stored event payload" in issue for issue in issues)
