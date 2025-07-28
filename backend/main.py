from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import os

from .api.pdf_routes import router as pdf_router
from .utils.exceptions import PDFException

# Charger les variables d'environnement
load_dotenv()

# Configuration de l'application
app = FastAPI(
    title="Grottocenter AI Tools API",
    description="API pour les outils IA de Grottocenter",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configuration CORS pour Streamlit
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gestionnaire d'exception global pour PDFException
@app.exception_handler(PDFException)
async def pdf_exception_handler(request, exc: PDFException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.detail, "error_code": "PDF_ERROR"}
    )

# Routes
app.include_router(pdf_router)

@app.get("/")
async def root():
    """Point d'entrée de l'API"""
    return {
        "message": "Grottocenter AI Tools API",
        "version": "0.1.0",
        "docs": "/docs"
    }

@app.get("/health")
async def health():
    """Health check général"""
    return {"status": "ok", "message": "API is running"}

if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8000"))
    
    uvicorn.run(
        "backend.main:app", 
        host=host, 
        port=port, 
        reload=True
    )