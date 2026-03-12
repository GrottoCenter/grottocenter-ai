from celery import Celery
from pipeline_ia.config import settings

celery_app = Celery(
    "document_pipeline",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Paris",
    enable_utc=True,
    worker_concurrency=settings.celery_concurrency,
    task_track_started=True,
    task_time_limit=600,  # 10 minutes max par tâche
    task_soft_time_limit=540,
    worker_prefetch_multiplier=1,  # Un job à la fois par worker
    task_acks_late=True,  # Acquitter après traitement
)