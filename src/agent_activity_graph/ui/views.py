from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from agent_activity_graph.db.repository import (
    get_workflow,
    get_workflow_events,
    list_incidents,
    list_policy_rules,
    list_workflows,
)
from agent_activity_graph.db.session import get_session
from agent_activity_graph.graph.queries import build_graph_snapshot
from agent_activity_graph.replay.evidence_pack import (
    build_evidence_pack,
    render_evidence_pack_markdown,
)
from agent_activity_graph.replay.incident import build_incident_detail
from agent_activity_graph.replay.timeline import build_replay_timeline

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _workflow_context(events: list) -> dict:
    metadata: dict = {}
    for event in reversed(events):
        event_metadata = getattr(event, "metadata", None) or {}
        for key, value in event_metadata.items():
            if key in metadata:
                continue
            if value is None or value == "":
                continue
            metadata[key] = value
    return {
        "invoice_amount": metadata.get("invoice_amount"),
        "currency": metadata.get("currency", "USD"),
        "vendor_name": metadata.get("vendor_name"),
        "cost_center": metadata.get("cost_center"),
        "payment_terms": metadata.get("payment_terms"),
        "invoice_due_date": metadata.get("invoice_due_date"),
        "payment_batch_cutoff": metadata.get("payment_batch_cutoff"),
        "risk_category": metadata.get("risk_category"),
        "business_consequence": metadata.get("business_consequence"),
    }


@router.get("/", response_class=HTMLResponse)
def home(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    workflows = list_workflows(session)
    incidents = list_incidents(session)
    rules = list_policy_rules(session)
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "workflow_count": len(workflows),
            "incident_count": len(incidents),
            "policy_rule_count": len(rules),
            "recent_workflows": workflows[:3],
            "recent_incidents": incidents[:3],
        },
    )


@router.get("/workflows", response_class=HTMLResponse)
def workflows_page(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "workflows.html",
        {"workflows": list_workflows(session)},
    )


@router.get("/workflows/{workflow_id}", response_class=HTMLResponse)
def workflow_detail_page(
    workflow_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    workflow = get_workflow(session, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} was not found.")

    events = get_workflow_events(session, workflow_id)
    graph = build_graph_snapshot(workflow_id, events)
    replay = build_replay_timeline(session, workflow_id, persist=False)
    incidents = list_incidents(session, workflow_id=workflow_id)
    return templates.TemplateResponse(
        request,
        "workflow_detail.html",
        {
            "workflow": workflow,
            "events": events,
            "graph": graph,
            "replay": replay,
            "incidents": incidents,
            "workflow_context": _workflow_context(events),
        },
    )


@router.get("/workflows/{workflow_id}/replay", response_class=HTMLResponse)
def replay_page(
    workflow_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    workflow = get_workflow(session, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} was not found.")

    replay = build_replay_timeline(session, workflow_id, persist=False)
    return templates.TemplateResponse(
        request,
        "replay.html",
        {
            "workflow": workflow,
            "replay": replay,
            "workflow_context": _workflow_context(get_workflow_events(session, workflow_id)),
        },
    )


@router.get("/incidents/{incident_id}/evidence-pack", response_class=HTMLResponse)
def evidence_pack_page(
    incident_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    try:
        detail = build_incident_detail(session, incident_id)
        evidence_pack = build_evidence_pack(session, incident_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return templates.TemplateResponse(
        request,
        "evidence_pack.html",
        {
            "detail": detail,
            "evidence_pack": evidence_pack,
        },
    )


@router.get("/incidents/{incident_id}/evidence-pack.md", response_class=PlainTextResponse)
def evidence_pack_markdown(
    incident_id: str,
    session: Session = Depends(get_session),
) -> PlainTextResponse:
    try:
        evidence_pack = build_evidence_pack(session, incident_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    response = PlainTextResponse(render_evidence_pack_markdown(evidence_pack))
    response.headers["Content-Type"] = "text/markdown; charset=utf-8"
    response.headers["Content-Disposition"] = (
        f'attachment; filename="{incident_id}-evidence-pack.md"'
    )
    return response


@router.get("/incidents/{incident_id}", response_class=HTMLResponse)
def incident_page(
    incident_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    try:
        detail = build_incident_detail(session, incident_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return templates.TemplateResponse(
        request,
        "incident.html",
        {
            "detail": detail,
            "evidence_pack": build_evidence_pack(session, incident_id),
            "workflow_context": _workflow_context(detail.related_events or [detail.trigger_event]),
        },
    )
