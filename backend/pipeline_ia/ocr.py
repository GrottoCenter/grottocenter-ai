import pytesseract
import logging
from pathlib import Path
from PIL import Image

from pipeline_ia.config import settings
from pipeline_ia.models import PageOCRResult

logger = logging.getLogger(__name__)

# Configuration Tesseract
pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd


def ocr_single_page(image_path: Path, lang: str = None) -> PageOCRResult:
    """
    Effectue l'OCR sur une seule page.

    Returns:
        PageOCRResult avec le texte et le score de confiance.
    """
    lang = lang or settings.tesseract_lang

    try:
        img = Image.open(str(image_path))

        # Extraction du texte
        text = pytesseract.image_to_string(
            img,
            lang=lang,
            config="--oem 3 --psm 3",  # LSTM engine, auto page segmentation
        )

        # Score de confiance moyen
        data = pytesseract.image_to_data(
            img,
            lang=lang,
            config="--oem 3 --psm 3",
            output_type=pytesseract.Output.DICT,
        )

        confidences = [
            int(c) for c in data["conf"]
            if str(c).isdigit() and int(c) > 0
        ]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        # Extraire le numéro de page depuis le nom de fichier
        page_num = 1
        name = image_path.stem
        for part in name.split("_"):
            if part.isdigit():
                page_num = int(part)
                break

        return PageOCRResult(
            page_number=page_num,
            text=text.strip(),
            confidence=avg_confidence / 100.0,
        )

    except Exception as e:
        logger.error(f"Erreur OCR sur {image_path.name}: {e}")
        return PageOCRResult(
            page_number=1,
            text="",
            confidence=0.0,
        )


def ocr_all_pages(
    image_paths: list[Path],
    lang: str = None,
    on_progress: callable = None,
) -> list[PageOCRResult]:
    """
    Effectue l'OCR sur toutes les pages.

    Returns:
        Liste de PageOCRResult triée par numéro de page.
    """
    results = []

    for i, img_path in enumerate(image_paths):
        logger.debug(f"OCR page {i + 1}/{len(image_paths)}: {img_path.name}")
        result = ocr_single_page(img_path, lang)
        result.page_number = i + 1  # Forcer la numérotation séquentielle
        results.append(result)

        if on_progress:
            on_progress(i + 1, len(image_paths))

    results.sort(key=lambda r: r.page_number)

    # Stats
    total_chars = sum(len(r.text) for r in results)
    avg_conf = sum(r.confidence for r in results) / len(results) if results else 0
    logger.info(
        f"OCR terminé: {len(results)} pages, "
        f"{total_chars} caractères, "
        f"confiance moyenne: {avg_conf:.2f}"
    )

    return results


def merge_ocr_results(results: list[PageOCRResult]) -> str:
    """Fusionne tous les résultats OCR en un seul texte."""
    parts = []
    for r in results:
        if r.text:
            parts.append(f"--- PAGE {r.page_number} ---\n{r.text}")
    return "\n\n".join(parts)