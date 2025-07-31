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

    # Ajouts à ajouter dans la classe DocumentService dans document_service.py

    async def get_document_children(self, doc_id: int) -> list:
        """Récupérer les enfants directs d'un document"""
        return await self.client.get(f"documents/{doc_id}/children")

    async def get_document_descendants(self, doc_id: int) -> list:
        """Récupérer récursivement tous les descendants (enfants + petits-enfants)"""
        all_descendants = []
        
        # Récupérer les enfants directs
        children_response = await self.get_document_children(doc_id)
        children = children_response.get("documents", [])
        
        for child in children:
            child_id = child.get("id")
            if child_id:
                # Ajouter l'enfant à la liste
                all_descendants.append(child)
                
                # Récupérer récursivement les descendants de cet enfant
                grandchildren = await self.get_document_descendants(child_id)
                all_descendants.extend(grandchildren)
        
        return all_descendants

    async def apply_inheritance(self, parent_doc: dict, child_ids: list, heritable_fields: dict) -> dict:
        """Appliquer l'héritage des champs sélectionnés sur une liste d'enfants"""
        results = {
            "success": [],
            "errors": [],
            "total": len(child_ids)
        }
        
        for child_id in child_ids:
            try:
                # Récupérer le document enfant actuel
                child_doc = await self.get_document(child_id)
                
                # Construire le payload avec seulement les champs à hériter
                payload = {}
                changes_needed = False
                
                for field_name, parent_value in heritable_fields.items():
                    current_value = child_doc.get(field_name)
                    
                    # Comparer les valeurs (gérer les objets avec id)
                    if self._values_different(current_value, parent_value):
                        payload[field_name] = parent_value
                        changes_needed = True
                
                if changes_needed:
                    # Appliquer les modifications
                    result = await self.client.put(f"documents/{child_id}", payload)
                    
                    # Valider le document
                    await self.validate_document(child_id, "Héritage depuis collection parente")
                    
                    results["success"].append({
                        "id": child_id,
                        "title": child_doc.get("title", f"Document {child_id}"),
                        "changes": payload
                    })
                else:
                    results["success"].append({
                        "id": child_id,
                        "title": child_doc.get("title", f"Document {child_id}"),
                        "changes": "Aucun changement nécessaire"
                    })
                    
            except Exception as e:
                results["errors"].append({
                    "id": child_id,
                    "error": str(e)
                })
        
        return results

    def _values_different(self, current, new) -> bool:
        """Comparer deux valeurs en gérant les objets avec id"""
        if current is None and new is None:
            return False
        if current is None or new is None:
            return True
        
        # Si c'est un objet avec un id
        if isinstance(current, dict) and "id" in current:
            if isinstance(new, dict) and "id" in new:
                return current["id"] != new["id"]
            return True
        
        # Comparaison simple
        return current != new