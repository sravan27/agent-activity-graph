from __future__ import annotations

from sqlalchemy.orm import Session

from agent_activity_graph.db.repository import (
    get_workflow_events,
    ingest_event,
    seed_policy_rules,
    verify_evidence_chain,
)
from agent_activity_graph.db.session import build_session_factory
from agent_activity_graph.policy.evaluator import PolicyEvaluator
from agent_activity_graph.sdk.events import (
    ActorType,
    PolicyStatus,
    ReviewReadinessCategory,
    ReviewReadinessReport,
    TraceIngestionRequest,
    WorkflowEvent,
)
from agent_activity_graph.sdk.trace_adapter import map_trace_to_workflow_events

REVIEW_READINESS_SPEC_VERSION = "aag.review_readiness.v1"

_WEIGHTS = {
    "authority": 20,
    "policy": 25,
    "human_review": 25,
    "provenance": 15,
    "evidence_integrity": 15,
}

_HIGH_IMPACT_ACTIONS = {
    "prepare_approval_recommendation",
    "propose_invoice_approval",
    "approve_invoice",
    "human_approve_invoice",
    "reject_invoice",
    "human_review_step",
    "call_tool",
    "call_mcp_tool",
    "agent_run_step",
    "release_payment",
}

_REVIEW_ACTIONS = {"human_approve_invoice", "reject_invoice", "human_review_step"}


def _review_case_expected(events: list[WorkflowEvent]) -> bool:
    return any(event.review_case_id for event in events) or any(
        event.action_type == "policy_evaluation" and event.policy_status != PolicyStatus.ALLOWED
        for event in events
    )


def _latest_policy_control_event(events: list[WorkflowEvent]) -> WorkflowEvent | None:
    for event in reversed(events):
        if event.action_type == "policy_evaluation" and event.policy_status != PolicyStatus.ALLOWED:
            return event
    return None


def _latest_resolution_event(events: list[WorkflowEvent]) -> WorkflowEvent | None:
    for event in reversed(events):
        if event.actor_type == ActorType.HUMAN and (
            event.action_type in _REVIEW_ACTIONS or event.closure_status or event.decision_code
        ):
            return event
    return None


def _score(passed_checks: int, total_checks: int) -> int:
    if total_checks <= 0:
        return 100
    return round((passed_checks / total_checks) * 100)


def _category(
    *,
    key: str,
    label: str,
    passed_checks: int,
    total_checks: int,
    notes: list[str],
    hard_fail_reasons: list[str],
) -> ReviewReadinessCategory:
    return ReviewReadinessCategory(
        key=key,
        label=label,
        score=_score(passed_checks, total_checks),
        passed_checks=passed_checks,
        total_checks=total_checks,
        notes=notes,
        hard_fail_reasons=hard_fail_reasons,
    )


def _authority_category(events: list[WorkflowEvent]) -> ReviewReadinessCategory:
    relevant = [
        event
        for event in events
        if event.actor_type in {ActorType.AGENT, ActorType.HUMAN}
        and event.action_type in _HIGH_IMPACT_ACTIONS
    ]
    if not relevant:
        return _category(
            key="authority",
            label="Authority completeness",
            passed_checks=0,
            total_checks=0,
            notes=["No high-impact delegated action was recorded in this run."],
            hard_fail_reasons=[],
        )

    passed = 0
    total = 0
    notes: list[str] = []
    for event in relevant:
        total += 2
        if event.authority_subject:
            passed += 1
        else:
            notes.append(f"{event.event_id}: missing authority_subject on a high-impact action.")
        if event.authority_delegation_source:
            passed += 1
        else:
            notes.append(f"{event.event_id}: missing authority_delegation_source on a high-impact action.")

    return _category(
        key="authority",
        label="Authority completeness",
        passed_checks=passed,
        total_checks=total,
        notes=notes,
        hard_fail_reasons=[],
    )


