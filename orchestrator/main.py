from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from orchestrator.api.router import api_router
from orchestrator.core.log_format import configure_logging
from orchestrator.core.storage import get_storage


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    storage = get_storage()
    await storage.connect()
    yield
    await storage.close()


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title="Marketing Strategy Sub-Orchestrator",
        version="0.1.0",
        description="Autonomous multi-agent marketing orchestration engine powered by LangGraph.",
        lifespan=lifespan,
    )

    app.include_router(api_router)

    @app.get("/healthz", tags=["health"])
    async def health_check() -> dict[str, str]:
        return {"status": "ok", "app": "marketing-orchestrator"}

    @app.get("/", tags=["health"])
    async def root_info() -> dict[str, str]:
        return {
            "name": "Marketing Strategy Sub-Orchestrator API",
            "docs": "/docs",
            "health": "/healthz",
        }

    return app


app = create_app()
