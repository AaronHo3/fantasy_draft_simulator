"""FastAPI application factory. Binds locally; no external calls on request paths."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import build_context, set_context
from app.api.routes import router
from app.api.season_routes import router as season_router
from app.settings import Settings
from app.settings import settings as default_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or default_settings

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ctx = build_context(cfg)
        set_context(ctx)
        app.state.ctx = ctx
        try:
            yield
        finally:
            ctx.jobs.shutdown()
            ctx.store.close()

    app = FastAPI(title="ESPN 9-cat Draft Copilot", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=cfg.cors_origins, allow_methods=["*"], allow_headers=["*"])
    app.include_router(router)
    app.include_router(season_router)
    return app


app = create_app()
