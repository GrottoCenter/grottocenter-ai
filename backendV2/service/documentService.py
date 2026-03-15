from .celeryService import CeleryService
import time

class DocumentService:
    def __init__(self):
        # Initialize any necessary resources, such as database connections
        self.celery_service = CeleryService()


    async def get_document(self, doc_id: int):
        task = self.celery_service.send_task('tasks.test_celery_task', args=[doc_id])
        result = self.celery_service.get_task_result(task.id)

        return {"doc_id": doc_id, "content": result}