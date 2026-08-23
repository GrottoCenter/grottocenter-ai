from __future__ import annotations

import json
import math
import os
import re
from typing import Any, Literal, TypedDict

import fitz  # PyMuPDF
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

DocumentTypeLabel = Literal[
    "article",
    "book",
    "thesis",
    "report",
    "conference paper",
    "issue",
]


class ArticleMetadata(TypedDict, total=False):
    title: str | None
    authors: list[str] | None
    document_type: Literal["article"]
    publication_year: int | None
    page_start: int | None
    page_end: int | None


class DocumentMetadata(TypedDict, total=False):
    title: str | None
    authors: list[str] | None
    issn: str | None
    isbn: str | None
    document_type: DocumentTypeLabel | None
    publication_year: int | None
    publisher: str | None
    articles: list[ArticleMetadata] | None


class DocumentChunk(TypedDict):
    chunk_id: int
    page_start: int
    page_end: int
    token_estimate: int
    text: str


SCHEMA_BLOCK = """
{
  "title": string or null,
  "authors": [string] or null,
  "issn": string or null,
  "isbn": string or null,
  "document_type": "article" | "book" | "thesis" | "report" | "conference paper" | "issue" | null,
  "publication_year": number or null,
  "publisher": string or null,
  "articles": [
    {
      "title": string or null,
      "authors": [string] or null,
      "document_type": "article",
      "publication_year": number or null,
      "page_start": number or null,
      "page_end": number or null
    }
  ] or null
}
""".strip()


BASE_RULES = """
You are an expert document metadata extractor.

You must return ONLY valid JSON.
Do not include explanations, markdown, or extra text.

Extract metadata from the document below.

Return this JSON schema:

{schema}

Rules:
- If a field is unknown, use null.
- If the document is not an issue, set "articles" to null.
- Do not add any extra fields.
- Treat as article only a real editorial unit with a distinct title and substantive body text.
- Do not create an article from editor names, addresses, phone numbers, page headers, page footers, issue metadata, credits, dates, section labels, or table-of-contents lines.
- If a block looks like publisher information or a recurring magazine header/footer, ignore it even if it contains names, places, years, or short headings.
- Prefer one article only when the evidence is weak; if no clear article body exists, set "articles" to null.
- Use page ranges only for genuine articles that span a contiguous article body.
- If a title is followed mainly by contact details, committee roles, editorial notes, or publication data, do not classify it as an article.
- Output must be strictly valid JSON.

Decision rule for "articles":
- Keep an entry only if the text contains a real article title and several sentences of narrative or analytical content.
- Reject entries that are mostly administrative, editorial, promotional, or publication metadata.
- A section title alone is not enough to create an article.
""".strip()


MAP_SYSTEM_PROMPT = (
    BASE_RULES.format(schema=SCHEMA_BLOCK)
    + """

Map phase instructions:
- You receive one chunk from a larger document.
- Extract only evidence visible in this chunk.
- Do not guess across chunks.
- If the chunk does not contain enough evidence for a field, use null.
- If the chunk clearly contains an article, include it; otherwise keep articles null.
"""
)


REDUCE_SYSTEM_PROMPT = (
    BASE_RULES.format(schema=SCHEMA_BLOCK)
    + """

Reduce phase instructions:
- You receive a list of partial JSON objects produced by chunk analysis.
- Merge them into one final JSON object.
- Deduplicate repeated metadata and repeated article candidates.
- Prefer the strongest consistent value across chunks.
- If chunk outputs disagree and the evidence is weak, use null.
- Return only the final merged JSON object.
"""
)


model_dict = {
    "mistral": "mistral-small-3.2-24b-instruct-2506",
    "gpt": "gpt-oss-120b",
    "gemma": "gemma-3-27b-it",
}


pricing_cents_per_1M = {
    "mistral-small-3.2-24b-instruct-2506": {"input": 15, "output": 35},
    "gpt-oss-120b": {"input": 15, "output": 60},
    "gemma-3-27b-it": {"input": 25, "output": 50},
}


SINGLE_CALL_TOKEN_LIMIT = 70_000
MAP_CHUNK_TOKEN_BUDGET = 50_000


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def extract_pdf_pages_from_bytes(pdf_bytes: bytes, max_pages: int = 500) -> dict[int, str]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages_text: dict[int, str] = {}

    for page_index, page in enumerate(doc):
        if page_index >= max_pages:
            break
        page_text = page.get_text().strip()
        pages_text[page_index + 1] = page_text

    return pages_text


