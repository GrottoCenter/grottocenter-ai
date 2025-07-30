#!/usr/bin/env python3
import uvicorn
import os
import logging
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Configurer les logs pour afficher les messages INFO ou supérieurs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

if __name__ == "__main__":
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8000"))

    # Lancer l'application FastAPI avec Uvicorn
    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        reload=True
    )
