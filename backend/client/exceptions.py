"""
Exceptions spécifiques pour l'API Grottocenter
"""

class GrottocenterError(Exception):
    """Exception de base pour toutes les erreurs Grottocenter"""
    pass


class GrottocenterConnectionError(GrottocenterError):
    """Erreur de connexion à l'API Grottocenter"""
    pass


class GrottocenterAuthError(GrottocenterError):
    """Erreur d'authentification"""
    pass


class GrottocenterAPIError(GrottocenterError):
    """Erreur générale de l'API Grottocenter"""
    def __init__(self, message: str, status_code: int = None, response_data: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class GrottocenterNotFoundError(GrottocenterAPIError):
    """Ressource non trouvée (404)"""
    def __init__(self, message: str):
        super().__init__(message, status_code=404)


class GrottocenterValidationError(GrottocenterAPIError):
    """Erreur de validation des données (400)"""
    def __init__(self, message: str, validation_errors: dict = None):
        super().__init__(message, status_code=400, response_data=validation_errors)
        self.validation_errors = validation_errors


class GrottocenterBusinessError(GrottocenterError):
    """Erreur de règle métier (ex: document non validé)"""
    pass