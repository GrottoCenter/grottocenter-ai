import os
import shutil

from fastapi import UploadFile

import time

from uuid import UUID

class DocumentService:
    def __init__(self):


    async def get_document(self, doc_id: UUID):
        print(doc_id)
        result = self.celery_service.get_task_result(str(doc_id))

        return {"doc_id": doc_id, "content": result}
    
    async def process_document(self, file: UploadFile):
        unique_filename = str(uuid()) + ".pdf"
        
        file_content = await file.read()

        object_name = "temp/" + unique_filename
        
        return {
            "message": "Fichier reçu et en cours de traitement", 
            "task_id": task.id,
            "filename": file.filename,
            "object_name": object_name
        }