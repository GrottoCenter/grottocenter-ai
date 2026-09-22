FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libmagic1 \
    libmagic-dev \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Lancement de l'API avec Uvicorn. On suppose que votre instance FastAPI s'appelle "app" dans backendV2/main.py
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]