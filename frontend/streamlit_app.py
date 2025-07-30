"""
Application Streamlit principale mise à jour avec la nouvelle interface collection
"""

import streamlit as st
import os
from dotenv import load_dotenv

# Chargement des variables d'environnement
load_dotenv()

# Configuration de la page
st.set_page_config(
    page_title="Grottocenter AI Tools",
    page_icon="🕳️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Configuration API
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

def main():
    # Header principal
    st.title("🕳️ Grottocenter AI Tools")
    st.markdown("---")

    # Navigation
    with st.sidebar:
        st.header("📋 Navigation")

        pages = {
            "🏠 Accueil": "home",
            "📝 Modifier Collection": "collection",
            "📄 Traitement PDF": "pdf"
        }

        selected_page_display = st.radio(
            "Choisir une page:",
            list(pages.keys()),
            index=0
        )

        selected_page = pages[selected_page_display]

    # Contenu principal basé sur la page sélectionnée
    if selected_page == "home":
        show_home_page()
    elif selected_page == "collection":
        show_collection_page()
    elif selected_page == "pdf":
        show_pdf_page()

def show_home_page():
    """Page d'accueil mise à jour"""
    st.header("🏠 Bienvenue sur Grottocenter AI Tools")

    st.markdown("""
    Cette application vous permet de :

    ### 📝 Modification de Collections ⚡ **NOUVELLE INTERFACE**
    - **Interface moderne** : Modification intuitive avec détection automatique des changements
    - **Prévisualisation** : Voir les modifications avant de les appliquer
    - **Pipeline optimisé** : Charger → Modifier → Prévisualiser → Appliquer → Valider
    - **Feedback visuel** : Indicateurs de changements et statut en temps réel

    ### 📄 Traitement PDF
    - **Upload et validation** : Télécharger des documents PDF avec validation automatique
    - **Division intelligente** : Séparer les revues PDF en articles individuels (à venir)
    - **Extraction métadonnées** : Récupérer automatiquement les informations (à venir)

    ### 🚀 Nouveau workflow de modification
    1. **🔍 Rechercher** : Entrez l'ID de la collection
    2. **✏️ Modifier** : Changez les champs directement (sans checkboxes !)
    3. **👁️ Prévisualiser** : Voyez vos modifications avant/après
    4. **✅ Appliquer** : Envoyez les changements à Grottocenter
    5. **📝 Valider** : Finalisez la modification
    6. **🔗 Accéder** : Lien direct vers votre collection mise à jour
    """)

def show_collection_page():
    """Page de modification des collections"""
    try:
        from pages.collection_editor import show_collection_editor
        show_collection_editor(API_BASE_URL)
    except ImportError as e:
        st.error("❌ **Erreur d'import du module collection_editor**")
        st.exception(e)
    except Exception as e:
        st.error("❌ **Erreur lors du chargement de la page de collection**")
        st.exception(e)

def show_pdf_page():
    st.header("📄 Traitement des documents PDF")
    try:
        from pages.pdf_processing import show_pdf_processing_page
        show_pdf_processing_page(API_BASE_URL)
    except Exception as e:
        st.error("❌ Impossible de charger le module PDF")
        st.exception(e)

if __name__ == "__main__":
    main()
