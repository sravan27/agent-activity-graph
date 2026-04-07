from __future__ import annotations

from datetime import datetime
import hashlib
import json
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from agent_activity_graph.db.models import (
    EventRecord,
    IncidentRecord,
    PolicyRuleRecord,
    ReplaySessionRecord,
    WorkflowRecord,
)
from agent_activity_graph.policy.evaluator import PolicyEvaluator
from agent_activity_graph.policy.rules import DEFAULT_RULES
from agent_activity_graph.sdk.events import (
    ActorType,
    EventIngestionResponse,
    IncidentSummary,
    OutcomeStatus,
    PolicyDecision,
    PolicyStatus,
    RuleViolation,
    WorkflowEvent,
    WorkflowSummary,
)
from agent_activity_graph.utils.time import ensure_utc, utcnow


def seed_policy_rules(session: Session) -> None:
    existing = {
        record.rule_key
        for record in session.scalars(select(PolicyRuleRecord)).all()
    }

    for rule in DEFAULT_RULES:
        if rule.rule_id in existing:
            continue
        session.add(
            PolicyRuleRecord(
                rule_key=rule.rule_id,
                name=rule.name,
                description=rule.description,
                decision_on_violation=rule.decision.value,
                config_json=rule.config,
                enabled=True,
            )
        )

    session.commit()


def list_policy_rules(session: Session) -> list[PolicyRuleRecord]:
    return session.scalars(select(PolicyRuleRecord).order_by(PolicyRuleRecord.rule_key)).all()


def map_event_record(record: EventRecord) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=record.event_id,
        timestamp=ensure_utc(record.timestamp),
        workflow_id=record.workflow_id,
        workflow_name=record.workflow_name,
        process_step=record.process_step,
        actor_type=record.actor_type,
        actor_id=record.actor_id,
        actor_name=record.actor_name,
        action_type=record.action_type,
        action_summary=record.action_summary,
        tool_name=record.tool_name,
        target_system=record.target_system,
        business_object_type=record.business_object_type,
        business_object_id=record.business_object_id,
        permission_scope=record.permission_scope,
        authority_subject=record.authority_subject,
        authority_delegation_source=record.authority_delegation_source,
        policy_status=record.policy_status,
        policy_rule_ids=list(record.policy_rule_ids_json or []),
        review_case_id=record.review_case_id,
        review_state=record.review_state,
        human_decision_reason=record.human_decision_reason,
        decision_code=record.decision_code,
        decision_rationale=record.decision_rationale,
        approved_exception_type=record.approved_exception_type,
        approver_role=record.approver_role,
        remediation_owner=record.remediation_owner,
        remediation_due_by=ensure_utc(record.remediation_due_by) if record.remediation_due_by else None,
        closure_status=record.closure_status,
        due_by=ensure_utc(record.due_by) if record.due_by else None,
        source_trace_ref=record.source_trace_ref,
        source_system_ref=record.source_system_ref,
        evidence_hash=record.evidence_hash,
        outcome_status=record.outcome_status,
        parent_event_id=record.parent_event_id,
        metadata=record.metadata_json or {},
    )


def map_workflow_record(record: WorkflowRecord) -> WorkflowSummary:
    return WorkflowSummary(
        workflow_id=record.workflow_id,
        workflow_name=record.workflow_name,
        business_object_type=record.business_object_type,
        business_object_id=record.business_object_id,
        status=record.status,
        current_step=record.current_step,
        started_at=ensure_utc(record.started_at),
        last_event_at=ensure_utc(record.last_event_at),
        event_count=record.event_count,
        incident_count=record.incident_count,
        last_policy_status=record.last_policy_status,
        final_outcome=record.final_outcome,
    )


def map_incident_record(record: IncidentRecord) -> IncidentSummary:
    return IncidentSummary(
        incident_id=record.incident_id,
        workflow_id=record.workflow_id,
        severity=record.severity,
        status=record.status,
        title=record.title,
        summary=record.summary,
        explanation=record.explanation,
        recommended_next_action=record.recommended_next_action,
        trigger_event_id=record.trigger_event_id,
        created_at=ensure_utc(record.created_at),
    )


