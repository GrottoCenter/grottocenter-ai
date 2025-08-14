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

# ----------------------------
# Helpers
# ----------------------------

def _sanitize_filename(name: str) -> str:
    name = re.sub(r"[^\w\-. ]", "_", name)
    return name.strip().replace(" ", "_")[:150]  # avoid extreme lengths


# Mois FR/EN (formes longues + quelques abréviations courantes)
_MONTHS_FR = {
    "janvier": "Janvier", "janv": "Janvier", "jan": "Janvier",
    "février": "Février", "fevrier": "Février", "févr": "Février", "fevr": "Février", "feb": "Février",
    "mars": "Mars",
    "avril": "Avril", "avr": "Avril",
    "mai": "Mai",
    "juin": "Juin",
    "juillet": "Juillet", "juil": "Juillet",
    "août": "Août", "aout": "Août", "aoû": "Août",
    "septembre": "Septembre", "sept": "Septembre", "sep": "Septembre",
    "octobre": "Octobre", "oct": "Octobre",
    "novembre": "Novembre", "nov": "Novembre",
    "décembre": "Décembre", "decembre": "Décembre", "déc": "Décembre", "dec": "Décembre"
}

_MONTHS_EN = {
    "january": "January", "jan": "January",
    "february": "February", "feb": "February",
    "march": "March", "mar": "March",
    "april": "April", "apr": "April",
    "may": "May",
    "june": "June", "jun": "June",
    "july": "July", "jul": "July",
    "august": "August", "aug": "August",
    "september": "September", "sep": "September", "sept": "September",
    "october": "October", "oct": "October",
    "november": "November", "nov": "November",
    "december": "December", "dec": "December",
}

# Regex basiques pour numéro / année / mois
_RE_NUMBER = re.compile(r"(?:\b(?:n|no|nº|n°|num(?:éro)?)\s*[:\.]?\s*)(\d{1,4})", re.IGNORECASE)
_RE_YEAR = re.compile(r"\b(19\d{2}|20\d{2})\b")
# Cherche un token qui ressemble à un mois (FR ou EN) parmi nos dictionnaires
_RE_MONTH_TOKEN = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]{3,12}")

def _normalize_month_token(token: str) -> Optional[str]:
    t = token.strip().lower()
    if t in _MONTHS_FR:
        return _MONTHS_FR[t]
    if t in _MONTHS_EN:
        return _MONTHS_EN[t]
    return None


def _format_issue_title(collection: Optional[str], number: Optional[str],
                        month: Optional[str], year: Optional[str]) -> Optional[str]:
    """
    Assemble uniquement les éléments disponibles dans l'ordre demandé.
    → "NomCollection N°<numéro> Mois Année"
    """
    parts: List[str] = []
    if collection:
        parts.append(collection.strip())
    if number:
        parts.append(f"N°{number.strip()}")
    if month:
        # Mois : capitaliser première lettre si besoin (déjà passé par normalisation)
        month_fmt = month.strip()
        if month_fmt:
            parts.append(month_fmt)
    if year:
        parts.append(year.strip())
    if not parts:
        return None
    return " ".join(parts)


