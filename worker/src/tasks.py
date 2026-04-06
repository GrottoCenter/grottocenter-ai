import os
import re
import uuid as uuid_lib
from datetime import datetime

import fitz
from celery import Celery
from langdetect import LangDetectException, detect

from backendV2.config.celeryconfig import CeleryConfig
from backendV2.model.Document import DocumentMetadata
from backendV2.service.minioService import MinioService
from worker.src import ocr
from worker.src.llm_analyzer import extract_metadata_with_llm, generate_global_summary


celery_app = Celery("tasks")
celery_app.config_from_object(CeleryConfig)


@celery_app.task(name="tasks.test_celery_task")
def test_celery_task(object_name: str): 
    minio_service = MinioService()

    temp_file_path = f"/tmp/{uuid_lib.uuid4()}.pdf"
    
    try:
        minio_service.download_file(object_name, temp_file_path)

        pages = ocr.extract_pdf_text_for_llm(temp_file_path)
        
        full_text = "\n\n".join(pages)
        
        chunks = []
        for i in range(0, len(pages), 4):
            chunks.append("\n\n".join(pages[i:i+4]))
            
        print(f"Document divisé en {len(chunks)} blocs de 4 pages.")

        deterministic = _extract_deterministic_metadata(temp_file_path, full_text)
        
        metadata_text = "\n\n".join([chunks[0], chunks[len(chunks)-1]]) if chunks else ""
        llm = extract_metadata_with_llm(metadata_text, known_metadata=deterministic)
        
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
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            
        try:
            minio_service.delete_file(object_name)
        except Exception as e:
            print(f"Erreur nettoyage minio : {e}")


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