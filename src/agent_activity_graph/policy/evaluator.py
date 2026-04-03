from __future__ import annotations

from agent_activity_graph.policy.rules import DEFAULT_RULES, RuntimeRule
from agent_activity_graph.sdk.events import PolicyDecision, PolicyStatus, WorkflowEvent


DECISION_PRIORITY = {
    PolicyStatus.ALLOWED: 0,
    PolicyStatus.REQUIRES_HUMAN_REVIEW: 1,
    PolicyStatus.ESCALATED: 2,
    PolicyStatus.BLOCKED: 3,
}


class PolicyEvaluator:
    def __init__(self, rules: list[RuntimeRule] | None = None) -> None:
        self.rules = rules or DEFAULT_RULES

    def evaluate(self, event: WorkflowEvent) -> PolicyDecision:
        violations = []
        decision = PolicyStatus.ALLOWED

        for rule in self.rules:
            outcome = rule.evaluator(event)
            if outcome is None:
                continue
            violations.append(outcome)
            if DECISION_PRIORITY[outcome.decision] > DECISION_PRIORITY[decision]:
                decision = outcome.decision

        if not violations:
            return PolicyDecision(
                decision=PolicyStatus.ALLOWED,
                violated_rules=[],
                explanation="No policy rule blocked or altered this action.",
                recommended_next_action="Continue the workflow and record the resulting evidence.",
            )

        explanation = " ".join(violation.message for violation in violations)
        recommended = next(
            violation.recommended_action
            for violation in violations
            if violation.decision == decision
        )
        return PolicyDecision(
            decision=decision,
            violated_rules=violations,
            explanation=explanation,
            recommended_next_action=recommended,
        )

