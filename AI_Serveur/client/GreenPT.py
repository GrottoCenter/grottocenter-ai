import enum
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

class Models(enum.Enum):
    GLM = "glm-5.3-flash"

class ReasoningEffort(enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


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

        response = await self.http_client.post("/chat/completions", json=body)
        if response.is_error:
            raise RuntimeError(
                f"GreenPT API error ({response.status_code}): {response.text}"
            )

        return response.json()

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

        response = await self.http_client.post("/tools/documents/convert/file", data=data, files=files)
        response.raise_for_status()

        return response.json()
