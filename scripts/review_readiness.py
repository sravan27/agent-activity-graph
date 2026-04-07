from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_activity_graph.db.session import build_session_factory, get_database_url
from agent_activity_graph.review import (
    build_review_readiness_markdown,
    grade_trace_request,
    grade_workflow,
)
from agent_activity_graph.sdk.events import TraceIngestionRequest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Grade a workflow or OpenInference-style trace against the Agent Activity Graph review-readiness spec.",
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--file", help="Path to a JSON trace file that matches TraceIngestionRequest.")
    target.add_argument("--workflow-id", help="Workflow ID to grade from the local database.")
    parser.add_argument(
        "--database-url",
        default=get_database_url(),
        help="Database URL used when grading a stored workflow.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Output format.",
    )
    parser.add_argument(
        "--output",
        help="Optional output file path. If omitted, the report is printed to stdout.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.file:
        payload = json.loads(Path(args.file).read_text())
        report = grade_trace_request(TraceIngestionRequest.model_validate(payload))
    else:
        engine, session_factory = build_session_factory(args.database_url)
        try:
            with session_factory() as session:
                report = grade_workflow(session, args.workflow_id)
        finally:
            engine.dispose()

    if args.format == "json":
        output = json.dumps(report.model_dump(mode="json"), indent=2)
    else:
        output = build_review_readiness_markdown(report)

    if args.output:
        Path(args.output).write_text(output)
        print(f"Wrote review-readiness report to {args.output}")
        print(f"Status: {report.status} | Score: {report.overall_score}")
        return

    print(output)


if __name__ == "__main__":
    main()
