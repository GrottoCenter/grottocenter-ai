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

from api_docs import API_DESCRIPTION, API_TITLE, API_VERSION
from config.settings import (
    UsageLimits,
    build_origin_regex,
    resolve_log_level,
    settings,
)
from controller.documentController import router as document_router
from docs_ui import install_docs
from errors import install_error_handlers
from lifespan import build_lifespan
from middleware import MaxBodySizeMiddleware, RequireValidTokenMiddleware
from service.analysisLocks import HashLocks
from service.usageService import ConcurrencyLimiter
from tracing import TRACE_HEADER, JsonFormatter, TraceIdFilter, TraceIdMiddleware

logger = logging.getLogger(__name__)


def configure_logging(level_name: str, stream=None) -> None:
    """One JSON object per line on stdout, each with the trace id of its request."""
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(TraceIdFilter())
    logging.basicConfig(level=resolve_log_level(level_name), handlers=[handler], force=True)


def create_app(config=settings, mongo_client_factory=pymongo.MongoClient) -> FastAPI:
    app = FastAPI(
        title=API_TITLE,
        description=API_DESCRIPTION,
        version=API_VERSION,
        # The documentation page is ours (docs_ui.py): the stock pages load their files from a
        # CDN and name the framework. ReDoc is not offered.
        docs_url=None,
        redoc_url=None,
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
        # Developers' machines and the staging deployments, when configured: matched against
        # the whole origin, and checked at startup so that they cannot become a wildcard.
        allow_origin_regex=build_origin_regex(
            getattr(config, "cors_allow_localhost", False),
            getattr(config, "cors_origin_regex", ""),
        ),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", TRACE_HEADER],
        # What a browser may read from an answer: the trace id to quote in a report, and
        # how long to wait after a 429 or a 503.
        expose_headers=[TRACE_HEADER, "Retry-After"],
    )

    # Outermost, so that every answer carries the trace id, including the refusals that the
    # middlewares above send and the CORS preflight.
    app.add_middleware(TraceIdMiddleware)

    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "message": API_TITLE,
            "version": API_VERSION,
            "status": "running"
        }

    @app.get("/health", include_in_schema=False)
    async def health_check():
        """Liveness: the process answers. No I/O, so it never depends on MongoDB."""
        return {
            "status": "ok",
            "message": "API is running",
        }

    @app.get("/ready", include_in_schema=False)
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

    install_docs(app)
    app.include_router(document_router)
    return app
