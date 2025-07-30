# backend/client/base_client.py (Updated for asynchronous operations with httpx)
import httpx 
import time
import logging
from typing import Dict, Any, Optional, List
from functools import wraps
from dotenv import load_dotenv
import os
import asyncio # For async sleep

from .exceptions import (
    GrottocenterAPIError,
    GrottocenterConnectionError,
    GrottocenterAuthError,
    GrottocenterNotFoundError,
    GrottocenterValidationError
)


def retry_on_failure_async(max_retries: int = 3, delay: float = 1.0):
    """Décorateur pour retry automatique asynchrone avec backoff exponentiel"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs): # func is now async
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs) # Await the function call
                except (httpx.RequestError, httpx.TimeoutException) as e:
                    last_exception = e
                    if attempt == max_retries - 1:
                        break
                    wait_time = delay * (2 ** attempt)  # Backoff exponentiel
                    logging.getLogger(__name__).warning(f"Attempt {attempt + 1}/{max_retries} failed. Retrying in {wait_time:.2f} seconds. Error: {e}")
                    await asyncio.sleep(wait_time) # Use asyncio.sleep
                except GrottocenterAPIError:
                    # Do not retry API errors (4xx, 5xx other than connection/timeout)
                    raise
            raise GrottocenterConnectionError(f"Failed after {max_retries} attempts: {last_exception}")
        return wrapper
    return decorator


class GrottocenterClient:
    """Client de base pour l'API Grottocenter (Asynchrone)"""

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None):
        load_dotenv()

        self.base_url = base_url or os.getenv("GROTTOCENTER_URL")
        if not self.base_url:
            raise ValueError("L'URL GROTTOCENTER_URL est manquante dans le fichier .env")

        self.token = token or os.getenv("GROTTOCENTER_TOKEN")
        if not self.token:
            raise ValueError("Le token GROTTOCENTER_TOKEN est manquant dans le fichier .env")

        self.timeout = 30
        self.logger = logging.getLogger(__name__)
        # httpx.AsyncClient should be managed with an async context manager
        # or initialized once and closed when the application shuts down.
        # For a FastAPI app, typically you'd want to create it once and reuse.
        self._async_client = None

    async def _get_async_client(self) -> httpx.AsyncClient:
        """Get or create the async client instance."""
        if self._async_client is None or self._async_client.is_closed:
            headers = {
                'Authorization': f'Bearer {self.token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            self._async_client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout, headers=headers)
        return self._async_client

    def _build_url(self, endpoint: str) -> str:
        """Construire l'URL complète"""
        if endpoint.startswith('/'):
            endpoint = endpoint[1:]
        # httpx.AsyncClient handles base_url internally if initialized with it
        return endpoint # Just return the endpoint as httpx client will combine with base_url

    async def _handle_response(self, response: httpx.Response, endpoint: str) -> Dict[str, Any]:
        """Gérer la réponse HTTP et les erreurs"""
        try:
            self.logger.info(f"{response.request.method} {endpoint} -> {response.status_code}")

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 204:
                return {"success": True}
            elif response.status_code == 401:
                raise GrottocenterAuthError("Token d'authentification invalide")
            elif response.status_code == 404:
                raise GrottocenterNotFoundError(f"Ressource non trouvée: {endpoint}")
            elif response.status_code == 400:
                error_data = response.json() if response.content else {}
                raise GrottocenterValidationError(f"Données invalides: {error_data}")
            elif response.status_code >= 500:
                raise GrottocenterAPIError(f"Erreur serveur ({response.status_code}): {response.text}")
            else:
                raise GrottocenterAPIError(f"Erreur HTTP {response.status_code}: {response.text}")

        except httpx.BadJSON as e: # Catch httpx's JSON decode error
            if response.status_code == 204:
                return {"success": True}
            raise GrottocenterAPIError(f"Réponse JSON invalide: {response.text}. Error: {e}")

    @retry_on_failure_async()
    async def get(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Requête GET asynchrone"""
        client = await self._get_async_client()
        response = await client.get(self._build_url(endpoint), params=params)
        return await self._handle_response(response, endpoint)

    @retry_on_failure_async()
    async def post(self, endpoint: str, data: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Requête POST asynchrone"""
        client = await self._get_async_client()
        response = await client.post(self._build_url(endpoint), json=data, params=params)
        return await self._handle_response(response, endpoint)

    @retry_on_failure_async()
    async def put(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Requête PUT asynchrone"""
        client = await self._get_async_client()
        response = await client.put(self._build_url(endpoint), json=data)
        return await self._handle_response(response, endpoint)

    @retry_on_failure_async()
    async def patch(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Requête PATCH asynchrone"""
        client = await self._get_async_client()
        response = await client.patch(self._build_url(endpoint), json=data)
        return await self._handle_response(response, endpoint)

    @retry_on_failure_async()
    async def delete(self, endpoint: str) -> Dict[str, Any]:
        """Requête DELETE asynchrone"""
        client = await self._get_async_client()
        response = await client.delete(self._build_url(endpoint))
        return await self._handle_response(response, endpoint)

    async def health_check(self) -> Dict[str, Any]:
        """Vérifier la connexion à l'API de manière asynchrone"""
        try:
            response = await self.get("licenses")

            if isinstance(response, dict) and "licenses" in response:
                return {
                    "status": "ok",
                    "connection": True,
                    "message": "Connexion Grottocenter API réussie",
                    "preview": response["licenses"][0] if response["licenses"] else None
                }
            else:
                return {
                    "status": "partial",
                    "connection": True,
                    "message": "Connexion établie mais réponse inattendue"
                }

        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return {
                "status": "error",
                "connection": False,
                "message": f"Échec connexion Grottocenter: {e}",
                "error": str(e)
            }

    async def close(self):
        """Fermer la session HTTPX asynchrone"""
        if self._async_client and not self._async_client.is_closed:
            await self._async_client.aclose()

    # Async context manager methods
    async def __aenter__(self):
        await self._get_async_client() # Ensure client is initialized
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# Instance globale (singleton pattern)
_client_instance: Optional[GrottocenterClient] = None

# You need to initialize this client asynchronously when your app starts
# For FastAPI, this is often done with lifespan events or dependency injection.
# For simplicity, we can make get_client async too.
async def get_client_async() -> GrottocenterClient:
    """Récupérer l'instance globale du client asynchrone"""
    global _client_instance
    if _client_instance is None:
        _client_instance = GrottocenterClient()
        # In a real FastAPI app, you'd manage the lifecycle of the httpx client
        # with an on_startup/on_shutdown event handler, not here directly.
        # This global instance approach is for simplicity, but more robust
        # client management is recommended for production.
    return _client_instance