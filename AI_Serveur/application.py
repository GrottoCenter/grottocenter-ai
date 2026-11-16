"""
Construction de l'application FastAPI.

Kept free of side effects at import time so that tests can build an application
from any configuration. `main.py` builds the real one.
"""

import logging
import sys

import pymongo
from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config.settings import UsageLimits, resolve_log_level, settings
from controller.documentController import router as document_router
from errors import install_error_handlers
from lifespan import build_lifespan
from middleware import MaxBodySizeMiddleware, RequireValidTokenMiddleware
from service.analysisLocks import HashLocks
from service.usageService import ConcurrencyLimiter

logger = logging.getLogger(__name__)


def configure_logging(level_name: str) -> None:
    logging.basicConfig(
        level=resolve_log_level(level_name),
        stream=sys.stdout,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        force=True,
    )


def create_app(config=settings, mongo_client_factory=pymongo.MongoClient) -> FastAPI:
    app = FastAPI(
        title="Grottocenter AI Tools API",
        description="API pour les outils IA de traitement des documents Grottocenter",
        version="0.2.0",
        lifespan=build_lifespan(config, mongo_client_factory),
    )

    # What the routes need that does not depend on the lifespan. The concurrency limiter
    # lives as long as the application, so it is shared by every request.
    app.state.config = config
    app.state.concurrency = ConcurrencyLimiter()
    app.state.analysis_locks = HashLocks()
    install_error_handlers(app)

    # An oversized upload is refused before it is read. Added before CORS so that the
    # CORS middleware wraps it and the 413 still carries the CORS headers a browser
    # needs to read it.
    app.add_middleware(
        MaxBodySizeMiddleware,
        max_file_bytes=UsageLimits.from_config(config).max_file_size_bytes,
        path="/documents/analyze",
    )

    # A request without a valid token is refused before its body is read. Added after the
    # size limit, so it runs first (the last middleware added is the outermost): an
    # anonymous caller learns nothing about the size limit and costs the server nothing.
    # Still inside CORS, so the 401 carries the CORS headers a browser needs to read it.
    app.add_middleware(RequireValidTokenMiddleware, path="/documents/analyze")

    # Browsers may only call this API from the listed origins. Authentication is a
    # bearer token, not a cookie, so credentials are not allowed. A wildcard is
    # refused at startup (see validate_settings).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.get("/")
    async def root():
        return {
            "message": "Grottocenter AI Tools API",
            "version": "0.2.0",
            "status": "running"
        }

    @app.get("/health")
    async def health_check():
        """Liveness: the process answers. No I/O, so it never depends on MongoDB."""
        return {
            "status": "ok",
            "message": "API is running",
        }

    @app.get("/ready")
    async def readiness_check(request: Request):
        """Readiness: MongoDB answers a ping."""
        try:
            await run_in_threadpool(
                request.app.state.mongo_client.admin.command, "ping"
            )
        except Exception:
            logger.exception("Readiness check failed: MongoDB is not reachable")
            return JSONResponse(
                status_code=503,
                content={"status": "unavailable", "message": "MongoDB is not reachable"},
            )
        return {"status": "ok", "message": "API is ready"}

    app.include_router(document_router)
    return app
