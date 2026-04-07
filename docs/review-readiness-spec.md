# Review Readiness Spec

Agent Activity Graph treats review-ready evidence as a stricter object than a trace.

The current version is:

- `aag.review_readiness.v1`

It answers one narrow question:

**Can a human reviewer approve, reject, or audit a policy-gated agent action from the stored record alone?**

## Categories

The spec scores five categories:

1. `authority`
   Does the run say under whose authority the agent or human acted, and where that delegation came from?
2. `policy`
   Does the run preserve the policy decision, rule IDs, explanation, recommended next action, and review case linkage?
3. `human_review`
   If a human was required, does the run preserve the review state and, when resolved, the structured decision record?
4. `provenance`
   Can the run be tied back to a source trace and any systems or tools it touched?
5. `evidence_integrity`
   Does the chained evidence hash still match the stored event payloads?

## Statuses

- `review_ready`
  The record can support human review or later audit without reconstructing hidden context.
- `needs_enrichment`
  The record is useful, but some authority, policy, or provenance context still needs to be made explicit.
- `not_review_ready`
  A hard-fail remains in policy, human review, provenance, or evidence integrity.

## Current Structured Review Fields

When a review case resolves, the product expects:

- `decision_code`
- `decision_rationale`
- `approved_exception_type`
- `approver_role`
- `remediation_owner`
- `remediation_due_by`
- `closure_status`

These fields are not extra narrative. They are the operating record that lets replay, incident, and evidence-pack surfaces stay consistent.

## Why This Exists

Tracing tells you what ran.

Review-ready evidence tells you what a human can approve.

That is the wedge. The spec exists to make the missing layer measurable instead of rhetorical.