def OCR_request(pdf_bytes: bytes, filename: str = "document.pdf") -> dict[str, Any]:
    url = "https://api.greenpt.ai/v1/tools/documents/convert/file"
    headers = {
        "Authorization": f"Bearer {os.getenv('GREENPT_API_KEY')}",
    }

    data = {
        "to_formats": "json",
        "do_ocr": "true",
        "table_mode": "accurate",
        "do_table_structure": "true",
        "include_images": "true",
    }

    files = {"files": (filename, pdf_bytes, "application/pdf")}
    response = requests.post(url, headers=headers, files=files, data=data, timeout=300)
    response.raise_for_status()
    return response.json()


def extract_text_by_page_from_ocr_response(ocr_response: dict[str, Any]) -> dict[int, str]:
    document = ocr_response.get("document", {})
    json_content = document.get("json_content", {})
    texts = json_content.get("texts", [])

    pages_text: dict[int, list[str]] = {}

    for item in texts:
        text = item.get("text") or item.get("orig") or ""
        if not text.strip():
            continue

        prov_list = item.get("prov", [])
        page_numbers = sorted(
            {
                prov.get("page_no")
                for prov in prov_list
                if prov.get("page_no") is not None
            }
        )

        if not page_numbers:
            page_numbers = [1]

        for page_no in page_numbers:
            pages_text.setdefault(int(page_no), []).append(text)

    return {
        page_no: "\n".join(page_lines).strip()
        for page_no, page_lines in sorted(pages_text.items())
    }


def format_pages_as_text(pages_text: dict[int, str]) -> str:
    return "\n\n".join(
        f"--- Page {page_no} ---\n{page_text}" for page_no, page_text in sorted(pages_text.items())
    )


def format_chunk_as_text(chunk: DocumentChunk) -> str:
    return (
        f"--- Chunk {chunk['chunk_id']} | Pages {chunk['page_start']} to {chunk['page_end']} "
        f"| Estimated tokens {chunk['token_estimate']} ---\n{chunk['text']}"
    )


def split_text_by_budget(text: str, token_budget: int) -> list[str]:
    max_chars = max(1, token_budget * 4)
    if len(text) <= max_chars:
        return [text]

    slices: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            break_point = text.rfind("\n", start, end)
            if break_point <= start:
                break_point = text.rfind(". ", start, end)
            if break_point <= start:
                break_point = end
            else:
                break_point += 1
            end = break_point
        slices.append(text[start:end].strip())
        start = end

    return [slice_text for slice_text in slices if slice_text]


def build_document_chunks(pages_text: dict[int, str], chunk_token_budget: int = MAP_CHUNK_TOKEN_BUDGET) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    current_pages: list[tuple[int, str]] = []
    current_tokens = 0
    chunk_id = 1

    def flush_current_chunk() -> None:
        nonlocal chunk_id, current_pages, current_tokens
        if not current_pages:
            return

        text = "\n\n".join(
            f"--- Page {page_no} ---\n{page_text}" for page_no, page_text in current_pages
        ).strip()

        chunks.append(
            {
                "chunk_id": chunk_id,
                "page_start": current_pages[0][0],
                "page_end": current_pages[-1][0],
                "token_estimate": estimate_tokens(text),
                "text": text,
            }
        )
        chunk_id += 1
        current_pages = []
        current_tokens = 0

    for page_no, page_text in sorted(pages_text.items()):
        page_text = page_text.strip()
        if not page_text:
            continue

        page_tokens = estimate_tokens(page_text)
        if page_tokens > chunk_token_budget:
            flush_current_chunk()
            page_slices = split_text_by_budget(page_text, chunk_token_budget)
            for page_slice in page_slices:
                chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "page_start": page_no,
                        "page_end": page_no,
                        "token_estimate": estimate_tokens(page_slice),
                        "text": f"--- Page {page_no} ---\n{page_slice}",
                    }
                )
                chunk_id += 1
            continue

        if current_pages and current_tokens + page_tokens > chunk_token_budget:
            flush_current_chunk()

        current_pages.append((page_no, page_text))
        current_tokens += page_tokens

    flush_current_chunk()
    return chunks


def extract_json_from_content(content: str) -> dict[str, Any]:
    content = content.strip()
    if not content:
        return {
            "title": None,
            "authors": None,
            "issn": None,
            "isbn": None,
            "document_type": None,
            "publication_year": None,
            "publisher": None,
            "articles": None,
        }

    match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
    if match:
        content = match.group(1).strip()
    else:
        start = content.find("{")
        if start != -1:
            depth = 0
            in_string = False
            escape_next = False
            for index, character in enumerate(content[start:], start=start):
                if escape_next:
                    escape_next = False
                    continue
                if character == "\\":
                    escape_next = True
                    continue
                if character == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if character == "{":
                    depth += 1
                elif character == "}":
                    depth -= 1
                    if depth == 0:
                        content = content[start : index + 1].strip()
                        break

    content = content.strip()
    if not content:
        return {
            "title": None,
            "authors": None,
            "issn": None,
            "isbn": None,
            "document_type": None,
            "publication_year": None,
            "publisher": None,
            "articles": None,
        }

    try:
        return json.loads(content)
    except (json.JSONDecodeError, ValueError):
        fixed = content.replace("\r\n", "\n")
        fixed = re.sub(r",\s*([}\]])", r"\1", fixed)
        fixed = re.sub(r"\n\s*([}\]])", r"\1", fixed)
        try:
            return json.loads(fixed)
        except (json.JSONDecodeError, ValueError):
            return {
                "title": None,
                "authors": None,
                "issn": None,
                "isbn": None,
                "document_type": None,
                "publication_year": None,
                "publisher": None,
                "articles": None,
            }


