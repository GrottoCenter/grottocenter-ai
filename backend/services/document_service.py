from backend.client.base_client import get_client_async
from backend.schemas.document_schemas import DocumentUpdateRequest

class DocumentService:
    def __init__(self, client):
        self.client = client

    async def get_document(self, doc_id: int) -> dict:
        return await self.client.get(f"documents/{doc_id}")

    async def update_document(self, doc_id: int, update_payload: DocumentUpdateRequest) -> dict:
        existing = await self.get_document(doc_id)
        updates = update_payload.model_dump(exclude_unset=True)
        updated = {**existing, **updates}
        updated.pop("id", None)
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

    async def get_document_children(self, doc_id: int) -> list:
        return await self.client.get(f"documents/{doc_id}/children")

    async def get_document_descendants(self, doc_id: int) -> list:
        all_descendants = []
        children_response = await self.get_document_children(doc_id)
        children = children_response.get("documents", [])
        
        for child in children:
            child_id = child.get("id")
            if child_id:
                all_descendants.append(child)
                grandchildren = await self.get_document_descendants(child_id)
                all_descendants.extend(grandchildren)
        
        return all_descendants

    async def apply_inheritance(self, parent_doc: dict, child_ids: list, heritable_fields: dict) -> dict:
        results = {
            "success": [],
            "errors": [],
            "total": len(child_ids)
        }
        
        for child_id in child_ids:
            try:
                child_doc = await self.get_document(child_id)
                payload = {}
                changes_needed = False

                for field_name, parent_value in heritable_fields.items():
                    current_value = child_doc.get(field_name)
                    if self._values_different(current_value, parent_value):
                        # Transformer la valeur selon les règles de l'API
                        transformed_value = self._transform_field_value(field_name, parent_value)
                        payload[field_name] = transformed_value
                        changes_needed = True

                if changes_needed:
                    # Utilisation de la méthode update_document
                    update_request = DocumentUpdateRequest(**payload)
                    await self.update_document(child_id, update_request)
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

    def _transform_field_value(self, field_name: str, value):
        """Transforme une valeur selon les règles de l'API pour un champ donné"""
        if value is None:
            return None
            
        # Les champs qui sont déjà des objets avec id ne nécessitent pas de transformation
        if field_name in ["license", "authorizationDocument", "editor"]:
            # Ces champs doivent être des objets avec un id
            if isinstance(value, dict) and "id" in value:
                return value
            elif isinstance(value, str) and value.strip():
                # Si c'est une string, on essaie de la convertir en objet
                if field_name == "license":
                    # Mapping des licences (comme dans le Streamlit)
                    license_mapping = {
                        "CC-BY-SA": 1, "CC-BY": 2, "ODBL": 3, "ODC-BY": 4,
                        "Licence Ouverte": 5, "CC-BY-NC-ND": 6, "CC BY NC": 7,
                        "CC BY ND": 8, "CC BY NC SA": 9
                    }
                    if value in license_mapping:
                        return {"id": license_mapping[value]}
                    else:
                        return {"id": int(value)} if value.isdigit() else None
                else:
                    # Pour authorizationDocument et editor, on assume que c'est un ID
                    try:
                        return {"id": int(value)}
                    except (ValueError, TypeError):
                        return None
            else:
                return None
        
        # Pour les autres champs (mainLanguage, etc.), on retourne la valeur telle quelle
        return value

    def _values_different(self, current, new) -> bool:
        if current is None and new is None:
            return False
        if current is None or new is None:
            return True
        if isinstance(current, dict) and "id" in current:
            return not (isinstance(new, dict) and current.get("id") == new.get("id"))
        return current != new