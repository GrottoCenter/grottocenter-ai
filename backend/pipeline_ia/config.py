from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # Chemins
    base_dir: Path = Path(__file__).parent.parent
    upload_dir: Path = Path(__file__).parent.parent / "uploads"
    results_dir: Path = Path(__file__).parent.parent / "results"
    temp_dir: Path = Path(__file__).parent.parent / "temp"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    celery_concurrency: int = 2  # Nombre de workers simultanés

    # OCR
    tesseract_cmd: str = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    tesseract_lang: str = "fra+eng+spa+deu+ita"
    ocr_dpi: int = 300

    # Preprocessing
    preprocessing_target_dpi: int = 300
    preprocessing_denoise: bool = True
    preprocessing_deskew: bool = True
    preprocessing_binarize: bool = True
    preprocessing_contrast_enhance: float = 1.5

    # LLM local (Ollama)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "mistral"  # ou "llama3", "phi3", "gemma2"
    ollama_timeout: int = 300
    llm_max_text_chars: int = 30000  # Limité pour petit modèle

    # Pipeline
    max_concurrent_jobs: int = 4
    max_pages_per_document: int = 200

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def ensure_dirs(self):
        """Crée les répertoires nécessaires."""
        for d in [self.upload_dir, self.results_dir, self.temp_dir]:
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()