# Architecture

Agent Activity Graph uses a deliberately small stack:

- FastAPI for ingestion and read APIs
- Pydantic for canonical schemas
- SQLite for local evidence storage
- SQLAlchemy for persistence
- NetworkX for activity graph construction
- Jinja2 templates for replay, incident, and evidence-pack views

The product wedge is deliberately narrower than generic observability:

- review system of record for blocked or escalated agent actions

## Core Flow

```text
workflow event or mapped trace
    -> validation
    -> policy evidence
    -> evidence hash chaining
    -> SQLite evidence store
    -> replay / incident / evidence pack
```

The projections are where the product thesis becomes visible:

- review queue
- review case
- workflow summary
- incident record
- activity graph
- replay timeline
- exportable evidence pack

## Design Choices

### Canonical event first

Everything is downstream of `WorkflowEvent`. The graph, replay, incident view, and evidence pack are all different readings of the same stored runtime trace.

The current event model now carries explicit authority, review, provenance, and integrity fields so the stored record can support human review rather than just debugging.

### Policy stored with the event

Policy is not treated as hidden control flow. Every ingested event carries the evaluated policy decision, explanation, violated rules, and recommended next action inside the stored metadata.

Trace-derived events can also preserve an upstream policy decision when the caller already has a policy verdict and wants Agent Activity Graph to act as the review layer above that trace.

### Trace adapter, not trace worship

The repository includes a single interoperability contract for OpenInference-style spans.

It can map:

- OpenAI Agents traces
- MCP tool spans
- generic OpenInference spans

The adapter does not pretend raw spans are already business evidence. The caller still has to make workflow step, authority, policy, and review context explicit.

When those fields are incomplete, the derived replay and evidence pack are marked as `needs_enrichment` rather than being presented as fully verified business evidence.

### Replay as the primary lens

The strongest product surface is replay. It reconstructs the ordered sequence of agent, system, and human actions while preserving why each step mattered and what policy decided at that point.

Replay also carries review case context, source trace references, and evidence-chain verification so the surface is useful for operational review, not only developer inspection.

### Review readiness as a named artifact

The repository now formalizes review readiness as `aag.review_readiness.v1`.

That spec grades each run across:

- authority completeness
- policy completeness
- human review completeness
- provenance completeness
- evidence integrity

This keeps the project from over-claiming. A trace can still be useful, but it only becomes review-ready evidence when those requirements are explicit and verifiable.

### Local-first by default

SQLite keeps the project inspectable and auditable. The point is to make the layer obvious on a laptop, not to bury it behind deployment complexity.

## Stored Objects

### WorkflowEvent

The atomic runtime evidence record.

Important fields beyond the basic action record:

- `authority_subject`
- `authority_delegation_source`
- `policy_rule_ids`
- `review_case_id`
- `review_state`
- `human_decision_reason`
- `decision_code`
- `decision_rationale`
- `approved_exception_type`
- `approver_role`
- `remediation_owner`
- `remediation_due_by`
- `closure_status`
- `due_by`
- `source_trace_ref`
- `source_system_ref`
- `evidence_hash`

### WorkflowRecord

Materialized workflow summary for lists and current state.

### IncidentRecord

Review object for blocked, escalated, or risky runs.

### PolicyRuleRecord

Persisted description of the active local rule set.

### ReplaySessionRecord

Cached summary of the current replay reconstruction for a workflow.
