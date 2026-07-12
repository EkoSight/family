"""All HTTP endpoints for the CEO Agent MVP.

Kept in one router for the MVP; split per-domain as it grows.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import briefings, models, permissions, service
from ..database import get_db

router = APIRouter(prefix="/api")


# --- Chat / voice ----------------------------------------------------------
class MessageIn(BaseModel):
    message: str
    source: str = "chat"
    speaker: Optional[str] = None


@router.post("/chat")
def chat(body: MessageIn, db: Session = Depends(get_db)):
    if not body.message.strip():
        raise HTTPException(400, "empty message")
    return service.process_message(db, body.message, body.source, body.speaker)


class VoiceIn(BaseModel):
    transcript: str
    audio_url: Optional[str] = None
    speaker: Optional[str] = None


@router.post("/voice")
def voice(body: VoiceIn, db: Session = Depends(get_db)):
    """Voice notes arrive already transcribed (Hindi/Hinglish/English) and are
    reviewed before major actions — same pipeline as chat."""
    if not body.transcript.strip():
        raise HTTPException(400, "empty transcript")
    return service.process_message(db, body.transcript, "voice", body.speaker)


# --- Approvals -------------------------------------------------------------
@router.post("/actions/{action_id}/approve")
def approve(action_id: str, db: Session = Depends(get_db)):
    res = service.approve_action(db, action_id)
    if "error" in res:
        raise HTTPException(400, res["error"])
    return res


@router.post("/actions/{action_id}/reject")
def reject(action_id: str, db: Session = Depends(get_db)):
    res = service.reject_action(db, action_id)
    if "error" in res:
        raise HTTPException(404, res["error"])
    return res


@router.get("/actions")
def list_actions(status: Optional[str] = None, limit: int = 50,
                 db: Session = Depends(get_db)):
    q = db.query(models.AgentAction).order_by(
        models.AgentAction.created_at.desc())
    if status:
        q = q.filter(models.AgentAction.execution_status == status)
    out = []
    for a in q.limit(limit).all():
        out.append({
            "action_id": a.action_id, "requested_action": a.requested_action,
            "tool": a.tool, "payload": a.payload, "requested_by": a.requested_by,
            "risk_level": a.risk_level, "approval_required": a.approval_required,
            "approved_by": a.approved_by, "execution_status": a.execution_status,
            "execution_result": a.execution_result,
            "created_at": str(a.created_at),
            "executed_at": str(a.executed_at) if a.executed_at else None,
            "risk_note": permissions.describe(a.tool),
        })
    return out


# --- Dashboard / briefings -------------------------------------------------
@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    return briefings.morning_brief(db)


@router.get("/briefing/morning")
def morning(db: Session = Depends(get_db)):
    return briefings.morning_brief(db)


@router.get("/briefing/evening")
def evening(db: Session = Depends(get_db)):
    return briefings.evening_brief(db)


@router.get("/counts")
def counts(db: Session = Depends(get_db)):
    return briefings.dashboard_counts(db)


# --- People ----------------------------------------------------------------
@router.get("/people")
def people(db: Session = Depends(get_db)):
    return [
        {"person_id": p.person_id, "name": p.name, "email": p.email,
         "designation": p.designation, "department": p.department,
         "permission_level": p.permission_level, "active": p.active}
        for p in db.query(models.Person).all()
    ]


# --- Projects --------------------------------------------------------------
@router.get("/projects")
def projects(db: Session = Depends(get_db)):
    out = []
    for p in db.query(models.Project).all():
        owner = db.get(models.Person, p.owner_id) if p.owner_id else None
        out.append({
            "project_id": p.project_id, "project_name": p.project_name,
            "objective": p.objective, "owner": owner.name if owner else None,
            "status": p.status, "health": p.health, "progress": p.progress,
            "priority": p.priority,
            "deadline": str(p.deadline) if p.deadline else None})
    return out


# --- Tasks -----------------------------------------------------------------
@router.get("/tasks")
def tasks(status: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(models.Task).order_by(models.Task.created_at.desc())
    if status:
        q = q.filter(models.Task.status == status)
    return [briefings._task_view(db, t) for t in q.all()]


class TaskUpdateIn(BaseModel):
    status: Optional[str] = None
    progress: Optional[int] = None
    blocked: Optional[bool] = None
    blocker_reason: Optional[str] = None
    deliverable_url: Optional[str] = None


@router.patch("/tasks/{task_id}")
def update_task(task_id: str, body: TaskUpdateIn, db: Session = Depends(get_db)):
    from .. import tools
    args = {k: v for k, v in body.model_dump().items() if v is not None}
    args["task_id"] = task_id
    res = tools.update_task(db, args)
    if "error" in res:
        raise HTTPException(404, res["error"])
    return res


# --- Memory ----------------------------------------------------------------
@router.get("/memory")
def memory(memory_type: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(models.Memory).order_by(models.Memory.created_at.desc())
    if memory_type:
        q = q.filter(models.Memory.memory_type == memory_type)
    return [
        {"memory_id": m.memory_id, "memory_type": m.memory_type,
         "subject": m.subject, "content": m.content, "source": m.source,
         "confidence": m.confidence, "created_at": str(m.created_at)}
        for m in q.all()
    ]


class MemoryIn(BaseModel):
    memory_type: str = "fact"
    subject: Optional[str] = None
    content: str
    source: str = "manual"


@router.post("/memory")
def add_memory(body: MemoryIn, db: Session = Depends(get_db)):
    m = models.Memory(**body.model_dump())
    db.add(m)
    db.commit()
    return {"memory_id": m.memory_id}


@router.delete("/memory/{memory_id}")
def delete_memory(memory_id: str, db: Session = Depends(get_db)):
    m = db.get(models.Memory, memory_id)
    if not m:
        raise HTTPException(404, "not found")
    db.delete(m)
    db.commit()
    return {"deleted": memory_id}


@router.get("/commitments")
def commitments(db: Session = Depends(get_db)):
    out = []
    for c in db.query(models.Commitment).order_by(
            models.Commitment.source_date.desc()).all():
        person = db.get(models.Person, c.person_id) if c.person_id else None
        out.append({
            "commitment_id": c.commitment_id, "text": c.commitment_text,
            "by": person.name if person else None, "made_to": c.made_to,
            "status": c.status, "source": c.source,
            "deadline": str(c.deadline) if c.deadline else None})
    return out


@router.get("/decisions")
def decisions(db: Session = Depends(get_db)):
    return [
        {"decision_id": d.decision_id, "decision": d.decision,
         "context": d.context, "reason": d.reason, "owner": d.decision_owner,
         "decision_date": str(d.decision_date)}
        for d in db.query(models.Decision).order_by(
            models.Decision.decision_date.desc()).all()
    ]


# --- Processes -------------------------------------------------------------
@router.get("/processes")
def processes(db: Session = Depends(get_db)):
    from .. import process_learning
    observations = process_learning.detect(db)
    definitions = [
        {"process_id": p.process_id, "process_name": p.process_name,
         "trigger": p.trigger, "steps": p.steps, "status": p.status,
         "automation_level": p.automation_level}
        for p in db.query(models.ProcessDefinition).all()
    ]
    return {"candidates": observations, "definitions": definitions}


class ProcessApproveIn(BaseModel):
    process_name: str
    trigger: Optional[str] = None
    steps: Optional[str] = None


@router.post("/processes/approve")
def approve_process(body: ProcessApproveIn, db: Session = Depends(get_db)):
    from .. import tools
    res = tools.create_process_proposal(db, body.model_dump())
    pd = db.get(models.ProcessDefinition, res["process_id"])
    pd.status = "approved"
    db.commit()
    return {"process_id": pd.process_id, "status": "approved"}


# --- Conversations / event log --------------------------------------------
@router.get("/conversations")
def conversations(limit: int = 30, db: Session = Depends(get_db)):
    return [
        {"conversation_id": c.conversation_id, "speaker": c.speaker,
         "message": c.message, "source": c.source,
         "classified_intent": c.classified_intent,
         "timestamp": str(c.timestamp)}
        for c in db.query(models.Conversation).order_by(
            models.Conversation.timestamp.desc()).limit(limit).all()
    ]


@router.get("/events")
def events(limit: int = 100, db: Session = Depends(get_db)):
    return [
        {"event_id": e.event_id, "event_type": e.event_type,
         "entity_type": e.entity_type, "actor": e.actor,
         "project": e.project, "detail": e.detail,
         "timestamp": str(e.timestamp)}
        for e in db.query(models.Event).order_by(
            models.Event.timestamp.desc()).limit(limit).all()
    ]
