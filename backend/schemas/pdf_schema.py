from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

class PDFMetadata(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    keywords: Optional[List[str]] = None
    creator: Optional[str] = None
    producer: Optional[str] = None
    creation_date: Optional[str] = None
    modification_date: Optional[str] = None
    encrypted: bool = False
    page_count: int

class PDFUploadResponse(BaseModel):
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
    success: bool = False
    error: str
    error_code: str