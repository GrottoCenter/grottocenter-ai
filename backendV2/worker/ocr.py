from __future__ import annotations

import io
import re
from pathlib import Path
from typing import BinaryIO, Union

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

from langdetect import detect, LangDetectException

PdfInput = Union[str, Path, bytes, bytearray, BinaryIO]

TESSERACT_LANG_MAP = {
    "fr": "fra",
    "en": "eng",
    "es": "spa",
    "de": "deu",
    "it": "ita",
    "pt": "por",
    "ru": "rus",
    "nl": "nld",
    "pl": "pol",
}


def detect_language_from_image(img: Image.Image) -> str:
    """Fait un OCR rapide en anglais pour déterminer la vraie langue."""
    try:
        # OCR rapide sans prêter attention aux accents
        raw_text = pytesseract.image_to_string(img, lang="eng")
        
        if len(raw_text.strip()) > 20:
            detected_code = detect(raw_text)
            return TESSERACT_LANG_MAP.get(detected_code, "eng") # Fallback sur anglais
    except LangDetectException:
        pass
    
    return "eng" # Langue par défaut si échec


def extract_pdf_text_for_llm(pdf_input: PdfInput, ocr_fallback: bool = True) -> str:
    """
    Extrait le texte d'un PDF et le normalise pour un traitement LLM.
    Utilise l'OCR (Tesseract) si une page ne contient pas de texte natif.

    - Accepte un chemin de fichier, des bytes, ou un flux binaire.
    - `ocr_fallback`: Si True, tente de lire le texte via OCR si la page semble être une image scannée.
    - Retourne un texte concaténé avec séparateurs de pages.
    """
    if isinstance(pdf_input, (str, Path)):
        doc = fitz.open(str(pdf_input))
    elif isinstance(pdf_input, (bytes, bytearray)):
        doc = fitz.open(stream=bytes(pdf_input), filetype="pdf")
    else:
        raise TypeError("pdf_input non valide.")
    
    pages_text: list[str] = []
    detected_lang = None 
    
    try:
        for page_index, page in enumerate(doc, start=1):
            page_text = page.get_text("text") or ""
            
            if ocr_fallback and len(page_text.strip()) < 50:
                mat = fitz.Matrix(2.0, 2.0)
                pix = page.get_pixmap(matrix=mat)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                
                # S'il y a du texte natif sur d'autres pages, on devine la langue depuis ce texte
                if not detected_lang and len(" ".join(pages_text)) > 50:
                    try:
                        lang_code = detect(" ".join(pages_text))
                        detected_lang = TESSERACT_LANG_MAP.get(lang_code, "eng")
                    except:
                        pass

                if not detected_lang:
                    detected_lang = detect_language_from_image(img)
                
                # OCR final avec la bonne langue
                page_text = pytesseract.image_to_string(img, lang=detected_lang)

            page_text = page_text.replace("\x00", "")
            page_text = re.sub(r"[ \t]+", " ", page_text)
            page_text = re.sub(r"\n{3,}", "\n\n", page_text).strip()

            if page_text:
                pages_text.append(f"--- PAGE {page_index} ---\n{page_text}")
    finally:
        doc.close()

    return "\n\n".join(pages_text).strip()