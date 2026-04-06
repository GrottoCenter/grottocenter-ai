from celery import Celery
from config.celeryconfig import CeleryConfig

class CeleryService:
    def __init__(self):
        self.celery_app = Celery('tasks')
        self.celery_app.config_from_object(CeleryConfig)
    
    def send_task(self, task_name: str, args=None, kwargs=None):
        return self.celery_app.send_task(task_name, args=args, kwargs=kwargs)
    
    def get_task_result(self, task_id: str):
        return self.celery_app.AsyncResult(task_id).get()
    
    def get_task_status(self, task_id: str):
        return self.celery_app.AsyncResult(task_id).status
    
    def get_task_progress(self, task_id: str):
        result = self.celery_app.AsyncResult(task_id)
        if result.state == 'PROGRESS':
            return result.info.get('progress', 0)
        return 0
    
    def revoke_task(self, task_id: str, terminate: bool = False):
        self.celery_app.control.revoke(task_id, terminate=terminate)