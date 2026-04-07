from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agent_activity_graph.db.repository import ingest_event, list_incidents
from agent_activity_graph.demo import seed as demo_seed
from agent_activity_graph.policy.evaluator import PolicyEvaluator
from agent_activity_graph.replay.evidence_pack import build_evidence_pack
from agent_activity_graph.replay.incident import build_incident_detail
from agent_activity_graph.replay.timeline import build_replay_timeline
from agent_activity_graph.sdk.events import ActorType, OutcomeStatus, WorkflowEvent
from agent_activity_graph.ui.views import _workflow_context

BASE_TIME = datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc)


def _event(
    sequence_number: int,
    *,
    workflow_id: str,
    business_object_id: str,
    process_step: str,
    actor_type: ActorType,
    actor_id: str,
    actor_name: str,
    action_type: str,
    action_summary: str,
    permission_scope: str,
    metadata: dict,
    parent_event_id: str | None = None,
    target_system: str | None = None,
    tool_name: str | None = None,
    outcome_status: OutcomeStatus = OutcomeStatus.SUCCESS,
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=f"evt_{workflow_id}_{sequence_number:02d}",
        timestamp=BASE_TIME + timedelta(minutes=sequence_number),
        workflow_id=workflow_id,
        workflow_name="Invoice Approval with Agent Participation",
        process_step=process_step,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_name=actor_name,
        action_type=action_type,
        action_summary=action_summary,
        tool_name=tool_name,
        target_system=target_system,
        business_object_type="invoice",
        business_object_id=business_object_id,
        permission_scope=permission_scope,
        parent_event_id=parent_event_id,
        outcome_status=outcome_status,
        metadata=metadata,
    )


