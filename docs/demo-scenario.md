# Demo Scenario

The v1 scenario is fixed on purpose:

**invoice approval workflow with agent participation**

This is not here to simulate a complete AP product. It is here because invoice approval gives a compact, believable place to show:

- agent action
- policy gating
- escalation
- blocked behavior
- human intervention
- final business outcome

## Workflow Shape

The workflow is modeled as a sequence of evidence-bearing steps:

1. invoice received
2. agent classification
3. PO or supporting evidence check
4. agent recommendation packet
5. policy gate
6. approval or rejection path
7. final outcome

The policy gate is intentionally explicit. It is the clearest way to show that orchestration and control are not the same thing.

## Seeded Runs

### Run 1: Normal path

- low-value invoice
- valid PO
- agent prepares the case
- policy gate allows continuation
- agent approves
- ERP schedules payment

What it proves:

- the agent can stay inside delegated authority
- policy is visible even when it allows the path
- replay can show a full successful run without inventing drama

### Run 2: Escalated path

- high-value consulting invoice
- same-day payment pressure
- agent prepares the case
- policy gate escalates because the amount exceeds the delegated threshold
- finance director approves
- ERP schedules payment before cut-off

What it proves:

- policy can redirect the workflow without erasing the original agent work
- human approval appears as a clear authority handoff
- replay can connect control logic to business consequence

Concrete consequence:

- if approval misses the payment cut-off, the invoice slips at least one business day

### Run 3: Blocked path

- exception invoice
- missing PO
- agent still prepares a recommendation
- policy gate blocks the path
- agent attempts a disallowed approval action anyway
- AP manager rejects and places the invoice on manual hold

What it proves:

- the evidence layer captures policy breach attempts, not just happy-path outcomes
- blocked actions become explicit incidents
- a human can close the run with a visible, reviewable intervention

Concrete consequence:

- the invoice is delayed by at least one payment cycle and now carries policy breach review overhead

