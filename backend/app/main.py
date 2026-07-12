"""Ekosight CEO Agent — V1 (FastAPI backend + served dashboard).

Run:  uvicorn app.main:app --reload  (from the backend/ directory)
Then open http://localhost:8000
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import config
from .database import SessionLocal, init_db
from .routers import api
from .seed import seed_if_empty

app = FastAPI(title="Ekosight CEO Agent — V1", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api.router)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok", "company": config.COMPANY_NAME,
            "llm_provider": config.LLM_PROVIDER}


# Serve the single-page dashboard --------------------------------------------
FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "frontend",
)


@app.get("/favicon.ico")
def favicon():
    return FileResponse(os.path.join(FRONTEND_DIR, "icon-192.png"))


# PWA + icon assets served at the site root (service-worker scope needs root).
_ROOT_FILES = {
    "manifest.webmanifest": "application/manifest+json",
    "sw.js": "application/javascript",
    "icon-192.png": "image/png",
    "icon-512.png": "image/png",
    "icon-maskable-512.png": "image/png",
    "apple-touch-icon.png": "image/png",
}


def _make_root_route(fname: str, media: str):
    def _route():
        return FileResponse(os.path.join(FRONTEND_DIR, fname), media_type=media)
    return _route


for _fname, _media in _ROOT_FILES.items():
    app.add_api_route(f"/{_fname}", _make_root_route(_fname, _media),
                      methods=["GET"], include_in_schema=False)


@app.get("/")
def index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