def call_greenpt_chat(prompt: str, system_prompt: str, model: str, max_tokens: int = 2000) -> dict[str, Any]:
    url = "https://api.greenpt.ai/v1/chat/completions"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "top_p": 1,
        "max_tokens": max_tokens,
        "reasoning_effort": "medium",
    }

    response = requests.post(
        url,
        json=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.getenv('GREENPT_API_KEY')}",
        },
        timeout=300,
    )
    response.raise_for_status()
    try:
        return response.json()
    except (json.JSONDecodeError, ValueError):
        return {
            "raw_response": response.text,
            "status_code": response.status_code,
        }


def call_llm_for_json(prompt: str, system_prompt: str, model: str, max_tokens: int = 2000) -> tuple[dict[str, Any], dict[str, Any]]:
    response_json = call_greenpt_chat(prompt, system_prompt, model, max_tokens=max_tokens)
    choices = response_json.get("choices", []) if isinstance(response_json, dict) else []
    content = ""
    if choices:
        content = choices[0].get("message", {}).get("content", "")
    parsed = extract_json_from_content(content)
    if not choices or (parsed.get("title") is None and parsed.get("document_type") is None and parsed.get("articles") is None):
        response_json["parse_error"] = content
        response_json["parse_error_reason"] = "empty-or-invalid-json-or-non-json-api-response"
    return parsed, response_json


def build_map_prompt(chunk: DocumentChunk) -> str:
    return (
        f"You are analyzing one chunk of a larger document.\n"
        f"Chunk id: {chunk['chunk_id']}\n"
        f"Pages: {chunk['page_start']} to {chunk['page_end']}\n"
        f"Estimated input tokens: {chunk['token_estimate']}\n\n"
        f"Text:\n{chunk['text']}"
    )


def build_reduce_prompt(map_results: list[dict[str, Any]]) -> str:
    return (
        "Merge these chunk-level JSON results into one final document metadata object.\n\n"
        f"Chunk results:\n{json.dumps(map_results, ensure_ascii=False, indent=2)}"
    )


def aggregate_usage(*responses: dict[str, Any]) -> dict[str, int]:
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for response in responses:
        usage = response.get("usage", {}) if isinstance(response, dict) else {}
        totals["prompt_tokens"] += int(usage.get("prompt_tokens", 0) or 0)
        totals["completion_tokens"] += int(usage.get("completion_tokens", 0) or 0)
        totals["total_tokens"] += int(usage.get("total_tokens", 0) or 0)
    return totals


def analyze_document(pages_text: dict[int, str], selected_model: str) -> tuple[DocumentMetadata, dict[str, Any], dict[str, Any]]:
    document_text = format_pages_as_text(pages_text)
    total_tokens_estimate = estimate_tokens(document_text)

    if total_tokens_estimate <= SINGLE_CALL_TOKEN_LIMIT:
        final_result, llm_response = call_llm_for_json(
            document_text,
            REDUCE_SYSTEM_PROMPT,
            selected_model,
        )
        return final_result, llm_response, {
            "mode": "single",
            "total_tokens_estimate": total_tokens_estimate,
            "chunk_count": 1,
            "usage": aggregate_usage(llm_response),
        }

    chunks = build_document_chunks(pages_text, MAP_CHUNK_TOKEN_BUDGET)
    map_results: list[dict[str, Any]] = []
    map_responses: list[dict[str, Any]] = []

    for chunk in chunks:
        chunk_result, chunk_response = call_llm_for_json(
            build_map_prompt(chunk),
            MAP_SYSTEM_PROMPT,
            selected_model,
            max_tokens=1200,
        )
        map_results.append(
            {
                "chunk": {
                    "chunk_id": chunk["chunk_id"],
                    "page_start": chunk["page_start"],
                    "page_end": chunk["page_end"],
                    "token_estimate": chunk["token_estimate"],
                },
                "result": chunk_result,
            }
        )
        map_responses.append(chunk_response)

    final_result, reduce_response = call_llm_for_json(
        build_reduce_prompt(map_results),
        REDUCE_SYSTEM_PROMPT,
        selected_model,
    )

    return final_result, {
        "map_responses": map_responses,
        "reduce_response": reduce_response,
        "chunks": chunks,
        "map_results": map_results,
    }, {
        "mode": "map-reduce",
        "total_tokens_estimate": total_tokens_estimate,
        "chunk_count": len(chunks),
        "usage": aggregate_usage(*map_responses, reduce_response),
    }


