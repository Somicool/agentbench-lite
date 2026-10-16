"""FastAPI application entry point: ``uvicorn app.main:app``."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(
    title="AgentBench Lite",
    description="Evaluate AI-generated Python repositories against a task specification.",
    version="1.0.0",
)
app.include_router(router)