def _normalize_policy_payload(event: WorkflowEvent, decision: PolicyDecision) -> dict:
    payload = decision.model_dump(mode="json")
    payload["source"] = "preserved" if event.metadata.get("_policy", {}).get("source") == "preserved" else "evaluated"
    return payload


def _decision_from_preserved_event(event: WorkflowEvent) -> PolicyDecision:
    payload = dict(event.metadata.get("_policy") or {})
    violated = payload.get("violated_rules") or []
    if violated:
        violations = [RuleViolation.model_validate(item) for item in violated]
    else:
        violations = [
            RuleViolation(
                rule_id=rule_id,
                rule_name=rule_id.replace("_", " ").title(),
                decision=event.policy_status,
                message=payload.get("explanation") or event.action_summary,
                recommended_action=payload.get("recommended_next_action")
                or "Review the mapped workflow evidence before continuing.",
            )
            for rule_id in event.policy_rule_ids
        ]

    return PolicyDecision(
        decision=event.policy_status,
        violated_rules=violations,
        explanation=str(payload.get("explanation") or event.action_summary),
        recommended_next_action=str(
            payload.get("recommended_next_action")
            or "Review the mapped workflow evidence before continuing."
        ),
    )


def _serialize_hash_payload(event: WorkflowEvent, previous_hash: str | None) -> str:
    metadata = dict(event.metadata)
    metadata.pop("_evidence", None)
    payload = event.model_dump(
        mode="json",
        exclude={"evidence_hash", "metadata"},
    )
    payload["metadata"] = metadata
    payload["previous_evidence_hash"] = previous_hash
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _compute_evidence_hash(event: WorkflowEvent, previous_hash: str | None) -> str:
    return hashlib.sha256(_serialize_hash_payload(event, previous_hash).encode("utf-8")).hexdigest()


def _get_latest_event_record(session: Session, workflow_id: str) -> EventRecord | None:
    return session.scalars(
        select(EventRecord)
        .where(EventRecord.workflow_id == workflow_id)
        .order_by(EventRecord.timestamp.desc(), EventRecord.event_id.desc())
        .limit(1)
    ).first()


def _decorate_evidence(session: Session, event: WorkflowEvent, decision: PolicyDecision) -> WorkflowEvent:
    previous_record = _get_latest_event_record(session, event.workflow_id)
    previous_hash = previous_record.evidence_hash if previous_record else None
    evidence_hash = _compute_evidence_hash(event, previous_hash)
    metadata = dict(event.metadata)
    metadata["_policy"] = _normalize_policy_payload(event, decision)
    metadata["_evidence"] = {
        "hash": evidence_hash,
        "previous_hash": previous_hash,
        "status": "verified",
    }
    return event.model_copy(
        update={
            "policy_rule_ids": list(dict.fromkeys(event.policy_rule_ids)),
            "evidence_hash": evidence_hash,
            "metadata": metadata,
        }
    )


def verify_evidence_chain(events: list[WorkflowEvent]) -> list[str]:
    issues: list[str] = []
    previous_hash: str | None = None
    for event in events:
        evidence_payload = dict(event.metadata.get("_evidence") or {})
        recorded_previous_hash = evidence_payload.get("previous_hash")
        if recorded_previous_hash != previous_hash:
            issues.append(
                f"{event.event_id}: expected previous hash {previous_hash or 'root'} but found {recorded_previous_hash or 'root'}."
            )

        expected_hash = _compute_evidence_hash(event, recorded_previous_hash)
        if event.evidence_hash != expected_hash:
            issues.append(f"{event.event_id}: recorded evidence hash does not match the stored event payload.")
        previous_hash = event.evidence_hash
    return issues


def _resolve_outcome_status(event: WorkflowEvent, decision: PolicyDecision) -> OutcomeStatus:
    if decision.decision == PolicyStatus.BLOCKED:
        return OutcomeStatus.SKIPPED
    if decision.decision in {PolicyStatus.ESCALATED, PolicyStatus.REQUIRES_HUMAN_REVIEW}:
        if event.outcome_status == OutcomeStatus.SUCCESS:
            return OutcomeStatus.PENDING
        return OutcomeStatus.PENDING
    return event.outcome_status