def read_document_text(pdf_bytes: bytes, filename: str) -> tuple[dict[int, str], bool]:
    pages_text = extract_pdf_pages_from_bytes(pdf_bytes)
    combined_text = format_pages_as_text(pages_text)

    if combined_text.strip() and len(combined_text) >= 500:
        return pages_text, False

    ocr_result = OCR_request(pdf_bytes, filename)
    pages_text = extract_text_by_page_from_ocr_response(ocr_result)
    return pages_text, True


st.set_page_config(page_title="Test GreenPT API", layout="wide")
st.title("Testeur d'Extraction PDF - GreenPT")

key = os.getenv("GREENPT_API_KEY")
if not key:
    st.error("⚠️ La clé GREENPT_API_KEY est introuvable. Veuillez l'ajouter à votre fichier `.env`.")

with st.sidebar:
    st.header("Paramètres")
    uploaded_file = st.file_uploader("Choisissez un document PDF", type=["pdf"])
    selected_model_key = st.selectbox("Modèle LLM", options=list(model_dict.keys()))
    st.caption(
        f"Fenêtre map: {MAP_CHUNK_TOKEN_BUDGET:,} tokens | Déclenchement map-reduce: {SINGLE_CALL_TOKEN_LIMIT:,} tokens"
    )

if st.button("Lancer l'analyse", type="primary"):
    if uploaded_file is None:
        st.warning("Veuillez d'abord uploader un fichier PDF.")
    elif not key:
        st.error("Impossible de lancer l'analyse sans clé API.")
    else:
        with st.spinner("Analyse du PDF et appel à l'API GreenPT en cours..."):
            pdf_bytes = uploaded_file.getvalue()
            pages_text, used_ocr = read_document_text(pdf_bytes, uploaded_file.name)

            if not pages_text or not any(page_text.strip() for page_text in pages_text.values()):
                st.error("Aucun texte exploitable n'a pu etre extrait du document.")
                st.stop()

            if used_ocr:
                st.warning("Le texte extrait du PDF etait vide ou trop court. L'OCR a ete utilise.")

            selected_model = model_dict[selected_model_key]

            try:
                result, llm_debug, analysis_info = analyze_document(pages_text, selected_model)
            except (requests.RequestException, json.JSONDecodeError, KeyError) as exc:
                st.error(f"Echec de l'analyse LLM: {exc}")
                st.stop()

            col1, col2 = st.columns([1.5, 1])

            with col1:
                st.subheader("Résultat JSON des métadonnées")
                st.json(result)

                with st.expander("Voir le texte extrait du PDF"):
                    st.text_area(
                        "Texte extrait",
                        value=format_pages_as_text(pages_text),
                        height=400,
                        disabled=True,
                    )

                if analysis_info["mode"] == "map-reduce":
                    with st.expander("Voir les chunks map-reduce"):
                        st.json(llm_debug.get("map_results", []))

            with col2:
                st.subheader("Métriques")
                st.write(f"**Modèle utilisé:** `{selected_model}`")
                st.write(f"**Mode:** {analysis_info['mode']}")
                st.write(f"**Estimation tokens entrée:** {analysis_info['total_tokens_estimate']}")
                st.write(f"**Nombre de chunks:** {analysis_info['chunk_count']}")

                usage = analysis_info.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)

                model_name = selected_model
                prices = pricing_cents_per_1M.get(model_name, {"input": 0, "output": 0})
                cost_prompt_eur = (prompt_tokens / 1_000_000) * (prices["input"] / 100)
                cost_completion_eur = (completion_tokens / 1_000_000) * (prices["output"] / 100)
                total_cost_eur = cost_prompt_eur + cost_completion_eur

                response_for_reasoning = llm_debug.get("reduce_response") if analysis_info["mode"] == "map-reduce" else llm_debug
                reasoning = response_for_reasoning.get("choices", [{}])[0].get("message", {}).get("reasoning") if isinstance(response_for_reasoning, dict) else None
                if reasoning:
                    with st.expander("Voir le raisonnement"):
                        st.write(reasoning)

                st.markdown("### Consommation des Tokens")
                t1, t2, t3, t4 = st.columns(4)
                t1.metric("Prompt", prompt_tokens)
                t2.metric("Completion", completion_tokens)
                t3.metric("Total", usage.get("total_tokens", 0))
                t4.metric("Coût", f"{total_cost_eur:.6f} €")