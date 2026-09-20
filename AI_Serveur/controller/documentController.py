from uuid import UUID
from fastapi import APIRouter, Depends, Request, UploadFile
from service.documentLlmAnalyzeService import LLMAnalyzerService
from service.documentService import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])

def get_document_service(request: Request) -> DocumentService:
    analyzer_service = LLMAnalyzerService(request.app.state.greenpt_client)
    return DocumentService(analyzer_service)

@router.post("/analyze")
async def process_document(file: UploadFile, service: DocumentService = Depends(get_document_service)):
    return await service.process_document(file)