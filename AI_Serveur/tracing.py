"""A trace id for every request, on the response and on every log line.

The id ties together what the front, the Grottocenter API and this server did for one user
action: the front sends the same `X-Trace-Id` on its calls, and the id is searched for in
each side's logs. A request that brings none, or a malformed one, gets a fresh id.

The id lives in a context variable. asyncio tasks and `asyncio.to_thread` copy it, so
concurrent requests never see each other's id.
"""

import json
import logging
import re
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

from logdetails import details_enabled

TRACE_HEADER = "X-Trace-Id"
_TRACE_HEADER_BYTES = TRACE_HEADER.lower().encode()

# Only a UUID is taken from the caller: anything else could carry a newline or JSON into
# the log. Anything that is not a UUID is replaced, never cleaned up.
_UUID_PATTERN = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

# Probes run every few seconds: their request line would drown the log.
QUIET_PATHS = frozenset({"/health", "/ready"})

current_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)

request_logger = logging.getLogger("request")


def read_trace_id(value: str | None) -> str:
    """The caller's trace id if it is a UUID, lower-cased, else a new one."""
    if value is not None and _UUID_PATTERN.fullmatch(value):
        return value.lower()
    return str(uuid.uuid4())


class TraceIdFilter(logging.Filter):
    """Puts the id of the request being handled on every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = current_trace_id.get()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line, so that a log collector never splits a traceback."""

    EXTRA_FIELDS = (
        "http_method",
        "http_path",
        "http_status",
        "duration_ms",
        # The detailed logs (logdetails.py)
        "file_name",
        "file_size_bytes",
        "content_type",
        "source",
        "result_json",
        "result_compact",
        "result_truncated",
        "raw_answer",
        "raw_answer_truncated",
    )

    def format(self, record: logging.LogRecord) -> str:
        line = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", None) or current_trace_id.get(),
        }
        for name in self.EXTRA_FIELDS:
            if hasattr(record, name):
                line[name] = getattr(record, name)
        if record.exc_info:
            line["exception"] = self.formatException(record.exc_info)
        return json.dumps(line, ensure_ascii=False)


class TraceIdMiddleware:
    """Gives each request its trace id, returns it, and logs one line when it is answered.

    It is the outermost middleware, so the refusals sent by the others (401, 413) carry
    the id too. The id is not reset at the end: each request runs in its own task, and
    keeping it lets the last-resort error handler, which runs after this middleware, still
    log with it.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(_TRACE_HEADER_BYTES)
        trace_id = read_trace_id(incoming.decode("latin-1") if incoming else None)
        current_trace_id.set(trace_id)
        config = getattr(getattr(scope.get("app"), "state", None), "config", None)
        details_enabled.set(getattr(config, "log_analysis_details", False) is True)
        started = time.perf_counter()
        status = 0

        async def send_with_trace_id(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != _TRACE_HEADER_BYTES]
                headers.append((_TRACE_HEADER_BYTES, trace_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_trace_id)
        finally:
            level = logging.DEBUG if scope["path"] in QUIET_PATHS else logging.INFO
            request_logger.log(
                level,
                "request %s %s %s",
                scope["method"],
                scope["path"],
                status,
                extra={
                    "http_method": scope["method"],
                    "http_path": scope["path"],
                    "http_status": status,
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                },
            )
