import os
import shutil

import fitz
import logging
from fastapi import UploadFile
from repository.mongo import MongoRepository
from service.documentLlmAnalyzeService import LLMAnalyzerService

import hashlib
from pathlib import Path

from model.DocumentMetadata import DocumentMetadata as DocumentMetadataModel
from model.DocumentMetadata import DocumentAnalyseMetadata
from model.MongoDocument import MongoDocument

from model.GrottocenterType import GrottocenterType

import time
from uuid import UUID

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
                "publication_date": article.publication_date or analysis.publication_date,
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

        documents_existing = self.mongo_repository.get_with_hash(self.get_file_hash(file_content))
        if documents_existing:
            return {
                "message": "success",
                "filename": unique_filename,
                "document_metadata": documents_existing
            }
        
        document_metadata = await self.analyze(file_content, unique_filename, file)

        logger.info("Processing document file %s", unique_filename)

        return {
            "message": "success", 
            "filename": unique_filename,
            "document_metadata": document_metadata
        }

    

    async def analyze(self, unique_filename: str, file: UploadFile) -> dict:
        file_content = await file.read()

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
            document_text += await self.analyzer_service.get_text_with_OCR(file)

        if not document_text.strip():
            raise ValueError("No text could be extracted from the PDF")

        document_analysis = await self.analyzer_service.analyze_document(document_text)

        document_metadata = self.map_document_analysis_to_metadata(document_analysis)
        for metadata in document_metadata:
            metadata.formats = [file.content_type]
            if not metadata.pages:
                metadata.pages = str(page_count)

        return document_metadata


    def get_file_hash(file_content: bytes) -> str:
        return hashlib.sha256(file_content).hexdigest()