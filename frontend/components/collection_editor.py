import streamlit as st
import requests
import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

# --- Data Models ---

@dataclass
class DocumentField:
    key: str
    label: str
    current_value: Any
    field_type: str = "text"
    options: List[str] = None
    help_text: str = ""

    def render(self) -> Any:
        if self.field_type == "textarea":
            return st.text_area(self.label, value=self.current_value or "", help=self.help_text)
        elif self.field_type == "select":
            default_index = 0
            if self.current_value in self.options:
                default_index = self.options.index(self.current_value)
            return st.selectbox(self.label, options=self.options, index=default_index, help=self.help_text)
        else:
            return st.text_input(self.label, value=self.current_value or "", help=self.help_text)

# --- Main Editor Class ---

class CollectionEditor:
    def __init__(self, api_base_url: str):
        self.api_base_url = api_base_url
        self.license_mapping = {
            "CC-BY-SA": 1, "CC-BY": 2, "ODBL": 3, "ODC-BY": 4,
            "Licence Ouverte": 5, "CC-BY-NC-ND": 6, "CC BY NC": 7,
            "CC BY ND": 8, "CC BY NC SA": 9
        }
        self.license_options = [""] + list(self.license_mapping.keys())
        self.identifier_type_options = ["", "doi", "issn", "isbn", "url"]

    def show_interface(self):
        st.title("🗂️ Édition de document Grottocenter")
        if "document" not in st.session_state:
            self._show_search()
        else:
            self._show_form()

    def _show_search(self):
        st.subheader("🔍 Rechercher un document")
        doc_id = st.text_input("ID du document", key="doc_id_input")
        if st.button("Charger"):
            self._load_document(doc_id)

    def _load_document(self, doc_id: str):
        if not doc_id:
            st.warning("Veuillez entrer un ID de document.")
            return
        try:
            with st.spinner("Chargement..."):
                res = requests.get(f"{self.api_base_url}/documents/{doc_id}")
            if res.status_code == 200:
                doc = res.json()
                st.session_state.document = doc
                st.session_state.initial_values = self._extract_values(doc)
                st.success("Document chargé.")
                st.rerun()
            else:
                st.error(f"Erreur: {res.status_code} - {res.text}")
        except Exception as e:
            st.error(f"Erreur: {e}")

    def _extract_values(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "title": doc.get("title", ""),
            "description": doc.get("description", ""),
            "identifier": doc.get("identifier", ""),
            "pages": doc.get("pages", ""),
            "creatorComment": doc.get("creatorComment", ""),
            "mainLanguage": doc.get("mainLanguage", ""),
            "license": doc.get("license", ""),  # string
            "identifierType": doc.get("identifierType", ""),  # string
            "iso3166": ";".join([entry.get("iso", "") for entry in doc.get("iso3166", [])]),
            "authorizationDocument": str(doc.get("authorizationDocument", {}).get("id", "")),
            "editor": str(doc.get("editor", {}).get("id", ""))
        }

    def _show_form(self):
        doc = st.session_state.document
        init = st.session_state.initial_values
        st.subheader(f"📄 Édition du document #{doc.get('id')}")

        changed = {}
        fields = [
            ("title", "Titre", "text"),
            ("description", "Description", "textarea"),
            ("identifier", "Identifiant", "text"),
            ("pages", "Pages", "text"),
            ("creatorComment", "Commentaire auteur", "textarea"),
            ("mainLanguage", "Langue", "text"),
            ("license", "Licence", "select", self.license_options),
            ("identifierType", "Type d'identifiant", "select", self.identifier_type_options),
            ("iso3166", "Régions ISO", "text"),
            ("authorizationDocument", "ID du document d'autorisation", "text"),
            ("editor", "ID de l’éditeur", "text")
        ]

        for f in fields:
            key, label, ftype = f[0], f[1], f[2]
            options = f[3] if len(f) > 3 else None
            cur_val = init.get(key, "")
            new_val = DocumentField(key, label, cur_val, ftype, options).render()
            if str(new_val).strip() != str(cur_val).strip():
                changed[key] = new_val

        if changed:
            st.markdown("### 📝 Champs modifiés")
            for k, v in changed.items():
                st.markdown(f"**{k}** : `{init.get(k, '[vide]')}` → `{v}`")

        if st.button("✅ Enregistrer et valider", disabled=not changed):
            self._save_changes(changed)

        if st.button("↩️ Revenir à la recherche"):
            self._reset()

    def _save_changes(self, changed: Dict[str, Any]):
        payload = {}

        init = st.session_state.initial_values
        doc = st.session_state.document
        doc_id = doc.get("id")

        # Reconstruire tout le payload proprement, même les champs non modifiés
        payload["title"] = changed.get("title", init.get("title", ""))
        payload["description"] = changed.get("description", init.get("description", ""))
        payload["identifier"] = changed.get("identifier", init.get("identifier", ""))
        payload["pages"] = changed.get("pages", init.get("pages", ""))
        payload["creatorComment"] = changed.get("creatorComment", init.get("creatorComment", ""))
        payload["mainLanguage"] = changed.get("mainLanguage", init.get("mainLanguage", ""))

        # ⚠️ license doit être encodé sous forme d’objet
        license_value = changed.get("license", init.get("license", ""))
        payload["license"] = {"id": self.license_mapping.get(license_value)} if license_value else None

        # ⚠️ identifierType aussi
        identifier_type_value = changed.get("identifierType", init.get("identifierType", ""))
        payload["identifierType"] = {"id": identifier_type_value} if identifier_type_value else None

        # iso3166 est une liste d’objets
        iso_value = changed.get("iso3166", init.get("iso3166", ""))
        iso_list = [iso.strip() for iso in iso_value.split(";") if iso.strip()]
        payload["iso3166"] = [{"iso": iso} for iso in iso_list] if iso_list else []
        
        # AuthorizationDocument
        auth_doc_id = changed.get("authorizationDocument", init.get("authorizationDocument", ""))
        payload["authorizationDocument"] = {"id": int(auth_doc_id)} if auth_doc_id else None

        # Editor
        editor_id = changed.get("editor", init.get("editor", ""))
        payload["editor"] = {"id": int(editor_id)} if editor_id else None


        try:
            res = requests.put(f"{self.api_base_url}/documents/{doc_id}/update-and-validate", json=payload)
            if res.status_code == 200:
                st.success("✅ Document mis à jour et validé.")
                self._load_document(str(doc_id))
            else:
                st.error(f"Erreur {res.status_code} : {res.text}")
        except Exception as e:
            st.error(f"Erreur pendant la mise à jour : {e}")

    def _reset(self):
        """Réinitialise l'état pour revenir à la recherche."""
        st.session_state.pop("document", None)
        st.session_state.pop("initial_values", None)
        st.rerun()


# --- Entrée principale ---

def show_collection_editor(api_base_url: str):
    editor = CollectionEditor(api_base_url)
    editor.show_interface()
