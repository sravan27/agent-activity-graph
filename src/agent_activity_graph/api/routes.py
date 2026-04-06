from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agent_activity_graph.db.repository import (
    get_workflow,
    get_workflow_events,
    ingest_event,
    list_incidents,
    list_workflows,
)
from agent_activity_graph.db.session import get_session
from agent_activity_graph.graph.queries import build_graph_snapshot
from agent_activity_graph.policy.evaluator import PolicyEvaluator
from agent_activity_graph.replay.evidence_pack import build_evidence_pack
from agent_activity_graph.replay.incident import build_incident_detail
from agent_activity_graph.replay.timeline import build_replay_timeline
from agent_activity_graph.sdk.trace_adapter import map_trace_to_workflow_events
from agent_activity_graph.sdk.events import (
    EvidencePack,
    EventIngestionResponse,
    IncidentDetail,
    IncidentSummary,
    ReplayTimeline,
    TraceIngestionRequest,
    TraceIngestionResponse,
    WorkflowDetailResponse,
    WorkflowEvent,
    WorkflowGraphSnapshot,
    WorkflowSummary,
)

router = APIRouter(prefix="/api", tags=["agent-activity-graph"])
policy_evaluator = PolicyEvaluator()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/events", response_model=EventIngestionResponse, status_code=201)
def post_event(event: WorkflowEvent, session: Session = Depends(get_session)) -> EventIngestionResponse:
    try:
        return ingest_event(session, event, evaluator=policy_evaluator)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/traces/openinference", response_model=TraceIngestionResponse, status_code=201)
def post_openinference_trace(
    request: TraceIngestionRequest,
    session: Session = Depends(get_session),
) -> TraceIngestionResponse:
    incident_ids: list[str] = []
    event_ids: list[str] = []
    try:
        for event in map_trace_to_workflow_events(request):
            result = ingest_event(
                session,
                event,
                evaluator=policy_evaluator,
                preserve_event_policy=True,
            )
            event_ids.append(result.event.event_id)
            if result.incident_id and result.incident_id not in incident_ids:
                incident_ids.append(result.incident_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return TraceIngestionResponse(
        workflow_id=request.workflow.workflow_id,
        source=request.source,
        ingested_events=len(event_ids),
        incident_ids=incident_ids,
        event_ids=event_ids,
    )


@router.get("/workflows", response_model=list[WorkflowSummary])
def get_workflows(session: Session = Depends(get_session)) -> list[WorkflowSummary]:
    return list_workflows(session)


@router.get("/workflows/{workflow_id}", response_model=WorkflowDetailResponse)
def get_workflow_detail(
    workflow_id: str,
    session: Session = Depends(get_session),
) -> WorkflowDetailResponse:
    workflow = get_workflow(session, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} was not found.")

    events = get_workflow_events(session, workflow_id)
    incidents = list_incidents(session, workflow_id=workflow_id)
    graph = build_graph_snapshot(workflow_id, events)
    return WorkflowDetailResponse(workflow=workflow, events=events, incidents=incidents, graph=graph)


@router.get("/workflows/{workflow_id}/graph", response_model=WorkflowGraphSnapshot)
def get_graph(workflow_id: str, session: Session = Depends(get_session)) -> WorkflowGraphSnapshot:
    workflow = get_workflow(session, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} was not found.")
    events = get_workflow_events(session, workflow_id)
    return build_graph_snapshot(workflow_id, events)


@router.get("/workflows/{workflow_id}/replay", response_model=ReplayTimeline)
def get_replay(workflow_id: str, session: Session = Depends(get_session)) -> ReplayTimeline:
    try:
        return build_replay_timeline(session, workflow_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/incidents", response_model=list[IncidentSummary])
def get_incident_list(session: Session = Depends(get_session)) -> list[IncidentSummary]:
    return list_incidents(session)


@router.get("/incidents/{incident_id}", response_model=IncidentDetail)
def get_incident_detail(incident_id: str, session: Session = Depends(get_session)) -> IncidentDetail:
    try:
        return build_incident_detail(session, incident_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/incidents/{incident_id}/evidence-pack", response_model=EvidencePack)
def get_incident_evidence_pack(
    incident_id: str,
    session: Session = Depends(get_session),
) -> EvidencePack:
    try:
        return build_evidence_pack(session, incident_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
