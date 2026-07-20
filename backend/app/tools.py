"""Controlled tools.

Every side effect the agent can produce goes through one of these functions.
The agent chooses *which* tool and *what* arguments; the permission engine
decides whether it may run. Each attempt is written to the agent_actions audit
trail regardless of outcome.
"""
from __future__ import annotations

import json
from datetime import datetime, date

from sqlalchemy.orm import Session

from . import models, permissions


# --- helpers ---------------------------------------------------------------
def _parse_date(value):
    if not value:
        return None
    if isinstance(value, (date, datetime)):
        return value if isinstance(value, date) else value.date()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _find_person(db: Session, name_or_id: str | None):
    if not name_or_id:
        return None
    p = db.get(models.Person, name_or_id)
    if p:
        return p
    return (
        db.query(models.Person)
        .filter(models.Person.name.ilike(f"%{name_or_id}%"))
        .first()
    )


def log_event(db: Session, event_type: str, entity_type=None, entity_id=None,
              actor=None, project=None, detail=None):
    ev = models.Event(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        actor=actor,
        project=project,
        detail=detail,
    )
    db.add(ev)
    db.commit()
    return ev


# --- individual tools ------------------------------------------------------
# Each returns a (result_dict) and performs its DB writes. They assume the
# permission engine has already authorised execution.

def create_task(db: Session, args: dict) -> dict:
    person = _find_person(db, args.get("assigned_to"))
    assigner = _find_person(db, args.get("assigned_by"))
    project = None
    if args.get("project"):
        project = (
            db.query(models.Project)
            .filter(models.Project.project_name.ilike(f"%{args['project']}%"))
            .first()
        )
    task = models.Task(
        title=args.get("title") or args.get("description") or "Untitled task",
        description=args.get("description"),
        assigned_to=person.person_id if person else None,
        assigned_by=assigner.person_id if assigner else None,
        project_id=project.project_id if project else None,
        deadline=_parse_date(args.get("deadline")),
        start_date=_parse_date(args.get("start_date")),
        priority=args.get("priority", "medium"),
        approval_required=bool(args.get("approval_required", False)),
    )
    db.add(task)
    db.commit()
    log_event(db, "task_created", "task", task.task_id,
              actor=args.get("assigned_by"), project=args.get("project"),
              detail=task.title)
    return {"task_id": task.task_id, "title": task.title,
            "assigned_to": person.name if person else None,
            "deadline": str(task.deadline) if task.deadline else None}


def update_task(db: Session, args: dict) -> dict:
    task = db.get(models.Task, args.get("task_id"))
    if not task:
        return {"error": "task not found"}
    for field in ("title", "description", "status", "priority", "progress",
                  "deliverable_url", "blocker_reason"):
        if field in args and args[field] is not None:
            setattr(task, field, args[field])
    if "deadline" in args:
        task.deadline = _parse_date(args["deadline"])
    if args.get("blocked") is not None:
        task.blocked = bool(args["blocked"])
    if args.get("status") == "done":
        task.completed_at = datetime.utcnow()
        task.progress = 100
    db.commit()
    log_event(db, "task_updated", "task", task.task_id, detail=task.status)
    return {"task_id": task.task_id, "status": task.status}


def assign_task(db: Session, args: dict) -> dict:
    task = db.get(models.Task, args.get("task_id"))
    person = _find_person(db, args.get("assigned_to"))
    if not task or not person:
        return {"error": "task or person not found"}
    task.assigned_to = person.person_id
    db.commit()
    log_event(db, "task_assigned", "task", task.task_id, detail=person.name)
    return {"task_id": task.task_id, "assigned_to": person.name}


def record_decision(db: Session, args: dict) -> dict:
    d = models.Decision(
        decision=args.get("decision", ""),
        context=args.get("context"),
        options_considered=args.get("options_considered"),
        reason=args.get("reason"),
        decision_owner=args.get("decision_owner"),
        review_date=_parse_date(args.get("review_date")),
    )
    db.add(d)
    db.commit()
    log_event(db, "decision_recorded", "decision", d.decision_id, detail=d.decision)
    return {"decision_id": d.decision_id, "decision": d.decision}


