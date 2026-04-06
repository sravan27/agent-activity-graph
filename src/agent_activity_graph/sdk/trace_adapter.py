from __future__ import annotations

import re
from typing import Any

from agent_activity_graph.sdk.events import (
    ActorType,
    OutcomeStatus,
    PolicyStatus,
    RuleViolation,
    TraceIngestionRequest,
    TraceSource,
    TraceSpan,
    WorkflowEvent,
)


def _attr(attributes: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in attributes and attributes[key] not in (None, ""):
            return attributes[key]
    return None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return text or "trace_step"


def _span_kind(span: TraceSpan) -> str:
    return str(_attr(span.attributes, "openinference.span.kind", "span.kind", "aag.span_kind") or "").lower()


def _resolve_policy_status(attributes: dict[str, Any]) -> PolicyStatus:
    raw = str(_attr(attributes, "aag.policy_status") or PolicyStatus.ALLOWED.value)
    return PolicyStatus(raw)


def _resolve_outcome_status(span: TraceSpan, policy_status: PolicyStatus) -> OutcomeStatus:
    raw = _attr(span.attributes, "aag.outcome_status", "status") or span.status
    if raw:
        return OutcomeStatus(str(raw))
    if policy_status == PolicyStatus.BLOCKED:
        return OutcomeStatus.SKIPPED
    if policy_status in {PolicyStatus.ESCALATED, PolicyStatus.REQUIRES_HUMAN_REVIEW}:
        return OutcomeStatus.PENDING
    return OutcomeStatus.SUCCESS


def _resolve_action_type(source: TraceSource, span: TraceSpan) -> str:
    attributes = span.attributes
    explicit = _attr(attributes, "aag.action_type")
    if explicit:
        return str(explicit)
    if _attr(attributes, "mcp.tool.name", "tool.name", "gen_ai.tool.name", "message.tool.name"):
        return "call_mcp_tool" if source == TraceSource.MCP else "call_tool"
    if str(_attr(attributes, "aag.actor_type") or "").lower() == ActorType.HUMAN.value:
        return "human_review_step"
    if _span_kind(span) == "agent":
        return "agent_run_step"
    if _span_kind(span) == "tool":
        return "call_tool"
    return _slug(span.name)


def _resolve_actor_type(source: TraceSource, span: TraceSpan, action_type: str) -> ActorType:
    attributes = span.attributes
    explicit = _attr(attributes, "aag.actor_type")
    if explicit:
        return ActorType(str(explicit))
    if action_type == "policy_evaluation":
        return ActorType.SYSTEM
    if source == TraceSource.MCP:
        return ActorType.AGENT
    if _span_kind(span) in {"agent", "tool", "chain", "llm"}:
        return ActorType.AGENT
    return ActorType.SYSTEM


def _resolve_actor_identity(source: TraceSource, span: TraceSpan, actor_type: ActorType) -> tuple[str, str]:
    attributes = span.attributes
    actor_id = _attr(
        attributes,
        "aag.actor_id",
        "agent.id",
        "agent.name",
        "gen_ai.agent.name",
        "openai.agent.name",
    )
    actor_name = _attr(
        attributes,
        "aag.actor_name",
        "agent.display_name",
        "agent.name",
        "gen_ai.agent.name",
        "openai.agent.name",
    )
    if actor_id and actor_name:
        return str(actor_id), str(actor_name)
    if actor_type == ActorType.SYSTEM:
        if _resolve_action_type(source, span) == "policy_evaluation":
            return "policy-engine", "Policy Engine"
        system_name = str(_attr(attributes, "service.name", "aag.source_system_ref") or "workflow-system")
        return _slug(system_name), system_name.replace("-", " ").title()
    if source == TraceSource.MCP:
        default_name = str(actor_name or actor_id or "MCP Agent Runtime")
        return _slug(str(actor_id or default_name)), default_name
    default_name = str(actor_name or actor_id or "Agent Runtime")
    return _slug(str(actor_id or default_name)), default_name


def _resolve_tool_name(span: TraceSpan) -> str | None:
    value = _attr(
        span.attributes,
        "aag.tool_name",
        "mcp.tool.name",
        "tool.name",
        "gen_ai.tool.name",
        "message.tool_calls.0.tool_call.function.name",
        "message.tool.name",
    )
    return str(value) if value else None


def _resolve_target_system(source: TraceSource, span: TraceSpan, action_type: str) -> str | None:
    attributes = span.attributes
    explicit = _attr(attributes, "aag.target_system")
    if explicit:
        return str(explicit)
    if action_type == "policy_evaluation":
        return "policy-engine"
    server_name = _attr(attributes, "mcp.server.name", "server.address")
    if server_name:
        return f"mcp:{server_name}"
    if source == TraceSource.OPENAI_AGENTS and _resolve_tool_name(span):
        return "tool-runtime"
    service_name = _attr(attributes, "service.name")
    return str(service_name) if service_name else None


def _resolve_permission_scope(actor_type: ActorType, span: TraceSpan, action_type: str) -> str | None:
    attributes = span.attributes
    explicit = _attr(attributes, "aag.permission_scope")
    if explicit:
        return str(explicit)
    if actor_type == ActorType.SYSTEM and action_type == "policy_evaluation":
        return "policy:evaluate"
    if actor_type == ActorType.HUMAN:
        return "invoice:review"
    if actor_type == ActorType.AGENT and _resolve_tool_name(span):
        return "tool:invoke"
    if actor_type == ActorType.AGENT:
        return "agent:act"
    return None


def _build_metadata(request: TraceIngestionRequest, span: TraceSpan) -> dict[str, Any]:
    metadata = dict(request.workflow.workflow_defaults)
    inline = _attr(span.attributes, "aag.metadata")
    if isinstance(inline, dict):
        metadata.update(inline)

    for key, value in span.attributes.items():
        if not key.startswith("aag.metadata.") or value in (None, ""):
            continue
        metadata[key.removeprefix("aag.metadata.")] = value

    for attr_key, metadata_key in {
        "aag.headline": "headline",
        "aag.why_it_mattered": "why_it_mattered",
        "aag.business_consequence": "business_consequence",
        "aag.candidate_actor_type": "candidate_actor_type",
        "aag.candidate_actor_id": "candidate_actor_id",
        "aag.candidate_action_type": "candidate_action_type",
        "aag.candidate_target_system": "candidate_target_system",
    }.items():
        value = _attr(span.attributes, attr_key)
        if value not in (None, ""):
            metadata[metadata_key] = value

    return metadata


def _build_policy_payload(span: TraceSpan, policy_status: PolicyStatus, rule_ids: list[str]) -> dict[str, Any]:
    explanation = str(
        _attr(span.attributes, "aag.policy_explanation", "aag.action_summary") or span.name
    )
    recommended_action = str(
        _attr(span.attributes, "aag.recommended_next_action")
        or (
            "Continue the workflow and keep recording evidence."
            if policy_status == PolicyStatus.ALLOWED
            else "Route the next step through human review."
        )
    )
    violations = [
        RuleViolation(
            rule_id=rule_id,
            rule_name=rule_id.replace("_", " ").title(),
            decision=policy_status,
            message=explanation,
            recommended_action=recommended_action,
        ).model_dump(mode="json")
        for rule_id in rule_ids
    ]
    return {
        "source": "preserved",
        "decision": policy_status.value,
        "violated_rules": violations,
        "explanation": explanation,
        "recommended_next_action": recommended_action,
    }


def _default_review_state(actor_type: ActorType, action_type: str, policy_status: PolicyStatus) -> str | None:
    if actor_type == ActorType.HUMAN and action_type in {"human_approve_invoice", "reject_invoice", "human_review_step"}:
        return "resolved_by_human"
    if policy_status in {PolicyStatus.ESCALATED, PolicyStatus.REQUIRES_HUMAN_REVIEW, PolicyStatus.BLOCKED}:
        return "pending_human_review"
    return None


def map_trace_to_workflow_events(request: TraceIngestionRequest) -> list[WorkflowEvent]:
    spans = sorted(request.spans, key=lambda span: (span.start_time, span.span_id))
    events: list[WorkflowEvent] = []
    previous_event_id: str | None = None

    for index, span in enumerate(spans, start=1):
        action_type = _resolve_action_type(request.source, span)
        actor_type = _resolve_actor_type(request.source, span, action_type)
        actor_id, actor_name = _resolve_actor_identity(request.source, span, actor_type)
        policy_status = _resolve_policy_status(span.attributes)
        policy_rule_ids = _string_list(_attr(span.attributes, "aag.policy_rule_ids"))
        metadata = _build_metadata(request, span)
        metadata["_policy"] = _build_policy_payload(span, policy_status, policy_rule_ids)

        event = WorkflowEvent(
            event_id=str(_attr(span.attributes, "aag.event_id") or f"evt_{request.workflow.workflow_id}_{index:02d}"),
            timestamp=span.start_time,
            workflow_id=request.workflow.workflow_id,
            workflow_name=request.workflow.workflow_name,
            process_step=str(_attr(span.attributes, "aag.workflow.process_step") or _slug(action_type)),
            actor_type=actor_type,
            actor_id=actor_id,
            actor_name=actor_name,
            action_type=action_type,
            action_summary=str(_attr(span.attributes, "aag.action_summary") or span.name),
            tool_name=_resolve_tool_name(span),
            target_system=_resolve_target_system(request.source, span, action_type),
            business_object_type=request.workflow.business_object_type,
            business_object_id=request.workflow.business_object_id,
            permission_scope=_resolve_permission_scope(actor_type, span, action_type),
            authority_subject=_attr(span.attributes, "aag.authority_subject"),
            authority_delegation_source=_attr(span.attributes, "aag.authority_delegation_source"),
            policy_status=policy_status,
            policy_rule_ids=policy_rule_ids,
            review_case_id=_attr(span.attributes, "aag.review_case_id"),
            review_state=str(
                _attr(span.attributes, "aag.review_state") or _default_review_state(actor_type, action_type, policy_status)
            )
            if _attr(span.attributes, "aag.review_state") or _default_review_state(actor_type, action_type, policy_status)
            else None,
            human_decision_reason=_attr(span.attributes, "aag.human_decision_reason"),
            due_by=_attr(span.attributes, "aag.due_by"),
            source_trace_ref=str(
                _attr(
                    span.attributes,
                    "aag.source_trace_ref",
                    "trace_id",
                    "trace.id",
                    "gen_ai.trace_id",
                    "openinference.trace.id",
                )
                or f"{request.source.value}:{request.workflow.workflow_id}"
            ),
            source_system_ref=_attr(
                span.attributes,
                "aag.source_system_ref",
                "service.name",
                "mcp.server.name",
                "server.address",
            ),
            outcome_status=_resolve_outcome_status(span, policy_status),
            parent_event_id=(
                str(_attr(span.attributes, "aag.parent_event_id") or previous_event_id)
                if (_attr(span.attributes, "aag.parent_event_id") or previous_event_id)
                else None
            ),
            metadata=metadata,
        )
        events.append(event)
        previous_event_id = event.event_id

    return events
