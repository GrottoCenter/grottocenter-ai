import os
import shutil

from celery import uuid
from fastapi import UploadFile

from .celeryService import CeleryService
import time

from uuid import UUID

class DocumentService:
    def __init__(self):
        # Initialize any necessary resources, such as database connections
        self.celery_service = CeleryService()

        self.upload_dir = "uploads"
        os.makedirs(self.upload_dir, exist_ok=True)


    async def get_document(self, doc_id: UUID):
        print(doc_id)
        result = self.celery_service.get_task_result(str(doc_id))

        return {"doc_id": doc_id, "content": result}
    
    async def process_document(self, file: UploadFile):
        unique_filename = f"{uuid()}"
        file_path = os.path.join(self.upload_dir, unique_filename)

        # 2. Sauvegarder le fichier sur le disque (partagé entre backend et worker)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 3. Envoyer uniquement le CHEMIN DU FICHIER à Celery
        task = self.celery_service.send_task('tasks.test_celery_task', args=[file_path])
        
        # 4. On retourne l'ID de la tâche à l'utilisateur pour qu'il puisse vérifier l'état
        return {
            "message": "Fichier reçu et en cours de traitement", 
            "task_id": task.id,
            "filename": file.filename
        }