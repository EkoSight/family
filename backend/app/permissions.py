"""Permission / approval engine.

The AI never touches Gmail, Calendar or company records directly. It only asks
to run a named tool. This engine classifies each requested tool call into one
of three risk levels and decides whether it may auto-execute, needs the CEO's
approval, or must never run autonomously.
"""
from __future__ import annotations

# Tools whose effect is internal and reversible -> run immediately.
AUTO_ALLOWED = {
    "create_task",
    "update_task",
    "assign_task",
    "record_decision",
    "record_commitment",
    "create_reminder",
    "generate_summary",
    "draft_email",  # a draft is internal; SENDING requires approval
    "send_internal_chat_message",  # routine reminders to assigned employees
    "read_calendar",
    "search_drive",
    "create_process_proposal",
    "update_dashboard",
    "log_event",
}

# Tools that have external / committed / confidential impact -> ask the CEO.
REQUIRE_APPROVAL = {
    "send_approved_email",  # external email
    "change_committed_deadline",  # deadline promised to a customer
    "share_confidential_drive",  # share confidential document
    "change_pricing",
    "confirm_order",
    "reassign_major_responsibility",
    "publish_content",
    "create_calendar_event",  # external calendar invitation
}

# Tools that must NEVER run autonomously (still require an explicit human path).
NEVER_AUTONOMOUS = {
    "make_payment",
    "sign_legal",
    "hire_or_terminate",
    "investor_commitment",
    "accept_contract",
    "delete_critical_record",
    "change_banking_details",
}


def classify(tool: str) -> tuple[str, bool]:
    """Return (risk_level, approval_required) for a tool name.

    risk_level: "low" | "medium" | "never"
    """
    if tool in NEVER_AUTONOMOUS:
        return "never", True
    if tool in REQUIRE_APPROVAL:
        return "medium", True
    if tool in AUTO_ALLOWED:
        return "low", False
    # Unknown tools are treated conservatively.
    return "medium", True


def describe(tool: str) -> str:
    risk, _ = classify(tool)
    return {
        "low": "auto-approved (internal, reversible)",
        "medium": "requires your approval",
        "never": "never autonomous — human action required",
    }[risk]