def _policy_category(events: list[WorkflowEvent]) -> ReviewReadinessCategory:
    relevant = [
        event
        for event in events
        if event.action_type == "policy_evaluation" and event.policy_status != PolicyStatus.ALLOWED
    ]
    if not relevant:
        return _category(
            key="policy",
            label="Policy completeness",
            passed_checks=0,
            total_checks=0,
            notes=["No escalated or blocked policy gate was recorded in this run."],
            hard_fail_reasons=[],
        )

    passed = 0
    total = 0
    notes: list[str] = []
    hard_fail_reasons: list[str] = []
    for event in relevant:
        policy_payload = dict(event.metadata.get("_policy") or {})
        total += 4
        if event.policy_rule_ids:
            passed += 1
        else:
            reason = f"{event.event_id}: policy-controlled step is missing policy_rule_ids."
            notes.append(reason)
            hard_fail_reasons.append(reason)
        if event.review_case_id:
            passed += 1
        else:
            reason = f"{event.event_id}: policy-controlled step is missing review_case_id."
            notes.append(reason)
            hard_fail_reasons.append(reason)
        if policy_payload.get("explanation"):
            passed += 1
        else:
            notes.append(f"{event.event_id}: preserved policy explanation is missing.")
        if policy_payload.get("recommended_next_action"):
            passed += 1
        else:
            notes.append(f"{event.event_id}: recommended next action is missing from the policy record.")

    return _category(
        key="policy",
        label="Policy completeness",
        passed_checks=passed,
        total_checks=total,
        notes=notes,
        hard_fail_reasons=hard_fail_reasons,
    )


def _human_review_category(events: list[WorkflowEvent]) -> ReviewReadinessCategory:
    if not _review_case_expected(events):
        return _category(
            key="human_review",
            label="Human review completeness",
            passed_checks=0,
            total_checks=0,
            notes=["This run did not require a human review case."],
            hard_fail_reasons=[],
        )

    resolution_event = _latest_resolution_event(events)
    if resolution_event is None:
        policy_event = _latest_policy_control_event(events)
        review_owner = None
        review_owner_role = None
        if policy_event:
            review_owner = policy_event.metadata.get("review_owner_name")
            review_owner_role = policy_event.metadata.get("review_owner_role")

        passed = 0
        total = 3
        notes: list[str] = []
        if policy_event and policy_event.review_state:
            passed += 1
        else:
            notes.append("Open review case is missing an explicit review_state.")
        if policy_event and policy_event.due_by:
            passed += 1
        else:
            notes.append("Open review case is missing a due_by deadline.")
        if review_owner or review_owner_role:
            passed += 1
        else:
            notes.append("Open review case is missing an assigned human owner or review role.")

        return _category(
            key="human_review",
            label="Human review completeness",
            passed_checks=passed,
            total_checks=total,
            notes=notes,
            hard_fail_reasons=[],
        )

    passed = 0
    total = 4
    notes: list[str] = []
    hard_fail_reasons: list[str] = []

    if resolution_event.decision_code:
        passed += 1
    else:
        reason = f"{resolution_event.event_id}: resolved review is missing decision_code."
        notes.append(reason)
        hard_fail_reasons.append(reason)

    if resolution_event.decision_rationale or resolution_event.human_decision_reason:
        passed += 1
    else:
        reason = f"{resolution_event.event_id}: resolved review is missing decision rationale."
        notes.append(reason)
        hard_fail_reasons.append(reason)

    if resolution_event.approver_role:
        passed += 1
    else:
        reason = f"{resolution_event.event_id}: resolved review is missing approver_role."
        notes.append(reason)
        hard_fail_reasons.append(reason)

    if resolution_event.closure_status:
        passed += 1
    else:
        reason = f"{resolution_event.event_id}: resolved review is missing closure_status."
        notes.append(reason)
        hard_fail_reasons.append(reason)

    if resolution_event.closure_status == "rejected" and not resolution_event.remediation_owner:
        notes.append(f"{resolution_event.event_id}: rejected review is missing remediation_owner.")
    if resolution_event.closure_status == "rejected" and not resolution_event.remediation_due_by:
        notes.append(f"{resolution_event.event_id}: rejected review is missing remediation_due_by.")

    return _category(
        key="human_review",
        label="Human review completeness",
        passed_checks=passed,
        total_checks=total,
        notes=notes,
        hard_fail_reasons=hard_fail_reasons,
    )


def _provenance_category(events: list[WorkflowEvent]) -> ReviewReadinessCategory:
    relevant = events or []
    if not relevant:
        return _category(
            key="provenance",
            label="Provenance completeness",
            passed_checks=0,
            total_checks=0,
            notes=["No events were available to grade."],
            hard_fail_reasons=[],
        )

    passed = 0
    total = 0
    notes: list[str] = []
    hard_fail_reasons: list[str] = []
    for event in relevant:
        total += 1
        if event.source_trace_ref:
            passed += 1
        else:
            notes.append(f"{event.event_id}: missing source_trace_ref.")

        if event.tool_name or event.target_system or event.actor_type == ActorType.SYSTEM:
            total += 1
            if event.source_system_ref:
                passed += 1
            else:
                notes.append(f"{event.event_id}: missing source_system_ref for a system-touching step.")

    if not any(event.source_trace_ref for event in relevant):
        hard_fail_reasons.append("The run has no source trace reference at all.")

    return _category(
        key="provenance",
        label="Provenance completeness",
        passed_checks=passed,
        total_checks=total,
        notes=notes,
        hard_fail_reasons=hard_fail_reasons,
    )


