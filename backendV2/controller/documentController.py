from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile

from backendV2.service.documentService import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])

@router.get("/{doc_id}")
async def get_document(doc_id: UUID, service: DocumentService = Depends()):
    return await service.get_document(doc_id)

@router.post("/")
async def process_document(file: UploadFile, service: DocumentService = Depends()):
    return await service.process_document(file)