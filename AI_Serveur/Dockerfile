FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Lancement de l'API avec Uvicorn. On suppose que votre instance FastAPI s'appelle "app" dans backendV2/main.py
# --proxy-headers makes the client address come from X-Forwarded-For behind Traefik, but
# only for peers listed in FORWARDED_ALLOW_IPS, which uvicorn reads from the environment
# (default 127.0.0.1,::1).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]