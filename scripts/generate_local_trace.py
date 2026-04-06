from __future__ import annotations

import argparse
from pathlib import Path

from agent_activity_graph.demo.local_trace import (
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_MODEL,
    generate_local_review_trace,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a real local invoice-review trace using an Ollama-backed agent.",
    )
    parser.add_argument(
        "--output",
        default="examples/traces/ollama_local_invoice_review.json",
        help="Path to write the generated TraceIngestionRequest JSON.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_OLLAMA_MODEL,
        help="Ollama model to use.",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_OLLAMA_BASE_URL,
        help="Ollama base URL.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    trace = generate_local_review_trace(model=args.model, base_url=args.base_url)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(trace.model_dump_json(indent=2))

    print(f"Wrote runtime-generated trace to {output_path}.")
    print(f"Workflow: {trace.workflow.workflow_id}")
    print(f"Trace source: {trace.source.value}")
    print(f"Model: {trace.workflow.workflow_defaults.get('ollama_model')}")


if __name__ == "__main__":
    main()
