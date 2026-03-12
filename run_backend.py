#!/usr/bin/env python3
import logging
import os

import uvicorn
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
        "backendV2.main:app",
        host=host,
        port=port,
        reload=True
    )
