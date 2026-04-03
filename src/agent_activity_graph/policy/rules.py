from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

from agent_activity_graph.sdk.events import ActorType, PolicyStatus, RuleViolation, WorkflowEvent


@dataclass(frozen=True)
class RuntimeRule:
    rule_id: str
    name: str
    description: str
    decision: PolicyStatus
    config: dict
    evaluator: Callable[[WorkflowEvent], RuleViolation | None]


def _auto_approval_threshold() -> float:
    return float(os.getenv("AAG_AUTO_APPROVAL_THRESHOLD", "5000"))


def _effective_action_type(event: WorkflowEvent) -> str:
    return str(event.metadata.get("candidate_action_type") or event.action_type)


def _effective_actor_type(event: WorkflowEvent) -> ActorType:
    candidate = event.metadata.get("candidate_actor_type")
    return ActorType(candidate) if candidate else event.actor_type


def _effective_actor_id(event: WorkflowEvent) -> str:
    return str(event.metadata.get("candidate_actor_id") or event.actor_id)


def _effective_target_system(event: WorkflowEvent) -> str | None:
    return event.metadata.get("candidate_target_system") or event.target_system


def _require_fields_for_approval(event: WorkflowEvent) -> RuleViolation | None:
    if _effective_action_type(event) not in {
        "check_purchase_order",
        "propose_invoice_approval",
        "approve_invoice",
    }:
        return None

    required = ["invoice_amount", "vendor_id", "currency", "po_number"]
    missing = [field for field in required if not event.metadata.get(field)]
    if not missing:
        return None

    return RuleViolation(
        rule_id="required_fields_for_approval",
        rule_name="Required fields for approval",
        decision=PolicyStatus.BLOCKED,
        message=f"Approval path is missing required invoice fields: {', '.join(missing)}.",
        recommended_action="Repair the invoice record before the agent continues.",
    )


def _enforce_agent_system_access(event: WorkflowEvent) -> RuleViolation | None:
    actor_type = _effective_actor_type(event)
    target_system = _effective_target_system(event)
    if actor_type != ActorType.AGENT or not target_system:
        return None

    allowed_systems = {
        "ap-agent": {"inbox", "erp-read", "erp-approvals", "policy-engine"},
        "procurement-agent": {"erp-read"},
    }
    actor_id = _effective_actor_id(event)
    permitted = allowed_systems.get(actor_id, set())
    if target_system in permitted:
        return None

    return RuleViolation(
        rule_id="agent_system_access",
        rule_name="Agent system access restriction",
        decision=PolicyStatus.BLOCKED,
        message=f"Agent {actor_id} is not allowed to write to {target_system}.",
        recommended_action="Route the action to an authorized human or narrow the system scope.",
    )


def _require_escalation_for_large_proposals(event: WorkflowEvent) -> RuleViolation | None:
    if _effective_actor_type(event) != ActorType.AGENT or _effective_action_type(event) != "propose_invoice_approval":
        return None

    amount = float(event.metadata.get("invoice_amount", 0))
    threshold = float(event.metadata.get("agent_approval_threshold", _auto_approval_threshold()))
    if amount <= threshold:
        return None

    return RuleViolation(
        rule_id="large_invoice_requires_escalation",
        rule_name="Large invoice escalation",
        decision=PolicyStatus.ESCALATED,
        message=f"Invoice amount {amount:,.2f} exceeds the agent approval threshold of {threshold:,.2f}.",
        recommended_action="Escalate to a finance approver before any approval is executed.",
    )


def _block_agent_auto_approval_over_threshold(event: WorkflowEvent) -> RuleViolation | None:
    if _effective_actor_type(event) != ActorType.AGENT or _effective_action_type(event) != "approve_invoice":
        return None

    amount = float(event.metadata.get("invoice_amount", 0))
    threshold = float(event.metadata.get("agent_approval_threshold", _auto_approval_threshold()))
    if amount <= threshold:
        return None

    return RuleViolation(
        rule_id="agent_auto_approval_threshold",
        rule_name="Agent auto-approval threshold",
        decision=PolicyStatus.BLOCKED,
        message=f"Agent approval is blocked because {amount:,.2f} is above {threshold:,.2f}.",
        recommended_action="Wait for a human approver to confirm or reject the invoice.",
    )


def _require_human_review_for_payment_release(event: WorkflowEvent) -> RuleViolation | None:
    if _effective_actor_type(event) != ActorType.AGENT or _effective_action_type(event) != "release_payment":
        return None

    return RuleViolation(
        rule_id="payment_release_requires_human",
        rule_name="Payment release requires human review",
        decision=PolicyStatus.REQUIRES_HUMAN_REVIEW,
        message="Agents may prepare a payment release, but a human must authorize the final release.",
        recommended_action="Assign the release step to an accounts payable manager.",
    )


DEFAULT_RULES: list[RuntimeRule] = [
    RuntimeRule(
        rule_id="required_fields_for_approval",
        name="Required fields for approval",
        description="Approval can proceed only when required invoice fields exist.",
        decision=PolicyStatus.BLOCKED,
        config={"required_fields": ["invoice_amount", "vendor_id", "currency", "po_number"]},
        evaluator=_require_fields_for_approval,
    ),
    RuntimeRule(
        rule_id="agent_system_access",
        name="Agent system access restriction",
        description="Only specific agents can touch specific systems.",
        decision=PolicyStatus.BLOCKED,
        config={
            "allowed_systems": {
                "ap-agent": ["inbox", "erp-read", "erp-approvals", "policy-engine"],
                "procurement-agent": ["erp-read"],
            }
        },
        evaluator=_enforce_agent_system_access,
    ),
    RuntimeRule(
        rule_id="large_invoice_requires_escalation",
        name="Large invoice escalation",
        description="Large invoice proposals require escalation before approval.",
        decision=PolicyStatus.ESCALATED,
        config={"agent_approval_threshold": _auto_approval_threshold()},
        evaluator=_require_escalation_for_large_proposals,
    ),
    RuntimeRule(
        rule_id="agent_auto_approval_threshold",
        name="Agent auto-approval threshold",
        description="Agents cannot auto-approve invoices above the threshold.",
        decision=PolicyStatus.BLOCKED,
        config={"agent_approval_threshold": _auto_approval_threshold()},
        evaluator=_block_agent_auto_approval_over_threshold,
    ),
    RuntimeRule(
        rule_id="payment_release_requires_human",
        name="Payment release requires human review",
        description="Certain actions require human review before the workflow can continue.",
        decision=PolicyStatus.REQUIRES_HUMAN_REVIEW,
        config={},
        evaluator=_require_human_review_for_payment_release,
    ),
]
