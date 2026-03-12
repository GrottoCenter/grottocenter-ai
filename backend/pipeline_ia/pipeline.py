import json
import shutil
import logging
from pathlib import Path
from datetime import datetime

from pipeline.celery_app import celery_app
from pipeline_ia.config import settings
from pipeline_ia.models import (
    DocumentMetadata,
    DocumentAnalysis,
    JobStatus,
    JobResult,
)
from pipeline_ia.pdf_extractor import (
    pdf_has_extractable_text,
    extract_text_direct,
    pdf_to_images,
    get_pdf_metadata,
)
from pipeline_ia.preprocessing import preprocess_all_pages
from pipeline_ia.ocr import ocr_all_pages, merge_ocr_results
from pipeline_ia.llm_analyzer import analyze_with_ollama

logger = logging.getLogger(__name__)


def update_task_state(task, status: JobStatus, progress: float, message: str = ""):
    """Met à jour l'état de la tâche Celery."""
    task.update_state(
        state=status.value.upper(),
        meta={
            "status": status.value,
            "progress": progress,
            "message": message,
        },
    )


@celery_app.task(bind=True, name="pipeline.process_document")
def process_document_task(
    self,
    pdf_filename: str,
    metadata_dict: dict = None,
) -> dict:
    """
    Tâche Celery principale : traite un document PDF complet.

    Étapes:
    1. Vérifier si le PDF a du texte extractible
    2. Si non: convertir en images → pré-traitement → OCR
    3. Si oui: extraction directe du texte
    4. Analyse via LLM local
    5. Sauvegarde du résultat

    Returns:
        Dictionnaire avec le résultat (sérialisable JSON).
    """
    job_id = self.request.id
    pdf_path = settings.upload_dir / pdf_filename
    work_dir = settings.temp_dir / job_id

    logger.info(f"[{job_id}] Début du traitement: {pdf_filename}")

    try:
        # Préparer le répertoire de travail
        work_dir.mkdir(parents=True, exist_ok=True)

        # Métadonnées fournies
        metadata = None
        if metadata_dict:
            metadata = DocumentMetadata(**metadata_dict)

        # Vérifier le fichier
        if not pdf_path.exists():
            raise FileNotFoundError(f"Fichier non trouvé: {pdf_path}")

        # === ÉTAPE 1: Détection du type de PDF ===
        update_task_state(self, JobStatus.PREPROCESSING, 0.05, "Analyse du PDF...")
        has_text = pdf_has_extractable_text(pdf_path)
        pdf_meta = get_pdf_metadata(pdf_path)

        if has_text:
            # === CHEMIN RAPIDE: Texte extractible directement ===
            logger.info(f"[{job_id}] PDF avec texte extractible, extraction directe")
            update_task_state(self, JobStatus.OCR, 0.2, "Extraction directe du texte...")

            pages_data = extract_text_direct(pdf_path)
            ocr_text = "\n\n".join(
                f"--- PAGE {p['page_number']} ---\n{p['text']}"
                for p in pages_data
                if p["text"]
            )

        else:
            # === CHEMIN OCR: PDF scanné ===
            logger.info(f"[{job_id}] PDF scanné détecté, lancement OCR")

            # Étape 2a: Conversion en images
            update_task_state(
                self, JobStatus.PREPROCESSING, 0.1,
                "Conversion PDF → images..."
            )
            images_dir = work_dir / "images"
            image_paths = pdf_to_images(pdf_path, images_dir, dpi=settings.ocr_dpi)

            # Étape 2b: Pré-traitement
            update_task_state(
                self, JobStatus.PREPROCESSING, 0.2,
                f"Pré-traitement de {len(image_paths)} pages..."
            )
            preprocessed_dir = work_dir / "preprocessed"

            def on_preprocess_progress(current, total):
                progress = 0.2 + (current / total) * 0.2
                update_task_state(
                    self, JobStatus.PREPROCESSING, progress,
                    f"Pré-traitement page {current}/{total}"
                )

            preprocessed = preprocess_all_pages(
                image_paths, preprocessed_dir, on_progress=on_preprocess_progress
            )

            # Étape 2c: OCR
            update_task_state(
                self, JobStatus.OCR, 0.4,
                f"OCR sur {len(preprocessed)} pages..."
            )

            def on_ocr_progress(current, total):
                progress = 0.4 + (current / total) * 0.3
                update_task_state(
                    self, JobStatus.OCR, progress,
                    f"OCR page {current}/{total}"
                )

            ocr_results = ocr_all_pages(
                preprocessed, on_progress=on_ocr_progress
            )
            ocr_text = merge_ocr_results(ocr_results)

        # === ÉTAPE 3: Analyse LLM ===
        update_task_state(
            self, JobStatus.ANALYZING, 0.75,
            "Analyse par le LLM local..."
        )

        analysis = analyze_with_ollama(ocr_text, metadata)

        # Enrichir avec les métadonnées PDF si nécessaire
        if analysis.title == "Unknown" and pdf_meta.get("title"):
            analysis.title = pdf_meta["title"]
        if not analysis.authors and pdf_meta.get("author"):
            analysis.authors = [pdf_meta["author"]]

        # === ÉTAPE 4: Sauvegarde ===
        update_task_state(
            self, JobStatus.COMPLETED, 1.0,
            "Analyse terminée"
        )

        result = JobResult(
            job_id=job_id,
            status=JobStatus.COMPLETED,
            progress=1.0,
            message="Analyse terminée avec succès",
            completed_at=datetime.now(),
            ocr_text=ocr_text[:10000] if ocr_text else None,  # Limiter la taille
            analysis=analysis,
        )

        # Sauvegarder le résultat en JSON
        result_path = settings.results_dir / f"{job_id}.json"
        result_path.write_text(
            result.model_dump_json(indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        logger.info(f"[{job_id}] Traitement terminé avec succès")
        return result.model_dump(mode="json")

    except Exception as e:
        logger.error(f"[{job_id}] Erreur: {e}", exc_info=True)

        error_result = JobResult(
            job_id=job_id,
            status=JobStatus.FAILED,
            progress=0.0,
            message=f"Erreur: {str(e)}",
            error=str(e),
        )
        return error_result.model_dump(mode="json")

    finally:
        # Nettoyage du répertoire temporaire
        if work_dir.exists():
            try:
                shutil.rmtree(work_dir)
                logger.debug(f"[{job_id}] Répertoire temporaire nettoyé")
            except Exception as e:
                logger.warning(f"[{job_id}] Erreur nettoyage: {e}")