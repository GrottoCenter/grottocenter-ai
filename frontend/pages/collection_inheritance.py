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

# --- Main Inheritance Editor Class ---

class CollectionInheritanceEditor:
    def __init__(self, api_base_url: str):
        self.api_base_url = api_base_url
        self.license_mapping = {
            "CC-BY-SA": 1, "CC-BY": 2, "ODBL": 3, "ODC-BY": 4,
            "Licence Ouverte": 5, "CC-BY-NC-ND": 6, "CC BY NC": 7,
            "CC BY ND": 8, "CC BY NC SA": 9
        }
        self.license_options = [""] + list(self.license_mapping.keys())
        self.identifier_type_options = ["", "doi", "issn", "isbn", "url"]
        
        # Champs héritable avec leurs labels
        self.heritable_fields = {
            "license": "Licence",
            "mainLanguage": "Langue principale", 
            "authorizationDocument": "Document d'autorisation",
            "editor": "Éditeur"
        }

    def show_interface(self):
        st.title("🏗️ Héritage de propriétés de collection")
        
        # Étapes dans des onglets
        tab1, tab2, tab3, tab4 = st.tabs([
            "🔍 1. Collection", 
            "✏️ 2. Modification", 
            "🎯 3. Héritage", 
            "📊 4. Résultats"
        ])
        
        with tab1:
            self._show_search_and_load()
            
        with tab2:
            if "collection" in st.session_state:
                self._show_collection_form()
            else:
                st.info("Veuillez d'abord charger une collection dans l'onglet 1.")
                
        with tab3:
            if "collection" in st.session_state:
                self._show_inheritance_setup()
            else:
                st.info("Veuillez d'abord charger une collection dans l'onglet 1.")
                
        with tab4:
            if "inheritance_results" in st.session_state:
                self._show_results()
            else:
                st.info("Aucun résultat d'héritage à afficher.")

    def _show_search_and_load(self):
        st.subheader("🔍 Rechercher une collection")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            doc_id = st.text_input("ID de la collection", key="collection_id_input", 
                                 help="Entrez l'ID de la collection parente")
        with col2:
            st.write("")  # Espacement
            if st.button("📥 Charger", type="primary"):
                self._load_collection(doc_id)
        
        # Affichage de la collection chargée
        if "collection" in st.session_state:
            doc = st.session_state.collection
            st.success(f"✅ Collection chargée : **{doc.get('title', 'Sans titre')}** (ID: {doc.get('id')})")
            
            # Infos de base
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Type", doc.get('type', 'N/A'))
            with col2:
                st.metric("Langue", doc.get('mainLanguage', 'N/A'))
            with col3:
                licence = doc.get('license', {})
                licence_name = licence.get('name', 'N/A') if isinstance(licence, dict) else str(licence)
                st.metric("Licence", licence_name)
            
            # Message de guidage
            st.info("👉 **Étape suivante :** Rendez-vous dans l'onglet **✏️ 2. Modification** pour modifier les propriétés de la collection (optionnel), puis dans l'onglet **🎯 3. Héritage** pour configurer l'héritage.")

    def _load_collection(self, doc_id: str):
        if not doc_id:
            st.warning("Veuillez entrer un ID de collection.")
            return
            
        try:
            with st.spinner("Chargement de la collection..."):
                res = requests.get(f"{self.api_base_url}/documents/{doc_id}")
                
            if res.status_code == 200:
                doc = res.json()
                
                # Vérifier si c'est un changement de collection (ID différent)
                current_doc_id = st.session_state.get("collection", {}).get("id")
                new_doc_id = int(doc_id)
                
                if current_doc_id != new_doc_id:
                    # Nouvelle collection - nettoyer tous les flags
                    keys_to_clean = ["collection_updated", "descendants", "inheritance_preview", "inheritance_results", "selected_heritable_fields", "show_success_message"]
                    for key in keys_to_clean:
                        if key in st.session_state:
                            del st.session_state[key]
                
                st.session_state.collection = doc
                st.session_state.initial_values = self._extract_values(doc)
                
                st.success("Collection chargée avec succès!")
                st.rerun()
            else:
                st.error(f"Erreur lors du chargement: {res.status_code} - {res.text}")
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
            "license": doc.get("license", ""),
            "identifierType": doc.get("identifierType", ""),
            "iso3166": ";".join([entry.get("iso", "") for entry in doc.get("iso3166", [])]),
            "authorizationDocument": str(doc.get("authorizationDocument", {}).get("id", "")),
            "editor": str(doc.get("editor", {}).get("id", ""))
        }

    def _show_collection_form(self):
        st.subheader("✏️ Modifier la collection")
        
        # Afficher le message de succès persistant
        if st.session_state.get("collection_updated", False):
            st.success("✅ **Collection mise à jour avec succès !**")
            st.info("👉 **Prochaine étape :** Rendez-vous dans l'onglet **🎯 3. Héritage** pour configurer l'héritage des propriétés.")
            
            # Options pour gérer le message
            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("✓ J'ai vu ce message", type="secondary"):
                    st.session_state.collection_updated = False
                    st.rerun()
            with col2:
                if st.button("🔄 Recharger les données", type="secondary", help="Recharger la collection depuis l'API"):
                    doc_id = st.session_state.collection.get("id")
                    st.session_state.collection_updated = False  # Nettoyer le flag avant rechargement
                    self._load_collection(str(doc_id))
        
        doc = st.session_state.collection
        init = st.session_state.initial_values
        
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
            ("editor", "ID de l'éditeur", "text")
        ]

        for f in fields:
            key, label, ftype = f[0], f[1], f[2]
            options = f[3] if len(f) > 3 else None
            cur_val = init.get(key, "")
            new_val = DocumentField(key, label, cur_val, ftype, options).render()
            if str(new_val).strip() != str(cur_val).strip():
                changed[key] = new_val

        if changed:
            st.markdown("### 📝 Modifications détectées")
            for k, v in changed.items():
                st.markdown(f"**{k}** : `{init.get(k, '[vide]')}` → `{v}`")
            
            if st.button("💾 Enregistrer les modifications", type="primary"):
                self._save_collection_changes(changed)
        else:
            st.info("Aucune modification détectée.")
            
            
            
        # Message de guidage (seulement si pas de message de succès)
        if not st.session_state.get("collection_updated", False):
            st.info("👉 **Étape suivante :** Rendez-vous dans l'onglet **🎯 3. Héritage** pour sélectionner les champs à hériter et appliquer l'héritage aux documents descendants.")

    def _save_collection_changes(self, changed: Dict[str, Any]):
        payload = {}
        init = st.session_state.initial_values
        doc = st.session_state.collection
        doc_id = doc.get("id")

        # Construire le payload complet
        payload["title"] = changed.get("title", init.get("title", ""))
        payload["description"] = changed.get("description", init.get("description", ""))
        payload["identifier"] = changed.get("identifier", init.get("identifier", ""))
        payload["pages"] = changed.get("pages", init.get("pages", ""))
        payload["creatorComment"] = changed.get("creatorComment", init.get("creatorComment", ""))
        payload["mainLanguage"] = changed.get("mainLanguage", init.get("mainLanguage", ""))

        # License
        license_value = changed.get("license", init.get("license", ""))
        payload["license"] = {"id": self.license_mapping.get(license_value)} if license_value else None

        # IdentifierType
        identifier_type_value = changed.get("identifierType", init.get("identifierType", ""))
        payload["identifierType"] = {"id": identifier_type_value} if identifier_type_value else None

        # ISO3166
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
            with st.spinner("Enregistrement des modifications..."):
                res = requests.put(f"{self.api_base_url}/documents/{doc_id}/update-and-validate", json=payload)
                
            if res.status_code == 200:
                # Flag pour maintenir le message de succès
                st.session_state.collection_updated = True
                
                # Recharger la collection pour avoir les données à jour
                self._reload_collection_silently(str(doc_id))
                
                st.rerun()
            else:
                st.error(f"Erreur lors de la mise à jour: {res.status_code} - {res.text}")
        except Exception as e:
            st.error(f"Erreur: {e}")
    
    def _reload_collection_silently(self, doc_id: str):
        """Recharger la collection sans afficher de message ni nettoyer les flags"""
        try:
            res = requests.get(f"{self.api_base_url}/documents/{doc_id}")
            if res.status_code == 200:
                doc = res.json()
                st.session_state.collection = doc
                st.session_state.initial_values = self._extract_values(doc)
        except Exception:
            pass  # En cas d'erreur, on garde les données actuelles

    def _show_inheritance_setup(self):
        st.subheader("🎯 Configuration de l'héritage")
        
        doc = st.session_state.collection
        doc_id = doc.get("id")
        
        # 1. Sélection des champs à hériter
        st.markdown("### 1. Champs à hériter")
        
        selected_fields = {}
        
        for field_key, field_label in self.heritable_fields.items():
            current_value = doc.get(field_key)
            
            # Affichage de la valeur actuelle
            if current_value:
                if isinstance(current_value, dict) and "name" in current_value:
                    display_value = current_value["name"]
                elif isinstance(current_value, dict) and "id" in current_value:
                    display_value = f"ID: {current_value['id']}"
                else:
                    display_value = str(current_value)
            else:
                display_value = "[Non défini]"
            
            # Checkbox pour sélectionner ce champ
            if st.checkbox(f"**{field_label}** : `{display_value}`", key=f"inherit_{field_key}"):
                selected_fields[field_key] = current_value
        
        if not selected_fields:
            st.warning("Sélectionnez au moins un champ à hériter.")
            return
        
        st.session_state.selected_heritable_fields = selected_fields
        
        # 2. Récupération des descendants
        st.markdown("### 2. Documents descendants")
        
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("📥 Charger les descendants", type="primary"):
                self._load_descendants(doc_id)
        
        with col2:
            if st.button("🔄 Actualiser", type="secondary"):
                if "descendants" in st.session_state:
                    self._load_descendants(doc_id)
        
        # Affichage des descendants
        if "descendants" in st.session_state:
            descendants = st.session_state.descendants
            st.success(f"✅ {len(descendants)} documents descendants trouvés")
            
            if descendants:
                with st.expander("📋 Liste des documents descendants", expanded=False):
                    for desc in descendants[:10]:  # Afficher les 10 premiers
                        st.markdown(f"- **{desc.get('title', 'Sans titre')}** (ID: {desc.get('id')}) - Type: {desc.get('type', 'N/A')}")
                    if len(descendants) > 10:
                        st.markdown(f"... et {len(descendants) - 10} autres documents")
                
                st.info("👉 **Étape suivante :** Analysez les changements nécessaires avec le bouton **👁️ Analyser les changements**.")
            else:
                st.warning("Aucun document descendant trouvé pour cette collection.")
                return
            
            # 3. Prévisualisation des changements
            st.markdown("### 3. Prévisualisation des changements")
            
            if st.button("👁️ Analyser les changements", type="secondary"):
                self._analyze_inheritance_changes(descendants, selected_fields)
            
            # 4. Application de l'héritage
            if "inheritance_preview" in st.session_state:
                preview = st.session_state.inheritance_preview
                
                st.success("✅ Analyse terminée !")
                st.markdown("#### 📋 Changements à appliquer")
                
                if preview["changes"]:
                    st.info(f"📊 **Résumé :** {len(preview['changes'])} documents seront modifiés sur {len(descendants)} descendants trouvés.")
                    
                    for change in preview["changes"]:
                        with st.expander(f"📄 {change['title']} (ID: {change['id']})"):
                            for field, values in change["modifications"].items():
                                st.markdown(f"**{self.heritable_fields.get(field, field)}** : `{values['from']}` → `{values['to']}`")
                    
                    st.markdown(f"**Total :** {len(preview['changes'])} documents à modifier")
                    
                    # Message d'avertissement
                    st.warning("⚠️ **Attention :** Cette opération va modifier et valider automatiquement tous les documents listés ci-dessus. Cette action est irréversible.")
                    
                    if st.button("🚀 Appliquer l'héritage", type="primary"):
                        self._apply_inheritance(selected_fields, [c["id"] for c in preview["changes"]])
                    
                    # Message de succès après application de l'héritage
                    if st.session_state.get("show_success_message", False):
                        st.success("🎉 **Héritage appliqué avec succès !**")
                        st.info("👉 **Voir le bilan complet dans l'onglet 📊 4. Résultats**")
                        # Note: le flag sera réinitialisé lors du démarrage d'une nouvelle collection
                else:
                    st.info("✅ Aucun changement nécessaire - tous les documents ont déjà les bonnes valeurs.")
                    st.info("👉 **Terminé !** Vous pouvez commencer un nouveau processus avec une autre collection.")
            else:
                st.info("👆 Cliquez sur **👁️ Analyser les changements** pour voir quels documents seront modifiés.")

    def _load_descendants(self, doc_id: int):
        try:
            with st.spinner("🔍 Recherche des documents descendants (enfants et petits-enfants)..."):
                res = requests.get(f"{self.api_base_url}/documents/{doc_id}/descendants")
                
            if res.status_code == 200:
                data = res.json()
                descendants = data.get("documents", [])
                st.session_state.descendants = descendants
                
                if descendants:
                    st.success(f"✅ {len(descendants)} documents descendants trouvés et chargés avec succès !")
                else:
                    st.info("ℹ️ Aucun document descendant trouvé pour cette collection.")
                    
                st.rerun()
            else:
                st.error(f"❌ Erreur lors du chargement des descendants: {res.status_code}")
        except Exception as e:
            st.error(f"❌ Erreur: {e}")

    def _analyze_inheritance_changes(self, descendants: list, selected_fields: dict):
        changes = []
        
        with st.spinner("Analyse des changements nécessaires..."):
            for desc in descendants:
                doc_id = desc.get("id")
                try:
                    # Récupérer les détails du document
                    res = requests.get(f"{self.api_base_url}/documents/{doc_id}")
                    if res.status_code == 200:
                        full_doc = res.json()
                        
                        modifications = {}
                        for field_key, parent_value in selected_fields.items():
                            current_value = full_doc.get(field_key)
                            
                            # Comparer les valeurs
                            if self._values_different(current_value, parent_value):
                                modifications[field_key] = {
                                    "from": self._format_value(current_value),
                                    "to": self._format_value(parent_value)
                                }
                        
                        if modifications:
                            changes.append({
                                "id": doc_id,
                                "title": full_doc.get("title", f"Document {doc_id}"),
                                "modifications": modifications
                            })
                            
                except Exception as e:
                    st.warning(f"Impossible d'analyser le document {doc_id}: {e}")
        
        st.session_state.inheritance_preview = {"changes": changes}
        st.rerun()

    def _apply_inheritance(self, selected_fields: dict, child_ids: list):
        try:
            with st.spinner(f"🔄 Application de l'héritage sur {len(child_ids)} documents..."):
                payload = {
                    "heritable_fields": selected_fields,
                    "child_ids": child_ids
                }
                
                doc_id = st.session_state.collection.get("id")
                res = requests.post(f"{self.api_base_url}/documents/{doc_id}/apply-inheritance", json=payload)
                
            if res.status_code == 200:
                results = res.json()
                st.session_state.inheritance_results = results
                st.session_state.show_success_message = True  # Flag pour afficher le message
                
                st.rerun()
            else:
                st.error(f"❌ Erreur lors de l'application: {res.status_code} - {res.text}")
        except Exception as e:
            st.error(f"❌ Erreur: {e}")

    def _show_results(self):
        st.subheader("📊 Résultats de l'héritage")
        
        results = st.session_state.inheritance_results
        
        # Métriques avec couleurs
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("📋 Total traités", results["total"])
        with col2:
            success_count = len(results["success"])
            st.metric("✅ Succès", success_count, delta=f"{success_count}/{results['total']}")
        with col3:
            error_count = len(results["errors"])
            st.metric("❌ Erreurs", error_count, 
                     delta=f"{error_count}/{results['total']}" if error_count > 0 else "Aucune erreur",
                     delta_color="inverse" if error_count > 0 else "normal")
        
        # Message de synthèse
        if error_count == 0:
            st.success(f"🎉 **Processus terminé avec succès !** Tous les {success_count} documents ont été traités sans erreur.")
        else:
            st.warning(f"⚠️ **Processus terminé avec des erreurs.** {success_count} documents traités avec succès, {error_count} erreurs rencontrées.")
        
        # Détails des succès
        if results["success"]:
            st.markdown("### ✅ Documents traités avec succès")
            
            # Option pour afficher tous les détails
            show_all_details = st.checkbox("Afficher les détails de tous les documents", value=False)
            
            for i, success in enumerate(results["success"]):
                if show_all_details or i < 5:  # Afficher les 5 premiers par défaut
                    with st.expander(f"📄 {success['title']} (ID: {success['id']})", expanded=False):
                        if isinstance(success["changes"], dict) and success["changes"]:
                            st.markdown("**Modifications appliquées :**")
                            for field, value in success["changes"].items():
                                field_label = self.heritable_fields.get(field, field)
                                st.markdown(f"- **{field_label}** : {self._format_value(value)}")
                        else:
                            st.markdown(success["changes"])
                elif i == 5 and not show_all_details:
                    st.info(f"... et {len(results['success']) - 5} autres documents (cochez la case ci-dessus pour tout voir)")
                    break
        
        # Détails des erreurs
        if results["errors"]:
            st.markdown("### ❌ Erreurs rencontrées")
            for error in results["errors"]:
                st.error(f"**Document {error['id']}** : {error['error']}")
        
        # Actions post-traitement
        st.markdown("---")
        st.markdown("### 🔄 Actions suivantes")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🏠 Nouvelle collection", type="primary"):
                # Nettoyer l'état
                keys_to_remove = ["collection", "initial_values", "descendants", "inheritance_preview", "inheritance_results", "selected_heritable_fields", "show_success_message", "collection_updated"]
                for key in keys_to_remove:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()
        
        with col2:
            # Lien vers Grottocenter si possible
            if "collection" in st.session_state:
                collection_id = st.session_state.collection.get("id")
                grottocenter_url = f"https://grottocenter.org/ui/documents/{collection_id}"
                st.markdown(f"🔗 [Voir la collection sur Grottocenter]({grottocenter_url})")
        
        # Résumé final
        st.info("💡 **Conseil :** Vous pouvez maintenant vérifier les modifications sur Grottocenter ou traiter une nouvelle collection.")

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
        
        return current != new

    def _format_value(self, value) -> str:
        """Formater une valeur pour affichage"""
        if value is None:
            return "[Non défini]"
        if isinstance(value, dict):
            if "name" in value:
                return value["name"]
            elif "id" in value:
                return f"ID: {value['id']}"
        return str(value)


# --- Entrée principale ---

def show_collection_inheritance(api_base_url: str):
    editor = CollectionInheritanceEditor(api_base_url)
    editor.show_interface()