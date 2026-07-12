"""The agent: interprets a message into a set of proposed tool calls.

Design: one agent, one database, ~13 controlled tools. The agent's job is
*interpretation* only — it proposes named tool calls with arguments. It never
executes them; the permission engine and the chat router do that.

Two backends:
  * "none"  -> a deterministic rule-based parser (default). No API keys, fully
               offline, good enough for the core delegation/commitment/decision
               commands and for demos.
  * gemini/claude -> the same task framed as a structured-output prompt. If the
               provider or key is missing it transparently falls back to rules.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from . import config

WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def _next_weekday(name: str) -> str:
    today = date.today()
    target = WEEKDAYS[name]
    delta = (target - today.weekday()) % 7
    delta = delta or 7  # always the upcoming one
    return str(today + timedelta(days=delta))


def _extract_deadline(text: str) -> str | None:
    t = text.lower()
    for name in WEEKDAYS:
        if re.search(rf"\b(by |before |on )?{name}\b", t):
            return _next_weekday(name)
    if "tomorrow" in t:
        return str(date.today() + timedelta(days=1))
    if "today" in t or "eod" in t:
        return str(date.today())
    if "next week" in t:
        return str(date.today() + timedelta(days=7))
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", t)
    if m:
        return m.group(1)
    return None


# Verbs that indicate a delegation / task instruction.
_TASK_VERBS = r"(create|prepare|collect|make|write|draft|review|complete|" \
              r"finish|send|call|schedule|organi[sz]e|build|design|check|" \
              r"do|handle|follow ?up|compile|update)"


def _split_clauses(text: str) -> list[str]:
    # Split on sentence boundaries and connective conjunctions.
    parts = re.split(r"[.\n]+|;|\bthen\b|\balso\b", text)
    return [p.strip() for p in parts if p.strip()]


class Interpretation:
    def __init__(self):
        self.actions: list[dict] = []
        self.notes: list[str] = []

    def add(self, tool: str, args: dict, summary: str):
        self.actions.append({"tool": tool, "args": args, "summary": summary})


def _rule_interpret(message: str, people_names: list[str]) -> Interpretation:
    result = Interpretation()
    text = message.strip()
    low = text.lower()

    # --- pure questions (no side effects) ---------------------------------
    is_question = (
        low.endswith("?")
        or re.match(r"^\s*(what|who|why|which|when|how|show|list|prepare me|"
                    r"brief me|give me|do i|are there)\b", low) is not None
    )
    if is_question:
        question_map = {
            r"attention|attend|needs? my": "needs_attention",
            r"waiting|response from me|need(s|ing)? (a )?(response|reply)": "waiting_on_me",
            r"promise|committed|commitment": "commitments",
            r"prepare me|meeting with|briefing|brief me|ready for": "meeting_prep",
            r"not moved|stalled|no progress|delayed|why is|why are|behind": "project_health",
            r"process": "processes",
            r"good morning|morning brief": "morning_brief",
            r"evening|end of day|closure|wrap up": "evening_brief",
        }
        for pat, kind in question_map.items():
            if re.search(pat, low):
                result.notes.append(f"query:{kind}")
                result.add("generate_summary", {"text": "", "kind": kind},
                           f"Answer question ({kind.replace('_', ' ')})")
                return result
        result.notes.append("query:general")
        result.add("generate_summary", {"text": "", "kind": "general"},
                   "Answer question")
        return result

    # --- send an external email (approval-gated) --------------------------
    if re.search(r"\b(send|reply to|respond to|email)\b.*\b(email|client|"
                 r"customer|partner|mail|them|him|her)\b", low) and \
       "draft" not in low and "internal" not in low:
        result.add("send_approved_email",
                   {"body": text, "to": None},
                   "Send external email (needs your approval)")
        return result

    # --- commitments the CEO/others made ("I promised X to Y") ------------
    if re.search(r"\bi (promised|committed|told|assured)\b", low) or \
       re.search(r"\bpromised .* to\b", low):
        made_to = None
        m = re.search(r"to ([A-Z][\w &]+?)(?:\s+(?:by|before|on|for|,|\.)|$)",
                      text)
        if m:
            made_to = m.group(1).strip()
        result.add("record_commitment",
                   {"commitment_text": text, "made_to": made_to,
                    "person": config.CEO_NAME, "deadline": _extract_deadline(text)},
                   f"Record commitment{' to ' + made_to if made_to else ''}")
        return result

    # --- decisions ("I decided / we will go with") -----------------------
    if re.search(r"\b(i|we) (decided|will go with|have chosen|are going to|" \
                 r"finali[sz]ed)\b", low) and "task" not in low:
        result.add("record_decision",
                   {"decision": text, "decision_owner": config.CEO_NAME},
                   "Record decision")
        return result

    # --- task delegation, possibly multiple clauses ----------------------
    # A message-level approval gate applies to publish/content tasks.
    msg_gate = bool(re.search(r"(review|approve).*(before|prior).*(publish|"
                              r"send|share)|before publishing|i (need|want) to "
                              r"(review|approve|see)", low))
    for clause in _split_clauses(text):
        clow = clause.lower()
        assignee = None
        for name in people_names:
            if re.search(rf"\b{re.escape(name.lower())}\b", clow):
                assignee = name
                break
        # detect an action verb to treat this clause as a task
        has_verb = re.search(rf"\b(ask|tell|get) \w+ to\b", clow) or \
            re.search(rf"\b{_TASK_VERBS}\b", clow)
        # Apply the message-level gate to content/publish tasks, or a
        # clause-local review instruction.
        is_publishable = bool(re.search(r"post|content|publish|linkedin|deck|"
                                        r"proposal|email|social", clow))
        approval = bool(re.search(r"review .*(before|prior).*publish|need to "
                                  r"(review|approve)|before publishing", clow)) \
            or (msg_gate and is_publishable)
        if has_verb and (assignee or re.search(r"\b(task|reminder)\b", clow)):
            title = re.sub(r"^\s*(ask|tell|get|please|and)\s+", "", clause,
                           flags=re.I).strip()
            result.add("create_task",
                       {"title": title, "description": clause,
                        "assigned_to": assignee,
                        "assigned_by": config.CEO_NAME,
                        "deadline": _extract_deadline(clause),
                        "approval_required": approval},
                       f"Create task"
                       + (f" for {assignee}" if assignee else "")
                       + (" (needs your approval before publishing)"
                          if approval else ""))

    if not result.actions:
        # Fall back to capturing it as a reminder/personal task so nothing is lost.
        result.add("create_reminder",
                   {"title": text, "assigned_by": config.CEO_NAME,
                    "deadline": _extract_deadline(text)},
                   "Capture as a personal reminder")
        result.notes.append("low_confidence")
    return result


def interpret(message: str, people_names: list[str]) -> Interpretation:
    """Public entry point. Tries the configured LLM, falls back to rules."""
    if config.LLM_PROVIDER in ("gemini", "claude"):
        try:
            return _llm_interpret(message, people_names)
        except Exception:  # noqa: BLE001 — any failure -> deterministic fallback
            pass
    return _rule_interpret(message, people_names)


# --- optional LLM backend ---------------------------------------------------
_SYSTEM = """You are the Ekosight CEO Agent's interpreter. Convert the CEO's
message into a JSON list of proposed tool calls. Available tools: create_task,
update_task, assign_task, record_decision, record_commitment, create_reminder,
generate_summary, draft_email, send_internal_chat_message, read_calendar,
search_drive, create_process_proposal. Each item: {"tool","args","summary"}.
Never invent people. Set approval_required=true when the CEO says they must
review before an external/publish action. Return ONLY JSON."""


def _llm_interpret(message: str, people_names: list[str]) -> Interpretation:
    import json

    prompt = (f"Known people: {', '.join(people_names)}\n"
              f"CEO message: {message}\n\nReturn the JSON array.")
    raw = None
    if config.LLM_PROVIDER == "claude" and config.ANTHROPIC_API_KEY:
        import anthropic  # type: ignore

        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model="claude-sonnet-5", max_tokens=1024, system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text
    elif config.LLM_PROVIDER == "gemini" and config.GEMINI_API_KEY:
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-pro", system_instruction=_SYSTEM)
        raw = model.generate_content(prompt).text
    if not raw:
        raise RuntimeError("no LLM response")

    raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.M).strip()
    items = json.loads(raw)
    result = Interpretation()
    for it in items:
        result.add(it["tool"], it.get("args", {}),
                   it.get("summary", it["tool"]))
    return result
