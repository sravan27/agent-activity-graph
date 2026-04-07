# Public Trace Fixtures

The JSON fixtures in this directory are intentionally small and deterministic.

They are **not** presented as raw production exports. They are public-source-derived
proof fixtures shaped to match `TraceIngestionRequest` and the current
invoice-review control loop.

The default fixtures are adapted from current official upstream patterns:

- OpenAI Agents tracing docs:
  `https://openai.github.io/openai-agents-python/tracing/`
- OpenAI Agents human-in-the-loop example:
  `https://github.com/openai/openai-agents-python/blob/main/examples/agent_patterns/human_in_the_loop.py`
- OpenAI Agents hosted MCP approval example:
  `https://github.com/openai/openai-agents-python/blob/main/examples/hosted_mcp/on_approval.py`
- MCP tools spec:
  `https://modelcontextprotocol.io/specification/2025-06-18/server/tools`

What is adapted:

- the business domain is invoice approval instead of weather or repository lookup
- the MCP tool call is expressed as a PO verification step in a finance workflow
- policy escalation and finance approval are modeled as business evidence instead
  of raw SDK interruption objects

What is preserved from the public source basis:

- a trace-shaped event stream with agent, tool, policy, and human steps
- human approval as an explicit runtime control point
- MCP tool invocation as a first-class step in the run
- a trace identifier that follows the OpenAI Agents tracing format

Included proof fixtures:

- `openai_agents_invoice_review.json`
- `openai_human_in_the_loop_invoice_reject.json`
- `mcp_same_day_payment_review.json`

The goal of these fixtures is honesty, not theater: they prove the ingestion,
review surface, and review-readiness benchmark against current public agent
runtime patterns without pretending they came from a private production system.

The repository can also generate a real local export for free:

```bash
make generate-local-trace
```

That command runs an actual Ollama-backed invoice approval agent on the local
machine and writes `ollama_local_invoice_review.json`. Unlike the public-source
fixture above, that file is runtime-generated from a real local execution.
