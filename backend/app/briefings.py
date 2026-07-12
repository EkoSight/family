"""Morning briefing, evening closure, and dashboard counters."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from . import models, config


def _open_tasks(db: Session):
    return db.query(models.Task).filter(
        models.Task.status.notin_(["done", "cancelled"]))


def dashboard_counts(db: Session) -> dict:
    today = date.today()
    open_q = _open_tasks(db)
    overdue = open_q.filter(models.Task.deadline.isnot(None),
                            models.Task.deadline < today).count()
    blocked = open_q.filter(models.Task.blocked.is_(True)).count()
    needs_approval = db.query(models.AgentAction).filter(
        models.AgentAction.execution_status == "awaiting_approval").count()
    # tasks the CEO needs to review/approve
    needs_approval += _open_tasks(db).filter(
        models.Task.approval_required.is_(True),
        models.Task.status == "in_progress").count()
    waiting_for_others = open_q.filter(
        models.Task.assigned_to.isnot(None)).count()
    needs_attention = overdue + blocked + needs_approval
    upcoming_meetings = 0  # wired to Calendar MCP in prod
    processes_detected = db.query(models.ProcessObservation).count()
    return {
        "needs_attention": needs_attention,
        "needs_approval": needs_approval,
        "overdue": overdue,
        "blocked": blocked,
        "waiting_for_others": waiting_for_others,
        "upcoming_meetings": upcoming_meetings,
        "processes_detected": processes_detected,
    }


def _task_view(db: Session, t: models.Task) -> dict:
    person = db.get(models.Person, t.assigned_to) if t.assigned_to else None
    proj = db.get(models.Project, t.project_id) if t.project_id else None
    return {
        "task_id": t.task_id, "title": t.title, "status": t.status,
        "priority": t.priority, "progress": t.progress,
        "deadline": str(t.deadline) if t.deadline else None,
        "assigned_to": person.name if person else None,
        "project": proj.project_name if proj else None,
        "blocked": t.blocked, "blocker_reason": t.blocker_reason,
        "approval_required": t.approval_required,
    }


def morning_brief(db: Session) -> dict:
    today = date.today()
    counts = dashboard_counts(db)
    priorities = [
        _task_view(db, t) for t in _open_tasks(db)
        .filter(or_(models.Task.priority == "high",
                    models.Task.deadline <= today))
        .order_by(models.Task.deadline.asc().nullslast()).limit(7).all()
    ]
    commitments = [
        {"commitment_id": c.commitment_id, "text": c.commitment_text,
         "made_to": c.made_to,
         "deadline": str(c.deadline) if c.deadline else None}
        for c in db.query(models.Commitment)
        .filter(models.Commitment.status == "open")
        .order_by(models.Commitment.deadline.asc().nullslast()).limit(10).all()
    ]
    waiting = [_task_view(db, t) for t in _open_tasks(db)
               .filter(models.Task.assigned_to.isnot(None)).limit(10).all()]
    projects = [
        {"project_id": p.project_id, "name": p.project_name,
         "health": p.health, "progress": p.progress, "status": p.status}
        for p in db.query(models.Project)
        .filter(models.Project.status == "active").all()
    ]
    return {
        "greeting": f"Good morning, {config.CEO_NAME}",
        "date": str(today),
        "counts": counts,
        "todays_priorities": priorities,
        "people_waiting_for_you": [],
        "your_commitments": commitments,
        "major_project_health": projects,
        "waiting_for_others": waiting,
        "recommendations": _recommendations(db),
    }


def evening_brief(db: Session) -> dict:
    today = date.today()
    completed = [
        _task_view(db, t) for t in db.query(models.Task).filter(
            models.Task.completed_at.isnot(None),
            models.Task.completed_at >= datetime(today.year, today.month, today.day)
        ).all()
    ]
    still_open = [_task_view(db, t) for t in _open_tasks(db)
                  .filter(models.Task.deadline <= today).all()]
    return {
        "greeting": f"Evening closure, {config.CEO_NAME}",
        "date": str(today),
        "completed_today": completed,
        "still_open": still_open,
        "counts": dashboard_counts(db),
        "recommendations": _recommendations(db),
    }


def _recommendations(db: Session) -> list[str]:
    recs = []
    overdue = _open_tasks(db).filter(
        models.Task.deadline.isnot(None),
        models.Task.deadline < date.today()).count()
    if overdue:
        recs.append(f"{overdue} task(s) are overdue — consider reminders or "
                    f"deadline changes.")
    blocked = _open_tasks(db).filter(models.Task.blocked.is_(True)).count()
    if blocked:
        recs.append(f"{blocked} task(s) are blocked — clear the blockers to "
                    f"unblock your team.")
    pending = db.query(models.AgentAction).filter(
        models.AgentAction.execution_status == "awaiting_approval").count()
    if pending:
        recs.append(f"{pending} action(s) are awaiting your approval.")
    if not recs:
        recs.append("Everything is on track. No urgent recommendations.")
    return recs
