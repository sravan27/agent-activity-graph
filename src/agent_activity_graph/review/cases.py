from __future__ import annotations

from sqlalchemy.orm import Session

from agent_activity_graph.db.repository import (
    get_event,
    get_workflow,
    get_workflow_events,
    list_incidents,
    list_review_case_ids,
    get_review_case_events,
)
from agent_activity_graph.replay.timeline import build_replay_timeline
from agent_activity_graph.review.readiness import grade_workflow
from agent_activity_graph.sdk.events import (
    ActorType,
    IncidentSummary,
    ReviewCaseDetail,
    ReviewCaseSummary,
    WorkflowEvent,
)


def _latest_policy_event(events: list[WorkflowEvent]) -> WorkflowEvent | None:
    for event in reversed(events):
        if event.action_type == "policy_evaluation":
            return event
    return None


def _latest_resolution_event(events: list[WorkflowEvent]) -> WorkflowEvent | None:
    for event in reversed(events):
        if event.actor_type == ActorType.HUMAN and (
            event.closure_status or event.decision_code or event.action_type in {"human_approve_invoice", "reject_invoice"}
        ):
            return event
    return None


def _case_incidents(session: Session, workflow_id: str, case_events: list[WorkflowEvent]) -> list[IncidentSummary]:
    case_event_ids = {event.event_id for event in case_events}
    incidents = list_incidents(session, workflow_id=workflow_id)
    return [incident for incident in incidents if incident.trigger_event_id in case_event_ids]


def _closure_status(resolution_event: WorkflowEvent | None) -> str | None:
    if resolution_event is None:
        return None
    if resolution_event.closure_status:
        return resolution_event.closure_status
    if resolution_event.action_type == "human_approve_invoice":
        return "approved"
    if resolution_event.action_type == "reject_invoice":
        return "rejected"
    return "closed"


def _human_owner(policy_event: WorkflowEvent | None, resolution_event: WorkflowEvent | None) -> str | None:
    if resolution_event is not None:
        return resolution_event.actor_name
    if policy_event is None:
        return None
    return (
        policy_event.metadata.get("review_owner_name")
        or policy_event.metadata.get("review_owner_role")
        or None
    )


def _authority_owner(policy_event: WorkflowEvent | None, resolution_event: WorkflowEvent | None) -> str | None:
    if resolution_event is not None:
        return resolution_event.approver_role or resolution_event.actor_name
    if policy_event is None:
        return None
    return (
        policy_event.metadata.get("review_owner_role")
        or policy_event.metadata.get("review_owner_name")
        or None
    )


def build_review_case(session: Session, review_case_id: str) -> ReviewCaseDetail:
    case_events = get_review_case_events(session, review_case_id)
    if not case_events:
        raise ValueError(f"Review case {review_case_id} was not found.")

    workflow = get_workflow(session, case_events[0].workflow_id)
    if workflow is None:
        raise ValueError(f"Workflow {case_events[0].workflow_id} was not found.")

    replay = build_replay_timeline(session, workflow.workflow_id, persist=False)
    readiness = grade_workflow(session, workflow.workflow_id)
    policy_event = _latest_policy_event(case_events)
    resolution_event = _latest_resolution_event(case_events)
    incidents = _case_incidents(session, workflow.workflow_id, case_events)
    primary_incident = incidents[0] if incidents else None
    closure_status = _closure_status(resolution_event)
    status = "closed" if closure_status else "open"
    title = primary_incident.title if primary_incident else (policy_event.metadata.get("headline") if policy_event else review_case_id)
    summary = (
        primary_incident.summary
        if primary_incident
        else (policy_event.action_summary if policy_event else replay.summary_headline)
    )

    review_case = ReviewCaseSummary(
        review_case_id=review_case_id,
        workflow_id=workflow.workflow_id,
        workflow_name=workflow.workflow_name,
        business_object_id=workflow.business_object_id,
        status=status,
        review_state=(resolution_event.review_state if resolution_event else (policy_event.review_state if policy_event else None)),
        policy_decision=policy_event.policy_status.value if policy_event else None,
        title=str(title),
        summary=summary,
        due_by=(policy_event.due_by if policy_event else None),
        business_consequence=replay.business_consequence,
        evidence_status=readiness.status,
        evidence_score=readiness.overall_score,
        authority_owner=_authority_owner(policy_event, resolution_event),
        human_owner=_human_owner(policy_event, resolution_event),
        approver_role=resolution_event.approver_role if resolution_event else (
            policy_event.metadata.get("review_owner_role") if policy_event else None
        ),
        closure_status=closure_status,
        primary_incident_id=primary_incident.incident_id if primary_incident else None,
        incident_count=len(incidents),
        decision_code=resolution_event.decision_code if resolution_event else None,
        approved_exception_type=resolution_event.approved_exception_type if resolution_event else None,
        remediation_owner=resolution_event.remediation_owner if resolution_event else None,
        remediation_due_by=resolution_event.remediation_due_by if resolution_event else None,
    )

    return ReviewCaseDetail(
        review_case=review_case,
        workflow=workflow,
        replay=replay.model_copy(
            update={
                "review_readiness_spec_version": readiness.spec_version,
                "evidence_status": readiness.status,
                "evidence_score": readiness.overall_score,
                "evidence_issues": readiness.issues,
            }
        ),
        incidents=incidents,
        primary_incident=primary_incident,
        policy_event=policy_event,
        resolution_event=resolution_event,
        case_events=case_events,
    )


def list_review_cases(session: Session, *, active_only: bool = False) -> list[ReviewCaseSummary]:
    summaries: list[ReviewCaseSummary] = []
    for review_case_id in list_review_case_ids(session):
        detail = build_review_case(session, review_case_id)
        if active_only and detail.review_case.status != "open":
            continue
        summaries.append(detail.review_case)

    return sorted(
        summaries,
        key=lambda case: (
            case.status != "open",
            case.due_by is None,
            case.due_by,
            -case.evidence_score,
            case.review_case_id,
        ),
    )
