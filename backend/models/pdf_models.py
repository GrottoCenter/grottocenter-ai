from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class PDFUploadResponse(BaseModel):
    """Modèle de réponse pour l'upload PDF"""
    success: bool
    message: str
    filename: Optional[str] = None
    file_size: Optional[int] = None
    upload_time: datetime = Field(default_factory=datetime.now)

class PDFUploadError(BaseModel):
    """Modèle d'erreur pour l'upload PDF"""
    success: bool = False
    error: str
    error_code: str