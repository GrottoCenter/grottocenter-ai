import cv2
import numpy as np
import logging
from pathlib import Path
from PIL import Image, ImageEnhance, ImageFilter

from pipeline_ia.config import settings

logger = logging.getLogger(__name__)


def load_image(image_path: Path) -> np.ndarray:
    """Charge une image avec OpenCV."""
    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(f"Impossible de charger l'image: {image_path}")
    return img


def to_grayscale(img: np.ndarray) -> np.ndarray:
    """Convertit en niveaux de gris."""
    if len(img.shape) == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img


def denoise(img: np.ndarray, strength: int = 10) -> np.ndarray:
    """Supprime le bruit de l'image."""
    if len(img.shape) == 2:
        return cv2.fastNlMeansDenoising(img, None, strength, 7, 21)
    return cv2.fastNlMeansDenoisingColored(img, None, strength, strength, 7, 21)


def deskew(img: np.ndarray) -> np.ndarray:
    """Corrige l'inclinaison du texte."""
    gray = to_grayscale(img) if len(img.shape) == 3 else img

    # Détection des coordonnées du texte
    coords = np.column_stack(np.where(gray < 128))
    if len(coords) < 100:
        return img  # Pas assez de pixels pour détecter l'angle

    # Calcul de l'angle via le rectangle minimum englobant
    angle = cv2.minAreaRect(coords)[-1]

    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    # Limiter la correction à des angles raisonnables
    if abs(angle) > 15:
        logger.warning(f"Angle de deskew trop grand ({angle:.1f}°), ignoré")
        return img

    if abs(angle) < 0.5:
        return img  # Pas de correction nécessaire

    (h, w) = img.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(
        img, matrix, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    logger.debug(f"Deskew appliqué: {angle:.2f}°")
    return rotated


def binarize(img: np.ndarray) -> np.ndarray:
    """Binarisation adaptative (texte noir sur fond blanc)."""
    gray = to_grayscale(img) if len(img.shape) == 3 else img
    return cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=31,
        C=11,
    )


def enhance_contrast(img: np.ndarray, factor: float = 1.5) -> np.ndarray:
    """Améliore le contraste via CLAHE."""
    gray = to_grayscale(img) if len(img.shape) == 3 else img
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def remove_borders(img: np.ndarray, margin_percent: float = 0.02) -> np.ndarray:
    """Supprime les bordures noires potentielles (scan)."""
    gray = to_grayscale(img) if len(img.shape) == 3 else img
    h, w = gray.shape[:2]

    margin_h = int(h * margin_percent)
    margin_w = int(w * margin_percent)

    # Vérifier si les bordures sont majoritairement noires
    top = np.mean(gray[:margin_h, :])
    bottom = np.mean(gray[-margin_h:, :])
    left = np.mean(gray[:, :margin_w])
    right = np.mean(gray[:, -margin_w:])

    y1 = margin_h if top < 50 else 0
    y2 = h - margin_h if bottom < 50 else h
    x1 = margin_w if left < 50 else 0
    x2 = w - margin_w if right < 50 else w

    if y1 > 0 or y2 < h or x1 > 0 or x2 < w:
        logger.debug(f"Bordures supprimées: [{y1}:{y2}, {x1}:{x2}]")
        return img[y1:y2, x1:x2]

    return img


def resize_for_ocr(img: np.ndarray, target_height: int = 3000) -> np.ndarray:
    """Redimensionne si l'image est trop petite pour un bon OCR."""
    h, w = img.shape[:2]
    if h >= target_height:
        return img

    scale = target_height / h
    new_w = int(w * scale)
    return cv2.resize(img, (new_w, target_height), interpolation=cv2.INTER_CUBIC)


def preprocess_image(image_path: Path, output_path: Path | None = None) -> Path:
    """
    Pipeline complète de pré-traitement d'une image avant OCR.

    Étapes:
    1. Chargement
    2. Suppression des bordures
    3. Niveaux de gris
    4. Amélioration du contraste
    5. Débruitage
    6. Correction de l'inclinaison
    7. Redimensionnement
    8. Binarisation

    Returns:
        Chemin vers l'image pré-traitée.
    """
    logger.debug(f"Pré-traitement de: {image_path.name}")

    # 1. Chargement
    img = load_image(image_path)

    # 2. Suppression des bordures
    img = remove_borders(img)

    # 3. Niveaux de gris
    img = to_grayscale(img)

    # 4. Amélioration du contraste
    if settings.preprocessing_contrast_enhance > 1.0:
        img = enhance_contrast(img, settings.preprocessing_contrast_enhance)

    # 5. Débruitage
    if settings.preprocessing_denoise:
        img = denoise(img)

    # 6. Correction inclinaison
    if settings.preprocessing_deskew:
        img = deskew(img)

    # 7. Redimensionnement
    img = resize_for_ocr(img)

    # 8. Binarisation
    if settings.preprocessing_binarize:
        img = binarize(img)

    # Sauvegarde
    if output_path is None:
        output_path = image_path.parent / f"preprocessed_{image_path.name}"

    cv2.imwrite(str(output_path), img)
    logger.debug(f"Image pré-traitée sauvegardée: {output_path.name}")

    return output_path


def preprocess_all_pages(
    image_paths: list[Path],
    output_dir: Path,
    on_progress: callable = None,
) -> list[Path]:
    """Pré-traite toutes les pages d'un document."""
    output_dir.mkdir(parents=True, exist_ok=True)
    preprocessed = []

    for i, img_path in enumerate(image_paths):
        try:
            out_path = output_dir / f"preprocessed_{img_path.name}"
            result = preprocess_image(img_path, out_path)
            preprocessed.append(result)
        except Exception as e:
            logger.error(f"Erreur pré-traitement page {i + 1}: {e}")
            # On garde l'image originale en fallback
            preprocessed.append(img_path)

        if on_progress:
            on_progress(i + 1, len(image_paths))

    logger.info(f"{len(preprocessed)} pages pré-traitées")
    return preprocessed