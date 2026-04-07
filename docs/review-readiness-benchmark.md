# Review Readiness Benchmark

This benchmark does not try to rank models or runtimes.
It measures whether a run is fit for policy-gated human review.

| Example | Source | Policy rule IDs | Authority chain | Review case | Human decision reason | Review readiness score | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| wf-invoice-2001 | seeded_workflow | yes | yes | yes | yes | 100 | review ready |
| wf-invoice-3001 | seeded_workflow | yes | yes | yes | yes | 100 | review ready |
| openai_agents_invoice_review | openai_agents | yes | yes | yes | yes | 100 | review ready |
| ollama_local_invoice_review | generic_openinference | yes | yes | yes | yes | 100 | review ready |
| openai_human_in_the_loop_invoice_reject | openai_agents | yes | yes | yes | yes | 100 | review ready |
| mcp_same_day_payment_review | mcp | yes | yes | yes | yes | 100 | review ready |

## Notes
- `review_ready` means a human can inspect the stored record without reconstructing hidden authority, policy, or provenance context.
- `needs_enrichment` means the record is usable, but some authority or provenance details still need to be made explicit.
- `not_review_ready` means a policy, human-review, provenance, or integrity hard-fail remains.

## Example basis
- `wf-invoice-2001`: Deterministic seeded invoice-approval run from the reference scenario.
- `wf-invoice-3001`: Deterministic seeded invoice-approval run from the reference scenario.
- `openai_agents_invoice_review`: Public-source-derived proof fixture based on official OpenAI Agents tracing and human approval patterns plus the MCP tools approval model.
- `ollama_local_invoice_review`: Runtime-generated free local export from an Ollama-backed invoice approval agent.
- `openai_human_in_the_loop_invoice_reject`: Public-source-derived fixture based on the OpenAI Agents human-in-the-loop approval pattern, mapped into the invoice review control loop.
- `mcp_same_day_payment_review`: Public-source-derived MCP fixture based on hosted MCP approval patterns, mapped into a finance control path with explicit policy and human review evidence.