def _is_high_risk_write_boundary(event: WorkflowEvent) -> bool:
    if event.actor_type != ActorType.AGENT:
        return False
    if event.target_system not in {"erp-payments", "finance-approval-gateway"}:
        return False
    return event.action_type in {"approve_invoice", "release_payment", "call_mcp_tool"}


def _default_review_state(event: WorkflowEvent, decision: PolicyDecision) -> str | None:
    if event.actor_type == ActorType.HUMAN and event.action_type in {"human_approve_invoice", "reject_invoice", "human_review_step"}:
        return "resolved_by_human"
    if decision.decision != PolicyStatus.ALLOWED or _is_high_risk_write_boundary(event):
        return "pending_human_review"
    return event.review_state


def _ensure_review_case(event: WorkflowEvent, decision: PolicyDecision) -> WorkflowEvent:
    needs_case = decision.decision != PolicyStatus.ALLOWED or _is_high_risk_write_boundary(event)
    if not needs_case:
        return event

    metadata = dict(event.metadata)
    auto_created = False
    review_case_id = event.review_case_id
    if not review_case_id:
        review_case_id = f"review-{event.workflow_id}"
        auto_created = True
    if auto_created:
        metadata["_review_case"] = {
            "auto_created": True,
            "reason": "policy_gate_or_high_risk_write_boundary",
        }

    return event.model_copy(
        update={
            "review_case_id": review_case_id,
            "review_state": event.review_state or _default_review_state(event, decision),
            "metadata": metadata,
        }
    )


def _apply_policy(event: WorkflowEvent, decision: PolicyDecision) -> WorkflowEvent:
    metadata = dict(event.metadata)
    metadata["_policy"] = {**decision.model_dump(mode="json"), "source": "evaluated"}
    resolved_event = event.model_copy(
        update={
            "policy_status": decision.decision,
            "policy_rule_ids": [violation.rule_id for violation in decision.violated_rules],
            "outcome_status": _resolve_outcome_status(event, decision),
            "metadata": metadata,
        }
    )
    return _ensure_review_case(resolved_event, decision)


def _apply_preserved_policy(event: WorkflowEvent, decision: PolicyDecision) -> WorkflowEvent:
    metadata = dict(event.metadata)
    metadata["_policy"] = {**decision.model_dump(mode="json"), "source": "preserved"}
    resolved_event = event.model_copy(
        update={
            "policy_rule_ids": event.policy_rule_ids or [violation.rule_id for violation in decision.violated_rules],
            "outcome_status": _resolve_outcome_status(event, decision),
            "metadata": metadata,
        }
    )
    return _ensure_review_case(resolved_event, decision)


def _incident_severity(decision: PolicyStatus) -> str:
    if decision == PolicyStatus.BLOCKED:
        return "high"
    if decision == PolicyStatus.ESCALATED:
        return "medium"
    if decision == PolicyStatus.REQUIRES_HUMAN_REVIEW:
        return "low"
    return "info"


def _derive_workflow_status(events: list[WorkflowEvent]) -> tuple[str, str | None, str | None]:
    if not events:
        return "in_progress", None, None

    ordered = sorted(events, key=lambda event: (event.timestamp, event.event_id))
    last = ordered[-1]
    if last.action_type == "reject_invoice" and last.outcome_status == OutcomeStatus.SUCCESS:
        return "rejected", last.outcome_status.value, last.policy_status.value
    if last.action_type in {"payment_scheduled", "release_payment"} and last.outcome_status == OutcomeStatus.SUCCESS:
        return "completed", last.outcome_status.value, last.policy_status.value
    if last.action_type in {"approve_invoice", "human_approve_invoice"} and last.outcome_status == OutcomeStatus.SUCCESS:
        return "approved", last.outcome_status.value, last.policy_status.value
    if last.policy_status == PolicyStatus.BLOCKED:
        return "blocked", last.outcome_status.value, last.policy_status.value
    if last.policy_status in {PolicyStatus.ESCALATED, PolicyStatus.REQUIRES_HUMAN_REVIEW}:
        return "needs_review", last.outcome_status.value, last.policy_status.value
    return "in_progress", last.outcome_status.value, last.policy_status.value


