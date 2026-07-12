"""The 10 core tables of the Ekosight CEO Agent.

"The database is more important than the chatbot." These structured records are
the agent's real memory; the chat/voice layer only reads from and writes to
them through controlled tools.
"""
from __future__ import annotations

import uuid
from datetime import datetime, date

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _id() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> datetime:
    return datetime.utcnow()


# 1. People ------------------------------------------------------------------
class Person(Base):
    __tablename__ = "people"

    person_id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String)
    designation: Mapped[str | None] = mapped_column(String)
    department: Mapped[str | None] = mapped_column(String)
    manager_id: Mapped[str | None] = mapped_column(ForeignKey("people.person_id"))
    responsibilities: Mapped[str | None] = mapped_column(Text)
    current_capacity: Mapped[str | None] = mapped_column(String)  # e.g. "light/normal/overloaded"
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    permission_level: Mapped[str] = mapped_column(String, default="member")  # ceo/manager/member


# 2. Projects ----------------------------------------------------------------
class Project(Base):
    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    project_name: Mapped[str] = mapped_column(String, nullable=False)
    objective: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("people.person_id"))
    start_date: Mapped[date | None] = mapped_column(Date)
    deadline: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String, default="active")  # active/paused/done
    health: Mapped[str] = mapped_column(String, default="green")  # green/amber/red
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    priority: Mapped[str] = mapped_column(String, default="medium")
    drive_folder_url: Mapped[str | None] = mapped_column(String)
    summary: Mapped[str | None] = mapped_column(Text)


# 3. Tasks -------------------------------------------------------------------
class Task(Base):
    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.project_id"))
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    assigned_to: Mapped[str | None] = mapped_column(ForeignKey("people.person_id"))
    assigned_by: Mapped[str | None] = mapped_column(ForeignKey("people.person_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    start_date: Mapped[date | None] = mapped_column(Date)
    deadline: Mapped[date | None] = mapped_column(Date)
    priority: Mapped[str] = mapped_column(String, default="medium")
    status: Mapped[str] = mapped_column(String, default="todo")  # todo/in_progress/done/cancelled
    progress: Mapped[int] = mapped_column(Integer, default=0)
    acceptance_status: Mapped[str] = mapped_column(String, default="pending")  # pending/accepted/rejected
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False)
    deliverable_url: Mapped[str | None] = mapped_column(String)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    blocker_reason: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)


# 4. Commitments -------------------------------------------------------------
class Commitment(Base):
    __tablename__ = "commitments"

    commitment_id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    person_id: Mapped[str | None] = mapped_column(ForeignKey("people.person_id"))
    commitment_text: Mapped[str] = mapped_column(Text, nullable=False)
    made_to: Mapped[str | None] = mapped_column(String)
    source: Mapped[str | None] = mapped_column(String)  # chat/voice/meeting/email
    source_date: Mapped[datetime] = mapped_column(DateTime, default=_now)
    deadline: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String, default="open")  # open/kept/broken
    related_project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.project_id"))


# 5. Decisions ---------------------------------------------------------------
class Decision(Base):
    __tablename__ = "decisions"

    decision_id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str | None] = mapped_column(Text)
    options_considered: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    decision_owner: Mapped[str | None] = mapped_column(String)
    decision_date: Mapped[datetime] = mapped_column(DateTime, default=_now)
    review_date: Mapped[date | None] = mapped_column(Date)
    related_project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.project_id"))


# 6. Conversations -----------------------------------------------------------
class Conversation(Base):
    __tablename__ = "conversations"

    conversation_id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    speaker: Mapped[str | None] = mapped_column(String)
    message: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_now)
    source: Mapped[str] = mapped_column(String, default="chat")  # chat/voice/email
    audio_url: Mapped[str | None] = mapped_column(String)
    transcript: Mapped[str | None] = mapped_column(Text)
    classified_intent: Mapped[str | None] = mapped_column(String)


# 7. Memories ----------------------------------------------------------------
MEMORY_TYPES = [
    "fact",
    "preference",
    "decision",
    "relationship",
    "process",
    "lesson",
    "commitment",
    "company_policy",
]


class Memory(Base):
    __tablename__ = "memories"

    memory_id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    memory_type: Mapped[str] = mapped_column(String, default="fact")
    subject: Mapped[str | None] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String)
    confidence: Mapped[float] = mapped_column(Float, default=0.8)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    access_level: Mapped[str] = mapped_column(String, default="ceo")


# 8. Process observations ----------------------------------------------------
class ProcessObservation(Base):
    __tablename__ = "process_observations"

    observation_id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    process_candidate: Mapped[str] = mapped_column(String)
    event_sequence: Mapped[str | None] = mapped_column(Text)  # arrow-joined steps
    people_involved: Mapped[str | None] = mapped_column(Text)
    project: Mapped[str | None] = mapped_column(String)
    frequency: Mapped[int] = mapped_column(Integer, default=1)
    average_duration: Mapped[str | None] = mapped_column(String)
    exceptions: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# 9. Process definitions -----------------------------------------------------
class ProcessDefinition(Base):
    __tablename__ = "process_definitions"

    process_id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    process_name: Mapped[str] = mapped_column(String)
    trigger: Mapped[str | None] = mapped_column(Text)
    steps: Mapped[str | None] = mapped_column(Text)
    owners: Mapped[str | None] = mapped_column(Text)
    deadlines: Mapped[str | None] = mapped_column(Text)
    approval_points: Mapped[str | None] = mapped_column(Text)
    exceptions: Mapped[str | None] = mapped_column(Text)
    automation_level: Mapped[str] = mapped_column(String, default="manual")  # manual/assisted/auto
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String, default="proposed")  # proposed/approved/retired


# 10. Agent actions (audit trail) -------------------------------------------
class AgentAction(Base):
    __tablename__ = "agent_actions"

    action_id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    requested_action: Mapped[str] = mapped_column(Text)
    tool: Mapped[str | None] = mapped_column(String)
    payload: Mapped[str | None] = mapped_column(Text)  # JSON of the tool args
    requested_by: Mapped[str | None] = mapped_column(String)
    risk_level: Mapped[str] = mapped_column(String, default="low")  # low/medium/never
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[str | None] = mapped_column(String)
    execution_status: Mapped[str] = mapped_column(String, default="pending")
    # pending / awaiting_approval / approved / executed / rejected / blocked
    execution_result: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime)


# Event log (Phase 4 foundation) --------------------------------------------
class Event(Base):
    """Append-only event log that the process-learning module analyses."""

    __tablename__ = "events"

    event_id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    event_type: Mapped[str] = mapped_column(String)  # e.g. lead_received, task_created
    entity_type: Mapped[str | None] = mapped_column(String)
    entity_id: Mapped[str | None] = mapped_column(String)
    actor: Mapped[str | None] = mapped_column(String)
    project: Mapped[str | None] = mapped_column(String)
    detail: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_now)
