import json
import logging
import math
import re
from typing import Any, TypedDict

from client.GreenPT import Models
from model.DocumentMetadata import DocumentAnalyseMetadata

logger = logging.getLogger(__name__)

class DocumentChunk(TypedDict):
    chunk_id: int
    token_estimate: int
    text: str

class LLMAnalyzerService:

    SINGLE_CALL_TOKEN_LIMIT = 70_000
    MAP_CHUNK_TOKEN_BUDGET = 50_000

    SCHEMA_BLOCK = json.dumps(
        DocumentAnalyseMetadata.model_json_schema(),
        ensure_ascii=False,
        indent=2,
    )


    BASE_RULES = """
    You are an expert document metadata extractor.

    You must return ONLY valid JSON.
    Do not include explanations, markdown, or extra text.

    Extract metadata from the document below.

    Return this JSON schema:

    {schema}

    Rules:
    - If a field is unknown, use null.
    - Do not add any extra fields.
    - If "grottocenter_type" is "issue", infer the articles contained in the issue during the same analysis.
    - For an issue, populate "articles" with only genuine articles that have a distinct title and substantive body text.
    - Do not create an article from editor names, addresses, page headers, page footers, issue metadata, credits, dates, section labels, or table-of-contents lines.
    - Use page ranges only for genuine articles that span a contiguous article body.
    - If the document is not an issue, set "articles" to null.
    - Output must be strictly valid JSON.
    """.strip()


    MAP_SYSTEM_PROMPT = (
        BASE_RULES.format(schema=SCHEMA_BLOCK)
        + """

    Map phase instructions:
    - You receive one chunk from a larger document.
    - Extract only evidence visible in this chunk.
    - Do not guess across chunks.
    - If the chunk does not contain enough evidence for a field, use null.
    - Populate only fields supported by the schema above.
    - When an issue article starts or ends in this chunk, report the evidence and its page range when available.
    """
    )


    REDUCE_SYSTEM_PROMPT = (
        BASE_RULES.format(schema=SCHEMA_BLOCK)
        + """

    Reduce phase instructions:
    - You receive a list of partial JSON objects produced by chunk analysis.
    - Merge them into one final JSON object.
    - Deduplicate repeated metadata values.
    - Prefer the strongest consistent value across chunks.
    - If chunk outputs disagree and the evidence is weak, use null.
    - For an issue, merge and deduplicate article candidates using their title, authors, and page range.
    - Return only the final merged JSON object.
    """
    ) 

    def __init__(self, greenpt_client):
        self.greenpt_client = greenpt_client

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Conservative estimate; API usage remains the authoritative count."""
        return max(1, math.ceil(len(text) / 4)) if text else 0

    @classmethod
    def split_text_by_budget(cls, text: str, token_budget: int) -> list[str]:
        max_chars = max(1, token_budget * 4)
        chunks: list[str] = []
        start = 0

        while start < len(text):
            end = min(len(text), start + max_chars)
            if end < len(text):
                boundary = text.rfind("\n", start, end)
                if boundary <= start:
                    boundary = text.rfind(". ", start, end)
                end = boundary + 1 if boundary > start else end
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start = end

        return chunks

    @classmethod
    def build_chunks(cls, document_text: str) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []
        for chunk_id, text in enumerate(
            cls.split_text_by_budget(document_text, cls.MAP_CHUNK_TOKEN_BUDGET),
            start=1,
        ):
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "token_estimate": cls.estimate_tokens(text),
                    "text": text,
                }
            )
        return chunks

    @staticmethod
    def empty_metadata() -> dict[str, Any]:
        return {
            field_name: None
            for field_name in DocumentAnalyseMetadata.model_fields
        }

    @staticmethod
    def format_json_for_log(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)

    @classmethod
    def parse_json_response(cls, response: dict[str, Any]) -> dict[str, Any]:
        choices = response.get("choices", [])
        content = choices[0].get("message", {}).get("content", "") if choices else ""
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            return cls.empty_metadata()
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return cls.empty_metadata()

    @staticmethod
    def aggregate_usage(*responses: dict[str, Any]) -> dict[str, int]:
        totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        for response in responses:
            usage = response.get("usage", {})
            for key in totals:
                totals[key] += int(usage.get(key, 0) or 0)
        return totals

    async def analyze_document(self, document_text: str) -> dict[str, Any]:
        if not isinstance(document_text, str):
            raise TypeError("document_text must be extracted text, not PDF bytes")

        estimated_tokens = self.estimate_tokens(document_text)
        responses: list[dict[str, Any]] = []

        if estimated_tokens <= self.SINGLE_CALL_TOKEN_LIMIT:
            response = await self.greenpt_client.call_greenpt_chat(
                document_text,
                system_prompt=self.REDUCE_SYSTEM_PROMPT,
                model=Models.DEFAULT,
            )

            # The answer holds the document's title, authors and abstract: only at DEBUG.
            logger.debug(
                "Single call response:\n%s",
                self.format_json_for_log(response),
            )

            responses.append(response)
            mode = "single"
            result = self.parse_json_response(response)
            chunk_count = 1
        else:
            chunks = self.build_chunks(document_text)
            map_results: list[dict[str, Any]] = []
            for chunk in chunks:
                prompt = (
                    f"Analyze chunk {chunk['chunk_id']} of a larger document.\n"
                    f"Estimated input tokens: {chunk['token_estimate']}\n\n"
                    f"Text:\n{chunk['text']}"
                )
                response = await self.greenpt_client.call_greenpt_chat(
                    prompt,
                    system_prompt=self.MAP_SYSTEM_PROMPT,
                    model=Models.DEFAULT,
                    max_tokens=2000,
                )

                logger.debug(
                    "Map call response for chunk %s:\n%s",
                    chunk["chunk_id"],
                    self.format_json_for_log(response),
                )

                responses.append(response)
                map_results.append(self.parse_json_response(response))

            reduce_prompt = (
                "Merge these chunk-level JSON results into one final document "
                "metadata object.\n\n"
                f"Chunk results:\n{json.dumps(map_results, ensure_ascii=False)}"
            )
            reduce_response = await self.greenpt_client.call_greenpt_chat(
                reduce_prompt,
                system_prompt=self.REDUCE_SYSTEM_PROMPT,
                model=Models.DEFAULT,
            )
            responses.append(reduce_response)
            result = self.parse_json_response(reduce_response)
            mode = "map-reduce"
            chunk_count = len(chunks)

        usage = self.aggregate_usage(*responses)

        logger.info(
            "LLM analysis mode=%s chunks=%d estimated_input_tokens=%d usage=%s",
            mode,
            chunk_count,
            estimated_tokens,
            usage,
        )
        
        return result


    async def get_text_with_OCR(self, pdf_content: bytes, filename: str) -> str:
        ocr_result = await self.greenpt_client.OCR_request(pdf_content, filename)
        if isinstance(ocr_result, str):
            return ocr_result
        return json.dumps(ocr_result, ensure_ascii=False)
