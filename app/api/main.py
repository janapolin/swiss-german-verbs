"""FastAPI app + DI wiring (§3, §12). The single entry point: `uvicorn app.api.main:app`."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.web.routes import router as web_router

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="Züritüütsch Verb Trainer")
app.include_router(api_router)
app.include_router(web_router)
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
