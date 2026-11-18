import enum
import logging
from typing import Any

import httpx

import logdetails
from errors import UpstreamError, UpstreamTimeoutError

logger = logging.getLogger(__name__)

class Models(enum.Enum):
    GLM = "glm-5.3-flash"

class ReasoningEffort(enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# What of a GreenPT answer is kept in the log (more with LOG_ANALYSIS_DETAILS). The answer is
# not shown to the caller.
LOGGED_BODY_CHARACTERS = 500


def _fail(operation: str, reason: str, response: httpx.Response | None = None) -> UpstreamError:
    """Log what GreenPT did, and build the error the caller is told about."""
    if response is not None:
        logger.error(
            "GreenPT %s failed: %s status=%s body=%s",
            operation,
            reason,
            response.status_code,
            response.text[
                : logdetails.UPSTREAM_BODY_CHARACTERS
                if logdetails.enabled()
                else LOGGED_BODY_CHARACTERS
            ],
        )
    else:
        logger.error("GreenPT %s failed: %s", operation, reason)
    return UpstreamError(f"GreenPT {operation} failed: {reason}")


async def _post(client: httpx.AsyncClient, operation: str, url: str, **kwargs) -> httpx.Response:
    """POST to GreenPT. A timeout, a connection failure or an HTTP error becomes an UpstreamError."""
    try:
        response = await client.post(url, **kwargs)
    except httpx.TimeoutException as error:
        logger.error("GreenPT %s timed out: %s", operation, type(error).__name__)
        raise UpstreamTimeoutError(f"GreenPT {operation} timed out") from error
    except httpx.TransportError as error:
        raise _fail(operation, f"cannot reach GreenPT ({type(error).__name__})") from error
    if response.is_error:
        raise _fail(operation, "GreenPT answered with an error", response)
    return response


def _json(operation: str, response: httpx.Response):
    try:
        return response.json()
    except ValueError as error:
        raise _fail(operation, "the answer is not JSON", response) from error


class GreenPTClient:
    def __init__(self, base_url: str, api_key: str, http_client: httpx.AsyncClient):
        self.api_key = api_key
        self.base_url = base_url
        self.http_client = http_client

    async def call_greenpt_chat(
        self,
        prompt: str,
        system_prompt: str,
        model: Models,
        max_tokens: int = 5_000,
    ) -> dict[str, Any]:
        body = {
            "model": model.value,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "top_p": 1,
            "max_tokens": max_tokens,
            "stream": False,
            "reasoning_effort": ReasoningEffort.LOW.value,
        }

        response = await _post(self.http_client, "chat", "/chat/completions", json=body)
        return _json("chat", response)

    async def OCR_request(self, pdf_bytes: bytes, filename: str) -> str:
        data = {
            "to_formats": "json",
            "do_ocr": "true",
            "table_mode": "accurate",
            "do_table_structure": "true",
            "include_images": "true",
        }

        files = {
            "files": (
                filename,
                pdf_bytes,
                "application/pdf",
            )
        }

        response = await _post(
            self.http_client, "OCR", "/tools/documents/convert/file", data=data, files=files
        )
        return _json("OCR", response)
