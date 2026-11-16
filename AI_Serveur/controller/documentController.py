import logging

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from auth import verify_token
from config.settings import UsageLimits
from errors import INTERNAL_ERROR_MESSAGE, InvalidDocumentError, UpstreamError
from repository.mongo import MongoRepository
from service.documentLlmAnalyzeService import LLMAnalyzerService
from service.documentService import DocumentService
from service.usageService import UsageService

logger = logging.getLogger(__name__)

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
        locks=state.analysis_locks,
    )

@router.post("/analyze")
async def process_document(
    file: UploadFile,
    caller: dict = Depends(verify_token),
    service: DocumentService = Depends(get_document_service),
):
    # `caller` holds the verified SSO claims; `sub` is the Grottocenter user id.
    try:
        return await service.process_document(file, caller_id=caller["sub"])
    except (StarletteHTTPException, InvalidDocumentError, UpstreamError):
        raise  # already an accurate answer: the status is part of the error
    except Exception as error:
        # Anything else is a bug or an outage this server did not plan for. The caller gets
        # a generic 500; the cause and its traceback stay in the log. Answering from here,
        # inside the CORS middleware, is what lets the front read the 500.
        logger.exception("Analysis failed unexpectedly caller=%s", caller["sub"])
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR_MESSAGE) from error