def _upsert_workflow(session: Session, event: WorkflowEvent) -> WorkflowRecord:
    workflow = session.get(WorkflowRecord, event.workflow_id)
    if workflow is None:
        workflow = WorkflowRecord(
            workflow_id=event.workflow_id,
            workflow_name=event.workflow_name,
            business_object_type=event.business_object_type,
            business_object_id=event.business_object_id,
            status="in_progress",
            current_step=event.process_step,
            started_at=event.timestamp,
            last_event_at=event.timestamp,
            event_count=0,
            incident_count=0,
            last_policy_status=event.policy_status.value,
            final_outcome=event.outcome_status.value,
        )
        session.add(workflow)
        session.flush()
        return workflow

    workflow.workflow_name = event.workflow_name
    workflow.business_object_type = event.business_object_type
    workflow.business_object_id = event.business_object_id
    workflow.current_step = event.process_step
    workflow.last_event_at = event.timestamp
    workflow.last_policy_status = event.policy_status.value
    workflow.final_outcome = event.outcome_status.value
    return workflow


def _record_event(session: Session, event: WorkflowEvent) -> EventRecord:
    if session.get(EventRecord, event.event_id):
        raise ValueError(f"Event {event.event_id} already exists.")

    record = EventRecord(
        event_id=event.event_id,
        timestamp=event.timestamp,
        workflow_id=event.workflow_id,
        workflow_name=event.workflow_name,
        process_step=event.process_step,
        actor_type=event.actor_type.value,
        actor_id=event.actor_id,
        actor_name=event.actor_name,
        action_type=event.action_type,
        action_summary=event.action_summary,
        tool_name=event.tool_name,
        target_system=event.target_system,
        business_object_type=event.business_object_type,
        business_object_id=event.business_object_id,
        permission_scope=event.permission_scope,
        authority_subject=event.authority_subject,
        authority_delegation_source=event.authority_delegation_source,
        policy_status=event.policy_status.value,
        policy_rule_ids_json=event.policy_rule_ids,
        review_case_id=event.review_case_id,
        review_state=event.review_state,
        human_decision_reason=event.human_decision_reason,
        decision_code=event.decision_code,
        decision_rationale=event.decision_rationale,
        approved_exception_type=event.approved_exception_type,
        approver_role=event.approver_role,
        remediation_owner=event.remediation_owner,
        remediation_due_by=event.remediation_due_by,
        closure_status=event.closure_status,
        due_by=event.due_by,
        source_trace_ref=event.source_trace_ref,
        source_system_ref=event.source_system_ref,
        evidence_hash=event.evidence_hash,
        outcome_status=event.outcome_status.value,
        parent_event_id=event.parent_event_id,
        metadata_json=event.metadata,
    )
    session.add(record)
    return record


def _maybe_create_incident(
    session: Session,
    event: WorkflowEvent,
    decision: PolicyDecision,
) -> IncidentRecord | None:
    if decision.decision == PolicyStatus.ALLOWED:
        return None

    title = str(event.metadata.get("headline") or f"{decision.decision.value.replace('_', ' ').title()} at {event.process_step}")
    incident = IncidentRecord(
        incident_id=f"inc_{event.event_id}",
        workflow_id=event.workflow_id,
        trigger_event_id=event.event_id,
        severity=_incident_severity(decision.decision),
        status="open",
        title=title,
        summary=event.action_summary,
        explanation=decision.explanation,
        recommended_next_action=decision.recommended_next_action,
        created_at=utcnow(),
    )
    session.add(incident)
    return incident


def _refresh_workflow_aggregate(session: Session, workflow_id: str) -> WorkflowRecord:
    workflow = session.get(WorkflowRecord, workflow_id)
    if workflow is None:
        raise ValueError(f"Workflow {workflow_id} does not exist.")

    events = get_workflow_events(session, workflow_id)
    incidents = list_incidents(session, workflow_id=workflow_id)
    status, final_outcome, last_policy_status = _derive_workflow_status(events)
    workflow.status = status
    workflow.current_step = events[-1].process_step if events else workflow.current_step
    workflow.event_count = len(events)
    workflow.incident_count = len(incidents)
    workflow.last_event_at = events[-1].timestamp if events else workflow.last_event_at
    workflow.last_policy_status = last_policy_status
    workflow.final_outcome = final_outcome
    return workflow


