import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ..schemas.pdf_schema import PDFUploadResponse
from ..services.pdf_service import PDFService
from ..utils.exceptions import PDFException

router = APIRouter(prefix="/pdf", tags=["PDF"])

def get_pdf_service() -> PDFService:
    """Dependency injection pour PDFService"""
    upload_dir = os.getenv("UPLOAD_DIR", "./uploads")
    max_size_mb = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
    return PDFService(upload_dir=upload_dir, max_size_mb=max_size_mb)

@router.post("/upload", response_model=PDFUploadResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    pdf_service: PDFService = Depends(get_pdf_service)
):
    """
    Upload d'un fichier PDF
    
    - **file**: Fichier PDF à uploader (max 50MB)
    
    Returns:
        PDFUploadResponse avec les détails du fichier uploadé
    """
    try:
        filename, file_size = pdf_service.save_pdf(file)
        
        return PDFUploadResponse(
            success=True,
            message="PDF uploadé avec succès",
            filename=filename,
            file_size=file_size
        )
        
    except PDFException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur interne du serveur: {str(e)}"
        )

@router.get("/health")
async def health_check():
    """Health check pour l'API PDF"""
    return {"status": "ok", "service": "pdf"}
