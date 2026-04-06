from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx

from agent_activity_graph.policy.evaluator import PolicyEvaluator
from agent_activity_graph.sdk.events import (
    ActorType,
    PolicyStatus,
    TraceIngestionRequest,
    TraceSource,
    TraceSpan,
    TraceWorkflowContext,
    WorkflowEvent,
)
from agent_activity_graph.utils.time import ensure_utc, utcnow

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "gemma3:4b"


def default_invoice_payload() -> dict[str, Any]:
    return {
        "invoice_id": "INV-OLLAMA-LOCAL-7001",
        "vendor_id": "VENDOR-OLLAMA-7001",
        "vendor_name": "Northstar Analytics",
        "invoice_amount": 12750,
        "currency": "USD",
        "po_number": "PO-OLLAMA-7001",
        "invoice_due_date": "2026-04-08",
        "payment_batch_cutoff": "2026-04-08T14:00:00Z",
        "payment_terms": "Net 10",
        "cost_center": "FINANCE-TRANSFORM-08",
        "request_reason": "Quarter-close analytics implementation",
        "agent_approval_threshold": 5000,
        "risk_category": "delayed_payment_risk",
        "business_consequence": "If finance review lands after the payment cut-off, the vendor payment moves to the next business day.",
    }


def lookup_purchase_order(invoice: dict[str, Any]) -> dict[str, Any]:
    return {
        "po_number": invoice["po_number"],
        "status": "matched",
        "budget_status": "approved",
        "amount_authorized": invoice["invoice_amount"],
        "cost_center": invoice["cost_center"],
    }


def _extract_json_object(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("Model output did not contain a JSON object.")
    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("Model output JSON must be an object.")
    return value


def run_ollama_json(
    prompt: str,
    *,
    model: str = DEFAULT_OLLAMA_MODEL,
    base_url: str = DEFAULT_OLLAMA_BASE_URL,
) -> dict[str, Any]:
    response = httpx.post(
        f"{base_url.rstrip('/')}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {"temperature": 0},
        },
        timeout=120.0,
    )
    response.raise_for_status()
    payload = response.json()
    return _extract_json_object(str(payload.get("response") or "{}"))


def _classification_prompt(invoice: dict[str, Any]) -> str:
    return (
        "You are an accounts payable triage agent.\n"
        "Read the invoice facts and return JSON only with keys "
        'classification, control_lane, risk_note, action_summary, headline.\n'
        f"Invoice facts: {json.dumps(invoice, sort_keys=True)}\n"
        "The invoice is in a finance approval workflow. Keep the wording concise and operational."
    )


def _proposal_prompt(invoice: dict[str, Any], po_record: dict[str, Any], classification: dict[str, Any]) -> str:
    return (
        "You are an accounts payable approval-preparation agent.\n"
        "Return JSON only with keys recommendation, why_it_mattered, review_summary, reviewer_note.\n"
        f"Invoice facts: {json.dumps(invoice, sort_keys=True)}\n"
        f"PO check: {json.dumps(po_record, sort_keys=True)}\n"
        f"Classification: {json.dumps(classification, sort_keys=True)}\n"
        "Prepare a recommendation packet for finance review without claiming final approval authority."
    )


def _proposal_event(
    workflow_id: str,
    workflow_name: str,
    invoice: dict[str, Any],
    action_summary: str,
) -> WorkflowEvent:
    return WorkflowEvent(
        workflow_id=workflow_id,
        workflow_name=workflow_name,
        process_step="approval_recommendation",
        actor_type=ActorType.AGENT,
        actor_id="ap-agent",
        actor_name="AP Agent",
        action_type="propose_invoice_approval",
        action_summary=action_summary,
        target_system="erp-approvals",
        business_object_type="invoice",
        business_object_id=invoice["invoice_id"],
        permission_scope="invoice:approve:proposal",
        authority_subject="AP Agent may prepare approval packets but cannot approve invoices above USD 5,000.",
        authority_delegation_source="Finance AP delegation policy v2026.03",
        metadata=dict(invoice),
    )


