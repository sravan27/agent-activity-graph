from __future__ import annotations

from sqlalchemy.orm import Session

from agent_activity_graph.db.repository import (
    get_workflow,
    get_workflow_events,
    upsert_replay_session,
)
from agent_activity_graph.sdk.events import (
    ActorType,
    PolicyStatus,
    ReplayEntry,
    ReplayHighlight,
    ReplayTimeline,
    WorkflowEvent,
)


def _policy_payload(event: WorkflowEvent) -> dict:
    return dict(event.metadata.get("_policy") or {})


def _policy_explanation(event: WorkflowEvent) -> str | None:
    payload = _policy_payload(event)
    explanation = payload.get("explanation")
    if event.action_type == "policy_evaluation":
        if not explanation or explanation == "No policy rule blocked or altered this action.":
            return event.action_summary
    return str(explanation) if explanation else None


def _headline(event: WorkflowEvent) -> str:
    return str(event.metadata.get("headline") or event.action_summary)


def _why_it_mattered(event: WorkflowEvent) -> str:
    explicit = event.metadata.get("why_it_mattered")
    if explicit:
        return str(explicit)
    if event.action_type == "policy_evaluation":
        return "This step decided whether the workflow could continue under policy."
    if event.policy_status == PolicyStatus.BLOCKED:
        return "This action could not continue because the workflow violated policy."
    if event.policy_status in {PolicyStatus.ESCALATED, PolicyStatus.REQUIRES_HUMAN_REVIEW}:
        return "This step moved the workflow out of the autonomous agent lane."
    if event.actor_type == ActorType.HUMAN:
        return "A human re-entered the workflow and took responsibility for the next step."
    return "This step advanced the invoice toward a concrete business outcome."


def _event_kind(event: WorkflowEvent) -> str:
    if event.action_type == "policy_evaluation":
        return "policy_evaluation"
    if event.actor_type == ActorType.HUMAN:
        return "human_intervention"
    if event.policy_status == PolicyStatus.BLOCKED:
        return "blocked_action"
    if event.policy_status in {PolicyStatus.ESCALATED, PolicyStatus.REQUIRES_HUMAN_REVIEW}:
        return "escalation"
    if event.actor_type == ActorType.AGENT:
        return "agent_action"
    return "system_update"


def _workflow_business_consequence(events: list[WorkflowEvent]) -> str | None:
    preferred = [
        event
        for event in events
        if event.action_type == "policy_evaluation"
        and event.policy_status != PolicyStatus.ALLOWED
        and event.metadata.get("business_consequence")
    ]
    if preferred:
        return str(preferred[-1].metadata["business_consequence"])

    policy_events = [
        event for event in events if event.action_type == "policy_evaluation" and event.metadata.get("business_consequence")
    ]
    if policy_events:
        return str(policy_events[-1].metadata["business_consequence"])

    for event in reversed(events):
        consequence = event.metadata.get("business_consequence")
        if consequence:
            return str(consequence)
    return None


def _entry_business_consequence(event: WorkflowEvent) -> str | None:
    if event.action_type == "policy_evaluation" or event.actor_type == ActorType.HUMAN:
        consequence = event.metadata.get("business_consequence")
        return str(consequence) if consequence else None
    if event.action_type in {"payment_scheduled", "reject_invoice"}:
        consequence = event.metadata.get("business_consequence")
        return str(consequence) if consequence else None
    return None


def _policy_story(events: list[WorkflowEvent]) -> str:
    for event in reversed(events):
        explanation = _policy_explanation(event)
        if event.action_type == "policy_evaluation" and event.policy_status != PolicyStatus.ALLOWED and explanation:
            return explanation

    for event in reversed(events):
        explanation = _policy_explanation(event)
        if event.action_type == "policy_evaluation" and explanation:
            return explanation

    for event in events:
        explanation = _policy_explanation(event)
        if explanation and event.policy_status != PolicyStatus.ALLOWED:
            return explanation

    return "Policy allowed the recorded workflow steps to continue."


def _summary_headline(
    workflow_status: str,
    events: list[WorkflowEvent],
    human_intervention_count: int,
    blocked_count: int,
) -> str:
    if events and events[-1].metadata.get("outcome_headline"):
        return str(events[-1].metadata["outcome_headline"])

    if workflow_status == "completed" and human_intervention_count:
        return "Escalated invoice reached payment after a human approval handoff."
    if workflow_status == "completed":
        return "Agent-guided invoice reached payment without leaving delegated authority."
    if workflow_status == "rejected":
        return "Policy and human review stopped the workflow before an unsafe approval could land."
    if blocked_count:
        return "The workflow stalled because policy blocked the requested action."
    return "The replay reconstructs the current workflow evidence trail."


