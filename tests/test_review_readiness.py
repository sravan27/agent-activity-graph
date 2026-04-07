from __future__ import annotations

from datetime import datetime, timezone

from agent_activity_graph.db.repository import ingest_event
from agent_activity_graph.policy.evaluator import PolicyEvaluator
from agent_activity_graph.review.benchmark import (
    build_review_readiness_benchmark_rows,
    render_review_readiness_benchmark_markdown,
)
from agent_activity_graph.review.cases import build_review_case
from agent_activity_graph.review.readiness import REVIEW_READINESS_SPEC_VERSION, grade_workflow
from agent_activity_graph.sdk.events import ActorType, OutcomeStatus, WorkflowEvent


def test_review_case_detail_captures_structured_resolution_fields(seeded_session):
    detail = build_review_case(seeded_session, "review-wf-invoice-3001")

    assert detail.review_case.decision_code == "reject_missing_purchase_order"
    assert detail.review_case.approver_role == "AP Manager"
    assert detail.review_case.remediation_owner == "Procurement Operations"
    assert detail.review_case.closure_status == "rejected"
    assert detail.replay.review_readiness_spec_version == REVIEW_READINESS_SPEC_VERSION


def test_grade_workflow_marks_seeded_blocked_case_review_ready(seeded_session):
    report = grade_workflow(seeded_session, "wf-invoice-3001")

    assert report.spec_version == REVIEW_READINESS_SPEC_VERSION
    assert report.status == "review_ready"
    assert report.overall_score >= 85
    assert any(category.key == "human_review" and category.score == 100 for category in report.categories)


def test_high_risk_write_boundary_auto_creates_review_case(session):
    result = ingest_event(
        session,
        WorkflowEvent(
            event_id="evt_wf_high_risk_01",
            timestamp=datetime(2026, 4, 3, 9, 0, tzinfo=timezone.utc),
            workflow_id="wf-high-risk-4101",
            workflow_name="Invoice Approval with Agent Participation",
            process_step="approval_execution",
            actor_type=ActorType.AGENT,
            actor_id="ap-agent",
            actor_name="AP Agent",
            action_type="approve_invoice",
            action_summary="AP Agent attempted to send the invoice to the finance approval gateway.",
            target_system="finance-approval-gateway",
            business_object_type="invoice",
            business_object_id="INV-HIGH-RISK-4101",
            permission_scope="invoice:approve:under_threshold",
            authority_subject="AP Agent may approve low-value invoices but write actions still require a review record.",
            authority_delegation_source="Finance AP delegation policy v2026.03",
            outcome_status=OutcomeStatus.SUCCESS,
            metadata={
                "invoice_amount": 1200,
                "currency": "USD",
                "vendor_name": "Low Value Office Supply",
                "po_number": "PO-HIGH-RISK-4101",
            },
        ),
        evaluator=PolicyEvaluator(),
    )

    assert result.policy.decision.value == "blocked"
    assert result.event.review_case_id == "review-wf-high-risk-4101"
    assert result.event.review_state == "pending_human_review"


def test_review_readiness_benchmark_covers_seeded_and_trace_examples():
    rows = build_review_readiness_benchmark_rows()
    markdown = render_review_readiness_benchmark_markdown(rows)
    examples = {row.example for row in rows}

    assert {
        "wf-invoice-2001",
        "wf-invoice-3001",
        "openai_agents_invoice_review",
        "ollama_local_invoice_review",
        "openai_human_in_the_loop_invoice_reject",
        "mcp_same_day_payment_review",
    }.issubset(examples)
    assert "| Example | Source | Policy rule IDs | Authority chain | Review case | Human decision reason | Review readiness score | Status |" in markdown
    assert "review_ready" in markdown or "review ready" in markdown
