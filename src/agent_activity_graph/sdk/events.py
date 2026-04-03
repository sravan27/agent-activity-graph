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
    policy_status: PolicyStatus = PolicyStatus.ALLOWED
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
    tool_name: str | None = None
    target_system: str | None = None
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


class EvidencePack(BaseModel):
    incident_id: str
    workflow_id: str
    workflow_name: str
    business_object_id: str
    title: str
    generated_at: datetime
    audience: list[str] = Field(default_factory=list)
    executive_summary: str
    risk_category: str | None = None
    business_consequence: str | None = None
    final_outcome: str
    findings: list[ReplayHighlight] = Field(default_factory=list)
    chronology: list[ReplayEntry] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
