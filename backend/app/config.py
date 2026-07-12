"""Application configuration.

Environment variables (all optional for local dev):
  DATABASE_URL   SQLAlchemy URL. Defaults to a local SQLite file so the app
                 runs with zero external dependencies. Point this at Postgres
                 in production, e.g. postgresql+psycopg://user:pass@host/db
  LLM_PROVIDER   "none" (default, deterministic rule parser), "gemini" or
                 "claude". When set to a real provider the matching API key
                 below must be present, otherwise the app falls back to rules.
  GEMINI_API_KEY / VERTEX_* for Gemini via Vertex AI.
  ANTHROPIC_API_KEY for Claude.
  CEO_NAME       Display name used in briefings. Defaults to "Dhiraj".
"""
from __future__ import annotations

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATABASE_URL = os.environ.get(
    "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'ceo_agent.db')}"
)

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "none").lower()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

CEO_NAME = os.environ.get("CEO_NAME", "Dhiraj")
COMPANY_NAME = os.environ.get("COMPANY_NAME", "Ekosight")
