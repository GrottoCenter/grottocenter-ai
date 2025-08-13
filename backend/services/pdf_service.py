# app/services/pdf_service.py
import hashlib
import os
import re
import uuid
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List

import fitz  # PyMuPDF
# Optional MIME sniffing:
try:
    import magic  # python-magic
except ImportError:
    magic = None

from fastapi import UploadFile

from ..utils.exceptions import FileSizeException, InvalidFileTypeException, PDFReadException

PDF_EXT = ".pdf"

def _sanitize_filename(name: str) -> str:
    name = re.sub(r"[^\w\-. ]", "_", name)
    return name.strip().replace(" ", "_")[:150]  # avoid extreme lengths

class PDFService:
    """Service for PDF upload & metadata extraction."""

    def __init__(self, upload_dir: str = "./uploads", max_size_mb: int = 50):
        self.upload_dir = Path(upload_dir)
        self.max_size_mb = max_size_mb
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def save_pdf_streaming(self, file: UploadFile) -> Tuple[str, int, str, Optional[str]]:
        """
        Save file to disk streaming, enforcing size budget and returning:
        (stored_filename, size_bytes, sha256_hex, mime_type)
        """
        original_name = file.filename or "file.pdf"
        if not original_name.lower().endswith(PDF_EXT):
            raise InvalidFileTypeException("File extension must be .pdf")

        # Stable stored filename
        stored_filename = f"{uuid.uuid4().hex}_{_sanitize_filename(original_name)}"
        stored_path = self.upload_dir / stored_filename

        sha256 = hashlib.sha256()
        total = 0

        with stored_path.open("wb") as out:
            while True:
                chunk = file.file.read(1024 * 1024)  # 1MB
                if not chunk:
                    break
                total += len(chunk)
                if total > self.max_size_bytes:
                    try:
                        stored_path.unlink(missing_ok=True)
                    finally:
                        pass
                    raise FileSizeException(self.max_size_mb)
                sha256.update(chunk)
                out.write(chunk)

        mime_type = None
        if magic:
            try:
                mime_type = magic.from_file(str(stored_path), mime=True)
            except Exception:
                pass

        # Basic PDF signature fallback if python-magic not available
        if not mime_type and not self._looks_like_pdf(stored_path):
            try:
                stored_path.unlink(missing_ok=True)
            finally:
                pass
            raise InvalidFileTypeException("Not a valid PDF file (signature check failed).")

        return stored_filename, total, sha256.hexdigest(), mime_type

    def _looks_like_pdf(self, path: Path) -> bool:
        try:
            with path.open("rb") as f:
                sig = f.read(5)
            return sig == b"%PDF-"
        except Exception:
            return False

    def extract_metadata(self, path: Path) -> Dict[str, Any]:
        """Return structured metadata using PyMuPDF with enhanced title/summary extraction."""
        try:
            doc = fitz.open(path)  # raises if corrupted
        except Exception as e:
            raise PDFReadException(str(e))

        try:
            meta = doc.metadata or {}
            encrypted = doc.is_encrypted
            page_count = doc.page_count

            # Normalize keywords
            raw_keywords = meta.get("keywords") or meta.get("Keywords")
            keywords: Optional[List[str]] = None
            if isinstance(raw_keywords, str):
                parts = [k.strip() for k in re.split(r"[;,]", raw_keywords) if k.strip()]
                keywords = parts or None

            # Extract title with fallbacks
            title = meta.get("title") or meta.get("Title")
            if not title:
                title = self._extract_title_from_content(doc)

            # Extract summary/subject with fallbacks
            subject = meta.get("subject") or meta.get("Subject")
            if not subject:
                subject = self._extract_summary_from_content(doc)

            result = {
                "title": title,
                "author": meta.get("author") or meta.get("Author"),
                "subject": subject,
                "keywords": keywords,
                "creator": meta.get("creator") or meta.get("Creator"),
                "producer": meta.get("producer") or meta.get("Producer"),
                "creation_date": meta.get("creationDate") or meta.get("CreationDate"),
                "modification_date": meta.get("modDate") or meta.get("ModDate"),
                "encrypted": bool(encrypted),
                "page_count": page_count,
            }
            return result
        finally:
            try:
                doc.close()
            except Exception:
                pass

    def _extract_title_from_content(self, doc) -> Optional[str]:
        """Extract title from PDF content using various heuristics."""
        if doc.page_count == 0:
            return None
        
        first_page = doc[0]
        
        # Method 1: Look for large text blocks (likely titles)
        blocks = first_page.get_text("dict")["blocks"]
        title_candidates = []
        
        for block in blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    text = span["text"].strip()
                    font_size = span.get("size", 0)
                    
                    # Consider text with larger font size as title candidates
                    if font_size > 14 and len(text) > 5 and len(text) < 100:
                        title_candidates.append((text, font_size))
        
        # Sort by font size and return the largest
        if title_candidates:
            title_candidates.sort(key=lambda x: x[1], reverse=True)
            return title_candidates[0][0]
        
        # Method 2: Fallback to first meaningful line
        text_lines = first_page.get_text().split('\n')
        for line in text_lines:
            line = line.strip()
            if len(line) > 5 and not line.isdigit():
                # Skip common headers like page numbers, dates
                if not re.match(r'^\d+$|^page \d+|^\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}$', line.lower()):
                    return line
        
        return None

    def _extract_summary_from_content(self, doc) -> Optional[str]:
        """Extract a summary from PDF content."""
        if doc.page_count == 0:
            return None
        
        # Extract text from first page
        first_page_text = doc[0].get_text()
        
        # Clean and split into paragraphs
        paragraphs = [p.strip() for p in first_page_text.split('\n\n') if p.strip()]
        
        # Look for abstract, summary, or introduction sections
        for i, paragraph in enumerate(paragraphs):
            lower_para = paragraph.lower()
            if any(keyword in lower_para for keyword in ['abstract', 'summary', 'résumé', 'introduction']):
                # Return the next paragraph if this is just a header
                if len(paragraph) < 50 and i + 1 < len(paragraphs):
                    return paragraphs[i + 1][:500] + "..." if len(paragraphs[i + 1]) > 500 else paragraphs[i + 1]
                else:
                    return paragraph[:500] + "..." if len(paragraph) > 500 else paragraph
        
        # Fallback: return first substantial paragraph
        for paragraph in paragraphs:
            if len(paragraph) > 100:  # Substantial content
                return paragraph[:500] + "..." if len(paragraph) > 500 else paragraph
        
        return None
