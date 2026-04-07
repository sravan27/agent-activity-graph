# Thesis

Agentic enterprise software is missing a runtime evidence layer.

Tracing tells you what ran.

Review-ready evidence tells you what a human can approve.

Most systems today stop at orchestration. They can route work, call tools, and produce outcomes, but they do not preserve the controlled runtime truth of what happened inside a business workflow.

That gap becomes obvious the moment an agent touches finance, procurement, support, or operations work.

The question is no longer:

- can the agent act?

The question becomes:

- what exactly did it do
- under whose authority
- against which system
- in which workflow step
- what did policy decide
- where did a human take over
- how do we replay the run now

That is a different layer from prompting, orchestration, or dashboards.

## What The Missing Layer Is

The missing layer is not another planner and not a generic observability tool.

It is a workflow-aware evidence model that preserves:

- action
- actor
- authority
- policy verdict
- system touchpoint
- business object
- sequence
- handoff
- outcome
- review case
- provenance
- evidence integrity

When that layer exists, engineering, process, and governance teams can all reason about the same runtime record.

When it does not, review collapses into scattered logs, application state, and prompt assumptions.

The trust boundary matters too: a trace may still be useful even when it is incomplete, but it should not be represented as review-ready evidence until authority, policy, and review context are explicit.

## Why This Matters

Enterprises do not just need agents that can act.

They need agents that can be investigated, replayed, and governed after acting.

That means policy has to be recorded as evidence. Human intervention has to be visible in the same trace. Business consequence has to be attached to the run so the workflow is understandable in operational terms, not only technical ones.

It also means the product should stay focused on the point where trust breaks:

- the blocked or escalated agent action that now needs human review

## Why This Project Is Narrow

Agent Activity Graph deliberately stays inside one workflow:

- invoice approval with agent participation

The narrowness is a feature. It keeps the core point visible:

runtime evidence should be treated as a first-class product layer for enterprise agent systems.
