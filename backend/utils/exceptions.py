from fastapi import HTTPException

class PDFException(HTTPException):
    """Exception personnalisée pour les erreurs PDF"""
    pass

class FileSizeException(PDFException):
    """Exception pour les fichiers trop volumineux"""
    def __init__(self, max_size_mb: int):
        super().__init__(
            status_code=413,
            detail=f"Le fichier dépasse la taille maximale autorisée de {max_size_mb} MB"
        )

class InvalidFileTypeException(PDFException):
    """Exception pour les types de fichiers invalides"""
    def __init__(self):
        super().__init__(
            status_code=400,
            detail="Le fichier doit être un PDF valide"
        )