def generate_local_review_trace(
    *,
    model: str = DEFAULT_OLLAMA_MODEL,
    base_url: str = DEFAULT_OLLAMA_BASE_URL,
    trace_id: str | None = None,
    started_at: datetime | None = None,
    invoice: dict[str, Any] | None = None,
    classification_result: dict[str, Any] | None = None,
    proposal_result: dict[str, Any] | None = None,
) -> TraceIngestionRequest:
    invoice_payload = dict(default_invoice_payload() if invoice is None else invoice)
    run_started_at = ensure_utc(started_at or utcnow())
    trace_ref = trace_id or f"trace_local_ollama_{run_started_at.strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"
    po_record = lookup_purchase_order(invoice_payload)

    classification = classification_result or run_ollama_json(
        _classification_prompt(invoice_payload),
        model=model,
        base_url=base_url,
    )
    proposal = proposal_result or run_ollama_json(
        _proposal_prompt(invoice_payload, po_record, classification),
        model=model,
        base_url=base_url,
    )

    workflow_id = f"wf-ollama-local-{invoice_payload['invoice_id'].split('-')[-1].lower()}"
    workflow_name = "Invoice Approval with Agent Participation"
    review_case_id = f"review-{workflow_id}"
    due_by = invoice_payload["payment_batch_cutoff"]
    evaluator = PolicyEvaluator()
    proposal_event = _proposal_event(
        workflow_id,
        workflow_name,
        invoice_payload,
        str(proposal.get("recommendation") or "AP Agent prepared a recommendation packet for finance review."),
    )
    policy = evaluator.evaluate(proposal_event)

    workflow = TraceWorkflowContext(
        workflow_id=workflow_id,
        workflow_name=workflow_name,
        business_object_type="invoice",
        business_object_id=invoice_payload["invoice_id"],
        workflow_defaults={
            **invoice_payload,
            "po_lookup_status": po_record["status"],
            "po_budget_status": po_record["budget_status"],
            "runtime_origin": "local_ollama_agent",
            "ollama_model": model,
            "trace_fixture_basis": "Runtime-generated free local export from an Ollama-backed invoice approval agent.",
        },
    )

    spans = [
        TraceSpan(
            span_id="span-local-01",
            name="Classify invoice",
            start_time=run_started_at,
            attributes={
                "openinference.span.kind": "agent",
                "agent.id": "ap-agent",
                "agent.name": "AP Agent",
                "trace.id": trace_ref,
                "aag.workflow.process_step": "classification",
                "aag.action_summary": str(
                    classification.get("action_summary")
                    or "AP Agent classified the invoice into a controlled finance review lane."
                ),
                "aag.permission_scope": "invoice:classify",
                "aag.authority_subject": "AP Agent may classify invoices and prepare approval packets.",
                "aag.authority_delegation_source": "Finance AP delegation policy v2026.03",
                "aag.headline": str(
                    classification.get("headline")
                    or "Agent classified the invoice into a finance-controlled review lane"
                ),
                "aag.metadata.classification": classification.get("classification"),
                "aag.metadata.control_lane": classification.get("control_lane"),
                "aag.metadata.risk_note": classification.get("risk_note"),
                "service.name": "ollama-agent-runtime",
            },
        ),
        TraceSpan(
            span_id="span-local-02",
            name="Lookup purchase order",
            start_time=run_started_at + timedelta(minutes=1),
            attributes={
                "openinference.span.kind": "tool",
                "agent.id": "ap-agent",
                "agent.name": "AP Agent",
                "trace.id": trace_ref,
                "tool.name": "lookup_purchase_order",
                "aag.tool_name": "lookup_purchase_order",
                "aag.workflow.process_step": "po_check",
                "aag.action_summary": "AP Agent verified the PO record before preparing the approval recommendation.",
                "aag.permission_scope": "erp:read:purchase_orders",
                "aag.authority_subject": "AP Agent may retrieve supporting PO records through approved read-only finance tools.",
                "aag.authority_delegation_source": "Finance AP delegation policy v2026.03",
                "aag.target_system": "erp-read",
                "aag.headline": "Agent pulled PO evidence from the finance system",
                "aag.why_it_mattered": "The approval packet included source-system evidence before the policy gate ran.",
                "aag.metadata.po_status": po_record["status"],
                "aag.metadata.budget_status": po_record["budget_status"],
                "service.name": "local-erp-tool",
            },
        ),
        TraceSpan(
            span_id="span-local-03",
            name="Prepare approval recommendation",
            start_time=run_started_at + timedelta(minutes=2),
            attributes={
                "openinference.span.kind": "agent",
                "agent.id": "ap-agent",
                "agent.name": "AP Agent",
                "trace.id": trace_ref,
                "aag.action_type": "propose_invoice_approval",
                "aag.workflow.process_step": "approval_recommendation",
                "aag.action_summary": str(
                    proposal.get("recommendation")
                    or "AP Agent prepared the approval packet with invoice, PO, and payment cut-off context."
                ),
                "aag.permission_scope": "invoice:approve:proposal",
                "aag.authority_subject": "AP Agent may prepare approval packets but cannot approve invoices above USD 5,000.",
                "aag.authority_delegation_source": "Finance AP delegation policy v2026.03",
                "aag.headline": "Agent assembled the approval packet for finance review",
                "aag.why_it_mattered": str(
                    proposal.get("why_it_mattered")
                    or "The agent accelerated review preparation without crossing the final approval boundary."
                ),
                "aag.metadata.review_summary": proposal.get("review_summary"),
                "aag.metadata.reviewer_note": proposal.get("reviewer_note"),
                "aag.target_system": "erp-approvals",
                "service.name": "ollama-agent-runtime",
            },
        ),
        TraceSpan(
            span_id="span-local-04",
            name="Policy evaluation",
            start_time=run_started_at + timedelta(minutes=3),
            attributes={
                "trace.id": trace_ref,
                "aag.action_type": "policy_evaluation",
                "aag.workflow.process_step": "policy_gate",
                "aag.action_summary": "Policy engine evaluated the approval recommendation against delegated authority.",
                "aag.policy_status": policy.decision.value,
                "aag.policy_rule_ids": [violation.rule_id for violation in policy.violated_rules],
                "aag.policy_explanation": policy.explanation,
                "aag.recommended_next_action": policy.recommended_next_action,
                "aag.review_case_id": review_case_id if policy.decision != PolicyStatus.ALLOWED else None,
                "aag.review_state": "pending_human_review" if policy.decision != PolicyStatus.ALLOWED else None,
                "aag.due_by": due_by if policy.decision != PolicyStatus.ALLOWED else None,
                "aag.headline": "Policy gate escalated the invoice into a finance review case"
                if policy.decision != PolicyStatus.ALLOWED
                else "Policy gate allowed the invoice to remain in the agent lane",
                "service.name": "policy-engine",
            },
        ),
        TraceSpan(
            span_id="span-local-05",
            name="Finance review",
            start_time=run_started_at + timedelta(minutes=8),
            attributes={
                "trace.id": trace_ref,
                "aag.actor_type": "human",
                "aag.actor_id": "finance-director-7",
                "aag.actor_name": "Finance Director",
                "aag.action_type": "human_approve_invoice",
                "aag.workflow.process_step": "finance_review",
                "aag.action_summary": "Finance Director approved the invoice after reviewing the PO evidence, control lane, and payment cut-off risk.",
                "aag.permission_scope": "invoice:approve:high_value",
                "aag.authority_subject": "Finance Director holds final approval authority for invoices above the delegated agent threshold.",
                "aag.authority_delegation_source": "Finance approval matrix FY2026",
                "aag.review_case_id": review_case_id,
                "aag.review_state": "resolved_by_human",
                "aag.human_decision_reason": "Approved because the PO matched, the spend was authorized, and missing the cut-off would have delayed vendor payment.",
                "aag.headline": "Finance Director resolved the review case and approved the invoice",
                "service.name": "finance-review-console",
            },
        ),
    ]

    return TraceIngestionRequest(
        source=TraceSource.GENERIC_OPENINFERENCE,
        workflow=workflow,
        spans=spans,
    )
