import os
import time
from celery import Celery
from backendV2.worker import ocr
from backendV2.config.celeryconfig import CeleryConfig

celery_app = Celery('tasks')
celery_app.config_from_object(CeleryConfig)

@celery_app.task(name='tasks.test_celery_task')
def test_celery_task(file_path: str):

    print(f"Received file path: {file_path}")

    try:
        text= ocr.extract_pdf_text_for_llm(file_path)

        if os.path.exists(file_path):
            os.remove(file_path)

        return f"Extracted text for document {file_path}: {text}"
    except Exception as e:
        return f"Error processing document {file_path}: {str(e)}"