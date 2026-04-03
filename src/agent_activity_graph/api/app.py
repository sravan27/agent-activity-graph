from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from agent_activity_graph.api.routes import router as api_router
from agent_activity_graph.db.repository import seed_policy_rules
from agent_activity_graph.db.session import SessionLocal, init_db
from agent_activity_graph.ui.views import router as ui_router
from agent_activity_graph.utils.logging import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    init_db()
    with SessionLocal() as session:
        seed_policy_rules(session)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Agent Activity Graph",
        summary="Runtime evidence for agentic business workflows.",
        lifespan=lifespan,
    )
    app.include_router(api_router)
    app.include_router(ui_router)
    return app

