# app/routes/pdf_routes.py
import os
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from ..schemas.pdf_schema import PDFUploadResponse, PDFMetadata
from ..services.pdf_service import PDFService
from ..utils.exceptions import PDFException

router = APIRouter(prefix="/pdf", tags=["PDF"])

def get_pdf_service() -> PDFService:
    upload_dir = os.getenv("UPLOAD_DIR", "./uploads")
    max_size_mb = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
    return PDFService(upload_dir=upload_dir, max_size_mb=max_size_mb)

@router.post("/upload", response_model=PDFUploadResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    pdf_service: PDFService = Depends(get_pdf_service),
):
    """
    Upload a PDF, persist to storage, and extract metadata with PyMuPDF.
    """
    try:
        stored_filename, size_bytes, sha256_hex, mime_type = pdf_service.save_pdf_streaming(file)
        metadata_dict = pdf_service.extract_metadata(pdf_service.upload_dir / stored_filename)

        return PDFUploadResponse(
            success=True,
            message="PDF uploaded & analyzed successfully",
            original_filename=file.filename,
            stored_filename=stored_filename,
            file_size=size_bytes,
            mime_type=mime_type,
            sha256=sha256_hex,
            metadata=PDFMetadata(**metadata_dict),
        )
    except PDFException as e:
        # bubbled exceptions with proper status
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")

@router.get("/health")
async def health_check():
    return {"status": "ok", "service": "pdf"}
