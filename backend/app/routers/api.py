"""All HTTP endpoints for the CEO Agent MVP.

Kept in one router for the MVP; split per-domain as it grows.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import briefings, models, permissions, service, tools
from ..database import get_db

router = APIRouter(prefix="/api")


def _resolve_person(db: Session, who: Optional[str]) -> Optional[models.Person]:
    if not who:
        return None
    p = db.get(models.Person, who)
    if p:
        return p
    return (db.query(models.Person)
            .filter(func.lower(models.Person.name) == who.lower().strip())
            .first())


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


# --- Auth (lightweight MVP: identify by email) -----------------------------
# NOTE: production should use Google Workspace login. This is a simple identify
# step so multiple people can use their own view without a password for the MVP.
class LoginIn(BaseModel):
    email: str


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    p = (db.query(models.Person)
         .filter(func.lower(models.Person.email) == body.email.lower().strip(),
                 models.Person.active.is_(True))
         .first())
    if not p:
        raise HTTPException(404, "No active user with that email. Ask the CEO "
                                 "to add you on the People screen.")
    return {"person_id": p.person_id, "name": p.name, "email": p.email,
            "designation": p.designation, "department": p.department,
            "permission_level": p.permission_level}


# --- People management -----------------------------------------------------
class PersonIn(BaseModel):
    name: str
    email: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    manager: Optional[str] = None  # name or id
    responsibilities: Optional[str] = None
    permission_level: str = "member"


@router.post("/people")
def create_person(body: PersonIn, db: Session = Depends(get_db)):
    mgr = _resolve_person(db, body.manager)
    p = models.Person(
        name=body.name, email=body.email, designation=body.designation,
        department=body.department, responsibilities=body.responsibilities,
        permission_level=body.permission_level,
        manager_id=mgr.person_id if mgr else None)
    db.add(p)
    db.commit()
    tools.log_event(db, "person_added", "person", p.person_id, detail=p.name)
    return {"person_id": p.person_id, "name": p.name}


@router.patch("/people/{person_id}")
def update_person(person_id: str, body: PersonIn, db: Session = Depends(get_db)):
    p = db.get(models.Person, person_id)
    if not p:
        raise HTTPException(404, "not found")
    for f in ("name", "email", "designation", "department",
              "responsibilities", "permission_level"):
        v = getattr(body, f)
        if v is not None:
            setattr(p, f, v)
    if body.manager is not None:
        mgr = _resolve_person(db, body.manager)
        p.manager_id = mgr.person_id if mgr else None
    db.commit()
    return {"person_id": p.person_id, "name": p.name}


@router.post("/people/{person_id}/deactivate")
def deactivate_person(person_id: str, db: Session = Depends(get_db)):
    p = db.get(models.Person, person_id)
    if not p:
        raise HTTPException(404, "not found")
    p.active = False
    db.commit()
    return {"person_id": p.person_id, "active": False}


@router.post("/people/{person_id}/activate")
def activate_person(person_id: str, db: Session = Depends(get_db)):
    p = db.get(models.Person, person_id)
    if not p:
        raise HTTPException(404, "not found")
    p.active = True
    db.commit()
    return {"person_id": p.person_id, "active": True}


# --- Task creation (form) + lifecycle (Phase 3) ----------------------------
class NewTaskIn(BaseModel):
    title: str
    description: Optional[str] = None
    assigned_to: Optional[str] = None  # name or id
    assigned_by: Optional[str] = None
    project: Optional[str] = None
    deadline: Optional[str] = None
    priority: str = "medium"
    approval_required: bool = False


@router.post("/tasks")
def create_task(body: NewTaskIn, db: Session = Depends(get_db)):
    return tools.create_task(db, body.model_dump())


def _get_task(db: Session, task_id: str) -> models.Task:
    t = db.get(models.Task, task_id)
    if not t:
        raise HTTPException(404, "task not found")
    return t


class ActorIn(BaseModel):
    actor: Optional[str] = None


@router.post("/tasks/{task_id}/accept")
def accept_task(task_id: str, body: ActorIn, db: Session = Depends(get_db)):
    t = _get_task(db, task_id)
    t.acceptance_status = "accepted"
    if t.status == "todo":
        t.status = "in_progress"
    db.commit()
    tools.log_event(db, "task_accepted", "task", t.task_id, actor=body.actor)
    return {"task_id": t.task_id, "acceptance_status": t.acceptance_status}


@router.post("/tasks/{task_id}/decline")
def decline_task(task_id: str, body: ActorIn, db: Session = Depends(get_db)):
    t = _get_task(db, task_id)
    t.acceptance_status = "rejected"
    db.commit()
    tools.log_event(db, "task_declined", "task", t.task_id, actor=body.actor)
    return {"task_id": t.task_id, "acceptance_status": t.acceptance_status}


class ProgressIn(BaseModel):
    progress: int
    actor: Optional[str] = None


@router.post("/tasks/{task_id}/progress")
def task_progress(task_id: str, body: ProgressIn, db: Session = Depends(get_db)):
    t = _get_task(db, task_id)
    t.progress = max(0, min(100, body.progress))
    if t.status in ("todo",):
        t.status = "in_progress"
    db.commit()
    tools.log_event(db, "task_progress", "task", t.task_id,
                    actor=body.actor, detail=str(t.progress))
    return {"task_id": t.task_id, "progress": t.progress}


class BlockerIn(BaseModel):
    reason: str
    actor: Optional[str] = None


@router.post("/tasks/{task_id}/blocker")
def report_blocker(task_id: str, body: BlockerIn, db: Session = Depends(get_db)):
    t = _get_task(db, task_id)
    t.blocked = True
    t.blocker_reason = body.reason
    db.commit()
    tools.log_event(db, "blocker_reported", "task", t.task_id,
                    actor=body.actor, detail=body.reason)
    return {"task_id": t.task_id, "blocked": True}


@router.post("/tasks/{task_id}/unblock")
def clear_blocker(task_id: str, db: Session = Depends(get_db)):
    t = _get_task(db, task_id)
    t.blocked = False
    t.blocker_reason = None
    db.commit()
    return {"task_id": t.task_id, "blocked": False}


class CompleteIn(BaseModel):
    deliverable_url: Optional[str] = None
    actor: Optional[str] = None


@router.post("/tasks/{task_id}/complete")
def complete_task(task_id: str, body: CompleteIn, db: Session = Depends(get_db)):
    """Employee submits completion. If approval is required it goes to the
    manager as 'submitted'; otherwise it is marked done."""
    t = _get_task(db, task_id)
    t.progress = 100
    t.deliverable_url = body.deliverable_url or t.deliverable_url
    t.completed_at = datetime.utcnow()
    if t.approval_required:
        t.status = "submitted"
    else:
        t.status = "done"
    db.commit()
    tools.log_event(db, "task_completed", "task", t.task_id, actor=body.actor)
    return {"task_id": t.task_id, "status": t.status}


@router.post("/tasks/{task_id}/approve")
def approve_task(task_id: str, body: ActorIn, db: Session = Depends(get_db)):
    t = _get_task(db, task_id)
    t.status = "done"
    t.approved_at = datetime.utcnow()
    db.commit()
    tools.log_event(db, "task_approved", "task", t.task_id, actor=body.actor)
    return {"task_id": t.task_id, "status": t.status}


# --- My work / team --------------------------------------------------------
@router.get("/my/tasks")
def my_tasks(person: str, db: Session = Depends(get_db)):
    p = _resolve_person(db, person)
    if not p:
        raise HTTPException(404, "person not found")
    q = (db.query(models.Task)
         .filter(models.Task.assigned_to == p.person_id)
         .order_by(models.Task.deadline.asc().nullslast()))
    return [briefings._task_view(db, t) for t in q.all()]


@router.get("/team/workload")
def team_workload(db: Session = Depends(get_db)):
    out = []
    for p in db.query(models.Person).filter(models.Person.active.is_(True)).all():
        open_tasks = (db.query(models.Task)
                      .filter(models.Task.assigned_to == p.person_id,
                              models.Task.status.notin_(["done", "cancelled"])))
        total = open_tasks.count()
        overdue = open_tasks.filter(
            models.Task.deadline < datetime.utcnow().date()).count()
        blocked = open_tasks.filter(models.Task.blocked.is_(True)).count()
        out.append({"person_id": p.person_id, "name": p.name,
                    "designation": p.designation, "open": total,
                    "overdue": overdue, "blocked": blocked,
                    "capacity": "overloaded" if total >= 5 else
                                "normal" if total >= 2 else "light"})
    return sorted(out, key=lambda x: -x["open"])


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
