import os
import re
from datetime import datetime

import fitz
from celery import Celery
from langdetect import LangDetectException, detect

from backendV2.config.celeryconfig import CeleryConfig
from backendV2.model.Document import DocumentMetadata
from backendV2.worker import ocr
from backendV2.worker.llm_analyzer import extract_metadata_with_llm, generate_global_summary


celery_app = Celery("tasks")
celery_app.config_from_object(CeleryConfig)


@celery_app.task(name="tasks.test_celery_task")
def test_celery_task(file_path: str):
    try:
        pages = ocr.extract_pdf_text_for_llm(file_path)
        
        # Le texte complet reste utile pour les regex déterministes
        full_text = "\n\n".join(pages)
        
        # Découpage des pages en blocs de 4 pages
        chunks = []
        for i in range(0, len(pages), 4):
            chunks.append("\n\n".join(pages[i:i+4]))
            
        print(f"Document divisé en {len(chunks)} blocs de 4 pages.")

        deterministic = _extract_deterministic_metadata(file_path, full_text)
        
        # L'extraction JSON ne reçoit que le premier et dernier bloc pour se concentrer sur les métadonnées souvent présentes en début/fin de document
        metadata_text = "\n\n".join([chunks[0], chunks[len(chunks)-1]]) if chunks else ""
        llm = extract_metadata_with_llm(metadata_text, known_metadata=deterministic)
        
        # Génération du résumé avec du Map-Reduce
        langue_doc_detectee = llm.language or deterministic.language or None
        global_summary = generate_global_summary(chunks, language=langue_doc_detectee)
        
        llm.summary = global_summary
        final_metadata = _merge_metadata(deterministic, llm)

        return {
            "status": "completed",
            "metadata": final_metadata.model_dump(mode="json"),
            "ocr_excerpt": full_text[:3000]
        }
    except Exception as e:
        return {
            "status": "failed",
            "error": str(e)
        }
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


def _extract_deterministic_metadata(file_path: str, text: str) -> DocumentMetadata:
    with fitz.open(file_path) as doc:
        meta = doc.metadata or {}
        page_count = doc.page_count

    language = None
    try:
        if len((text or "").strip()) > 20:
            language = detect(text[:5000])
    except LangDetectException:
        language = None

    return DocumentMetadata(
        language=language,
        page=str(page_count),
        created_at=datetime.utcnow(),
    )


def _is_empty(value):
    return value is None or value == "" or value == []


def _merge_metadata(base: DocumentMetadata, llm: DocumentMetadata) -> DocumentMetadata:
    merged = base.model_copy(deep=True)

    for field in ["title", "authors", "language", "summary", "iso3166", "editor", "issue", "issn", "isbn"]:
        base_val = getattr(merged, field)
        llm_val = getattr(llm, field)
        if _is_empty(base_val) and not _is_empty(llm_val):
            setattr(merged, field, llm_val)

    return merged