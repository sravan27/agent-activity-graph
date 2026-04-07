from __future__ import annotations

from pathlib import Path

from agent_activity_graph.review import (
    build_review_readiness_benchmark_rows,
    render_review_readiness_benchmark_markdown,
)


def main() -> None:
    rows = build_review_readiness_benchmark_rows()
    output_path = Path(__file__).resolve().parents[1] / "docs" / "review-readiness-benchmark.md"
    output_path.write_text(render_review_readiness_benchmark_markdown(rows))
    print(f"Wrote review-readiness benchmark to {output_path}")
    print(f"Benchmarked {len(rows)} runs.")


if __name__ == "__main__":
    main()
