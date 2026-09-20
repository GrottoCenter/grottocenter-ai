import os
import shutil

import fitz
import logging
from fastapi import UploadFile
from service.documentLlmAnalyzeService import LLMAnalyzerService

import time
from uuid import UUID

logger = logging.getLogger(__name__)

class DocumentService:

    def __init__(self, analyzer_service: LLMAnalyzerService):
        self.analyzer_service = analyzer_service
    
    
    async def process_document(self, file: UploadFile) -> dict:
        unique_filename = str(UUID(int=time.time_ns())) + ".pdf"
        
        file_content = await file.read()

        pdf = fitz.open(stream=file_content, filetype="pdf")
        document_text = "\n\n".join(
            f"--- Page {page_number} ---\n{page.get_text()}"
            for page_number, page in enumerate(pdf, start=1)
            if page.get_text().strip()
        )
        pdf.close()

        if len(document_text) < 1000:
            logger.info("Using OCR for document file %s", unique_filename)
            document_text += await self.analyzer_service.get_text_with_OCR(file)

        if not document_text.strip():
            raise ValueError("No text could be extracted from the PDF")

        document_analysis = await self.analyzer_service.analyze_document(document_text)
        
        return {
            "message": "success", 
            "filename": unique_filename,
            "document_analysis": document_analysis
        }