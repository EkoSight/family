# Ekosight CEO Agent — V1

A small, working **CEO assistant** that turns natural language (typed or voice)
into tracked **tasks, decisions, commitments, follow-ups and approvals** — with
a permission layer and full audit trail. Built to grow into the company
operating agent, one phase at a time, without starting from multi-agent
complexity or autonomous automation.

> First success criterion: *you can speak naturally for five minutes and the
> agent reliably converts the conversation into the correct tasks, decisions,
> commitments, follow-ups and approvals — then tracks them until closure.*

## What V1 does (the seven things)

1. Listens to your voice or typed message.
2. Understands tasks, decisions, reminders and commitments.
3. Asks for confirmation before taking important actions.
4. Creates and tracks tasks.
5. Provides morning and evening briefings.
6. Remembers people, projects and company context.
7. Identifies repeated processes and suggests standardisation (early).

It **proposes**; the **permission engine decides**; every attempt is **audited**.

## Architecture

```
Chat / Voice / Dashboard            frontend/index.html  (6 screens, one SPA)
        ↓
CEO Agent Backend                   FastAPI  (backend/app)
        ↓
Memory + Tasks + Processes + Approval Engine
  agent.py  service.py  tools.py  permissions.py  process_learning.py
        ↓
Operational database                SQLAlchemy → SQLite (dev) / PostgreSQL (prod)
```

- **One agent, one database, ~13 controlled tools.** The AI never touches
  Gmail/Calendar/records directly — it only requests a named tool.
- **Permission engine** (`permissions.py`) sorts every tool into
  *auto-allowed* / *requires-approval* / *never-autonomous* exactly per the
  approval rules, and gated tools refuse to self-execute.
- **Audit trail** = the `agent_actions` table; visible on the *Agent Activity*
  screen.

### The 10 core tables (`backend/app/models.py`)
People · Projects · Tasks · Commitments · Decisions · Conversations · Memories ·
Process observations · Process definitions · Agent actions — plus an append-only
`events` log that feeds process learning.

### The app (`frontend/index.html`) — installable PWA, mobile-first
A single-page app that installs to your phone's home screen (Add to Home Screen →
own icon, full-screen, offline app-shell) and adapts from a desktop sidebar to a
mobile bottom-nav. **Role-aware:**
- **CEO / manager:** Today · Chat · People · Company · Team · Memory · Processes · Activity
- **Team member:** My Work · Chat · Team

**Multi-user:** each person signs in with their work email and sees their own
view. Members **accept/decline** assigned tasks, update **progress**, **report
blockers**, and **submit completion**; approval-required work routes back to the
CEO/manager to sign off. The CEO manages people (add / edit / enable-disable) and
assigns tasks from a form or from chat.

> Auth is a lightweight email identify for the MVP — production swaps in Google
> Workspace login. No passwords are stored.

## Run it locally (zero external dependencies)

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
# open http://localhost:8000
```

The database is a local SQLite file, seeded with Ekosight people, projects and a
few demo tasks so the dashboard is meaningful on first run.

### Try these (Conversation screen or `POST /api/chat`)
- `Ask Priya to create three Soil Didi posts by Thursday. Kajal should collect photographs by Tuesday. I need to review everything before publishing.`
- `Create a task for Saumya to complete the GeM checklist by Friday.`
- `I promised the revised deck to Dayal Group by Friday.`
- `We decided to go with the GeM route for procurement.`
- `Send an email to Dayal Group with the revised proposal.` → **needs approval**
- `Who is waiting for a response from me?`

## Configuration (all optional — see `backend/app/config.py`)

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Point at PostgreSQL in production. Defaults to SQLite. |
| `LLM_PROVIDER` | `none` (default deterministic parser), `gemini`, or `claude`. |
| `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` | Key for the chosen provider. |
| `CEO_NAME` / `COMPANY_NAME` | Briefing / branding. |

The default parser is **rule-based and offline** so the app always runs. Setting
a provider swaps in structured LLM interpretation and transparently falls back to
rules on any error. In production the recommended stack is **Gemini via Vertex
AI**; `read_calendar` / `search_drive` / email tools are wired to the Google
Workspace MCP integrations.

## API surface

`POST /api/chat` · `POST /api/voice` · `GET /api/dashboard` ·
`GET /api/briefing/{morning,evening}` · `GET /api/{people,projects,tasks}` ·
`PATCH /api/tasks/{id}` · `GET/POST/DELETE /api/memory` · `GET /api/commitments` ·
`GET /api/decisions` · `GET /api/processes` · `POST /api/processes/approve` ·
`GET /api/actions` · `POST /api/actions/{id}/{approve,reject}` ·
`GET /api/{conversations,events}` · `GET /health` ·
`POST /api/login` · `POST/PATCH /api/people` · `POST /api/people/{id}/{activate,deactivate}` ·
`POST /api/tasks` · `POST /api/tasks/{id}/{accept,decline,progress,blocker,unblock,complete,approve}` ·
`GET /api/my/tasks` · `GET /api/team/workload`.

### Install as a mobile app
Open the site on your phone → browser menu → **Add to Home Screen**. It launches
full-screen with its own icon. (A true native Android build can follow once the
backend is deployed to a public URL.)

## Roadmap (from the phase plan)

- **Phase 1 (this MVP):** login, people/projects/tasks, chat+voice capture,
  dashboard, audit log, permissions. ✅
- **Phase 2:** morning/evening briefings ✅, commitments ✅, decision register ✅,
  Calendar + Gmail read/draft, meeting prep, voice-note processing.
- **Phase 3:** employee login ✅, task acceptance ✅, progress/blocker reporting ✅,
  completion submission ✅, manager approval ✅, team workload ✅.
- **Mobile app:** installable PWA (home-screen icon, standalone, offline shell) ✅.
- **Phase 4:** unified event log ✅, repetition detection ✅, process maps,
  bottleneck analysis.
- **Phase 5:** reusable workflow blocks (trigger/condition/action/approval/
  reminder/escalation/output).
- **Phase 6:** controlled autonomy for mature processes, with full logging.

## What this deliberately does **not** do yet
Multiple specialised agents · always-on microphone · automatic software
generation · autonomous external communication · AI-only memory without
structured records · a spreadsheet as the permanent backend.

---
_The previous `family.html` family-tree page is retained in the repo root._
