from __future__ import annotations

from sqlalchemy.orm import Session

from agent_activity_graph.db.repository import (
    get_event,
    get_incident,
    get_incident_record,
    get_workflow,
    get_workflow_events,
)
from agent_activity_graph.replay.timeline import build_replay_timeline
from agent_activity_graph.sdk.events import IncidentDetail


def build_incident_detail(session: Session, incident_id: str) -> IncidentDetail:
    incident = get_incident(session, incident_id)
    incident_record = get_incident_record(session, incident_id)
    if incident is None or incident_record is None:
        raise ValueError(f"Incident {incident_id} was not found.")

    workflow = get_workflow(session, incident.workflow_id)
    if workflow is None:
        raise ValueError(f"Workflow {incident.workflow_id} was not found.")

    trigger_event = get_event(session, incident.trigger_event_id)
    if trigger_event is None:
        raise ValueError(f"Trigger event {incident.trigger_event_id} was not found.")

    events = get_workflow_events(session, incident.workflow_id)
    trigger_index = next(
        (index for index, event in enumerate(events) if event.event_id == incident.trigger_event_id),
        0,
    )
    start = max(trigger_index - 2, 0)
    end = min(trigger_index + 3, len(events))
    related_events = events[start:end]
    replay = build_replay_timeline(session, incident.workflow_id, persist=False)

    return IncidentDetail(
        incident=incident,
        workflow=workflow,
        trigger_event=trigger_event,
        related_events=related_events,
        replay=replay,
    )
