from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_activity_graph.db.repository import get_workflow_events, ingest_event, seed_policy_rules
from agent_activity_graph.db.session import build_session_factory
from agent_activity_graph.demo.scenarios import invoice_approval_scenario
from agent_activity_graph.policy.evaluator import PolicyEvaluator
from agent_activity_graph.review.readiness import grade_trace_request, grade_workflow
from agent_activity_graph.sdk.events import TraceIngestionRequest, WorkflowEvent
from agent_activity_graph.sdk.trace_adapter import map_trace_to_workflow_events

DEFAULT_TRACE_FIXTURES = (
    "openai_agents_invoice_review.json",
    "ollama_local_invoice_review.json",
    "openai_human_in_the_loop_invoice_reject.json",
    "mcp_same_day_payment_review.json",
)


@dataclass(frozen=True)
class ReviewReadinessBenchmarkRow:
    example: str
    source: str
    has_policy_rule_ids: bool
    has_authority_chain: bool
    has_review_case: bool
    has_human_decision_reason: bool
    review_readiness_score: int
    status: str
    notes: str | None = None


def _bool_cell(value: bool) -> str:
    return "yes" if value else "no"


def _summarize_events(events: list[WorkflowEvent]) -> dict[str, bool]:
    return {
        "has_policy_rule_ids": any(event.policy_rule_ids for event in events),
        "has_authority_chain": any(
            event.authority_subject and event.authority_delegation_source
            for event in events
            if event.actor_type.value in {"agent", "human"}
        ),
        "has_review_case": any(bool(event.review_case_id) for event in events),
        "has_human_decision_reason": any(
            bool(event.human_decision_reason or event.decision_rationale)
            for event in events
            if event.actor_type.value == "human"
        ),
    }


def _trace_row(path: Path) -> ReviewReadinessBenchmarkRow:
    payload = json.loads(path.read_text())
    request = TraceIngestionRequest.model_validate(payload)
    report = grade_trace_request(request)
    summary = _summarize_events(map_trace_to_workflow_events(request))
    note = request.workflow.workflow_defaults.get("trace_fixture_basis")

    return ReviewReadinessBenchmarkRow(
        example=path.stem,
        source=request.source.value,
        has_policy_rule_ids=summary["has_policy_rule_ids"],
        has_authority_chain=summary["has_authority_chain"],
        has_review_case=summary["has_review_case"],
        has_human_decision_reason=summary["has_human_decision_reason"],
        review_readiness_score=report.overall_score,
        status=report.status,
        notes=str(note) if note else None,
    )


def _seeded_workflow_rows() -> list[ReviewReadinessBenchmarkRow]:
    with TemporaryDirectory() as tmp_dir:
        database_url = f"sqlite:///{Path(tmp_dir) / 'benchmark.db'}"
        engine, session_factory = build_session_factory(database_url)
        try:
            with session_factory() as session:
                seed_policy_rules(session)
                evaluator = PolicyEvaluator()
                for event in invoice_approval_scenario():
                    ingest_event(session, event, evaluator=evaluator)

                rows: list[ReviewReadinessBenchmarkRow] = []
                for workflow_id in ("wf-invoice-2001", "wf-invoice-3001"):
                    report = grade_workflow(session, workflow_id)
                    summary = _summarize_events(get_workflow_events(session, workflow_id))
                    rows.append(
                        ReviewReadinessBenchmarkRow(
                            example=workflow_id,
                            source="seeded_workflow",
                            has_policy_rule_ids=summary["has_policy_rule_ids"],
                            has_authority_chain=summary["has_authority_chain"],
                            has_review_case=summary["has_review_case"],
                            has_human_decision_reason=summary["has_human_decision_reason"],
                            review_readiness_score=report.overall_score,
                            status=report.status,
                            notes="Deterministic seeded invoice-approval run from the reference scenario.",
                        )
                    )
                return rows
        finally:
            engine.dispose()


def build_review_readiness_benchmark_rows(trace_dir: Path | None = None) -> list[ReviewReadinessBenchmarkRow]:
    benchmark_rows = _seeded_workflow_rows()
    fixtures_root = trace_dir or (Path(__file__).resolve().parents[3] / "examples" / "traces")
    for fixture_name in DEFAULT_TRACE_FIXTURES:
        benchmark_rows.append(_trace_row(fixtures_root / fixture_name))
    return benchmark_rows


def render_review_readiness_benchmark_markdown(rows: list[ReviewReadinessBenchmarkRow]) -> str:
    lines = [
        "# Review Readiness Benchmark",
        "",
        "This benchmark does not try to rank models or runtimes.",
        "It measures whether a run is fit for policy-gated human review.",
        "",
        "| Example | Source | Policy rule IDs | Authority chain | Review case | Human decision reason | Review readiness score | Status |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for row in rows:
        lines.append(
            "| "
            f"{row.example} | "
            f"{row.source} | "
            f"{_bool_cell(row.has_policy_rule_ids)} | "
            f"{_bool_cell(row.has_authority_chain)} | "
            f"{_bool_cell(row.has_review_case)} | "
            f"{_bool_cell(row.has_human_decision_reason)} | "
            f"{row.review_readiness_score} | "
            f"{row.status.replace('_', ' ')} |"
        )

    lines.extend(
        [
            "",
            "## Notes",
            "- `review_ready` means a human can inspect the stored record without reconstructing hidden authority, policy, or provenance context.",
            "- `needs_enrichment` means the record is usable, but some authority or provenance details still need to be made explicit.",
            "- `not_review_ready` means a policy, human-review, provenance, or integrity hard-fail remains.",
            "",
            "## Example basis",
        ]
    )

    for row in rows:
        if row.notes:
            lines.append(f"- `{row.example}`: {row.notes}")

    return "\n".join(lines)
