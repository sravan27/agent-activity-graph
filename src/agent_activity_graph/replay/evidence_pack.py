from __future__ import annotations

from agent_activity_graph.replay.incident import build_incident_detail
from agent_activity_graph.sdk.events import EvidencePack, ReplayHighlight
from agent_activity_graph.utils.time import utcnow


def _resolution_entry(detail):
    for entry in reversed(detail.replay.entries):
        if entry.human_intervention and (
            entry.closure_status or entry.decision_code or entry.human_decision_reason
        ):
            return entry
    return None


def build_evidence_pack(session, incident_id: str) -> EvidencePack:
    detail = build_incident_detail(session, incident_id)
    trigger_metadata = detail.trigger_event.metadata
    risk_category = trigger_metadata.get("risk_category")
    resolution_entry = _resolution_entry(detail)

    findings = [
        ReplayHighlight(
            label="Incident trigger",
            detail=detail.incident.explanation,
            severity=detail.incident.severity,
            event_id=detail.incident.trigger_event_id,
        )
    ]
    findings.extend(
        highlight
        for highlight in detail.replay.highlights
        if highlight.label in {"Policy gate", "Blocked path", "Human intervention", "Final outcome"}
    )

    recommended_actions = [detail.incident.recommended_next_action]
    if detail.replay.business_consequence:
        recommended_actions.append(
            "Confirm whether the business consequence requires operational follow-up."
        )
    if detail.workflow.status == "rejected":
        recommended_actions.append(
            "Repair the missing controls or source data before allowing the workflow back into an approval path."
        )

    return EvidencePack(
        incident_id=detail.incident.incident_id,
        workflow_id=detail.workflow.workflow_id,
        workflow_name=detail.workflow.workflow_name,
        business_object_id=detail.workflow.business_object_id,
        title=detail.incident.title,
        generated_at=utcnow(),
        audience=["Engineering lead", "AI governance lead", "Process owner"],
        executive_summary=f"{detail.replay.summary_headline} {detail.incident.explanation}",
        review_case_id=detail.replay.review_case_id,
        risk_category=str(risk_category) if risk_category else None,
        business_consequence=detail.replay.business_consequence,
        final_outcome=detail.replay.final_outcome,
        review_readiness_spec_version=detail.replay.review_readiness_spec_version,
        evidence_status=detail.replay.evidence_status,
        evidence_score=detail.replay.evidence_score,
        evidence_issues=detail.replay.evidence_issues,
        source_trace_refs=detail.replay.source_trace_refs,
        decision_code=resolution_entry.decision_code if resolution_entry else None,
        decision_rationale=(
            resolution_entry.decision_rationale or resolution_entry.human_decision_reason
            if resolution_entry
            else None
        ),
        approved_exception_type=resolution_entry.approved_exception_type if resolution_entry else None,
        approver_role=resolution_entry.approver_role if resolution_entry else None,
        remediation_owner=resolution_entry.remediation_owner if resolution_entry else None,
        remediation_due_by=resolution_entry.remediation_due_by if resolution_entry else None,
        closure_status=resolution_entry.closure_status if resolution_entry else None,
        findings=findings,
        chronology=detail.replay.entries,
        recommended_actions=recommended_actions,
    )


def render_evidence_pack_markdown(pack: EvidencePack) -> str:
    lines = [
        f"# {pack.title}",
        "",
        f"- Incident ID: `{pack.incident_id}`",
        f"- Workflow ID: `{pack.workflow_id}`",
        f"- Business object: `{pack.business_object_id}`",
        f"- Generated at: `{pack.generated_at.isoformat()}`",
        f"- Final outcome: `{pack.final_outcome}`",
        f"- Review readiness spec: `{pack.review_readiness_spec_version}`",
        f"- Evidence status: `{pack.evidence_status}`",
        f"- Evidence score: `{pack.evidence_score}`",
    ]
    if pack.review_case_id:
        lines.append(f"- Review case: `{pack.review_case_id}`")
    if pack.risk_category:
        lines.append(f"- Risk category: `{pack.risk_category}`")
    if pack.source_trace_refs:
        lines.append(f"- Source trace refs: `{', '.join(pack.source_trace_refs)}`")
    if pack.decision_code:
        lines.append(f"- Decision code: `{pack.decision_code}`")
    if pack.approver_role:
        lines.append(f"- Approver role: `{pack.approver_role}`")
    if pack.closure_status:
        lines.append(f"- Closure status: `{pack.closure_status}`")
    lines.extend(
        [
            "",
            "## Executive Summary",
            pack.executive_summary,
        ]
    )

    if pack.evidence_issues:
        lines.extend(["", "## Evidence Integrity Notes"])
        for issue in pack.evidence_issues:
            lines.append(f"- {issue}")

    if pack.business_consequence:
        lines.extend(
            [
                "",
                "## Business Consequence",
                pack.business_consequence,
            ]
        )

    if pack.decision_code or pack.decision_rationale or pack.approved_exception_type or pack.remediation_owner:
        lines.extend(["", "## Resolution Record"])
        if pack.decision_code:
            lines.append(f"- Decision code: `{pack.decision_code}`")
        if pack.decision_rationale:
            lines.append(f"- Decision rationale: {pack.decision_rationale}")
        if pack.approved_exception_type:
            lines.append(f"- Approved exception type: `{pack.approved_exception_type}`")
        if pack.approver_role:
            lines.append(f"- Approver role: `{pack.approver_role}`")
        if pack.closure_status:
            lines.append(f"- Closure status: `{pack.closure_status}`")
        if pack.remediation_owner:
            lines.append(f"- Remediation owner: `{pack.remediation_owner}`")
        if pack.remediation_due_by:
            lines.append(f"- Remediation due by: `{pack.remediation_due_by.isoformat()}`")

    lines.extend(["", "## Findings"])
    for finding in pack.findings:
        lines.append(f"- {finding.label}: {finding.detail}")

    lines.extend(["", "## Chronology"])
    for entry in pack.chronology:
        lines.append(
            f"- {entry.sequence_number:02d}. {entry.timestamp.isoformat()} | "
            f"{entry.headline or entry.action_summary} | "
            f"actor={entry.actor_name} | policy={entry.policy_status} | outcome={entry.outcome_status}"
        )
        evidence_bits = []
        if entry.review_case_id:
            evidence_bits.append(f"review_case={entry.review_case_id}")
        if entry.source_trace_ref:
            evidence_bits.append(f"trace={entry.source_trace_ref}")
        if entry.source_system_ref:
            evidence_bits.append(f"source={entry.source_system_ref}")
        if entry.evidence_hash:
            evidence_bits.append(f"evidence_hash={entry.evidence_hash[:12]}")
        if evidence_bits:
            lines.append(f"  {' | '.join(evidence_bits)}")

    lines.extend(["", "## Recommended Actions"])
    for action in pack.recommended_actions:
        lines.append(f"- {action}")

    return "\n".join(lines)
