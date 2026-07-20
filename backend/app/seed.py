"""Seed the database with Ekosight people, projects and a few demo records so
the dashboard is meaningful on first run. Idempotent: only runs when empty.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from . import models


PEOPLE = [
    ("Dhiraj", "dhiraj@ekosight.com", "CEO", "Leadership", None, "ceo"),
    ("Saumya", "saumya@ekosight.com", "Operations", "Operations", "Dhiraj", "manager"),
    ("Priya", "priya@ekosight.com", "Content Lead", "Marketing", "Dhiraj", "member"),
    ("Kajal", "kajal@ekosight.com", "Field & Media", "Operations", "Saumya", "member"),
    ("Dayal", "dayal@ekosight.com", "Partnerships", "Business", "Dhiraj", "member"),
]

PROJECTS = [
    ("Soil Didi content", "Publish Soil Didi awareness content", "Priya", "high"),
    ("Soil Doctor Clinic deployment", "Deploy Soil Doctor clinics", "Saumya", "high"),
    ("GeM registration", "Complete GeM checklist and registration", "Saumya", "medium"),
]


def seed_if_empty(db: Session) -> None:
    if db.query(models.Person).count() > 0:
        return

    people = {}
    # first pass without managers
    for name, email, desig, dept, _mgr, perm in PEOPLE:
        p = models.Person(name=name, email=email, designation=desig,
                          department=dept, permission_level=perm)
        db.add(p)
        people[name] = p
    db.commit()
    # link managers
    for name, _e, _d, _dept, mgr, _p in PEOPLE:
        if mgr:
            people[name].manager_id = people[mgr].person_id
    db.commit()

    projects = {}
    today = date.today()
    for pname, obj, owner, prio in PROJECTS:
        pr = models.Project(project_name=pname, objective=obj,
                            owner_id=people[owner].person_id,
                            start_date=today - timedelta(days=20),
                            deadline=today + timedelta(days=20),
                            priority=prio, progress=35, health="amber")
        db.add(pr)
        projects[pname] = pr
    db.commit()

    # A couple of demo tasks so the dashboard shows realistic counts.
    demo_tasks = [
        ("Collect Soil Didi photographs", "Kajal", "Soil Didi content",
         today + timedelta(days=1), "high", False, None),
        ("Prepare three Soil Didi posts", "Priya", "Soil Didi content",
         today + timedelta(days=3), "high", True, None),
        ("Complete GeM checklist", "Saumya", "GeM registration",
         today - timedelta(days=2), "high", False, "Waiting on DSC"),
    ]
    for title, who, proj, dl, prio, appr, blocker in demo_tasks:
        t = models.Task(
            title=title, assigned_to=people[who].person_id,
            assigned_by=people["Dhiraj"].person_id,
            project_id=projects[proj].project_id, deadline=dl, priority=prio,
            status="in_progress", approval_required=appr,
            blocked=bool(blocker), blocker_reason=blocker, progress=40)
        db.add(t)

    db.add(models.Commitment(
        person_id=people["Dhiraj"].person_id,
        commitment_text="Send revised proposal to Dayal Group",
        made_to="Dayal Group", source="meeting",
        deadline=today + timedelta(days=2)))
    db.add(models.Memory(
        memory_type="preference", subject="Dhiraj",
        content="Wants to review all content before publishing.",
        source="onboarding", confidence=1.0))
    db.commit()
