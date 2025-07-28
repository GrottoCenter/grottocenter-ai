import os
import shutil
from pathlib import Path
from typing import Tuple
from fastapi import UploadFile
import PyPDF2
from ..utils.exceptions import FileSizeException, InvalidFileTypeException

class PDFService:
    """Service pour la gestion des fichiers PDF"""
    
    def __init__(self, upload_dir: str = "./uploads", max_size_mb: int = 50):
        self.upload_dir = Path(upload_dir)
        self.max_size_mb = max_size_mb
        self.max_size_bytes = max_size_mb * 1024 * 1024
        
        # Créer le dossier uploads s'il n'existe pas
        self.upload_dir.mkdir(exist_ok=True)
    
    def validate_pdf(self, file: UploadFile) -> None:
        """Valide le fichier PDF"""
        # Vérifier l'extension
        if not file.filename.lower().endswith('.pdf'):
            raise InvalidFileTypeException()
        
        # Vérifier la taille
        if file.size and file.size > self.max_size_bytes:
            raise FileSizeException(self.max_size_mb)
    
    def save_pdf(self, file: UploadFile) -> Tuple[str, int]:
        """Sauvegarde le fichier PDF et retourne le nom et la taille"""
        # Validation
        self.validate_pdf(file)
        
        # Générer un nom de fichier unique
        filename = self._generate_unique_filename(file.filename)
        file_path = self.upload_dir / filename
        
        # Sauvegarder le fichier
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # Vérifier que c'est un PDF valide
            self._verify_pdf_integrity(file_path)
            
            file_size = file_path.stat().st_size
            return filename, file_size
            
        except Exception as e:
            # Nettoyer en cas d'erreur
            if file_path.exists():
                file_path.unlink()
            raise InvalidFileTypeException()
    
    def _generate_unique_filename(self, original_filename: str) -> str:
        """Génère un nom de fichier unique"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name, ext = os.path.splitext(original_filename)
        return f"{timestamp}_{name}{ext}"
    
    def _verify_pdf_integrity(self, file_path: Path) -> None:
        """Vérifie l'intégrité du PDF"""
        try:
            with open(file_path, 'rb') as f:
                PyPDF2.PdfReader(f)
        except Exception:
            raise InvalidFileTypeException()