def _ingest_dense_review_flow(session, workflow_id: str = "wf-invoice-dense") -> None:
    evaluator = PolicyEvaluator()
    meta = {
        "invoice_amount": 12000,
        "currency": "USD",
        "vendor_id": "V-DENSE",
        "vendor_name": "Meridian Controls",
        "po_number": "PO-7711",
        "payment_batch_cutoff": "2026-04-01T14:00:00Z",
        "invoice_due_date": "2026-04-01",
        "cost_center": "OPS-99",
        "payment_terms": "Net 10",
        "risk_category": "delayed_payment_risk",
        "business_consequence": "Dense review path risks missing same-day payment if handoffs take too long.",
    }
    events = [
        _event(
            1,
            workflow_id=workflow_id,
            business_object_id="INV-DENSE",
            process_step="invoice_received",
            actor_type=ActorType.SYSTEM,
            actor_id="ap-inbox",
            actor_name="AP Inbox",
            action_type="invoice_received",
            action_summary="Invoice arrived.",
            target_system="inbox",
            permission_scope="invoice:intake",
            metadata=meta,
        ),
        _event(
            2,
            workflow_id=workflow_id,
            business_object_id="INV-DENSE",
            process_step="classification",
            actor_type=ActorType.AGENT,
            actor_id="ap-agent",
            actor_name="AP Agent",
            action_type="classify_invoice",
            action_summary="Agent classified invoice.",
            target_system="inbox",
            permission_scope="invoice:classify",
            parent_event_id=f"evt_{workflow_id}_01",
            metadata={**meta, "headline": "Agent classified invoice"},
        ),
        _event(
            3,
            workflow_id=workflow_id,
            business_object_id="INV-DENSE",
            process_step="po_check",
            actor_type=ActorType.AGENT,
            actor_id="ap-agent",
            actor_name="AP Agent",
            action_type="check_purchase_order",
            action_summary="Agent checked the purchase order.",
            target_system="erp-read",
            permission_scope="erp:read:purchase_orders",
            parent_event_id=f"evt_{workflow_id}_02",
            metadata=meta,
        ),
        _event(
            4,
            workflow_id=workflow_id,
            business_object_id="INV-DENSE",
            process_step="approval_recommendation",
            actor_type=ActorType.AGENT,
            actor_id="ap-agent",
            actor_name="AP Agent",
            action_type="prepare_approval_recommendation",
            action_summary="Agent prepared the first recommendation.",
            target_system="erp-read",
            permission_scope="invoice:approve:proposal",
            parent_event_id=f"evt_{workflow_id}_03",
            metadata=meta,
        ),
        _event(
            5,
            workflow_id=workflow_id,
            business_object_id="INV-DENSE",
            process_step="policy_gate",
            actor_type=ActorType.SYSTEM,
            actor_id="policy-engine",
            actor_name="Policy Engine",
            action_type="policy_evaluation",
            action_summary="Policy engine escalated the first recommendation.",
            target_system="policy-engine",
            permission_scope="policy:evaluate",
            parent_event_id=f"evt_{workflow_id}_04",
            metadata={
                **meta,
                "headline": "Initial policy gate escalated the invoice",
                "candidate_actor_type": "agent",
                "candidate_actor_id": "ap-agent",
                "candidate_action_type": "propose_invoice_approval",
                "candidate_target_system": "erp-approvals",
            },
        ),
        _event(
            6,
            workflow_id=workflow_id,
            business_object_id="INV-DENSE",
            process_step="manager_review",
            actor_type=ActorType.HUMAN,
            actor_id="finance-manager",
            actor_name="Finance Manager",
            action_type="annotate_invoice",
            action_summary="Finance manager added a review note.",
            target_system="finance-console",
            permission_scope="invoice:review",
            parent_event_id=f"evt_{workflow_id}_05",
            metadata=meta,
        ),
        _event(
            7,
            workflow_id=workflow_id,
            business_object_id="INV-DENSE",
            process_step="agent_revision",
            actor_type=ActorType.AGENT,
            actor_id="ap-agent",
            actor_name="AP Agent",
            action_type="prepare_approval_recommendation",
            action_summary="Agent revised the recommendation packet.",
            target_system="erp-read",
            permission_scope="invoice:approve:proposal",
            parent_event_id=f"evt_{workflow_id}_06",
            metadata={
                **meta,
                "business_consequence": "Further delay pushes the invoice out of same-day payment.",
            },
        ),
        _event(
            8,
            workflow_id=workflow_id,
            business_object_id="INV-DENSE",
            process_step="policy_gate_2",
            actor_type=ActorType.SYSTEM,
            actor_id="policy-engine",
            actor_name="Policy Engine",
            action_type="policy_evaluation",
            action_summary="Policy engine blocked the revised execution.",
            target_system="policy-engine",
            permission_scope="policy:evaluate",
            parent_event_id=f"evt_{workflow_id}_07",
            metadata={
                **meta,
                "po_number": None,
                "headline": "Second policy gate blocked the revised invoice",
                "business_consequence": "Further delay pushes the invoice out of same-day payment.",
                "candidate_actor_type": "agent",
                "candidate_actor_id": "ap-agent",
                "candidate_action_type": "approve_invoice",
                "candidate_target_system": "erp-approvals",
            },
        ),
        _event(
            9,
            workflow_id=workflow_id,
            business_object_id="INV-DENSE",
            process_step="approval_execution",
            actor_type=ActorType.AGENT,
            actor_id="ap-agent",
            actor_name="AP Agent",
            action_type="approve_invoice",
            action_summary="Agent attempted approval after dense handoffs.",
            target_system="erp-approvals",
            permission_scope="invoice:approve:under_threshold",
            parent_event_id=f"evt_{workflow_id}_08",
            metadata={**meta, "po_number": None},
        ),
        _event(
            10,
            workflow_id=workflow_id,
            business_object_id="INV-DENSE",
            process_step="director_review",
            actor_type=ActorType.HUMAN,
            actor_id="finance-director",
            actor_name="Finance Director",
            action_type="reject_invoice",
            action_summary="Finance director rejected the invoice.",
            target_system="erp-approvals",
            permission_scope="invoice:reject",
            parent_event_id=f"evt_{workflow_id}_09",
            metadata={**meta, "headline": "Finance Director rejected the invoice"},
        ),
    ]

    for event in events:
        ingest_event(session, event, evaluator=evaluator)


