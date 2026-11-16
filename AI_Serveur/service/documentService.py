import asyncio
import hashlib
import logging
import time
from contextlib import nullcontext
from datetime import datetime, timezone
from uuid import UUID

import fitz
from fastapi import HTTPException, UploadFile

from config.settings import UsageLimits
from model.DocumentMetadata import DocumentAnalyseMetadata
from model.DocumentMetadata import DocumentMetadata as DocumentMetadataModel
from model.GrottocenterType import GrottocenterType
from model.MongoDocument import MongoDocument
from repository.mongo import MongoRepository
from service.documentLlmAnalyzeService import LLMAnalyzerService
from service.usageService import UsageService

logger = logging.getLogger(__name__)

READ_CHUNK_BYTES = 1024 * 1024
# A PDF starts with this marker; readers accept it anywhere in the first kilobyte.
PDF_SIGNATURE = b"%PDF-"
PDF_SIGNATURE_WINDOW = 1024

class DocumentService:

    def __init__(
        self,
        analyzer_service: LLMAnalyzerService,
        mongo_repository: MongoRepository,
        usage: UsageService | None = None,
        limits: UsageLimits | None = None,
    ):
        self.analyzer_service = analyzer_service
        self.mongo_repository = mongo_repository
        # Without a UsageService nothing is metered. The application always passes one
        # (see get_document_service); only unit tests build the service without it.
        self.usage = usage
        self.limits = limits or UsageLimits()

    @staticmethod
    def map_document_analysis_to_metadata(document_analysis: DocumentAnalyseMetadata | dict) -> list[DocumentMetadataModel]:
        analysis = DocumentAnalyseMetadata.model_validate(document_analysis)

        if not analysis.articles:
            return [
                DocumentMetadataModel.model_validate(
                    analysis.model_dump(exclude={"articles"})
                )
            ]

        issue_metadata = DocumentMetadataModel.model_validate(
            analysis.model_dump(exclude={"articles"})
        )
        shared_metadata = analysis.model_dump(
            exclude={"identifiers", "articles"},
        )
        documents = [issue_metadata]

        for article in analysis.articles:
            article_metadata = {
                **shared_metadata,
                "title": article.title,
                "authors": article.authors,
                "grottocenter_type": GrottocenterType.ARTICLE,
                "identifiers": [],
                "parent": analysis.title,
                "pages": f"{article.page_start}-{article.page_end}",
            }
            documents.append(DocumentMetadataModel.model_validate(article_metadata))

        return documents
    
    
    async def process_document(
        self, file: UploadFile, caller_id: int | str | None = None
    ) -> dict:
        started = time.perf_counter()
        unique_filename = str(UUID(int=time.time_ns())) + ".pdf"

        if not self.limits.analyze_enabled:
            raise HTTPException(
                status_code=503, detail="Document analysis is temporarily disabled"
            )

        file_content = await self._read_upload(file)
        if len(file_content) == 0:
            raise ValueError("Uploaded file is empty")
        await asyncio.to_thread(self._validate_pdf, file_content)

        file_hash = self.get_file_hash(file_content)
        documents_existing = await asyncio.to_thread(
            self.mongo_repository.get_with_hash, file_hash
        )
        # A file that was analysed before is answered from storage: no OCR, no LLM call,
        # so it uses neither quota nor a concurrency slot.
        if documents_existing:
            self._log_analysis(
                caller_id, file_hash, file_content, started, source="storage"
            )
            return {
                "message": "success",
                "filename": documents_existing[0].fileName,
                "document_metadata": [
                    document.metadata for document in documents_existing
                ],
            }

        metered = self.usage.metered(caller_id) if self.usage else nullcontext()
        async with metered:
            document_metadata = await self.analyze(
                file_content,
                unique_filename,
                file.content_type or "application/pdf",
            )

            created_at = datetime.now(timezone.utc)
            documents_to_insert = []
            for metadata in document_metadata:
                document = MongoDocument(
                    fileName=unique_filename,
                    hash=file_hash,
                    mimeType=file.content_type or "application/pdf",
                    createdAt=created_at,
                    model="GreenPT",
                    metadata=metadata,
                )
                document_data = document.model_dump(exclude={"metadata"})
                document_data["metadata"] = metadata.model_dump(mode="json")
                documents_to_insert.append(document_data)

            await asyncio.to_thread(self.mongo_repository.insert_many, documents_to_insert)

        logger.info("Processing document file %s", unique_filename)
        self._log_analysis(
            caller_id, file_hash, file_content, started, source="analyzed"
        )

        return {
            "message": "success", 
            "filename": unique_filename,
            "document_metadata": document_metadata
        }

    async def analyze(
        self,
        file_content: bytes,
        unique_filename: str,
        content_type: str,
    ) -> list[DocumentMetadataModel]:
        pdf = fitz.open(stream=file_content, filetype="pdf")
        document_text = "\n\n".join(
            f"--- Page {page_number} ---\n{page.get_text()}"
            for page_number, page in enumerate(pdf, start=1)
            if page.get_text().strip()
        )
        page_count = pdf.page_count
        pdf.close()

        if len(document_text) < 1000:
            logger.info("Using OCR for document file %s", unique_filename)
            ocr_text = await self.analyzer_service.get_text_with_OCR(
                file_content,
                unique_filename,
            )
            document_text = f"{document_text}\n\n{ocr_text}".strip()

        if not document_text.strip():
            raise ValueError("No text could be extracted from the PDF")

        expected_calls = self._expected_llm_calls(document_text)
        if expected_calls > self.limits.max_llm_calls:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"The document is too large to analyse: it would take {expected_calls} "
                    f"model calls and the limit is {self.limits.max_llm_calls}"
                ),
            )

        document_analysis = await self.analyzer_service.analyze_document(document_text)

        document_metadata = self.map_document_analysis_to_metadata(document_analysis)
        for metadata in document_metadata:
            metadata.formats = [content_type]
            if not metadata.pages:
                metadata.pages = str(page_count)

        return document_metadata


    async def _read_upload(self, file: UploadFile) -> bytes:
        """Read the upload in chunks and stop as soon as it is over the size limit."""
        limit = self.limits.max_file_size_bytes
        content = bytearray()
        while chunk := await file.read(READ_CHUNK_BYTES):
            content.extend(chunk)
            if len(content) > limit:
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large: the limit is {self.limits.max_file_size_mb} MB",
                )
        return bytes(content)

    def _validate_pdf(self, content: bytes) -> None:
        """Refuse what is not a readable, reasonably sized PDF, before anything is paid for."""
        if PDF_SIGNATURE not in content[:PDF_SIGNATURE_WINDOW]:
            raise HTTPException(status_code=415, detail="Only PDF files are accepted")
        try:
            with fitz.open(stream=content, filetype="pdf") as pdf:
                if pdf.needs_pass:
                    raise HTTPException(
                        status_code=422, detail="The PDF is password protected"
                    )
                pages = pdf.page_count
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(
                status_code=422, detail="The PDF could not be read"
            ) from error
        if pages == 0:
            raise HTTPException(status_code=422, detail="The PDF has no pages")
        if pages > self.limits.max_pages:
            raise HTTPException(
                status_code=422,
                detail=f"The PDF has {pages} pages; the limit is {self.limits.max_pages}",
            )

    @staticmethod
    def _expected_llm_calls(document_text: str) -> int:
        """How many chat calls the analysis will make: one, or one per chunk plus a merge."""
        if (
            LLMAnalyzerService.estimate_tokens(document_text)
            <= LLMAnalyzerService.SINGLE_CALL_TOKEN_LIMIT
        ):
            return 1
        return len(LLMAnalyzerService.build_chunks(document_text)) + 1

    @staticmethod
    def _log_analysis(
        caller_id: int | str | None,
        file_hash: str,
        file_content: bytes,
        started: float,
        source: str,
    ) -> None:
        """One audit line per analysis: who, which file, how big, how long, from where.

        Never receives the token, so it cannot log it. The page count is best effort
        and must not turn a successful analysis into an error.
        """
        try:
            with fitz.open(stream=file_content, filetype="pdf") as pdf:
                pages = pdf.page_count
        except Exception:
            pages = None
        logger.info(
            "analysis caller=%s hash=%s pages=%s duration_ms=%d source=%s",
            caller_id,
            file_hash[:12],
            pages,
            (time.perf_counter() - started) * 1000,
            source,
        )

    @staticmethod
    def get_file_hash(file_content: bytes) -> str:
        return hashlib.sha256(file_content).hexdigest()
