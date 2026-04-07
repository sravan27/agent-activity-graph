from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agent_activity_graph.utils.time import ensure_utc, utcnow


class ActorType(str, Enum):
    HUMAN = "human"
    AGENT = "agent"
    SYSTEM = "system"


class PolicyStatus(str, Enum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    ESCALATED = "escalated"
    REQUIRES_HUMAN_REVIEW = "requires_human_review"


class OutcomeStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"
    SKIPPED = "skipped"


class WorkflowEvent(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    event_id: str = Field(default_factory=lambda: f"evt_{uuid4().hex}")
    timestamp: datetime = Field(default_factory=utcnow)
    workflow_id: str
    workflow_name: str
    process_step: str
    actor_type: ActorType
    actor_id: str
    actor_name: str
    action_type: str
    action_summary: str
    tool_name: str | None = None
    target_system: str | None = None
    business_object_type: str
    business_object_id: str
    permission_scope: str | None = None
    authority_subject: str | None = None
    authority_delegation_source: str | None = None
    policy_status: PolicyStatus = PolicyStatus.ALLOWED
    policy_rule_ids: list[str] = Field(default_factory=list)
    review_case_id: str | None = None
    review_state: str | None = None
    human_decision_reason: str | None = None
    decision_code: str | None = None
    decision_rationale: str | None = None
    approved_exception_type: str | None = None
    approver_role: str | None = None
    remediation_owner: str | None = None
    remediation_due_by: datetime | None = None
    closure_status: str | None = None
    due_by: datetime | None = None
    source_trace_ref: str | None = None
    source_system_ref: str | None = None
    evidence_hash: str | None = None
    outcome_status: OutcomeStatus = OutcomeStatus.PENDING
    parent_event_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "workflow_id",
        "workflow_name",
        "process_step",
        "actor_id",
        "actor_name",
        "action_type",
        "action_summary",
        "business_object_type",
        "business_object_id",
    )
    @classmethod
    def require_non_empty_strings(cls, value: str) -> str:
        if not value:
            raise ValueError("field must not be empty")
        return value

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @field_validator("due_by", "remediation_due_by")
    @classmethod
    def normalize_due_by(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value else None

    @field_validator("policy_rule_ids")
    @classmethod
    def normalize_policy_rule_ids(cls, value: list[str]) -> list[str]:
        return [item for item in dict.fromkeys(item.strip() for item in value if item and item.strip())]

    @field_validator("metadata")
    @classmethod
    def require_dict_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return value or {}

    @model_validator(mode="after")
    def validate_authority_fields(self) -> "WorkflowEvent":
        if self.actor_type in {ActorType.HUMAN, ActorType.AGENT} and not self.permission_scope:
            raise ValueError("permission_scope is required for human and agent actions")
        return self


class RuleViolation(BaseModel):
    rule_id: str
    rule_name: str
    decision: PolicyStatus
    message: str
    recommended_action: str


class PolicyDecision(BaseModel):
    decision: PolicyStatus
    violated_rules: list[RuleViolation] = Field(default_factory=list)
    explanation: str
    recommended_next_action: str


class EventIngestionResponse(BaseModel):
    event: WorkflowEvent
    policy: PolicyDecision
    incident_id: str | None = None


class TraceSource(str, Enum):
    GENERIC_OPENINFERENCE = "generic_openinference"
    OPENAI_AGENTS = "openai_agents"
    MCP = "mcp"


class TraceWorkflowContext(BaseModel):
    workflow_id: str
    workflow_name: str
    business_object_type: str
    business_object_id: str
    workflow_defaults: dict[str, Any] = Field(default_factory=dict)


class TraceSpan(BaseModel):
    span_id: str
    parent_span_id: str | None = None
    name: str
    start_time: datetime
    end_time: datetime | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    status: str | None = None

    @field_validator("start_time", "end_time")
    @classmethod
    def normalize_span_time(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value else None


class TraceIngestionRequest(BaseModel):
    source: TraceSource = TraceSource.GENERIC_OPENINFERENCE
    workflow: TraceWorkflowContext
    spans: list[TraceSpan]


class TraceIngestionResponse(BaseModel):
    workflow_id: str
    source: TraceSource
    ingested_events: int
    incident_ids: list[str] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)


class WorkflowSummary(BaseModel):
    workflow_id: str
    workflow_name: str
    business_object_type: str
    business_object_id: str
    status: str
    current_step: str | None = None
    started_at: datetime
    last_event_at: datetime
    event_count: int
    incident_count: int
    last_policy_status: str | None = None
    final_outcome: str | None = None


class IncidentSummary(BaseModel):
    incident_id: str
    workflow_id: str
    severity: str
    status: str
    title: str
    summary: str
    explanation: str
    recommended_next_action: str
    trigger_event_id: str
    created_at: datetime


class GraphNode(BaseModel):
    event_id: str
    label: str
    timestamp: datetime
    process_step: str
    actor_type: str
    actor_name: str
    action_type: str
    policy_status: str
    outcome_status: str
    target_system: str | None = None


class GraphEdge(BaseModel):
    source_event_id: str
    target_event_id: str
    relationship: str


class WorkflowGraphSnapshot(BaseModel):
    workflow_id: str
    node_count: int
    edge_count: int
    actor_transitions: int
    systems_touched: list[str]
    blocked_event_ids: list[str]
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class ReplayEntry(BaseModel):
    sequence_number: int
    event_id: str
    timestamp: datetime
    process_step: str
    actor_type: str
    actor_name: str
    action_type: str
    action_summary: str
    policy_status: str
    outcome_status: str
    headline: str | None = None
    event_kind: str = "activity"
    permission_scope: str | None = None
    authority_subject: str | None = None
    authority_delegation_source: str | None = None
    tool_name: str | None = None
    target_system: str | None = None
    policy_rule_ids: list[str] = Field(default_factory=list)
    review_case_id: str | None = None
    review_state: str | None = None
    human_decision_reason: str | None = None
    decision_code: str | None = None
    decision_rationale: str | None = None
    approved_exception_type: str | None = None
    approver_role: str | None = None
    remediation_owner: str | None = None
    remediation_due_by: datetime | None = None
    closure_status: str | None = None
    due_by: datetime | None = None
    source_trace_ref: str | None = None
    source_system_ref: str | None = None
    evidence_hash: str | None = None
    why_it_mattered: str | None = None
    policy_explanation: str | None = None
    recommended_next_action: str | None = None
    business_consequence: str | None = None
    transition_label: str | None = None
    escalation_point: bool = False
    blocked: bool = False
    human_intervention: bool = False


class ReplayHighlight(BaseModel):
    label: str
    detail: str
    severity: str = "info"
    event_id: str | None = None


class ReplayTimeline(BaseModel):
    replay_session_id: str
    workflow_id: str
    workflow_name: str
    final_outcome: str
    summary_headline: str
    policy_story: str
    business_consequence: str | None = None
    escalation_count: int
    blocked_count: int
    human_intervention_count: int
    actor_handoff_count: int
    review_case_id: str | None = None
    source_trace_refs: list[str] = Field(default_factory=list)
    review_readiness_spec_version: str | None = None
    evidence_status: str = "verified"
    evidence_score: int = 100
    evidence_issues: list[str] = Field(default_factory=list)
    highlights: list[ReplayHighlight] = Field(default_factory=list)
    entries: list[ReplayEntry]


class WorkflowDetailResponse(BaseModel):
    workflow: WorkflowSummary
    events: list[WorkflowEvent]
    incidents: list[IncidentSummary]
    graph: WorkflowGraphSnapshot


class IncidentDetail(BaseModel):
    incident: IncidentSummary
    workflow: WorkflowSummary
    trigger_event: WorkflowEvent
    related_events: list[WorkflowEvent]
    replay: ReplayTimeline


class ReviewCaseSummary(BaseModel):
    review_case_id: str
    workflow_id: str
    workflow_name: str
    business_object_id: str
    status: str
    review_state: str | None = None
    policy_decision: str | None = None
    title: str
    summary: str
    due_by: datetime | None = None
    business_consequence: str | None = None
    evidence_status: str = "verified"
    evidence_score: int = 100
    authority_owner: str | None = None
    human_owner: str | None = None
    approver_role: str | None = None
    closure_status: str | None = None
    primary_incident_id: str | None = None
    incident_count: int = 0
    decision_code: str | None = None
    approved_exception_type: str | None = None
    remediation_owner: str | None = None
    remediation_due_by: datetime | None = None


class ReviewCaseDetail(BaseModel):
    review_case: ReviewCaseSummary
    workflow: WorkflowSummary
    replay: ReplayTimeline
    incidents: list[IncidentSummary] = Field(default_factory=list)
    primary_incident: IncidentSummary | None = None
    policy_event: WorkflowEvent | None = None
    resolution_event: WorkflowEvent | None = None
    case_events: list[WorkflowEvent] = Field(default_factory=list)


class ReviewReadinessCategory(BaseModel):
    key: str
    label: str
    score: int
    passed_checks: int
    total_checks: int
    hard_fail_reasons: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ReviewReadinessReport(BaseModel):
    spec_version: str
    target_type: str
    target_id: str
    status: str
    overall_score: int
    hard_fail_reasons: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    summary: str
    categories: list[ReviewReadinessCategory] = Field(default_factory=list)


class EvidencePack(BaseModel):
    incident_id: str
    workflow_id: str
    workflow_name: str
    business_object_id: str
    title: str
    generated_at: datetime
    audience: list[str] = Field(default_factory=list)
    executive_summary: str
    review_case_id: str | None = None
    risk_category: str | None = None
    business_consequence: str | None = None
    final_outcome: str
    review_readiness_spec_version: str | None = None
    evidence_status: str = "verified"
    evidence_score: int = 100
    evidence_issues: list[str] = Field(default_factory=list)
    source_trace_refs: list[str] = Field(default_factory=list)
    decision_code: str | None = None
    decision_rationale: str | None = None
    approved_exception_type: str | None = None
    approver_role: str | None = None
    remediation_owner: str | None = None
    remediation_due_by: datetime | None = None
    closure_status: str | None = None
    findings: list[ReplayHighlight] = Field(default_factory=list)
    chronology: list[ReplayEntry] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
