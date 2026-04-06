from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class WorkflowRecord(Base):
    __tablename__ = "workflows"

    workflow_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    workflow_name: Mapped[str] = mapped_column(String(255), nullable=False)
    business_object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    business_object_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="in_progress")
    current_step: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    incident_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_policy_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    final_outcome: Mapped[str | None] = mapped_column(String(64), nullable=True)


class EventRecord(Base):
    __tablename__ = "events"

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    workflow_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workflow_name: Mapped[str] = mapped_column(String(255), nullable=False)
    process_step: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    action_type: Mapped[str] = mapped_column(String(128), nullable=False)
    action_summary: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_system: Mapped[str | None] = mapped_column(String(255), nullable=True)
    business_object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    business_object_id: Mapped[str] = mapped_column(String(128), nullable=False)
    permission_scope: Mapped[str | None] = mapped_column(String(255), nullable=True)
    authority_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    authority_delegation_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    policy_status: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_rule_ids_json: Mapped[list] = mapped_column("policy_rule_ids", JSON, nullable=False, default=list)
    review_case_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    review_state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    human_decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_by: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_trace_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_system_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    evidence_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    outcome_status: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)


class IncidentRecord(Base):
    __tablename__ = "incidents"

    incident_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    trigger_event_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_next_action: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PolicyRuleRecord(Base):
    __tablename__ = "policy_rules"

    rule_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    decision_on_violation: Mapped[str] = mapped_column(String(64), nullable=False)
    config_json: Mapped[dict] = mapped_column("config", JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)


class ReplaySessionRecord(Base):
    __tablename__ = "replay_sessions"

    replay_session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    final_outcome: Mapped[str] = mapped_column(String(64), nullable=False)
    summary_json: Mapped[dict] = mapped_column("summary", JSON, nullable=False, default=dict)
