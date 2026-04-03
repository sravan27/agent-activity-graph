# Architecture

Agent Activity Graph uses a deliberately small stack:

- FastAPI for ingestion and read APIs
- Pydantic for canonical schemas
- SQLite for local evidence storage
- SQLAlchemy for persistence
- NetworkX for activity graph construction
- Jinja2 templates for replay, incident, and evidence-pack views

## Core Flow

```text
event -> validation -> policy evaluation -> SQLite evidence store -> projections
```

The projections are where the product thesis becomes visible:

- workflow summary
- incident record
- activity graph
- replay timeline
- exportable evidence pack

## Design Choices

### Canonical event first

Everything is downstream of `WorkflowEvent`. The graph, replay, incident view, and evidence pack are all different readings of the same stored runtime trace.

### Policy stored with the event

Policy is not treated as hidden control flow. Every ingested event carries the evaluated policy decision, explanation, violated rules, and recommended next action inside the stored metadata.

### Replay as the primary lens

The strongest product surface is replay. It reconstructs the ordered sequence of agent, system, and human actions while preserving why each step mattered and what policy decided at that point.

### Local-first by default

SQLite keeps the project inspectable and auditable. The point is to make the layer obvious on a laptop, not to bury it behind deployment complexity.

## Stored Objects

### WorkflowEvent

The atomic runtime evidence record.

### WorkflowRecord

Materialized workflow summary for lists and current state.

### IncidentRecord

Review object for blocked, escalated, or risky runs.

### PolicyRuleRecord

Persisted description of the active local rule set.

### ReplaySessionRecord

Cached summary of the current replay reconstruction for a workflow.