def test_seed_main_prints_deterministic_demo_path(monkeypatch, capsys):
    monkeypatch.setattr(demo_seed, "seed_demo_data", lambda: {"workflows": 3, "events": 20})

    demo_seed.main()
    output = capsys.readouterr().out

    assert "http://127.0.0.1:8000/" in output
    assert "http://127.0.0.1:8000/reviews" in output
    assert "http://127.0.0.1:8000/reviews/review-wf-invoice-3001" in output
    assert "http://127.0.0.1:8000/workflows/wf-invoice-3001/replay" in output
    assert "http://127.0.0.1:8000/incidents/inc_evt_wf_3001_05" in output
    assert "http://127.0.0.1:8000/incidents/inc_evt_wf_3001_05/evidence-pack" in output


def test_workflow_context_prefers_latest_available_metadata():
    events = [
        _event(
            1,
            workflow_id="wf-invoice-context",
            business_object_id="INV-CONTEXT",
            process_step="invoice_received",
            actor_type=ActorType.SYSTEM,
            actor_id="ap-inbox",
            actor_name="AP Inbox",
            action_type="invoice_received",
            action_summary="Invoice arrived.",
            permission_scope="invoice:intake",
            target_system="inbox",
            metadata={
                "invoice_amount": 3200,
                "currency": "USD",
                "vendor_id": "V-CTX",
                "po_number": "PO-CTX-1",
            },
        ),
        _event(
            2,
            workflow_id="wf-invoice-context",
            business_object_id="INV-CONTEXT",
            process_step="classification",
            actor_type=ActorType.AGENT,
            actor_id="ap-agent",
            actor_name="AP Agent",
            action_type="classify_invoice",
            action_summary="Agent classified invoice.",
            permission_scope="invoice:classify",
            target_system="inbox",
            parent_event_id="evt_wf-invoice-context_01",
            metadata={
                "invoice_amount": 4800,
                "currency": "USD",
                "vendor_id": "V-CTX",
                "vendor_name": "Context Vendor",
                "po_number": "PO-CTX-1",
                "payment_terms": "Net 15",
                "business_consequence": "Later metadata should become visible in the UI context.",
            },
        ),
    ]

    context = _workflow_context(events)

    assert context["invoice_amount"] == 4800
    assert context["vendor_name"] == "Context Vendor"
    assert context["payment_terms"] == "Net 15"
    assert context["business_consequence"] == "Later metadata should become visible in the UI context."


def test_replay_prefers_latest_decisive_policy_story_and_consequence(session):
    _ingest_dense_review_flow(session)

    replay = build_replay_timeline(session, "wf-invoice-dense", persist=False)
    incidents = list_incidents(session, workflow_id="wf-invoice-dense")

    assert replay.escalation_count == 1
    assert any(incident.incident_id == "inc_evt_wf-invoice-dense_05" for incident in incidents)
    assert "po_number" in replay.policy_story
    assert "12,000.00" in replay.policy_story
    assert replay.business_consequence == "Further delay pushes the invoice out of same-day payment."
    assert next(highlight for highlight in replay.highlights if highlight.label == "Policy gate").detail == (
        "Second policy gate blocked the revised invoice"
    )
    assert next(highlight for highlight in replay.highlights if highlight.label == "Human intervention").detail == (
        "Finance Director rejected the invoice"
    )


def test_incident_detail_keeps_more_context_for_dense_runs(session):
    _ingest_dense_review_flow(session)

    incidents = list_incidents(session, workflow_id="wf-invoice-dense")
    detail = build_incident_detail(session, incidents[0].incident_id)

    assert incidents[0].incident_id == "inc_evt_wf-invoice-dense_09"
    assert [event.event_id for event in detail.related_events] == [
        "evt_wf-invoice-dense_07",
        "evt_wf-invoice-dense_08",
        "evt_wf-invoice-dense_09",
        "evt_wf-invoice-dense_10",
    ]


def test_evidence_pack_stays_linked_to_latest_incident_story_under_density(session):
    _ingest_dense_review_flow(session)

    incidents = list_incidents(session, workflow_id="wf-invoice-dense")
    pack = build_evidence_pack(session, incidents[0].incident_id)

    assert pack.workflow_id == "wf-invoice-dense"
    assert pack.title == incidents[0].title
    assert pack.findings[0].label == "Incident trigger"
    assert pack.business_consequence == "Further delay pushes the invoice out of same-day payment."
