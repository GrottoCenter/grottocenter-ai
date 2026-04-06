"""
Application FastAPI principale
"""

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Import des routes
from controller.documentController import router as document_router

# Créer l'application FastAPI
app = FastAPI(
    title="Grottocenter AI Tools API",
    description="API pour les outils IA de traitement des documents Grottocenter",
    version="0.2.0"
)

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
        return {
            "status": "ok",
            "message": "API is running",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {e}")

# Inclure les routes
app.include_router(document_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
