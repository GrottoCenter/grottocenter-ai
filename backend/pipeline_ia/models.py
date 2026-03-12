from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime


class JobStatus(str, Enum):
    QUEUED = "queued"
    PREPROCESSING = "preprocessing"
    OCR = "ocr"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"


class Article(BaseModel):
    title: str = Field(description="Titre de l'article ou de la section")
    authors: list[str] = Field(default_factory=list)
    summary: str = Field(default="")
    page_start: Optional[int] = None
    page_end: Optional[int] = None


class DocumentMetadata(BaseModel):
    title: Optional[str] = None
    authors: Optional[list[str]] = None
    language: Optional[str] = None
    year: Optional[int] = None


class DocumentAnalysis(BaseModel):
    title: str = Field(default="Unknown")
    authors: list[str] = Field(default_factory=list)
    summary: str = Field(default="")
    language: str = Field(default="unknown")
    iso_code: str = Field(default="unknown")
    year: Optional[int] = None
    keywords: list[str] = Field(default_factory=list)
    document_type: str = Field(default="unknown")
    articles: list[Article] = Field(default_factory=list)
    caves_mentioned: list[str] = Field(default_factory=list)
    regions_mentioned: list[str] = Field(default_factory=list)
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)


class PageOCRResult(BaseModel):
    page_number: int
    text: str
    confidence: float = 0.0


class JobRequest(BaseModel):
    pdf_filename: str
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)


class JobResult(BaseModel):
    job_id: str
    status: JobStatus
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    message: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    ocr_text: Optional[str] = None
    analysis: Optional[DocumentAnalysis] = None
    error: Optional[str] = None