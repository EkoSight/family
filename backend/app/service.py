"""Orchestration: message -> interpretation -> gated tool execution.

This ties the pieces together following the spec's flow:
  user instruction -> agent interprets -> proposed actions -> permission engine
  checks risk -> approval requested where necessary -> tool executes -> action
  recorded in audit log.
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from . import agent, models, permissions, tools


def _people_names(db: Session) -> list[str]:
    return [p.name for p in db.query(models.Person)
            .filter(models.Person.active.is_(True)).all()]


def _record_action(db: Session, tool: str, args: dict, summary: str,
                   requested_by: str) -> models.AgentAction:
    risk, approval = permissions.classify(tool)
    action = models.AgentAction(
        requested_action=summary,
        tool=tool,
        payload=json.dumps(args, default=str),
        requested_by=requested_by,
        risk_level=risk,
        approval_required=approval,
        execution_status="pending",
    )
    db.add(action)
    db.commit()
    return action


def process_message(db: Session, message: str, source: str = "chat",
                    speaker: str | None = None) -> dict:
    speaker = speaker or "Dhiraj"

    # 1. persist the raw conversation turn
    conv = models.Conversation(speaker=speaker, message=message, source=source)
    db.add(conv)
    db.commit()

    # 2. interpret into proposed tool calls
    interp = agent.interpret(message, _people_names(db))
    conv.classified_intent = ",".join(a["tool"] for a in interp.actions)
    db.commit()

    executed, awaiting = [], []
    for proposal in interp.actions:
        action = _record_action(db, proposal["tool"], proposal["args"],
                                 proposal["summary"], speaker)
        risk = action.risk_level
        if risk == "low":
            # auto-approved, internal, reversible -> execute now
            result = tools.execute(db, action)
            executed.append({
                "action_id": action.action_id, "tool": action.tool,
                "summary": action.requested_action, "result": result})
        elif risk == "never":
            action.execution_status = "blocked"
            db.commit()
            awaiting.append({
                "action_id": action.action_id, "tool": action.tool,
                "summary": action.requested_action,
                "risk": "never — human action required"})
        else:  # medium -> awaiting CEO approval
            action.execution_status = "awaiting_approval"
            db.commit()
            awaiting.append({
                "action_id": action.action_id, "tool": action.tool,
                "summary": action.requested_action, "risk": "needs your approval"})

    return {
        "conversation_id": conv.conversation_id,
        "message": message,
        "interpretation": [
            {"tool": a["tool"], "summary": a["summary"], "args": a["args"]}
            for a in interp.actions
        ],
        "executed": executed,
        "awaiting_approval": awaiting,
        "notes": interp.notes,
    }


def approve_action(db: Session, action_id: str, approver: str = "Dhiraj") -> dict:
    action = db.get(models.AgentAction, action_id)
    if not action:
        return {"error": "action not found"}
    if action.risk_level == "never":
        return {"error": "this action can never run autonomously"}
    if action.execution_status not in ("awaiting_approval", "pending"):
        return {"error": f"action is {action.execution_status}"}
    action.approved_by = approver
    action.execution_status = "approved"
    db.commit()
    result = tools.execute(db, action)
    return {"action_id": action_id, "status": action.execution_status,
            "result": result}


def reject_action(db: Session, action_id: str) -> dict:
    action = db.get(models.AgentAction, action_id)
    if not action:
        return {"error": "action not found"}
    action.execution_status = "rejected"
    db.commit()
    return {"action_id": action_id, "status": "rejected"}
