from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_activity_graph.sdk.client import AgentActivityGraphClient
from agent_activity_graph.sdk.events import TraceIngestionRequest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest an OpenInference-style trace into Agent Activity Graph.",
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Path to a JSON file that matches TraceIngestionRequest.",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Agent Activity Graph base URL.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    payload = json.loads(Path(args.file).read_text())
    trace = TraceIngestionRequest.model_validate(payload)
    client = AgentActivityGraphClient(base_url=args.base_url)
    result = client.send_openinference_trace(trace)

    print(f"Ingested {result.ingested_events} events into workflow {result.workflow_id}.")
    print(f"Source: {result.source.value}")
    print(f"Replay: {args.base_url.rstrip('/')}/workflows/{result.workflow_id}/replay")
    if result.incident_ids:
        print("Incidents:")
        for incident_id in result.incident_ids:
            print(f"  {args.base_url.rstrip('/')}/incidents/{incident_id}")
            print(f"  {args.base_url.rstrip('/')}/incidents/{incident_id}/evidence-pack")


if __name__ == "__main__":
    main()
