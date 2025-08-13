# app/models/pdf_models.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class PDFMetadata(BaseModel):
    """Métadonnées extraites du PDF."""
    title: Optional[str] = Field(None, description="Titre du document")
    page_count: int = Field(description="Nombre de pages")
    is_color: Optional[bool] = Field(None, description="True si le document contient de la couleur, False si noir et blanc, None si indéterminable")
    has_editorial: Optional[bool] = Field(None, description="True si un éditorial est détecté, False sinon, None si indéterminable")
    has_summary: Optional[bool] = Field(None, description="True si un sommaire est détecté, False sinon, None si indéterminable")
    language: Optional[str] = Field(None, description="Langue détectée (code ISO: fr, en, nl, de, etc.)")
    is_text_extractable: bool = Field(description="True si le texte peut être extrait (PDF textuel), False si le PDF est uniquement composé d'images")
    extraction_note: Optional[str] = Field(None, description="Notes sur l'extraction des métadonnées")

class PDFUploadResponse(BaseModel):
    """Réponse de l'upload PDF."""
    success: bool
    message: str
    original_filename: Optional[str] = None
    stored_filename: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    sha256: Optional[str] = None
    metadata: Optional[PDFMetadata] = None
    upload_time: datetime = Field(default_factory=datetime.utcnow)

class PDFUploadError(BaseModel):
    """Erreur lors de l'upload PDF."""
    success: bool = False
    error: str
    error_code: str