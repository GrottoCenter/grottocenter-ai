from fastapi import APIRouter, Depends, HTTPException

from backend.client.base_client import get_client_async
from backend.schemas.document_schemas import (
    DocumentUpdateRequest,
    InheritanceRequest,
    InheritanceResult,
)
from backend.services.document_service import DocumentService

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
    

@router.get("/{doc_id}/children")
async def get_document_children(doc_id: int, service: DocumentService = Depends(get_document_service)):
    """Récupérer les enfants directs d'un document"""
    try:
        return await service.get_document_children(doc_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{doc_id}/descendants")
async def get_document_descendants(doc_id: int, service: DocumentService = Depends(get_document_service)):
    """Récupérer tous les descendants (enfants + petits-enfants) d'un document"""
    try:
        descendants = await service.get_document_descendants(doc_id)
        return {"documents": descendants, "total": len(descendants)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{doc_id}/apply-inheritance", response_model=InheritanceResult)
async def apply_inheritance(
    doc_id: int,
    request: InheritanceRequest,
    service: DocumentService = Depends(get_document_service)
):
    """Appliquer l'héritage des champs sélectionnés sur les enfants"""
    try:
        # Récupérer le document parent
        parent_doc = await service.get_document(doc_id)
        
        # Appliquer l'héritage
        results = await service.apply_inheritance(
            parent_doc, 
            request.child_ids, 
            request.heritable_fields
        )
        
        return results
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