def _build_highlights(entries: list[ReplayEntry]) -> list[ReplayHighlight]:
    highlights: list[ReplayHighlight] = []

    def add_highlight(label: str, predicate, severity: str, *, latest: bool = False) -> None:
        ordered_entries = reversed(entries) if latest else entries
        for entry in ordered_entries:
            if predicate(entry):
                highlights.append(
                    ReplayHighlight(
                        label=label,
                        detail=entry.headline or entry.action_summary,
                        severity=severity,
                        event_id=entry.event_id,
                    )
                )
                return

    add_highlight("Agent action", lambda entry: entry.event_kind == "agent_action", "info")
    add_highlight("Policy gate", lambda entry: entry.event_kind == "policy_evaluation", "medium", latest=True)
    add_highlight("Blocked path", lambda entry: entry.blocked, "high")
    add_highlight("Human intervention", lambda entry: entry.human_intervention, "medium", latest=True)

    if entries:
        last = entries[-1]
        highlights.append(
            ReplayHighlight(
                label="Final outcome",
                detail=last.headline or last.action_summary,
                severity="low" if last.outcome_status == "success" else "high",
                event_id=last.event_id,
            )
        )

    return highlights


def build_replay_timeline(
    session: Session,
    workflow_id: str,
    persist: bool = True,
) -> ReplayTimeline:
    workflow = get_workflow(session, workflow_id)
    if workflow is None:
        raise ValueError(f"Workflow {workflow_id} was not found.")

    events = get_workflow_events(session, workflow_id)
    entries: list[ReplayEntry] = []
    escalation_count = 0
    blocked_count = 0
    human_intervention_count = 0
    actor_handoff_count = 0
    previous_event = None

    for index, event in enumerate(events, start=1):
        transition_label = None
        if previous_event and previous_event.actor_type != event.actor_type:
            actor_handoff_count += 1
            transition_label = f"{previous_event.actor_type.value} -> {event.actor_type.value}"

        escalation_point = event.policy_status in {
            PolicyStatus.ESCALATED,
            PolicyStatus.REQUIRES_HUMAN_REVIEW,
        }
        blocked = event.policy_status == PolicyStatus.BLOCKED
        human_intervention = event.actor_type == ActorType.HUMAN
        if escalation_point:
            escalation_count += 1
        if blocked:
            blocked_count += 1
        if human_intervention:
            human_intervention_count += 1

        entries.append(
            ReplayEntry(
                sequence_number=index,
                event_id=event.event_id,
                timestamp=event.timestamp,
                process_step=event.process_step,
                actor_type=event.actor_type.value,
                actor_name=event.actor_name,
                action_type=event.action_type,
                action_summary=event.action_summary,
                policy_status=event.policy_status.value,
                outcome_status=event.outcome_status.value,
                headline=_headline(event),
                event_kind=_event_kind(event),
                permission_scope=event.permission_scope,
                tool_name=event.tool_name,
                target_system=event.target_system,
                why_it_mattered=_why_it_mattered(event),
                policy_explanation=_policy_explanation(event),
                recommended_next_action=_policy_payload(event).get("recommended_next_action"),
                business_consequence=_entry_business_consequence(event),
                transition_label=transition_label,
                escalation_point=escalation_point,
                blocked=blocked,
                human_intervention=human_intervention,
            )
        )
        previous_event = event

    final_outcome = workflow.status
    summary_headline = _summary_headline(
        workflow_status=final_outcome,
        events=events,
        human_intervention_count=human_intervention_count,
        blocked_count=blocked_count,
    )
    policy_story = _policy_story(events)
    business_consequence = _workflow_business_consequence(events)
    highlights = _build_highlights(entries)

    summary = {
        "workflow_name": workflow.workflow_name,
        "final_outcome": final_outcome,
        "summary_headline": summary_headline,
        "policy_story": policy_story,
        "business_consequence": business_consequence,
        "escalation_count": escalation_count,
        "blocked_count": blocked_count,
        "human_intervention_count": human_intervention_count,
        "actor_handoff_count": actor_handoff_count,
        "highlights": [highlight.model_dump(mode="json") for highlight in highlights],
    }
    replay_session_id = f"replay_{workflow_id}"
    if persist:
        replay_session_id = upsert_replay_session(
            session=session,
            workflow_id=workflow_id,
            event_count=len(entries),
            final_outcome=final_outcome,
            summary_json=summary,
        )

    return ReplayTimeline(
        replay_session_id=replay_session_id,
        workflow_id=workflow.workflow_id,
        workflow_name=workflow.workflow_name,
        final_outcome=final_outcome,
        summary_headline=summary_headline,
        policy_story=policy_story,
        business_consequence=business_consequence,
        escalation_count=escalation_count,
        blocked_count=blocked_count,
        human_intervention_count=human_intervention_count,
        actor_handoff_count=actor_handoff_count,
        highlights=highlights,
        entries=entries,
    )
