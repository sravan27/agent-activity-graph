from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from agent_activity_graph.sdk.events import ActorType, WorkflowEvent


def test_event_validation_accepts_valid_agent_event():
    event = WorkflowEvent(
        timestamp=datetime(2026, 3, 31, 10, 0, tzinfo=timezone.utc),
        workflow_id="wf-1",
        workflow_name="Invoice Approval with Agent Participation",
        process_step="classification",
        actor_type=ActorType.AGENT,
        actor_id="ap-agent",
        actor_name="AP Agent",
        action_type="classify_invoice",
        action_summary="Agent classified the invoice.",
        tool_name="invoice-classifier",
        target_system="inbox",
        business_object_type="invoice",
        business_object_id="INV-1",
        permission_scope="invoice:classify",
        metadata={"invoice_amount": 100},
    )

    assert event.actor_type == ActorType.AGENT
    assert event.permission_scope == "invoice:classify"


def test_event_validation_rejects_agent_action_without_permission_scope():
    with pytest.raises(ValidationError):
        WorkflowEvent(
            timestamp=datetime(2026, 3, 31, 10, 0, tzinfo=timezone.utc),
            workflow_id="wf-1",
            workflow_name="Invoice Approval with Agent Participation",
            process_step="classification",
            actor_type=ActorType.AGENT,
            actor_id="ap-agent",
            actor_name="AP Agent",
            action_type="classify_invoice",
            action_summary="Agent classified the invoice.",
            tool_name="invoice-classifier",
            target_system="inbox",
            business_object_type="invoice",
            business_object_id="INV-1",
            metadata={"invoice_amount": 100},
        )