def ingest_event(
    session: Session,
    event: WorkflowEvent,
    evaluator: PolicyEvaluator | None = None,
    preserve_event_policy: bool = False,
) -> EventIngestionResponse:
    if preserve_event_policy:
        decision = _decision_from_preserved_event(event)
        resolved_event = _apply_preserved_policy(event, decision)
    else:
        evaluator = evaluator or PolicyEvaluator()
        decision = evaluator.evaluate(event)
        resolved_event = _apply_policy(event, decision)

    resolved_event = _decorate_evidence(session, resolved_event, decision)

    _upsert_workflow(session, resolved_event)
    _record_event(session, resolved_event)
    incident = _maybe_create_incident(session, resolved_event, decision)
    session.flush()
    _refresh_workflow_aggregate(session, resolved_event.workflow_id)
    session.commit()

    return EventIngestionResponse(
        event=resolved_event,
        policy=decision,
        incident_id=incident.incident_id if incident else None,
    )


def get_workflow(session: Session, workflow_id: str) -> WorkflowSummary | None:
    record = session.get(WorkflowRecord, workflow_id)
    return map_workflow_record(record) if record else None


def list_workflows(session: Session) -> list[WorkflowSummary]:
    records = session.scalars(select(WorkflowRecord).order_by(WorkflowRecord.last_event_at.desc())).all()
    return [map_workflow_record(record) for record in records]


def get_workflow_events(session: Session, workflow_id: str) -> list[WorkflowEvent]:
    records = session.scalars(
        select(EventRecord)
        .where(EventRecord.workflow_id == workflow_id)
        .order_by(EventRecord.timestamp.asc(), EventRecord.event_id.asc())
    ).all()
    return [map_event_record(record) for record in records]


def get_event(session: Session, event_id: str) -> WorkflowEvent | None:
    record = session.get(EventRecord, event_id)
    return map_event_record(record) if record else None


def list_incidents(session: Session, workflow_id: str | None = None) -> list[IncidentSummary]:
    query = select(IncidentRecord)
    if workflow_id:
        query = query.where(IncidentRecord.workflow_id == workflow_id)
    records = session.scalars(query.order_by(IncidentRecord.created_at.desc())).all()
    return [map_incident_record(record) for record in records]


def list_review_case_ids(session: Session) -> list[str]:
    rows = session.execute(
        select(EventRecord.review_case_id)
        .where(EventRecord.review_case_id.is_not(None))
        .distinct()
        .order_by(EventRecord.review_case_id.asc())
    )
    return [row[0] for row in rows if row[0]]


def get_review_case_events(session: Session, review_case_id: str) -> list[WorkflowEvent]:
    records = session.scalars(
        select(EventRecord)
        .where(EventRecord.review_case_id == review_case_id)
        .order_by(EventRecord.timestamp.asc(), EventRecord.event_id.asc())
    ).all()
    return [map_event_record(record) for record in records]


def get_incident(session: Session, incident_id: str) -> IncidentSummary | None:
    record = session.get(IncidentRecord, incident_id)
    return map_incident_record(record) if record else None


def get_incident_record(session: Session, incident_id: str) -> IncidentRecord | None:
    return session.get(IncidentRecord, incident_id)


def upsert_replay_session(
    session: Session,
    workflow_id: str,
    event_count: int,
    final_outcome: str,
    summary_json: dict,
) -> str:
    replay_session_id = f"replay_{workflow_id}"
    record = session.get(ReplaySessionRecord, replay_session_id)
    if record is None:
        record = ReplaySessionRecord(
            replay_session_id=replay_session_id,
            workflow_id=workflow_id,
            created_at=utcnow(),
            event_count=event_count,
            final_outcome=final_outcome,
            summary_json=summary_json,
        )
        session.add(record)
    else:
        record.created_at = utcnow()
        record.event_count = event_count
        record.final_outcome = final_outcome
        record.summary_json = summary_json
    session.commit()
    return replay_session_id


def reset_database(session: Session) -> None:
    session.execute(delete(ReplaySessionRecord))
    session.execute(delete(IncidentRecord))
    session.execute(delete(EventRecord))
    session.execute(delete(WorkflowRecord))
    session.execute(delete(PolicyRuleRecord))
    session.commit()