def _clean_collection_name(name: str) -> str:
    # Nettoyage simple pour la collection (éviter les traînards de ponctuation/espaces)
    name = re.sub(r"\s+", " ", name or "").strip(" -_.,")
    # Éviter de garder des occurrences de "N° xx", dates, url, etc.
    name = re.sub(_RE_NUMBER, "", name)
    name = re.sub(_RE_YEAR, "", name)
    name = re.sub(r"\bpage\s+\d+\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"^\W+|\W+$", "", name)
    return name.strip()


class PDFService:
    """Service for PDF upload & metadata extraction."""

    def __init__(self, upload_dir: str = "./uploads", max_size_mb: int = 50):
        self.upload_dir = Path(upload_dir)
        self.max_size_mb = max_size_mb
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    # ----------------------------
    # Upload
    # ----------------------------
    def save_pdf_streaming(self, file: UploadFile) -> Tuple[str, int, str, Optional[str]]:
        """
        Save file to disk streaming, enforcing size budget and returning:
        (stored_filename, size_bytes, sha256_hex, mime_type)
        """
        original_name = file.filename or "file.pdf"
        if not original_name.lower().endswith(PDF_EXT):
            raise InvalidFileTypeException("File extension must be .pdf")

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

    # ----------------------------
    # Public API
    # ----------------------------
    def extract_metadata(self, path: Path) -> Dict[str, Any]:
        """Return structured metadata with enhanced extraction."""
        try:
            doc = fitz.open(path)
        except Exception as e:
            raise PDFReadException(str(e))

        try:
            # Vérifier si le PDF contient du texte extractible
            is_text_extractable = self._check_text_extractable(doc)

            # Base du résultat
            page_count = doc.page_count
            result: Dict[str, Any] = {
                "title": None,
                "page_count": page_count,
                "is_color": None,
                "has_editorial": None,
                "has_summary": None,
                "language": None,
                "is_text_extractable": is_text_extractable,
                "extraction_note": None,
            }

            if not is_text_extractable:
                result["extraction_note"] = (
                    "PDF appears to be image-only (not OCR'd). Text extraction not possible."
                )
                # Même si non extractible, on peut tenter le titre via nom de fichier
                meta = doc.metadata or {}
                title_via_name = self._build_issue_title_from_metadata_or_filename(meta, path.name)
                result["title"] = title_via_name
                return result

            # ---------- Extraction "revue/collection" avec fusion des sources ----------
            meta = doc.metadata or {}

            # 1) Extraire les composants depuis les métadonnées/nom de fichier
            metadata_components = self._extract_components_from_metadata_or_filename(meta, path.name)

            # 2) Extraire les composants depuis la page de couverture
            cover_components = self._extract_components_from_cover(doc)

            # 3) Fusionner les composants (priorisant les plus fiables)
            merged_components = self._merge_components(metadata_components, cover_components)
            
            # 4) Formater le titre final
            issue_title = _format_issue_title(*merged_components)

            # 5) Si toujours rien : fallback ancien algo de titre
            if not issue_title:
                issue_title = self._extract_title_enhanced(doc, meta)

            # ---------- Autres flags légers (limiter le coût) ----------
            is_color = self._detect_color_content(doc)
            has_editorial = self._detect_editorial(doc)
            has_summary = self._detect_summary(doc)
            language = self._detect_language(doc)

            result.update(
                {
                    "title": issue_title,
                    "is_color": is_color,
                    "has_editorial": has_editorial,
                    "has_summary": has_summary,
                    "language": language,
                    "extraction_note": "Successfully extracted metadata from text content.",
                }
            )
            return result

        finally:
            try:
                doc.close()
            except Exception:
                pass

    # ----------------------------
    # Extractability
    # ----------------------------
    def _check_text_extractable(self, doc) -> bool:
        if doc.page_count == 0:
            return False
        pages_to_check = min(3, doc.page_count)
        for page_num in range(pages_to_check):
            page = doc[page_num]
            text = page.get_text().strip()
            if len(text) > 50:
                return True
        return False

    # ----------------------------
    # Issue Title Builders
    # ----------------------------
    def _build_issue_title_from_metadata_or_filename(self, meta: dict, filename: str) -> Optional[str]:
        """
        Essaie de parser NomCollection / numéro / mois / année depuis :
        1) meta['title']
        2) filename (sans extension)
        
        Gère spécialement les formats comme "Regards-94-Janvier2024.indd Janvier"
        """
        # 1) Métadonnées - essayer d'abord le titre PDF
        pdf_title = (meta.get("title") or meta.get("Title") or "").strip()
        if pdf_title and len(pdf_title) > 3:
            # Nettoyer les suffixes comme ".indd", "Janvier" répété, etc.
            cleaned_title = self._clean_metadata_title(pdf_title)
            c, n, m, y = self._parse_issue_components_from_text(cleaned_title)
            formatted = _format_issue_title(c, n, m, y)
            if formatted and self._has_meaningful_content(c, n, m, y):
                return formatted

        # 2) Nom de fichier (sans UUID prefix et extension)
        base = self._extract_original_filename(filename)
        if base:
            # Nettoyer et parser le nom de fichier
            base_clean = self._clean_filename_for_parsing(base)
            c, n, m, y = self._parse_issue_components_from_text(base_clean)
            formatted = _format_issue_title(c, n, m, y)
            if formatted and self._has_meaningful_content(c, n, m, y):
                return formatted
        
        return None

    def _extract_components_from_metadata_or_filename(self, meta: dict, filename: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        Extrait les composants (collection, number, month, year) depuis les métadonnées et le nom de fichier.
        """
        # 1) Métadonnées
        pdf_title = (meta.get("title") or meta.get("Title") or "").strip()
        if pdf_title and len(pdf_title) > 3:
            cleaned_title = self._clean_metadata_title(pdf_title)
            components = self._parse_issue_components_from_text(cleaned_title)
            if self._has_meaningful_content(*components):
                return components

        # 2) Nom de fichier 
        base = self._extract_original_filename(filename)
        if base:
            base_clean = self._clean_filename_for_parsing(base)
            components = self._parse_issue_components_from_text(base_clean)
            if self._has_meaningful_content(*components):
                return components
        
        return None, None, None, None

    def _extract_components_from_cover(self, doc) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        Extrait les composants (collection, number, month, year) depuis la page de couverture.
        """
        if doc.page_count == 0:
            return None, None, None, None
        
        page = doc[0]
        page_text = page.get_text()
        
        # Extraire les composants numériques/temporels du texte
        number = self._extract_number_enhanced(" " + page_text + " ")
        year = self._extract_year_enhanced(" " + page_text + " ") 
        month = self._extract_month_enhanced(" " + page_text + " ")
        
        # Pour la collection, essayer d'abord par font-size/position
        collection_name = self._extract_title_by_font_size(page)
        if not collection_name:
            collection_name = self._extract_title_by_position(page)
        
        # Nettoyer le nom de collection trouvé
        if collection_name:
            collection_name = _clean_collection_name(collection_name)
        
        # Si pas de collection trouvée par font/position, essayer l'extraction textuelle
        if not collection_name or len(collection_name) < 3:
            collection_name = self._extract_collection_enhanced(" " + page_text + " ", number, year, month)

        return (
            collection_name if collection_name and len(collection_name) >= 3 else None,
            number,
            month,
            year
        )

    def _merge_components(self, metadata_components: Tuple[Optional[str], Optional[str], Optional[str], Optional[str]], 
                         cover_components: Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        Fusionne les composants de deux sources en priorisant la meilleure information disponible.
        Stratégie :
        - Collection : prioriser métadonnées si présente, sinon couverture
        - Number : prioriser couverture (souvent plus visible), sinon métadonnées
        - Month : prioriser couverture, sinon métadonnées
        - Year : prioriser couverture, sinon métadonnées
        """
        meta_col, meta_num, meta_month, meta_year = metadata_components
        cover_col, cover_num, cover_month, cover_year = cover_components
        
        # Collection : métadonnées en premier (plus fiables pour le nom exact)
        final_collection = meta_col if meta_col else cover_col
        
        # Number : couverture en premier (plus visible sur la page)
        final_number = cover_num if cover_num else meta_num
        
        # Month : couverture en premier
        final_month = cover_month if cover_month else meta_month
        
        # Year : couverture en premier
        final_year = cover_year if cover_year else meta_year
        
        return final_collection, final_number, final_month, final_year

    def _clean_metadata_title(self, title: str) -> str:
        """
        Nettoie le titre des métadonnées en retirant les suffixes techniques.
        Ex: "Regards-94-Janvier2024.indd Janvier" -> "Regards-94-Janvier2024"
        """
        # Retirer les extensions techniques
        title = re.sub(r'\.(indd|ai|psd|eps|pdf)\b', '', title, flags=re.IGNORECASE)
        
        # Détecter si un mois est répété à la fin et le retirer
        words = title.split()
        if len(words) >= 2:
            last_word = words[-1]
            month_normalized = _normalize_month_token(last_word)
            if month_normalized:
                # Vérifier si ce mois apparaît déjà dans le reste du titre
                title_without_last = ' '.join(words[:-1])
                if month_normalized.lower() in title_without_last.lower() or last_word.lower() in title_without_last.lower():
                    title = title_without_last
        
        return title.strip()

    def _extract_original_filename(self, stored_filename: str) -> Optional[str]:
        """
        Extrait le nom de fichier original depuis le nom stocké avec UUID.
        Ex: "e2765b4e7bbd454db68880702960fd04_Regards-94.pdf" -> "Regards-94"
        """
        # Le format stocké est: {UUID}_{nom_original}.pdf
        if '_' in stored_filename:
            parts = stored_filename.split('_', 1)
            if len(parts) == 2:
                original_with_ext = parts[1]
                # Retirer l'extension
                if original_with_ext.lower().endswith(PDF_EXT):
                    return original_with_ext[:-len(PDF_EXT)]
                return original_with_ext
        return None

    def _clean_filename_for_parsing(self, filename: str) -> str:
        """
        Nettoie le nom de fichier pour améliorer le parsing.
        """
        # Remplacer les séparateurs par des espaces
        cleaned = re.sub(r'[_\-\.]+', ' ', filename)
        
        # Retirer les extensions techniques courantes
        cleaned = re.sub(r'\.(indd|ai|psd|eps|pdf)\b', '', cleaned, flags=re.IGNORECASE)
        
        # Normaliser les espaces
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned

    def _has_meaningful_content(self, collection: Optional[str], number: Optional[str], 
                               month: Optional[str], year: Optional[str]) -> bool:
        """
        Vérifie si au moins un élément significatif a été trouvé.
        """
        return any([
            collection and len(collection.strip()) >= 3,
            number,
            month, 
            year
        ])

    def _build_issue_title_from_cover(self, doc) -> Optional[str]:
        """
        Analyse la 1re page :
        - Collection = plus gros titre (font-size) "propre"  
        - Numéro / Mois / Année = utilise les méthodes améliorées
        """
        if doc.page_count == 0:
            return None
        page = doc[0]

        # Collection via plus gros titre
        collection_name = self._extract_title_by_font_size(page)
        if not collection_name:
            collection_name = self._extract_title_by_position(page)
        
        # Nettoyer le nom de collection trouvé
        if collection_name:
            collection_name = _clean_collection_name(collection_name)
        
        # Numéro / mois / année via méthodes améliorées
        page_text = page.get_text()
        number = self._extract_number_enhanced(" " + page_text + " ")
        year = self._extract_year_enhanced(" " + page_text + " ") 
        month = self._extract_month_enhanced(" " + page_text + " ")

        # Si aucun nom de collection trouvé par font-size/position, 
        # essayer d'en extraire un du texte général
        if not collection_name or len(collection_name) < 3:
            collection_name = self._extract_collection_enhanced(" " + page_text + " ", number, year, month)

        return _format_issue_title(
            collection_name if collection_name and len(collection_name) >= 3 else None,
            number,
            month,
            year,
        )

    # ----------------------------
    # Core parsers for components
    # ----------------------------
    def _parse_issue_components_from_text(self, text: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        Déduit (collection, number, month, year) depuis une chaîne libre.
        Améliore la gestion des formats comme "Regards-94-Janvier2024".
        """
        if not text:
            return None, None, None, None
        
        raw = " " + text.strip() + " "
        
        # Extraction des composants
        number = self._extract_number_enhanced(raw)
        year = self._extract_year_enhanced(raw)
        month = self._extract_month_enhanced(raw)
        
        # Collection : ce qui reste après avoir retiré les autres éléments
        collection = self._extract_collection_enhanced(raw, number, year, month)

        return collection, number, month, year

    def _extract_number_enhanced(self, text: str) -> Optional[str]:
        """
        Extraction améliorée du numéro, gère les formats comme "Regards-94" 
        """
        # Essayer d'abord le pattern classique "N° 94", "No 94", etc.
        m = _RE_NUMBER.search(text)
        if m:
            return m.group(1)
        
        # Chercher un nombre seul (pas une année) entre tirets ou en fin de mot
        # Ex: "Regards-94-Janvier" -> "94"
        pattern = r'[-\s](\d{1,3})[-\s]'
        matches = re.findall(pattern, text)
        for match in matches:
            num = int(match)
            # Éviter de confondre avec les années (typiquement > 1900)
            if 1 <= num <= 999:
                return match
        
        # Pattern en fin de segment
        pattern = r'[-\s](\d{1,3})\b'
        matches = re.findall(pattern, text)
        for match in matches:
            num = int(match)
            if 1 <= num <= 999:
                return match
        
        return None

    def _extract_year_enhanced(self, text: str) -> Optional[str]:
        """
        Extraction améliorée de l'année, gère les formats collés comme "Janvier2024"
        """
        # Pattern classique
        m = _RE_YEAR.search(text)
        if m:
            return m.group(1)
        
        # Chercher année collée après un mois
        # Ex: "Janvier2024" -> "2024"
        for token in re.findall(_RE_MONTH_TOKEN, text):
            if _normalize_month_token(token):
                # Chercher un nombre de 4 chiffres après ce token
                remaining = text[text.lower().find(token.lower()) + len(token):]
                year_match = re.search(r'^(\d{4})\b', remaining)
                if year_match:
                    year = int(year_match.group(1))
                    if 1900 <= year <= 2100:
                        return str(year)
        
        return None

    def _extract_month_enhanced(self, text: str) -> Optional[str]:
        """
        Extraction améliorée du mois.
        """
        # Parcourir tous les tokens de lettres pour trouver un mois
        for m in _RE_MONTH_TOKEN.finditer(text):
            candidate = m.group(0)
            month_fmt = _normalize_month_token(candidate)
            if month_fmt:
                return month_fmt
        return None

    def _extract_collection_enhanced(self, text: str, number: Optional[str], 
                                    year: Optional[str], month: Optional[str]) -> Optional[str]:
        """
        Extrait le nom de la collection en retirant les autres éléments identifiés.
        """
        collection = text
        
        # Retirer le numéro (avec ses préfixes potentiels)
        if number:
            # Retirer "N° XX", "No XX", etc.
            collection = re.sub(rf'\b(?:n|no|nº|n°|num(?:éro)?)\s*[:\.]?\s*{re.escape(number)}\b', 
                               ' ', collection, flags=re.IGNORECASE)
            # Retirer le numéro seul avec ses séparateurs
            collection = re.sub(rf'[-\s]{re.escape(number)}[-\s]', ' ', collection)
            collection = re.sub(rf'[-\s]{re.escape(number)}\b', ' ', collection)
        
        # Retirer l'année (avec année collée au mois)
        if year:
            collection = re.sub(rf'\b{re.escape(year)}\b', ' ', collection)
        
        # Retirer le mois (avec ses variantes et année collée)
        if month:
            # Retirer le mois exact trouvé
            collection = re.sub(rf'\b{re.escape(month)}\b', ' ', collection, flags=re.IGNORECASE)
            
            # Si on a à la fois mois et année, retirer aussi les patterns "moisannée"
            if year:
                month_year_pattern = rf'\b\w+{re.escape(year)}\b'
                collection = re.sub(month_year_pattern, ' ', collection, flags=re.IGNORECASE)
        
        # Nettoyer et valider
        collection = _clean_collection_name(collection)
        
        if len(collection) < 3:
            return None
        
        return collection

    def _extract_number(self, text: str) -> Optional[str]:
        m = _RE_NUMBER.search(text or "")
        return m.group(1) if m else None

    def _extract_year(self, text: str) -> Optional[str]:
        m = _RE_YEAR.search(text or "")
        return m.group(1) if m else None

    def _extract_month(self, text: str) -> Optional[str]:
        if not text:
            return None
        for token in re.findall(_RE_MONTH_TOKEN, text):
            month_fmt = _normalize_month_token(token)
            if month_fmt:
                return month_fmt
        return None

    # ----------------------------
    # Legacy title heuristics (fallback)
    # ----------------------------
    def _extract_title_enhanced(self, doc, meta: dict) -> Optional[str]:
        """Fallback générique si aucun titre magazine n'a pu être construit."""
        if doc.page_count == 0:
            return None

        pdf_title = meta.get("title") or meta.get("Title")
        if pdf_title and len(pdf_title.strip()) > 3:
            return pdf_title.strip()

        first_page = doc[0]
        title = self._extract_title_by_font_size(first_page)
        if title:
            return title
        title = self._extract_title_by_position(first_page)
        if title:
            return title
        return self._extract_title_fallback(first_page)

    def _extract_title_by_font_size(self, page) -> Optional[str]:
        try:
            blocks = page.get_text("dict")["blocks"]
            title_candidates = []
            for block in blocks:
                if "lines" not in block:
                    continue
                for line in block["lines"]:
                    line_text = ""
                    max_font_size = 0
                    for span in line["spans"]:
                        text = span["text"].strip()
                        font_size = span.get("size", 0)
                        if text:
                            line_text += text + " "
                            max_font_size = max(max_font_size, font_size)
                    line_text = line_text.strip()
                    if (
                        max_font_size > 12
                        and 3 < len(line_text) < 200
                        and not re.match(r"^\d+$", line_text)
                        and not re.match(r"^page \d+", line_text.lower())
                        and not self._is_likely_noise(line_text)
                        and not self._is_likely_metadata_info(line_text)
                    ):
                        title_candidates.append((line_text, max_font_size))
            
            if title_candidates:
                title_candidates.sort(key=lambda x: x[1], reverse=True)
                
                # Essayer de combiner les lignes adjacentes si elles semblent faire partie du même titre
                combined_candidates = []
                
                for i, (candidate, font_size) in enumerate(title_candidates[:5]):
                    # Vérifier si ce candidat ressemble à un nom de collection
                    if self._looks_like_collection_name(candidate):
                        combined_candidates.append((candidate, font_size))
                        
                        # Essayer de combiner avec la ligne suivante si elle a une taille similaire
                        if i + 1 < len(title_candidates):
                            next_candidate, next_font_size = title_candidates[i + 1]
                            if (abs(font_size - next_font_size) <= 2 and 
                                len(candidate) + len(next_candidate) < 100):
                                combined_title = f"{candidate} {next_candidate}"
                                if self._looks_like_collection_name(combined_title):
                                    combined_candidates.append((combined_title, font_size))
                
                # Retourner le meilleur candidat
                if combined_candidates:
                    combined_candidates.sort(key=lambda x: (x[1], len(x[0].split())), reverse=True)
                    return combined_candidates[0][0]
                
                # Fallback : retourner le premier candidat valide
                for candidate, _ in title_candidates:
                    if self._looks_like_collection_name(candidate):
                        return candidate
                        
        except Exception:
            pass
        return None

    def _is_likely_metadata_info(self, text: str) -> bool:
        """Détecte les informations de métadonnées qui ne sont pas des titres de collection."""
        text_lower = text.lower()
        metadata_patterns = [
            r'traverse des muses',
            r'namur',
            r'@',
            r'asbl',
            r'pôle',
            r'contact',
            r'tél',
            r'www\.',
            r'\d{3}[\s\-]\d{3}[\s\-]\d{3}',  # numéros de téléphone
            r'[a-z]+@[a-z]+\.[a-z]+',  # emails
        ]
        
        for pattern in metadata_patterns:
            if re.search(pattern, text_lower):
                return True
        return False

    def _looks_like_collection_name(self, text: str) -> bool:
        """Vérifie si un texte ressemble à un nom de collection/magazine."""
        # Doit avoir au moins 3 caractères et pas plus de 50
        if len(text) < 3 or len(text) > 50:
            return False
        
        # Ne doit pas être uniquement des chiffres
        if text.isdigit():
            return False
            
        # Ne doit pas être du bruit
        if self._is_likely_noise(text) or self._is_likely_metadata_info(text):
            return False
        
        # Éviter les textes qui sont clairement des dates ou des numéros
        if re.match(r'^\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}$', text):
            return False
        
        # Favoriser les textes qui contiennent des lettres
        letter_count = sum(1 for c in text if c.isalpha())
        if letter_count < 2:
            return False
        
        return True

    def _extract_title_by_position(self, page) -> Optional[str]:
        try:
            text_lines = page.get_text().split("\n")
            for line in text_lines[:10]:
                line = line.strip()
                if (
                    5 < len(line) < 150
                    and not re.match(r"^\d+$", line)
                    and not re.match(r"^page \d+", line.lower())
                    and not self._is_likely_noise(line)
                ):
                    return line
        except Exception:
            pass
        return None

    def _extract_title_fallback(self, page) -> Optional[str]:
        try:
            text_lines = page.get_text().split("\n")
            for line in text_lines:
                line = line.strip()
                if (
                    len(line) > 5
                    and not line.isdigit()
                    and not re.match(r"^page \d+|^\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}$", line.lower())
                ):
                    return line
        except Exception:
            pass
        return None

    def _is_likely_noise(self, text: str) -> bool:
        text_lower = text.lower()
        noise_patterns = [
            r"^\d+$",
            r"^page \d+",
            r"^\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}$",
            r"^www\.",
            r"@",
            r"^\s*$",
            r"^[,.\-_\s]+$",
        ]
        for pattern in noise_patterns:
            if re.match(pattern, text_lower):
                return True
        special_chars = len(re.findall(r"[^\w\s]", text))
        if special_chars > len(text) * 0.3:
            return True
        return False

    # ----------------------------
    # Other detectors (kept, trimmed for efficiency)
    # ----------------------------
    def _detect_color_content(self, doc) -> bool:
        try:
            pages_to_check = min(5, doc.page_count)
            for page_num in range(pages_to_check):
                page = doc[page_num]
                image_list = page.get_images()
                for img in image_list:
                    try:
                        xref = img[0]
                        pix = fitz.Pixmap(doc, xref)
                        if pix.n > 2:  # RGB/CMYK
                            pix = None
                            return True
                        pix = None
                    except Exception:
                        continue
                drawings = page.get_drawings()
                for drawing in drawings:
                    if "fill" in drawing and drawing["fill"]:
                        fill_color = drawing["fill"]
                        if isinstance(fill_color, (list, tuple)) and len(fill_color) >= 3:
                            r, g, b = fill_color[:3]
                            if not (abs(r - g) < 0.1 and abs(g - b) < 0.1 and abs(r - b) < 0.1):
                                return True
        except Exception:
            pass
        return False

    def _detect_editorial(self, doc) -> bool:
        editorial_keywords = [
            "éditorial", "editorial", "édito", "edito",
            "mot du directeur", "mot de la rédaction",
            "avant-propos", "préface", "introduction",
        ]
        return self._search_keywords_in_document(doc, editorial_keywords)

    def _detect_summary(self, doc) -> bool:
        summary_keywords = [
            "sommaire", "table des matières", "contents",
            "index", "au sommaire", "dans ce numéro",
        ]
        return self._search_keywords_in_document(doc, summary_keywords)

    def _search_keywords_in_document(self, doc, keywords: List[str]) -> bool:
        try:
            pages_to_search = min(5, doc.page_count)
            for page_num in range(pages_to_search):
                page = doc[page_num]
                text = page.get_text().lower()
                for keyword in keywords:
                    if keyword.lower() in text:
                        return True
        except Exception:
            pass
        return False

    def _detect_language(self, doc) -> Optional[str]:
        try:
            sample_text = ""
            pages_to_check = min(3, doc.page_count)
            for page_num in range(pages_to_check):
                page = doc[page_num]
                sample_text += " " + page.get_text()
            if len(sample_text) < 100:
                return None
            sample_text = sample_text.lower()
            language_indicators = {
                "fr": ["le", "la", "les", "de", "du", "des", "et", "à", "un", "une", "dans", "pour", "sur", "avec", "par", "ce", "cette", "qui", "que", "est", "sont"],
                "en": ["the", "and", "of", "to", "in", "is", "are", "for", "with", "on", "by", "this", "that", "which", "what", "from"],
                "nl": ["de", "het", "en", "van", "in", "op", "voor", "met", "aan", "bij", "door", "dit", "dat", "een", "zijn", "is"],
                "de": ["der", "die", "das", "und", "von", "in", "zu", "für", "mit", "auf", "durch", "ist", "sind", "ein", "eine"],
            }
            language_scores = {}
            for lang, words in language_indicators.items():
                score = 0
                for word in words:
                    pattern = r"\b" + re.escape(word) + r"\b"
                    matches = len(re.findall(pattern, sample_text))
                    score += matches
                language_scores[lang] = score
            if not language_scores or max(language_scores.values()) == 0:
                return None
            detected_lang = max(language_scores, key=language_scores.get)
            if language_scores[detected_lang] < 5:
                return None
            return detected_lang
        except Exception:
            return None
