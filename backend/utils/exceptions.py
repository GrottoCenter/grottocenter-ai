from fastapi import HTTPException, status


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

# Collection Management Exceptions
class GrottocenterUpdateError(Exception):
    """Exception pour les erreurs de mise à jour Grottocenter"""
    pass

class CollectionException(HTTPException):
    """Exception de base pour les erreurs de collections"""
    pass

class CollectionNotFoundError(CollectionException):
    """Exception pour les collections non trouvées"""
    def __init__(self, collection_id: str):
        super().__init__(
            status_code=404,
            detail=f"Collection {collection_id} non trouvée"
        )

class CollectionValidationError(CollectionException):
    """Exception pour les erreurs de validation de collections"""
    def __init__(self, message: str):
        super().__init__(
            status_code=400,
            detail=f"Erreur de validation: {message}"
        )

class DocumentNotValidatedError(CollectionException):
    """Exception pour les documents non validés"""
    def __init__(self, document_id: str):
        super().__init__(
            status_code=400,
            detail=f"Le document {document_id} n'est pas validé. Validez d'abord le changement précédent."
        )

# CSV Processing Exceptions
class CSVException(HTTPException):
    """Exception de base pour les erreurs CSV"""
    pass

class InvalidCSVFormatError(CSVException):
    """Exception pour les formats CSV invalides"""
    def __init__(self, message: str):
        super().__init__(
            status_code=400,
            detail=f"Format CSV invalide: {message}"
        )

class CSVParsingError(CSVException):
    """Exception pour les erreurs de parsing CSV"""
    def __init__(self, message: str):
        super().__init__(
            status_code=400,
            detail=f"Erreur lors du parsing CSV: {message}"
        )

class MissingCSVColumnsError(CSVException):
    """Exception pour les colonnes CSV manquantes"""
    def __init__(self, missing_columns: list):
        super().__init__(
            status_code=400,
            detail=f"Colonnes CSV manquantes: {', '.join(missing_columns)}"
        )

class DuplicateCSVRecordError(CSVException):
    """Exception pour les enregistrements CSV dupliqués"""
    def __init__(self, duplicate_id: str):
        super().__init__(
            status_code=400,
            detail=f"ID dupliqué dans le CSV: {duplicate_id}"
        )

class EmptyCSVError(CSVException):
    """Exception pour les fichiers CSV vides"""
    def __init__(self):
        super().__init__(
            status_code=400,
            detail="Le fichier CSV est vide"
        )

# Configuration Exceptions
class ConfigurationException(HTTPException):
    """Exception de base pour les erreurs de configuration"""
    pass

class InvalidConfigurationError(ConfigurationException):
    """Exception pour les configurations invalides"""
    def __init__(self, errors: list):
        super().__init__(
            status_code=400,
            detail=f"Configuration invalide: {', '.join(errors)}"
        )

class ConfigurationLoadError(ConfigurationException):
    """Exception pour les erreurs de chargement de configuration"""
    def __init__(self, message: str):
        super().__init__(
            status_code=500,
            detail=f"Erreur lors du chargement de la configuration: {message}"
        )

# License Management Exceptions
class LicenseException(HTTPException):
    """Exception de base pour les erreurs de licence"""
    pass

class UnknownLicenseError(LicenseException):
    """Exception pour les licences non reconnues"""
    def __init__(self, license_name: str, document_id: str = None):
        detail = f"Licence '{license_name}' non reconnue"
        if document_id:
            detail += f" pour le document {document_id}"
        super().__init__(
            status_code=400,
            detail=detail
        )

# API Connection Exceptions
class APIConnectionException(HTTPException):
    """Exception de base pour les erreurs de connexion API"""
    pass

class GrottocenterAPIError(APIConnectionException):
    """Exception pour les erreurs de l'API Grottocenter"""
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(
            status_code=status_code,
            detail=f"Erreur API Grottocenter: {message}"
        )

class APITimeoutError(APIConnectionException):
    """Exception pour les timeouts API"""
    def __init__(self, operation: str):
        super().__init__(
            status_code=504,
            detail=f"Timeout lors de l'opération: {operation}"
        )

class APIRateLimitError(APIConnectionException):
    """Exception pour les limites de taux API"""
    def __init__(self):
        super().__init__(
            status_code=429,
            detail="Limite de taux API atteinte. Veuillez réessayer plus tard."
        )

# Batch Processing Exceptions
class BatchProcessingException(HTTPException):
    """Exception de base pour les erreurs de traitement par lot"""
    pass

class BatchSizeExceededError(BatchProcessingException):
    """Exception pour les lots trop volumineux"""
    def __init__(self, current_size: int, max_size: int):
        super().__init__(
            status_code=400,
            detail=f"Taille du lot trop importante: {current_size} éléments (maximum: {max_size})"
        )

class BatchProcessingTimeoutError(BatchProcessingException):
    """Exception pour les timeouts de traitement par lot"""
    def __init__(self):
        super().__init__(
            status_code=504,
            detail="Timeout lors du traitement par lot"
        )

# Inheritance Processing Exceptions
class InheritanceException(HTTPException):
    """Exception de base pour les erreurs d'héritage"""
    pass

class NoInheritableFieldsError(InheritanceException):
    """Exception quand aucun champ héritable n'est trouvé"""
    def __init__(self):
        super().__init__(
            status_code=400,
            detail="Aucun champ héritable trouvé dans le payload"
        )

class InheritanceProcessingError(InheritanceException):
    """Exception pour les erreurs de traitement d'héritage"""
    def __init__(self, parent_id: str, message: str):
        super().__init__(
            status_code=500,
            detail=f"Erreur lors du traitement de l'héritage pour {parent_id}: {message}"
        )

# Cache Management Exceptions
class CacheException(Exception):
    """Exception de base pour les erreurs de cache"""
    pass

class CacheInvalidationError(CacheException):
    """Exception pour les erreurs d'invalidation de cache"""
    def __init__(self, cache_key: str):
        super().__init__(f"Erreur lors de l'invalidation du cache pour: {cache_key}")

# Validation Exceptions
class DocumentValidationException(HTTPException):
    """Exception pour les erreurs de validation de documents"""
    pass

class BulkValidationError(DocumentValidationException):
    """Exception pour les erreurs de validation en lot"""
    def __init__(self, failed_ids: list, message: str = None):
        detail = f"Échec de validation pour les documents: {', '.join(failed_ids)}"
        if message:
            detail += f". {message}"
        super().__init__(
            status_code=400,
            detail=detail
        )

class ValidationTimeoutError(DocumentValidationException):
    """Exception pour les timeouts de validation"""
    def __init__(self, document_ids: list):
        super().__init__(
            status_code=504,
            detail=f"Timeout lors de la validation des documents: {', '.join(document_ids)}"
        )

class PDFException(HTTPException):
    pass

class InvalidFileTypeException(PDFException):
    def __init__(self, detail: str = "Invalid file type. PDF expected."):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

class FileSizeException(PDFException):
    def __init__(self, max_mb: int):
        super().__init__(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Max {max_mb} MB."
        )

class PDFReadException(PDFException):
    def __init__(self, detail: str = "Unable to read PDF (possibly corrupted or encrypted)."):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
