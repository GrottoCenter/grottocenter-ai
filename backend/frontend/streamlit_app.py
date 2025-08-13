"""
Application Streamlit principale mise à jour avec les nouvelles interfaces
"""

import os

import streamlit as st
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
            "📝 Modifier Document": "collection",
            "🏗️ Héritage Collection": "inheritance",
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
    elif selected_page == "inheritance":
        show_inheritance_page()
    elif selected_page == "pdf":
        show_pdf_page()

def show_home_page():
    """Page d'accueil mise à jour"""
    st.header("🏠 Bienvenue sur Grottocenter AI Tools")

    st.markdown("""
    Cette application vous permet de :

    ### 📝 Modification de Documents
    - **Interface classique** : Modification simple d'un document individuel
    - **Tous types** : Collections, articles, revues, etc.
    - **Validation automatique** : Modification + validation en une seule étape

    ### 🏗️ Héritage de Collection ⚡ **NOUVELLE FONCTIONNALITÉ**
    - **Modification de collection** : Éditez d'abord la collection parente
    - **Sélection de champs** : Choisissez quels champs hériter (licence, langue, éditeur, etc.)
    - **Récupération automatique** : Trouve tous les enfants et petits-enfants
    - **Prévisualisation** : Voyez tous les changements avant application
    - **Application en masse** : Modifie et valide automatiquement tous les descendants

    ### 📄 Traitement PDF
    - **Upload et validation** : Télécharger des documents PDF avec validation automatique
    - **Division intelligente** : Séparer les revues PDF en articles individuels (à venir)
    - **Extraction métadonnées** : Récupérer automatiquement les informations (à venir)

    ### 🚀 Workflow d'héritage de collection
    1. **🔍 Rechercher** : Chargez la collection parente par son ID
    2. **✏️ Modifier** : Éditez les propriétés de la collection
    3. **🎯 Sélectionner** : Choisissez les champs à hériter (licence, langue, etc.)
    4. **📥 Charger** : Récupération automatique de tous les descendants
    5. **👁️ Prévisualiser** : Analysez les changements avant/après
    6. **🚀 Appliquer** : Application automatique sur tous les documents descendants
    7. **📊 Résultats** : Rapport détaillé des succès et erreurs

    ### 💡 Cas d'usage typiques
    - **Mise à jour de licence** : Changer la licence de toute une collection
    - **Correction d'éditeur** : Propager l'information d'éditeur manquante
    - **Harmonisation de langue** : Assurer la cohérence linguistique
    - **Gestion d'autorisation** : Appliquer un document d'autorisation

    ---
    
    🎯 **Conseil** : Commencez par l'héritage de collection pour des modifications en masse, ou utilisez la modification simple pour des documents individuels.
    """)

def show_collection_page():
    """Page de modification classique des documents"""
    try:
        from components.collection_editor import show_collection_editor
        show_collection_editor(API_BASE_URL)
    except ImportError as e:
        st.error("❌ **Erreur d'import du module collection_editor**")
        st.exception(e)
    except Exception as e:
        st.error("❌ **Erreur lors du chargement de la page de modification**")
        st.exception(e)

def show_inheritance_page():
    """Page d'héritage de collection"""
    try:
        from components.collection_inheritance import show_collection_inheritance
        show_collection_inheritance(API_BASE_URL)
    except ImportError as e:
        st.error("❌ **Erreur d'import du module collection_inheritance**")
        st.exception(e)
        st.info("Assurez-vous que le fichier `pages/collection_inheritance.py` existe.")
    except Exception as e:
        st.error("❌ **Erreur lors du chargement de la page d'héritage**")
        st.exception(e)

def show_pdf_page():
    st.header("📄 Traitement des documents PDF")
    try:
        from components.pdf_processing import show_pdf_processing_page
        show_pdf_processing_page(API_BASE_URL)
    except Exception as e:
        st.error("❌ Impossible de charger le module PDF")
        st.exception(e)

if __name__ == "__main__":
    main()
