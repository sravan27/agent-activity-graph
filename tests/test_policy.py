from __future__ import annotations

from datetime import datetime, timezone

from agent_activity_graph.policy.evaluator import PolicyEvaluator
from agent_activity_graph.sdk.events import ActorType, PolicyStatus, WorkflowEvent


def _event(action_type: str, amount: int, **overrides) -> WorkflowEvent:
    data = {
        "timestamp": datetime(2026, 3, 31, 10, 0, tzinfo=timezone.utc),
        "workflow_id": "wf-policy",
        "workflow_name": "Invoice Approval with Agent Participation",
        "process_step": "approval_recommendation",
        "actor_type": ActorType.AGENT,
        "actor_id": "ap-agent",
        "actor_name": "AP Agent",
        "action_type": action_type,
        "action_summary": "Test policy event.",
        "tool_name": "policy-evaluator",
        "target_system": "policy-engine",
        "business_object_type": "invoice",
        "business_object_id": "INV-POLICY",
        "permission_scope": "invoice:approve:proposal",
        "metadata": {
            "invoice_amount": amount,
            "currency": "USD",
            "vendor_id": "VENDOR-1",
            "po_number": "PO-1",
            "agent_approval_threshold": 5000,
        },
    }
    data.update(overrides)
    return WorkflowEvent(**data)


def test_policy_escalates_large_invoice_proposals():
    decision = PolicyEvaluator().evaluate(_event("propose_invoice_approval", 12000))

    assert decision.decision == PolicyStatus.ESCALATED
    assert any(rule.rule_id == "large_invoice_requires_escalation" for rule in decision.violated_rules)


def test_policy_blocks_agent_auto_approval_over_threshold():
    decision = PolicyEvaluator().evaluate(
        _event("approve_invoice", 12000, target_system="erp-approvals", permission_scope="invoice:approve:under_threshold")
    )

    assert decision.decision == PolicyStatus.BLOCKED
    assert any(rule.rule_id == "agent_auto_approval_threshold" for rule in decision.violated_rules)


def test_policy_blocks_missing_required_fields():
    decision = PolicyEvaluator().evaluate(
        _event(
            "propose_invoice_approval",
            2000,
            metadata={
                "invoice_amount": 2000,
                "currency": "USD",
                "vendor_id": "VENDOR-1",
                "po_number": None,
                "agent_approval_threshold": 5000,
            },
        )
    )

    assert decision.decision == PolicyStatus.BLOCKED
    assert any(rule.rule_id == "required_fields_for_approval" for rule in decision.violated_rules)

