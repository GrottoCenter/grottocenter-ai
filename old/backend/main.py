"""
Application FastAPI principale
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Import des routes
from old.backend.api.document_routes import router as document_router
from old.backend.api.pdf_routes import router as pdf_router

# Charger les variables d'environnement
load_dotenv()

# Créer l'application FastAPI
app = FastAPI(
    title="Grottocenter AI Tools API",
    description="API pour les outils IA de traitement des documents Grottocenter",
    version="0.2.0"
)

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes principales
@app.get("/")
async def root():
    return {
        "message": "Grottocenter AI Tools API",
        "version": "0.2.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    """Point de santé global de l'API"""
    try:
        # Vérifier la configuration Grottocenter
        grottocenter_url = os.getenv("GROTTOCENTER_URL")
        grottocenter_token = os.getenv("GROTTOCENTER_TOKEN")
        
        grottocenter_configured = bool(grottocenter_url and grottocenter_token)
        
        return {
            "status": "ok",
            "message": "API is running",
            "grottocenter_configured": grottocenter_configured
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {e}")

# Inclure les routes
app.include_router(pdf_router)
app.include_router(document_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
