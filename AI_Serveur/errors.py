"""What can go wrong in an analysis, and the HTTP answer for each case.

The answers are `{"detail": "<short message>"}`, like the other errors of this API. A
failure of the analysis service (GreenPT) is described in the log, never in the answer:
its body may quote the document or its own internals.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

UPSTREAM_FAILED_MESSAGE = "The analysis service failed. Try again later."
UPSTREAM_TIMEOUT_MESSAGE = "The analysis service did not answer in time. Try again later."
INTERNAL_ERROR_MESSAGE = "Internal server error"


class InvalidDocumentError(ValueError):
    """The upload cannot be analysed (HTTP 422). Subclasses ValueError, as it did before."""


class EmptyUploadError(InvalidDocumentError):
    def __init__(self) -> None:
        super().__init__("Uploaded file is empty")


class NoTextError(InvalidDocumentError):
    def __init__(self) -> None:
        super().__init__("No text could be extracted from the PDF")


class UpstreamError(Exception):
    """GreenPT failed, or answered something unusable: the caller gets a 502.

    `status_code` and `public_message` are what the caller is told. What happened is in
    the log. A GreenPT 401, 403 or 429 is a 502 as well: it concerns this server's own
    credentials and quota, and must never look like a problem with the caller's token.
    """

    status_code = 502
    public_message = UPSTREAM_FAILED_MESSAGE

    def __init__(self, reason: str) -> None:
        super().__init__(reason)


class UpstreamTimeoutError(UpstreamError):
    """GreenPT did not answer within the client's timeout: the caller gets a 504."""

    status_code = 504
    public_message = UPSTREAM_TIMEOUT_MESSAGE


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(InvalidDocumentError)
    async def invalid_document(request: Request, error: InvalidDocumentError):
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.exception_handler(UpstreamError)
    async def upstream_failure(request: Request, error: UpstreamError):
        return JSONResponse(
            status_code=error.status_code, content={"detail": error.public_message}
        )

    @app.exception_handler(Exception)
    async def unexpected(request: Request, error: Exception):
        # Safety net for what happens outside the analysis route (which has its own, see
        # documentController). Starlette runs this one outside the CORS middleware.
        logger.error("Unhandled error on %s", request.url.path, exc_info=error)
        return JSONResponse(
            status_code=500, content={"detail": INTERNAL_ERROR_MESSAGE}
        )
