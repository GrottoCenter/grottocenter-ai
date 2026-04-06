import os
import shutil

from celery import uuid
from fastapi import UploadFile

from .celeryService import CeleryService
from .minioService import MinioService
import time

from uuid import UUID

class DocumentService:
    def __init__(self):
        self.celery_service = CeleryService()
        self.minio_service = MinioService()  # Nouvelle init


    async def get_document(self, doc_id: UUID):
        print(doc_id)
        result = self.celery_service.get_task_result(str(doc_id))

        return {"doc_id": doc_id, "content": result}
    
    async def process_document(self, file: UploadFile):
        unique_filename = str(uuid()) + ".pdf"
        
        file_content = await file.read()

        object_name = self.minio_service.upload_file(
            unique_filename, 
            file_content, 
            file.content_type
        )

        task = self.celery_service.send_task('tasks.test_celery_task', args=[object_name])
        
        return {
            "message": "Fichier reçu et en cours de traitement", 
            "task_id": task.id,
            "filename": file.filename,
            "object_name": object_name
        }