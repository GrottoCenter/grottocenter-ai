from backend.client.base_client import get_client_async
from backend.schemas.document_schemas import DocumentUpdateRequest

class DocumentService:
    def __init__(self, client):
        self.client = client

    async def get_document(self, doc_id: int) -> dict:
        return await self.client.get(f"documents/{doc_id}")

    async def update_document(self, doc_id: int, update_payload: DocumentUpdateRequest) -> dict:
        # Étape 1 : Récupérer le document existant
        existing = await self.get_document(doc_id)

        # Étape 2 : Appliquer les modifications
        updates = update_payload.model_dump(exclude_unset=True)
        updated = {**existing, **updates}  # fusion intelligente : les champs de updates remplacent ceux d'existing

        # Étape 3 : Nettoyer les champs non acceptés (si besoin)
        updated.pop("id", None)  # on ne renvoie jamais l'ID dans le body

        # Étape 4 : PUT avec l'objet complet modifié
        return await self.client.put(f"documents/{doc_id}", updated)

    async def validate_document(self, doc_id: int, comment: str = "Validated by FastAPI update tool") -> dict:
        payload = {
            "documents": [
                {
                    "id": doc_id,
                    "isValidated": "true",
                    "validationComment": comment
                }
            ]
        }
        return await self.client.put("documents/validate", payload)
