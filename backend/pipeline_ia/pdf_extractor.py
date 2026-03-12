import fitz  # PyMuPDF
import logging
from pathlib import Path
from PIL import Image
import io

from pipeline_ia.config import settings

logger = logging.getLogger(__name__)


def pdf_has_extractable_text(pdf_path: Path, sample_pages: int = 5) -> bool:
    """Vérifie si le PDF contient du texte extractible (non scanné)."""
    doc = fitz.open(str(pdf_path))
    text_pages = 0
    pages_to_check = min(sample_pages, len(doc))

    for i in range(pages_to_check):
        text = doc[i].get_text("text").strip()
        if len(text) > 50:  # Plus de 50 caractères = probablement du vrai texte
            text_pages += 1

    doc.close()
    ratio = text_pages / pages_to_check if pages_to_check > 0 else 0
    logger.info(f"Ratio de pages avec texte extractible: {ratio:.2f}")
    return ratio > 0.5


def extract_text_direct(pdf_path: Path) -> list[dict]:
    """Extraction directe du texte (PDF non scanné)."""
    doc = fitz.open(str(pdf_path))
    pages = []
    for i in range(min(len(doc), settings.max_pages_per_document)):
        text = doc[i].get_text("text").strip()
        pages.append({"page_number": i + 1, "text": text, "confidence": 1.0})
    doc.close()
    return pages


def pdf_to_images(pdf_path: Path, output_dir: Path, dpi: int = 300) -> list[Path]:
    """Convertit chaque page du PDF en image PNG."""
    output_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf_path))
    image_paths = []

    total_pages = min(len(doc), settings.max_pages_per_document)
    zoom = dpi / 72  # 72 DPI est la résolution par défaut de PDF
    matrix = fitz.Matrix(zoom, zoom)

    for i in range(total_pages):
        page = doc[i]
        pix = page.get_pixmap(matrix=matrix)

        # Convertir en PIL Image
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))

        # Sauvegarder
        img_path = output_dir / f"page_{i + 1:04d}.png"
        img.save(str(img_path), "PNG")
        image_paths.append(img_path)

        logger.debug(f"Page {i + 1}/{total_pages} convertie en image ({img.size})")

    doc.close()
    logger.info(f"{len(image_paths)} pages converties en images (DPI: {dpi})")
    return image_paths


def get_pdf_metadata(pdf_path: Path) -> dict:
    """Extrait les métadonnées embarquées du PDF."""
    doc = fitz.open(str(pdf_path))
    metadata = doc.metadata or {}
    metadata["page_count"] = len(doc)
    doc.close()
    return metadata