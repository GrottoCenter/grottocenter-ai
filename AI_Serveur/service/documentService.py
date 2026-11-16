import hashlib
import logging
import time
from datetime import datetime, timezone
from uuid import UUID

import fitz
from fastapi import UploadFile

from model.DocumentMetadata import DocumentAnalyseMetadata
from model.DocumentMetadata import DocumentMetadata as DocumentMetadataModel
from model.GrottocenterType import GrottocenterType
from model.MongoDocument import MongoDocument
from repository.mongo import MongoRepository
from service.documentLlmAnalyzeService import LLMAnalyzerService

logger = logging.getLogger(__name__)

class DocumentService:

    def __init__(self, analyzer_service: LLMAnalyzerService, mongo_repository: MongoRepository):
        self.analyzer_service = analyzer_service
        self.mongo_repository = mongo_repository

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
    
    
    async def process_document(self, file: UploadFile) -> dict:
        unique_filename = str(UUID(int=time.time_ns())) + ".pdf"

        file_content = await file.read()
        if file_content is None or len(file_content) == 0:
            raise ValueError("Uploaded file is empty")

        file_hash = self.get_file_hash(file_content)
        documents_existing = self.mongo_repository.get_with_hash(file_hash)
        if documents_existing:
            return {
                "message": "success",
                "filename": documents_existing[0].fileName,
                "document_metadata": [
                    document.metadata for document in documents_existing
                ],
            }

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

        self.mongo_repository.insert_many(documents_to_insert)

        logger.info("Processing document file %s", unique_filename)

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

        document_analysis = await self.analyzer_service.analyze_document(document_text)

        document_metadata = self.map_document_analysis_to_metadata(document_analysis)
        for metadata in document_metadata:
            metadata.formats = [content_type]
            if not metadata.pages:
                metadata.pages = str(page_count)

        return document_metadata


    @staticmethod
    def get_file_hash(file_content: bytes) -> str:
        return hashlib.sha256(file_content).hexdigest()
