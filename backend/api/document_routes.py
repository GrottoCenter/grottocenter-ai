from fastapi import APIRouter, Depends, HTTPException
from backend.services.document_service import DocumentService
from backend.schemas.document_schemas import DocumentUpdateRequest
from backend.client.base_client import get_client_async

router = APIRouter(prefix="/documents", tags=["documents"])

async def get_document_service() -> DocumentService:
    client = await get_client_async()
    return DocumentService(client)

@router.get("/{doc_id}")
async def get_document(doc_id: int, service: DocumentService = Depends(get_document_service)):
    return await service.get_document(doc_id)

@router.put("/{doc_id}")
async def update_document(doc_id: int, update: DocumentUpdateRequest, service: DocumentService = Depends(get_document_service)):
    try:
        return await service.update_document(doc_id, update)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/{doc_id}/validate")
async def validate_document(doc_id: int, service: DocumentService = Depends(get_document_service)):
    return await service.validate_document(doc_id)

@router.put("/{doc_id}/update-and-validate")
async def update_and_validate_document(
    doc_id: int,
    update: DocumentUpdateRequest,
    service: DocumentService = Depends(get_document_service)
):
    update_result = await service.update_document(doc_id, update)
    validation_result = await service.validate_document(doc_id, comment="Mise à jour via interface FastAPI")
    return {
        "update": update_result,
        "validation": validation_result
    }