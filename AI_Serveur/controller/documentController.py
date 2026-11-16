from fastapi import APIRouter, Depends, Request, UploadFile

from auth import verify_token
from repository.mongo import MongoRepository
from service.documentLlmAnalyzeService import LLMAnalyzerService
from service.documentService import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"], dependencies=[Depends(verify_token)])

def get_document_service(request: Request) -> DocumentService:
    analyzer_service = LLMAnalyzerService(request.app.state.greenpt_client)
    return DocumentService(analyzer_service, MongoRepository(request.app.state.mongo_db))

@router.post("/analyze")
async def process_document(
    file: UploadFile,
    caller: dict = Depends(verify_token),
    service: DocumentService = Depends(get_document_service),
):
    # `caller` holds the verified SSO claims; `sub` is the Grottocenter user id.
    return await service.process_document(file, caller_id=caller["sub"])
