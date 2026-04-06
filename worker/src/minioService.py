import os
import io
from minio import Minio

class MinioService:
    def __init__(self):
        self.endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
        self.access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        self.secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
        self.bucket_name = os.getenv("MINIO_BUCKET_NAME", "documents")

        self.client = Minio(
            self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=False
        )

        if not self.client.bucket_exists(self.bucket_name):
            self.client.make_bucket(self.bucket_name)

    def upload_file(self, object_name: str, file_data: bytes, content_type: str = "application/pdf"):
        data_stream = io.BytesIO(file_data)
        self.client.put_object(
            self.bucket_name,
            object_name,
            data_stream,
            length=len(file_data),
            content_type=content_type
        )
        return object_name

    def download_file(self, object_name: str, file_path: str):
        self.client.fget_object(self.bucket_name, object_name, file_path)
        return file_path
        
    def delete_file(self, object_name: str):
        self.client.remove_object(self.bucket_name, object_name)