FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-fra \
    tesseract-ocr-spa \
    tesseract-ocr-deu \
    tesseract-ocr-ita \
    tesseract-ocr-por \
    tesseract-ocr-rus \
    tesseract-ocr-nld \
    tesseract-ocr-pol \
    && rm -rf /var/lib/apt/lists/*

# Copier uniquement le requirements du worker
COPY worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY worker/ ./worker/
COPY /backendV2/model/ ./backendV2/model/
COPY /backendV2/model/ ./backendV2/config/

CMD ["celery", "-A", "worker.src.tasks", "worker", "--loglevel=info"]