def record_commitment(db: Session, args: dict) -> dict:
    person = _find_person(db, args.get("person"))
    c = models.Commitment(
        person_id=person.person_id if person else None,
        commitment_text=args.get("commitment_text", ""),
        made_to=args.get("made_to"),
        source=args.get("source", "chat"),
        deadline=_parse_date(args.get("deadline")),
    )
    db.add(c)
    db.commit()
    log_event(db, "commitment_recorded", "commitment", c.commitment_id,
              detail=c.commitment_text)
    return {"commitment_id": c.commitment_id, "commitment": c.commitment_text,
            "made_to": c.made_to}


def create_reminder(db: Session, args: dict) -> dict:
    # A personal reminder is modelled as a self-assigned task.
    return create_task(db, {**args, "title": args.get("title", "Reminder"),
                            "priority": args.get("priority", "low")})


def generate_summary(db: Session, args: dict) -> dict:
    return {"summary": args.get("text", ""), "note": "summary generated"}


def draft_email(db: Session, args: dict) -> dict:
    # Only creates an internal draft record; sending is a separate, gated tool.
    return {"draft": {"to": args.get("to"), "subject": args.get("subject"),
                      "body": args.get("body")}, "status": "drafted"}


def send_internal_chat_message(db: Session, args: dict) -> dict:
    log_event(db, "internal_message_sent", detail=args.get("message"))
    return {"to": args.get("to"), "message": args.get("message"), "status": "sent"}


def read_calendar(db: Session, args: dict) -> dict:
    return {"note": "read_calendar is wired to the Google Calendar MCP in prod",
            "range": args.get("range", "today")}


def search_drive(db: Session, args: dict) -> dict:
    return {"note": "search_drive is wired to the Google Drive MCP in prod",
            "query": args.get("query")}


def create_process_proposal(db: Session, args: dict) -> dict:
    pd = models.ProcessDefinition(
        process_name=args.get("process_name", "Untitled process"),
        trigger=args.get("trigger"),
        steps=args.get("steps"),
        owners=args.get("owners"),
        approval_points=args.get("approval_points"),
        status="proposed",
    )
    db.add(pd)
    db.commit()
    log_event(db, "process_proposed", "process", pd.process_id, detail=pd.process_name)
    return {"process_id": pd.process_id, "process_name": pd.process_name,
            "status": "proposed"}


def update_dashboard(db: Session, args: dict) -> dict:
    return {"status": "dashboard refreshed"}


# Gated / never-autonomous tools are registered so they can be *proposed* and
# audited, but their executors intentionally refuse to act on their own.
def _gated(name):
    def _fn(db: Session, args: dict) -> dict:
        return {"status": "queued", "tool": name,
                "note": "requires explicit human execution — not run by the agent"}
    return _fn


REGISTRY = {
    "create_task": create_task,
    "update_task": update_task,
    "assign_task": assign_task,
    "record_decision": record_decision,
    "record_commitment": record_commitment,
    "create_reminder": create_reminder,
    "generate_summary": generate_summary,
    "draft_email": draft_email,
    "send_internal_chat_message": send_internal_chat_message,
    "read_calendar": read_calendar,
    "search_drive": search_drive,
    "create_process_proposal": create_process_proposal,
    "update_dashboard": update_dashboard,
    # gated
    "send_approved_email": _gated("send_approved_email"),
    "change_committed_deadline": _gated("change_committed_deadline"),
    "share_confidential_drive": _gated("share_confidential_drive"),
    "change_pricing": _gated("change_pricing"),
    "confirm_order": _gated("confirm_order"),
    "reassign_major_responsibility": _gated("reassign_major_responsibility"),
    "publish_content": _gated("publish_content"),
    "create_calendar_event": _gated("create_calendar_event"),
}


def execute(db: Session, action: models.AgentAction) -> dict:
    """Run an approved/auto action and record the result on the audit row."""
    fn = REGISTRY.get(action.tool)
    args = json.loads(action.payload) if action.payload else {}
    if fn is None:
        action.execution_status = "rejected"
        action.execution_result = json.dumps({"error": f"unknown tool {action.tool}"})
        db.commit()
        return {"error": "unknown tool"}
    result = fn(db, args)
    action.execution_status = "executed"
    action.execution_result = json.dumps(result, default=str)
    action.executed_at = datetime.utcnow()
    db.commit()
    return result