def _integrity_category(events: list[WorkflowEvent]) -> ReviewReadinessCategory:
    if not events:
        return _category(
            key="evidence_integrity",
            label="Evidence integrity",
            passed_checks=0,
            total_checks=0,
            notes=["No events were available to verify."],
            hard_fail_reasons=["No events were available to verify."],
        )

    issues = verify_evidence_chain(events)
    if issues:
        return _category(
            key="evidence_integrity",
            label="Evidence integrity",
            passed_checks=0,
            total_checks=len(events),
            notes=issues,
            hard_fail_reasons=issues,
        )

    return _category(
        key="evidence_integrity",
        label="Evidence integrity",
        passed_checks=len(events),
        total_checks=len(events),
        notes=[],
        hard_fail_reasons=[],
    )


def _aggregate_issues(categories: list[ReviewReadinessCategory]) -> list[str]:
    issues: list[str] = []
    for category in categories:
        for item in [*category.hard_fail_reasons, *category.notes]:
            if item not in issues:
                issues.append(item)
    return issues


def build_review_readiness_report(
    events: list[WorkflowEvent],
    *,
    target_type: str,
    target_id: str,
) -> ReviewReadinessReport:
    categories = [
        _authority_category(events),
        _policy_category(events),
        _human_review_category(events),
        _provenance_category(events),
        _integrity_category(events),
    ]
    overall_score = round(
        sum(category.score * _WEIGHTS[category.key] for category in categories) / sum(_WEIGHTS.values())
    )
    hard_fail_reasons = []
    for category in categories:
        for reason in category.hard_fail_reasons:
            if reason not in hard_fail_reasons:
                hard_fail_reasons.append(reason)

    if hard_fail_reasons:
        status = "not_review_ready"
        summary = "The run is not review-ready because key policy, human decision, provenance, or integrity fields are missing."
    elif overall_score >= 85:
        status = "review_ready"
        summary = "The run is review-ready: a human can inspect the record and make or audit a decision without reconstructing hidden context."
    else:
        status = "needs_enrichment"
        summary = "The run is usable for review, but some authority, policy, or provenance fields still need to be made explicit."

    return ReviewReadinessReport(
        spec_version=REVIEW_READINESS_SPEC_VERSION,
        target_type=target_type,
        target_id=target_id,
        status=status,
        overall_score=overall_score,
        hard_fail_reasons=hard_fail_reasons,
        issues=_aggregate_issues(categories),
        summary=summary,
        categories=categories,
    )


def build_review_readiness_markdown(report: ReviewReadinessReport) -> str:
    lines = [
        f"# Review Readiness Report: {report.target_id}",
        "",
        f"- Spec version: `{report.spec_version}`",
        f"- Target type: `{report.target_type}`",
        f"- Status: `{report.status}`",
        f"- Overall score: `{report.overall_score}`",
        "",
        "## Summary",
        report.summary,
    ]
    if report.hard_fail_reasons:
        lines.extend(["", "## Hard-fail reasons"])
        for reason in report.hard_fail_reasons:
            lines.append(f"- {reason}")

    lines.extend(["", "## Category scores"])
    for category in report.categories:
        lines.append(
            f"- {category.label}: `{category.score}` "
            f"({category.passed_checks}/{category.total_checks} checks passed)"
        )
        for reason in category.hard_fail_reasons:
            lines.append(f"  - hard fail: {reason}")
        for note in category.notes:
            lines.append(f"  - note: {note}")

    return "\n".join(lines)


def grade_workflow(session: Session, workflow_id: str) -> ReviewReadinessReport:
    events = get_workflow_events(session, workflow_id)
    if not events:
        raise ValueError(f"Workflow {workflow_id} was not found.")
    return build_review_readiness_report(events, target_type="workflow", target_id=workflow_id)


def grade_trace_request(request: TraceIngestionRequest) -> ReviewReadinessReport:
    engine, session_factory = build_session_factory("sqlite://")
    try:
        with session_factory() as session:
            seed_policy_rules(session)
            evaluator = PolicyEvaluator()
            for event in map_trace_to_workflow_events(request):
                ingest_event(
                    session,
                    event,
                    evaluator=evaluator,
                    preserve_event_policy=True,
                )
            events = get_workflow_events(session, request.workflow.workflow_id)
            return build_review_readiness_report(
                events,
                target_type="trace",
                target_id=request.workflow.workflow_id,
            )
    finally:
        engine.dispose()
