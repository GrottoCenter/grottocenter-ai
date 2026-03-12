import logging
from pathlib import Path
from celery.result import AsyncResult

from pipeline.celery_app import celery_app
from pipeline_ia.tasks import process_document_task
from pipeline_ia.models import JobStatus, DocumentMetadata
from pipeline_ia.config import settings

logger = logging.getLogger(__name__)


class QueueManager:
    """Gestionnaire de la file d'attente de traitement."""

    def submit_job(
        self,
        pdf_filename: str,
        metadata: DocumentMetadata | None = None,
    ) -> str:
        """
        Soumet un job de traitement dans la file d'attente.

        Returns:
            job_id unique pour suivre le traitement.
        """
        metadata_dict = metadata.model_dump(exclude_none=True) if metadata else None

        task = process_document_task.delay(
            pdf_filename=pdf_filename,
            metadata_dict=metadata_dict,
        )

        logger.info(f"Job soumis: {task.id} pour {pdf_filename}")
        return task.id

    def get_job_status(self, job_id: str) -> dict:
        """Récupère le statut d'un job."""
        result = AsyncResult(job_id, app=celery_app)

        if result.state == "PENDING":
            return {
                "job_id": job_id,
                "status": JobStatus.QUEUED.value,
                "progress": 0.0,
                "message": "En attente dans la file...",
            }
        elif result.state in ("PREPROCESSING", "OCR", "ANALYZING"):
            meta = result.info or {}
            return {
                "job_id": job_id,
                "status": meta.get("status", result.state.lower()),
                "progress": meta.get("progress", 0.0),
                "message": meta.get("message", ""),
            }
        elif result.state == "SUCCESS":
            return result.result
        elif result.state == "FAILURE":
            return {
                "job_id": job_id,
                "status": JobStatus.FAILED.value,
                "progress": 0.0,
                "message": "Échec du traitement",
                "error": str(result.info),
            }
        else:
            return {
                "job_id": job_id,
                "status": result.state.lower(),
                "progress": 0.0,
                "message": f"État: {result.state}",
            }

    def get_job_result(self, job_id: str) -> dict | None:
        """
        Récupère le résultat complet d'un job terminé.
        Tente d'abord via Celery, puis via le fichier JSON sauvegardé.
        """
        # Via Celery
        result = AsyncResult(job_id, app=celery_app)
        if result.state == "SUCCESS" and result.result:
            return result.result

        # Via fichier
        result_path = settings.results_dir / f"{job_id}.json"
        if result_path.exists():
            import json
            return json.loads(result_path.read_text(encoding="utf-8"))

        return None

    def cancel_job(self, job_id: str) -> bool:
        """Annule un job en attente."""
        try:
            celery_app.control.revoke(job_id, terminate=True)
            logger.info(f"Job annulé: {job_id}")
            return True
        except Exception as e:
            logger.error(f"Erreur annulation job {job_id}: {e}")
            return False

    def get_queue_info(self) -> dict:
        """Récupère les informations sur la file d'attente."""
        inspector = celery_app.control.inspect()

        active = inspector.active() or {}
        reserved = inspector.reserved() or {}
        scheduled = inspector.scheduled() or {}

        total_active = sum(len(v) for v in active.values())
        total_reserved = sum(len(v) for v in reserved.values())
        total_scheduled = sum(len(v) for v in scheduled.values())

        return {
            "active_jobs": total_active,
            "queued_jobs": total_reserved,
            "scheduled_jobs": total_scheduled,
            "workers": list(active.keys()),
        }


# Singleton
queue_manager = QueueManager()