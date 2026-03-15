import time
from celery import Celery
from backendV2.config.celeryconfig import CeleryConfig

celery_app = Celery('tasks')
celery_app.config_from_object(CeleryConfig)

@celery_app.task(name='tasks.test_celery_task')
def test_celery_task(doc_id: int):
    time.sleep(5)  
    return doc_id * 2