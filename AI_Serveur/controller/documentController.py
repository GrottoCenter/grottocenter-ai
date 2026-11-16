from fastapi import APIRouter, Depends, Request, UploadFile

from auth import verify_token
from config.settings import UsageLimits
from repository.mongo import MongoRepository
from service.documentLlmAnalyzeService import LLMAnalyzerService
from service.documentService import DocumentService
from service.usageService import UsageService

router = APIRouter(prefix="/documents", tags=["documents"], dependencies=[Depends(verify_token)])

def get_document_service(request: Request) -> DocumentService:
    state = request.app.state
    limits = UsageLimits.from_config(state.config)
    analyzer_service = LLMAnalyzerService(state.greenpt_client)
    return DocumentService(
        analyzer_service,
        MongoRepository(state.mongo_db),
        usage=UsageService(state.mongo_db, limits, state.concurrency),
        limits=limits,
    )

@router.post("/analyze")
async def process_document(
    file: UploadFile,
    caller: dict = Depends(verify_token),
    service: DocumentService = Depends(get_document_service),
):
    # `caller` holds the verified SSO claims; `sub` is the Grottocenter user id.
    return await service.process_document(file, caller_id=caller["sub"])
