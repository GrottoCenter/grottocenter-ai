from fastapi import APIRouter, Depends

from backendV2.service.documentService import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])

@router.get("/{doc_id}")
async def get_document(doc_id: int, service: DocumentService = Depends()):
    return await service.get_document(doc_id)