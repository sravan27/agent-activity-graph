from __future__ import annotations

from sqlalchemy import select

from agent_activity_graph.db.models import WorkflowRecord
from agent_activity_graph.db.repository import ingest_event, reset_database, seed_policy_rules
from agent_activity_graph.db.session import SessionLocal, init_db
from agent_activity_graph.demo.scenarios import invoice_approval_scenario
from agent_activity_graph.policy.evaluator import PolicyEvaluator

DEMO_WORKFLOW_IDS = {"wf-invoice-1001", "wf-invoice-2001", "wf-invoice-3001"}


def seed_demo_data() -> dict[str, int]:
    init_db()
    evaluator = PolicyEvaluator()

    with SessionLocal() as session:
        seed_policy_rules(session)
        existing = set(session.scalars(select(WorkflowRecord.workflow_id)).all())
        if existing and existing.issubset(DEMO_WORKFLOW_IDS):
            reset_database(session)
            seed_policy_rules(session)
        elif existing:
            return {"workflows": len(existing), "events": 0}

        events = invoice_approval_scenario()
        for event in events:
            ingest_event(session, event, evaluator=evaluator)
        workflows = session.scalars(select(WorkflowRecord.workflow_id)).all()
        return {"workflows": len(workflows), "events": len(events)}


def main() -> None:
    result = seed_demo_data()
    print(f"Seed complete: {result['workflows']} workflows available, {result['events']} events ingested.")
    print("Suggested demo path after `make run`:")
    print("  http://127.0.0.1:8000/")
    print("  http://127.0.0.1:8000/workflows/wf-invoice-3001")
    print("  http://127.0.0.1:8000/workflows/wf-invoice-3001/replay")
    print("  http://127.0.0.1:8000/incidents/inc_evt_wf_3001_05")
    print("  http://127.0.0.1:8000/incidents/inc_evt_wf_3001_05/evidence-pack")


if __name__ == "__main__":
    main()
